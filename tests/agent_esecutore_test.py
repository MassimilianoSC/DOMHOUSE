"""Tool A, package A1 (docs/progetto-strumento-a-base.md §1, §3, §5, §6): the executor, scripts/agent/esecutore.py.
Root, minimal: it takes orders only from the reader's uid on a local socket, checks everything again with its OWN
configuration (prod refused on the shared VM, the sequence per apartment kept in a root file that stays as a
tombstone), and runs programs with a list of arguments and a clean environment, never a shell. In A1 it executes only
«stato» and «capienza»; the other five operations are refused «non_disponibile».

The logic is tested everywhere, with the programs and the engine's /health replaced; the socket with SO_PEERCRED only
on Linux (the CI runs it)."""
import importlib.util
import json
import os
import socket
import sys
import threading
import time
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
esecutore = load("esecutore")

READER_UID = 4242
OP = "8b2f6a3e-4c1d-4e5f-9a0b-1c2d3e4f5a6b"


def order(**kw) -> bytes:
    base = {"op_id": OP, "operazione": "stato", "apartment_id": "lab-01", "seq": 3, "parametri": {},
            "ambiente": "staging", "richiesto_da": "Uk9TgS2vLmQ1"}
    base.update(kw)
    return json.dumps(base).encode("utf-8")


class World:
    """The VM as the executor sees it: /opt/domhouse with the settings files, its state folder, /proc/meminfo, the
    programs it runs (recorded, never run) and the engines' /health."""

    def __init__(self, tmp: Path, ambiente="staging", condivisa=True):
        self.opt = tmp / "opt"
        self.state = tmp / "state"
        self.opt.mkdir()
        (self.opt / "lab-01.settings").write_text("APARTMENT_ID=lab-01\nPORT=8169\n", encoding="utf-8")
        (self.opt / "dev.settings").write_text("APARTMENT_ID=dev\nPORT=8100\n", encoding="utf-8")
        self.meminfo = tmp / "meminfo"
        self.meminfo.write_text("MemTotal:        2014000 kB\nMemAvailable:     812000 kB\n", encoding="utf-8")
        self.runs, self.gets, self.logs = [], [], []
        self.health = {8169: (200, {"status": "ok", "implementation": {"name": "domhouse-engine"},
                                    "connector": {"status": "up"}})}
        self.image = "europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:247fda0"
        self.config = esecutore.Config(ambiente=ambiente, condivisa=condivisa, reader_uid=READER_UID,
                                       opt=self.opt, state=self.state, bind_ip="10.198.0.2", max_staging=4,
                                       meminfo=self.meminfo)
        self.ex = esecutore.Esecutore(self.config, run=self.run, http_get=self.get, log=self.logs.append)

    def run(self, argv, env, timeout):
        self.runs.append((list(argv), dict(env)))
        if argv[:2] == ["/usr/bin/docker", "inspect"]:
            return 0, self.image + "\n"
        return 1, ""

    def get(self, url, timeout):
        self.gets.append(url)
        port = int(url.split(":")[2].split("/")[0])
        if port not in self.health:
            return 0, None
        return self.health[port]


@pytest.fixture
def w(tmp_path):
    return World(tmp_path)


def test_stato_answers_health_connector_and_image(w):
    r = w.ex.handle(order(), READER_UID)
    assert (r["esito"], r["codice"]) == ("riuscito", "ok")
    assert r["dati"] == {"health": 200, "stato": "ok", "connector": "up", "immagine": w.image}
    assert w.gets == ["http://10.198.0.2:8169/api/v1/health"]
    [(argv, env)] = w.runs
    assert argv == ["/usr/bin/docker", "inspect", "-f", "{{.Config.Image}}", "engine-lab-01"]
    assert env == {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin",                     # env -i: nothing else but
                   "DOCKER_CONFIG": str(w.state / "docker")}                    # docker's folder in the state (ProtectHome)


def test_stato_of_an_engine_that_does_not_answer(w):
    w.health = {}
    r = w.ex.handle(order(), READER_UID)
    assert (r["esito"], r["codice"]) == ("riuscito", "ok") and r["dati"]["health"] == 0


