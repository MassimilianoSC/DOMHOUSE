"""Tool A, package A1 (docs/progetto-strumento-a-base.md §1, §3, §6): the reader, scripts/agent/lettore.py. The
unprivileged service that takes the orders from the environment's Pub/Sub subscription with the VM's token, checks
them (comune.py), keeps a journal per op_id, acknowledges an order as soon as it is in the journal, passes it to the
executor and publishes the result. Pub/Sub, the token and the executor are replaced here."""
import base64
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "scripts" / "agent"
sys.path.insert(0, str(AGENT))


def load(name):
    spec = importlib.util.spec_from_file_location(name, AGENT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


comune = load("comune")
lettore = load("lettore")

OP = "8b2f6a3e-4c1d-4e5f-9a0b-1c2d3e4f5a6b"
OP2 = "9c3a7b4f-5d2e-4f60-8b1c-2d3e4f5a6b7c"
NOW = datetime(2026, 11, 17, 9, 0, 0, tzinfo=UTC)


def order(**kw) -> dict:
    base = {"op_id": OP, "operazione": "stato", "apartment_id": "lab-01", "seq": 3, "parametri": {},
            "ambiente": "staging", "richiesto_da": "Uk9TgS2vLmQ1"}
    base.update(kw)
    return base


class FakePubSub:
    def __init__(self, events):
        self.queue, self.acked, self.nacked, self.published, self.events = [], [], [], [], events
        self.fail_publish = 0

    def put(self, o, age_s=5, raw=None):
        data = raw if raw is not None else json.dumps(o).encode("utf-8")
        ack_id = f"ack-{len(self.queue) + len(self.acked) + len(self.nacked)}"
        self.queue.append({"ackId": ack_id, "message": {
            "data": base64.b64encode(data).decode("ascii"),
            "publishTime": (NOW - timedelta(seconds=age_s)).isoformat().replace("+00:00", "Z"),
            "messageId": ack_id}})
        return ack_id

    def pull(self, max_messages):
        out, self.queue = self.queue[:max_messages], self.queue[max_messages:]
        return out

    def ack(self, ack_id):
        self.events.append(("ack", ack_id))
        self.acked.append(ack_id)

    def nack(self, ack_id):
        self.events.append(("nack", ack_id))
        self.nacked.append(ack_id)

    def publish(self, result: dict):
        if self.fail_publish:
            self.fail_publish -= 1
            raise OSError("pubsub non risponde")
        self.events.append(("publish", result["op_id"]))
        self.published.append(result)


class World:
    def __init__(self, tmp: Path):
        self.events, self.logs, self.calls = [], [], []
        self.pubsub = FakePubSub(self.events)
        self.journal = tmp / "giornale"
        self.answer = lambda data: {**comune.result_for_raw(data, "riuscito", "ok"), "dati": {"health": 200}}
        self.reader = self.make()

    def make(self):
        return lettore.Lettore(ambiente="staging", pubsub=self.pubsub, execute=self.execute, journal=self.journal,
                               clock=lambda: NOW, log=self.logs.append)

    def execute(self, data: bytes) -> dict:
        self.events.append(("execute", json.loads(data)["op_id"]))
        self.calls.append(data)
        return self.answer(data)


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


def test_an_order_is_journalled_then_acknowledged_then_executed_and_its_result_published(w):
    ack = w.pubsub.put(order())
    assert w.reader.step() == 1
    assert w.events == [("ack", ack), ("execute", OP), ("publish", OP)]
    [result] = w.pubsub.published
    assert (result["op_id"], result["esito"], result["codice"], result["dati"]) == (OP, "riuscito", "ok", {"health": 200})
    entry = json.loads((w.journal / f"{OP}.json").read_text(encoding="utf-8"))
    assert entry["stato"] == "chiuso" and entry["risultato"] == result and entry["pubblicato"] is True
    assert "parametri" not in entry and "richiesto_da" not in entry           # only what is needed to answer


def test_the_journal_is_written_before_the_acknowledgement(w, monkeypatch):
    seen = []
    original = w.reader._write

    def spy(op_id, entry):
        seen.append(("write", entry["stato"], list(w.pubsub.acked)))
        original(op_id, entry)
    monkeypatch.setattr(w.reader, "_write", spy)
    ack = w.pubsub.put(order())
    w.reader.step()
    assert seen[0] == ("write", "in_corso", [])                    # in corso, and not yet acknowledged
    assert ack in w.pubsub.acked


def test_an_order_older_than_15_minutes_is_discarded(w):
    w.pubsub.put(order(), age_s=15 * 60 + 1)
    w.reader.step()
    [result] = w.pubsub.published
    assert (result["esito"], result["codice"]) == ("scartato", "scaduto") and w.calls == []
    assert w.pubsub.acked and any("esito=scartato" in line for line in w.logs)


def test_a_refused_order_never_reaches_the_executor(w):
    w.pubsub.put(order(apartment_id="lab_01"))
    w.pubsub.put(None, raw=b"\xff\xfe non json")
    w.reader.step()
    assert [(r["esito"], r["codice"]) for r in w.pubsub.published] == [("rifiutato", "id_non_valido"),
                                                                       ("rifiutato", "json_non_valido")]
    assert w.calls == [] and len(w.pubsub.acked) == 2


def test_an_order_of_another_environment_raises_an_alarm(w):
    w.pubsub.put(order(ambiente="prod", apartment_id="a-k3f9x2qm"))
    w.reader.step()
    assert w.pubsub.published[0]["codice"] == "ambiente_diverso" and w.calls == []
    assert any(line.startswith("agent alarm ") and "codice=ambiente_diverso" in line for line in w.logs)


def test_a_copy_of_a_finished_order_gets_the_recorded_result_again(w):
    w.pubsub.put(order())
    w.reader.step()
    w.pubsub.put(order())                                           # Pub/Sub delivers it again
    w.reader.step()
    assert len(w.calls) == 1 and len(w.pubsub.published) == 2
    assert w.pubsub.published[0] == w.pubsub.published[1] and len(w.pubsub.acked) == 2


def test_a_copy_of_an_order_in_progress_is_ignored(w):
    w.reader._write(OP, {"op_id": OP, "operazione": "stato", "apartment_id": "lab-01", "ambiente": "staging",
                         "seq": 3, "stato": "in_corso", "ricevuto": NOW.isoformat()})
    w.pubsub.put(order())
    w.reader.step()
    assert w.calls == [] and w.pubsub.published == [] and len(w.pubsub.acked) == 1


def test_if_the_journal_cannot_be_written_the_order_is_not_acknowledged(w, monkeypatch):
    def broken(op_id, entry):
        raise OSError("disco pieno")
    monkeypatch.setattr(w.reader, "_write", broken)
    ack = w.pubsub.put(order())
    w.reader.step()
    assert w.pubsub.acked == [] and w.pubsub.nacked == [ack] and w.calls == []   # Pub/Sub tries again, then the dead letters


def test_after_a_restart_an_open_entry_is_failed_interrupted_and_never_run_again(w):
    w.reader._write(OP, {"op_id": OP, "operazione": "stato", "apartment_id": "lab-01", "ambiente": "staging",
                         "seq": 3, "stato": "in_corso", "ricevuto": NOW.isoformat()})
    again = w.make()
    again.recover()
    [result] = w.pubsub.published
    assert (result["op_id"], result["esito"], result["codice"]) == (OP, "fallito", "interrotto") and w.calls == []
    assert json.loads((w.journal / f"{OP}.json").read_text(encoding="utf-8"))["stato"] == "chiuso"


def test_an_executor_that_does_not_answer_is_an_internal_error(w):
    def down(data):
        raise OSError("socket assente")
    w.answer = down
    w.pubsub.put(order())
    w.reader.step()
    assert (w.pubsub.published[0]["esito"], w.pubsub.published[0]["codice"]) == ("fallito", "errore_interno")


def test_the_executors_answer_is_filtered_to_codes_and_short_data(w):
    w.answer = lambda data: {**comune.result_for_raw(data, "riuscito", "ok"), "dati": {"health": 200},
                             "uscita": "tutto il log dello script", "email": "mario@example.com"}
    w.pubsub.put(order())
    w.reader.step()
    assert set(w.pubsub.published[0]) == {"op_id", "operazione", "apartment_id", "ambiente", "seq", "esito",
                                          "codice", "dati"}
    w.answer = lambda data: {**comune.result_for_raw(data, "riuscito", "ok"), "codice": "testo libero"}
    w.pubsub.put(order(op_id=OP2, seq=4))
    w.reader.step()
    assert (w.pubsub.published[1]["esito"], w.pubsub.published[1]["codice"]) == ("fallito", "errore_interno")


def test_a_result_not_published_is_published_at_the_next_step(w):
    w.pubsub.fail_publish = 1
    w.pubsub.put(order())
    w.reader.step()
    assert w.pubsub.published == [] and len(w.calls) == 1
    w.reader.step()
    assert [r["op_id"] for r in w.pubsub.published] == [OP] and len(w.calls) == 1


def test_log_lines_have_no_email_and_the_day_is_counted(w):
    w.pubsub.put(order())
    w.pubsub.put(order(op_id=OP2, apartment_id="lab_01"))
    w.reader.step()
    w.reader.count_line()
    line = w.logs[-1]
    assert line.startswith("agent count ambiente=staging") and "ricevuti=2" in line and "riusciti=1" in line
    assert "rifiutati=1" in line and all("@" not in l for l in w.logs)


def test_the_configuration_is_strict(tmp_path):
    good = tmp_path / "lettore.conf"
    good.write_text("AMBIENTE=staging\nSOTTOSCRIZIONE=projects/domotica-poc-511707/subscriptions/domhouse-staging-ordini-vm\n"
                    "RISULTATI=projects/domotica-poc-511707/topics/domhouse-staging-risultati\n", encoding="utf-8")
    c = lettore.read_config(good)
    assert c["AMBIENTE"] == "staging" and c["SOTTOSCRIZIONE"].endswith("/domhouse-staging-ordini-vm")
    for text in ("AMBIENTE=prod\nSOTTOSCRIZIONE=x\nRISULTATI=y\n",
                 "AMBIENTE=staging\nSOTTOSCRIZIONE=projects/p/subscriptions/s\nRISULTATI=projects/p/topics/t\nX=1\n",
                 "AMBIENTE=staging\nSOTTOSCRIZIONE=https://evil/x\nRISULTATI=projects/p/topics/t\n"):
        bad = tmp_path / "bad.conf"
        bad.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            lettore.read_config(bad)