def test_stato_of_dev_is_allowed_and_of_a_missing_engine_is_motore_assente(w):
    w.health[8100] = (200, {"status": "ok", "implementation": {}, "connector": {"status": "up"}})
    assert w.ex.handle(order(apartment_id="dev"), READER_UID)["esito"] == "riuscito"
    r = w.ex.handle(order(apartment_id="lab-99", seq=1), READER_UID)
    assert (r["esito"], r["codice"]) == ("rifiutato", "motore_assente") and w.gets[-1].endswith(":8100/api/v1/health")


def test_capienza_reads_memory_and_counts_the_engines(w):
    r = w.ex.handle(order(operazione="capienza", apartment_id=None, seq=None), READER_UID)
    assert (r["esito"], r["codice"]) == ("riuscito", "ok")
    assert r["dati"] == {"mem_available_mb": 793, "motori": 2, "motori_staging": 2, "massimo_staging": 4}
    assert w.runs == [] and w.gets == []


def test_only_the_readers_uid_is_served(w):
    r = w.ex.handle(order(), READER_UID + 1)
    assert (r["esito"], r["codice"]) == ("rifiutato", "chiamante_non_ammesso") and w.runs == [] and w.gets == []


def test_it_checks_again_what_the_reader_should_have_refused(w):
    """A compromised reader passes anything: the executor refuses it by itself, with the same codes."""
    assert w.ex.handle(order(apartment_id="lab_01"), READER_UID)["codice"] == "id_non_valido"
    assert w.ex.handle(order(apartment_id="dev", operazione="togli_motore"), READER_UID)["codice"] == "dev_escluso"
    assert w.ex.handle(order(parametri={"x": 1}), READER_UID)["codice"] == "parametri_non_validi"
    assert w.ex.handle(b"{rotto", READER_UID)["codice"] == "json_non_valido"
    assert w.runs == [] and w.gets == []


def test_prod_is_refused_on_the_shared_vm_whatever_the_order_says(w):
    r = w.ex.handle(order(apartment_id="a-k3f9x2qm", ambiente="prod"), READER_UID)
    assert (r["esito"], r["codice"]) == ("rifiutato", "prod_non_ammesso") and w.gets == []


def test_the_sequence_per_apartment_only_grows_and_stays_as_a_tombstone(w):
    assert w.ex.handle(order(seq=5), READER_UID)["esito"] == "riuscito"
    assert w.ex.handle(order(seq=5, op_id="9c3a7b4f-5d2e-4f60-8b1c-2d3e4f5a6b7c"), READER_UID)["codice"] == "seq_vecchia"
    assert w.ex.handle(order(seq=4, op_id="9c3a7b4f-5d2e-4f60-8b1c-2d3e4f5a6b7d"), READER_UID)["codice"] == "seq_vecchia"
    assert w.ex.handle(order(seq=6, op_id="9c3a7b4f-5d2e-4f60-8b1c-2d3e4f5a6b7e"), READER_UID)["esito"] == "riuscito"
    assert (w.state / "seq" / "lab-01").read_text(encoding="utf-8").strip() == "6"
    (w.opt / "lab-01.settings").unlink()                                    # the engine goes: the tombstone stays
    again = World.__new__(World)
    again.__dict__.update(w.__dict__)
    again.ex = esecutore.Esecutore(w.config, run=w.run, http_get=w.get, log=w.logs.append)
    assert again.ex.handle(order(seq=6, op_id="9c3a7b4f-5d2e-4f60-8b1c-2d3e4f5a6b7f"), READER_UID)["codice"] == "seq_vecchia"


def test_the_other_operations_are_not_yet_available(w):
    for op, params in (("crea_motore", {"porta": 8151}), ("aggiorna_motore", {}), ("togli_motore", {}),
                       ("aggiorna_broker", {"dispositivi": []}),
                       ("applica_catalogo", {"catalogo": "devices: []", "versione": 1})):
        r = w.ex.handle(order(operazione=op, apartment_id="lab-02", seq=1, parametri=params), READER_UID)
        assert (r["esito"], r["codice"]) == ("rifiutato", "non_disponibile"), op
    assert w.runs == [] and w.gets == [] and not (w.state / "seq" / "lab-02").exists()


def test_a_refusal_carries_what_could_be_read_of_the_order(w):
    r = w.ex.handle(order(apartment_id="Lab-01"), READER_UID)
    assert (r["op_id"], r["operazione"], r["apartment_id"], r["ambiente"]) == (OP, "stato", "Lab-01", "staging")
    assert set(r) <= {"op_id", "operazione", "apartment_id", "ambiente", "seq", "esito", "codice", "dati"}


def test_the_log_line_has_no_output_and_no_email(w):
    w.ex.handle(order(), READER_UID)
    [line] = w.logs
    assert line.startswith("agent exec ") and f"op_id={OP}" in line and "esito=riuscito" in line
    assert "durata_ms=" in line and w.image not in line and "@" not in line


def test_the_executor_journal_keeps_the_output_for_root(w):
    w.ex.handle(order(), READER_UID)
    files = list((w.state / "giornale").glob("*.jsonl"))
    assert len(files) == 1
    entry = json.loads(files[0].read_text(encoding="utf-8").splitlines()[-1])
    assert entry["op_id"] == OP and entry["esito"] == "riuscito" and w.image in json.dumps(entry)


def test_the_configuration_file_is_strict(tmp_path):
    good = tmp_path / "agent.conf"
    good.write_text("AMBIENTE=staging\nCONDIVISA=1\nLETTORE=domhouse-agent\nMAX_MOTORI_STAGING=4\n", encoding="utf-8")
    c = esecutore.read_config(good, uid_of=lambda name: 4242, check_owner=False)
    assert (c.ambiente, c.condivisa, c.reader_uid, c.max_staging) == ("staging", True, 4242, 4)
    for text in ("AMBIENTE=sviluppo\n", "AMBIENTE=staging\nSCONOSCIUTO=1\n", "AMBIENTE=staging\nCONDIVISA=forse\n"):
        bad = tmp_path / "bad.conf"
        bad.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            esecutore.read_config(bad, uid_of=lambda name: 4242, check_owner=False)


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="SO_PEERCRED e i socket UNIX: solo Linux (CI)")
def test_the_socket_serves_one_request_and_checks_the_peer(tmp_path):
    w = World(tmp_path)
    w.config = w.config._replace(reader_uid=os.getuid())
    w.ex = esecutore.Esecutore(w.config, run=w.run, http_get=w.get, log=w.logs.append)
    path = tmp_path / "run" / "esecutore.sock"
    path.parent.mkdir()
    server = esecutore.make_server(path, w.ex)
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(str(path))
        s.sendall(json.dumps({"ordine": order().decode("utf-8")}).encode("utf-8") + b"\n")
        answer = json.loads(s.makefile("rb").readline())
    t.join(5)
    server.server_close()
    assert (answer["esito"], answer["codice"]) == ("riuscito", "ok")
    assert oct(path.stat().st_mode & 0o777) == "0o660"


# ---- second reading, 16 November (security review of A1: R6, R7, R13, R14, R16) ----------------------------------
def test_r6_an_unreadable_tombstone_refuses_with_an_alarm(w):
    folder = w.state / "seq"
    folder.mkdir(parents=True)
    for content in ("non un numero\n", "0\n", ""):
        (folder / "lab-01").write_text(content, encoding="utf-8")
        r = w.ex.handle(order(seq=9), READER_UID)
        assert (r["esito"], r["codice"]) == ("rifiutato", "errore_interno"), content
        assert w.gets == [] and any(l.startswith("agent alarm codice=lapide_illeggibile") for l in w.logs)
    assert (folder / "lab-01").read_text(encoding="utf-8") == ""          # never overwritten


def test_r6_the_tombstone_and_its_folder_are_synced(w, monkeypatch):
    synced = []
    monkeypatch.setattr(esecutore.os, "fsync", lambda fd: synced.append(fd))
    monkeypatch.setattr(esecutore, "_sync_dir", lambda path: synced.append(str(path)))
    w.ex.handle(order(), READER_UID)
    assert len([s for s in synced if isinstance(s, int)]) >= 1 and str(w.state / "seq") in synced


def test_r13_the_engines_health_is_read_without_redirects_nor_proxies():
    opener = esecutore.HEALTH_OPENER
    kinds = [type(h).__name__ for h in opener.handlers]
    assert "HTTPRedirectHandler" not in kinds and "NoRedirect" in kinds
    proxies = [h for h in opener.handlers if type(h).__name__ == "ProxyHandler"]
    assert all(h.proxies == {} for h in proxies)              # an empty ProxyHandler is not even registered
    assert not any(hasattr(h, "http_proxy_open") or hasattr(h, "https_proxy_open") for h in opener.handlers)


def test_r16_refusals_that_mean_a_compromised_reader_raise_an_alarm(w):
    w.ex.handle(order(), READER_UID + 1)
    w.ex.handle(order(apartment_id="a-k3f9x2qm", ambiente="prod"), READER_UID)
    w.ex.handle(order(ambiente="prod"), READER_UID)
    alarms = [l for l in w.logs if l.startswith("agent alarm ")]
    assert [a.split()[2] for a in alarms] == ["codice=chiamante_non_ammesso", "codice=prod_non_ammesso",
                                             "codice=prod_non_ammesso"]


def test_r16_the_alarm_policy_reads_both_services():
    policy = json.loads((ROOT / "scripts" / "agent" / "allarmi" / "agente-allarme.json").read_text(encoding="utf-8"))
    flt = policy["conditions"][0]["conditionMatchedLog"]["filter"]
    assert "domhouse-agent-(lettore|esecutore)" in flt


def test_r7_the_executor_unit_is_strict_and_without_capabilities():
    unit = (AGENT / "domhouse-agent-esecutore.service").read_text(encoding="utf-8")
    assert "ProtectSystem=strict" in unit and "CapabilityBoundingSet=\n" in unit and "ProtectSystem=full" not in unit


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="SO_PEERCRED e i socket UNIX: solo Linux (CI)")
def test_r14_a_stranger_is_answered_before_anything_is_read_and_a_silent_peer_times_out(tmp_path, monkeypatch):
    w = World(tmp_path)
    w.ex = esecutore.Esecutore(w.config, run=w.run, http_get=w.get, log=w.logs.append)   # reader_uid is not ours
    monkeypatch.setattr(esecutore, "PEER_TIMEOUT_S", 0.5)
    path = tmp_path / "run" / "esecutore.sock"
    path.parent.mkdir()
    server = esecutore.make_server(path, w.ex)
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect(str(path))                                   # sends nothing at all
        answer = json.loads(s.makefile("rb").readline())
    t.join(5)
    server.server_close()
    assert answer["codice"] == "chiamante_non_ammesso"


# ---- third reading, 16 November (R16, R6, DOCKER_CONFIG) -----------------------------------------------------------
def test_r16_every_refusal_the_reader_should_have_made_raises_an_alarm(w):
    w.ex.handle(order(apartment_id="lab_01"), READER_UID)                       # id_non_valido: the reader lets it pass?
    w.ex.handle(order(parametri={"x": 1}), READER_UID)
    w.ex.handle(b"{rotto", READER_UID)
    w.ex.handle(order(operazione="togli_motore", seq=1, apartment_id="lab-02"), READER_UID)   # non_disponibile: normal
    w.ex.handle(order(apartment_id="lab-99", seq=1), READER_UID)                              # motore_assente: normal
    w.ex.handle(order(seq=1), READER_UID)
    w.ex.handle(order(seq=1, op_id="9c3a7b4f-5d2e-4f60-8b1c-2d3e4f5a6b7c"), READER_UID)       # seq_vecchia: normal
    codes = [l.split()[2] for l in w.logs if l.startswith("agent alarm ")]
    assert codes == ["codice=id_non_valido", "codice=parametri_non_validi", "codice=json_non_valido"]


@pytest.mark.parametrize("kind", ["cartella", "binario"])
def test_r6_a_tombstone_unreadable_in_any_way_is_refused_with_an_alarm(w, kind):
    folder = w.state / "seq"
    folder.mkdir(parents=True)
    if kind == "cartella":
        (folder / "lab-01").mkdir()
    else:
        (folder / "lab-01").write_bytes(b"\xff\xfe\x00")
    r = w.ex.handle(order(seq=9), READER_UID)
    assert (r["esito"], r["codice"]) == ("rifiutato", "errore_interno") and w.gets == []
    assert any(l.startswith("agent alarm codice=lapide_illeggibile") for l in w.logs)
