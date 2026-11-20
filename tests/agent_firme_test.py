"""A3 (docs/proposta-a3-server.md §6.3; review point 1, 9 and N5): signatures both ways.

- The server signs every order (HMAC-SHA256, the «ordini» key) on its canonical form, with `firmato_at`; the field
  `firma` travels in the JSON body and is left out of what is signed. The operation keeps the SHA-256 of the order.
- The executor checks the signature BEFORE anything else (`firma_non_valida`, an alarm) and the time by itself (more
  than 15 minutes old, or more than 2 ahead: `scaduto`); during a change of key it accepts the old one and the new one.
- The executor signs every result (the «risultati» key) with the SHA-256 of the order it executed; the reader passes
  both fields through. The server accepts «riuscito» only signed AND with the fingerprint of the order it published;
  the results the reader writes by itself (scaduto, interrotto, refusals) are unsigned and never «riuscito».
"""
import asyncio
import base64
import dataclasses
import hashlib
import hmac
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from bff import agent, device_credentials
from bff.auth import require_platform
from bff.config import get_settings
from bff.main import app
from bff.repository import get_repository

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
lettore = load("lettore")

K_ORD, K_ORD_OLD, K_RIS = b"\x01" * 32, b"\x02" * 32, b"\x03" * 32
OP = "8b2f6a3e-4c1d-4e5f-9a0b-1c2d3e4f5a6b"
# the real time when the file is read: the server of these tests runs on NOW, but the repository judges an
# operation's age by the real clock (finish_agent_op); a fixed date passed on 19 November and was «tardi» the day
# after (CI, 20 November). Whole milliseconds, as the timestamps are written
_STARTED = datetime.now(UTC)
NOW = _STARTED.replace(microsecond=_STARTED.microsecond // 1000 * 1000)
READER_UID = 4242


def iso(moment: datetime) -> str:
    return moment.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def signed(key=K_ORD, at=NOW, **kw) -> dict:
    o = {"op_id": OP, "operazione": "capienza", "apartment_id": None, "seq": None, "parametri": {},
         "ambiente": "staging", "richiesto_da": "Uk9TgS2vLmQ1", "firmato_at": iso(at)}
    o.update(kw)
    o["firma"] = comune.signature(key, o)
    return o


# ---- the shared functions -----------------------------------------------------------------------------------------
def test_the_server_and_the_agent_sign_and_fingerprint_the_same_way():
    o = signed()
    assert comune.canonical(o) == device_credentials.canonical(o)
    unsigned = {k: v for k, v in o.items() if k != "firma"}
    assert o["firma"] == hmac.new(K_ORD, device_credentials.canonical(unsigned), hashlib.sha256).hexdigest()
    assert comune.order_sha256(o) == hashlib.sha256(device_credentials.canonical(unsigned)).hexdigest()
    assert agent.signature(K_ORD, o) == o["firma"] and agent.order_sha256(o) == comune.order_sha256(o)
    assert comune.signed_by([K_ORD_OLD, K_ORD], o) and not comune.signed_by([K_RIS], o)
    assert not comune.signed_by([K_ORD], {**o, "seq": 4})                 # any change breaks it


def test_an_order_must_carry_the_time_and_the_signature_fields():
    o = signed()
    assert comune.check_order(json.dumps(o).encode(), "staging").op_id == OP
    for broken in ({k: v for k, v in o.items() if k != "firma"}, {**o, "firma": "xyz"}, {**o, "firmato_at": "ieri"}):
        with pytest.raises(comune.Refused):
            comune.check_order(json.dumps(broken).encode(), "staging")


# ---- the executor ---------------------------------------------------------------------------------------------------
class Vm:
    def __init__(self, tmp: Path, ordini=(K_ORD,), risultati=(K_RIS,)):
        opt, state = tmp / "opt", tmp / "state"
        opt.mkdir()
        meminfo = tmp / "meminfo"
        meminfo.write_text("MemTotal:        2014000 kB\nMemAvailable:     812000 kB\n", encoding="utf-8")
        self.keys = {"ordini": list(ordini), "risultati": list(risultati)}
        self.logs = []
        config = esecutore.Config(ambiente="staging", condivisa=True, reader_uid=READER_UID, opt=opt, state=state,
                                  bind_ip="10.198.0.2", max_staging=4, meminfo=meminfo)
        self.ex = esecutore.Esecutore(config, run=lambda *a, **k: (1, ""), http_get=lambda *a, **k: (0, None),
                                      log=self.logs.append, keys=lambda name: self.keys[name],
                                      clock=lambda: NOW)

    def send(self, o) -> dict:
        return self.ex.handle(json.dumps(o).encode("utf-8"), READER_UID)


@pytest.fixture
def vm(tmp_path):
    return Vm(tmp_path)


def test_a_signed_order_runs_and_its_result_is_signed_with_the_orders_fingerprint(vm):
    o = signed()
    out = vm.send(o)
    assert (out["esito"], out["codice"]) == ("riuscito", "ok")
    assert out["ordine_sha256"] == comune.order_sha256(o)
    assert comune.signed_by([K_RIS], out) and not comune.signed_by([K_ORD], out)


@pytest.mark.parametrize("o", [
    {k: v for k, v in signed().items() if k != "firma"},                 # no signature at all
    signed(key=K_RIS),                                                    # another key
    {**signed(), "richiesto_da": "Altro9TgS2vL"},                         # changed after the signature
])
def test_an_order_without_the_servers_signature_is_refused_before_anything_with_an_alarm(vm, o):
    out = vm.send(o)
    assert (out["esito"], out["codice"]) == ("rifiutato", "firma_non_valida")
    assert any("agent alarm codice=firma_non_valida" in line for line in vm.logs)


def test_the_executor_checks_the_time_itself(vm):
    assert vm.send(signed(at=NOW - timedelta(minutes=16)))["codice"] == "scaduto"
    assert vm.send(signed(at=NOW + timedelta(minutes=3)))["codice"] == "scaduto"
    assert vm.send(signed(at=NOW - timedelta(minutes=14)))["codice"] == "ok"


def test_during_a_change_of_key_the_executor_accepts_the_old_and_the_new(tmp_path):
    vm = Vm(tmp_path, ordini=(K_ORD, K_ORD_OLD))
    assert vm.send(signed(key=K_ORD_OLD))["codice"] == "ok" and vm.send(signed(key=K_ORD))["codice"] == "ok"


def test_without_its_keys_the_executor_refuses_everything(tmp_path):
    vm = Vm(tmp_path, ordini=(), risultati=())
    out = vm.send(signed())
    assert (out["esito"], out["codice"]) == ("rifiutato", "firma_non_valida") and "firma" not in out


def test_the_key_files_are_roots_and_hold_one_or_two_keys(tmp_path):
    f = tmp_path / "agent-ordini.key"
    f.write_text(K_ORD.hex() + "\n" + K_ORD_OLD.hex() + "\n", encoding="utf-8")
    assert esecutore.read_keys(f, check_owner=False) == [K_ORD, K_ORD_OLD]
    for bad in ("", "zz" * 32, K_ORD.hex()[:-2], "\n".join([K_ORD.hex()] * 3)):
        f.write_text(bad, encoding="utf-8")
        with pytest.raises(ValueError):
            esecutore.read_keys(f, check_owner=False)


# ---- the reader -------------------------------------------------------------------------------------------------
def test_the_reader_passes_the_signature_and_the_fingerprint_through(tmp_path):
    reader = lettore.Lettore(ambiente="staging", pubsub=None, execute=None, journal=tmp_path, clock=lambda: NOW,
                             log=lambda line: None)
    entry = {"op_id": OP, "operazione": "capienza", "apartment_id": None, "ambiente": "staging", "seq": None}
    answer = {**entry, "esito": "riuscito", "codice": "ok", "dati": {"motori": 2}, "ordine_sha256": "a" * 64}
    answer["firma"] = comune.signature(K_RIS, answer)
    out = reader._filtered(entry, answer)
    assert out == answer and comune.signed_by([K_RIS], out)


# ---- the server ---------------------------------------------------------------------------------------------------
SUBSCRIPTION = "projects/p/subscriptions/domhouse-staging-risultati-push"


@pytest.fixture
def server(monkeypatch):
    settings = dataclasses.replace(get_settings(), agent_ambiente="staging", agent_orders_topic="projects/p/topics/o",
                                   agent_push_audience="https://aud", agent_push_email="push@p.iam.gserviceaccount.com",
                                   agent_push_subscription=SUBSCRIPTION, agent_ordini_key=K_ORD.hex(),
                                   agent_risultati_key=K_RIS.hex(), agent_risultati_key_prev="")
    monkeypatch.setattr(agent, "get_settings", lambda: settings)
    published = []
    monkeypatch.setattr(agent, "publish", lambda topic, body, key: published.append(json.loads(body)))
    monkeypatch.setattr(agent, "authorised", _yes)
    monkeypatch.setattr(agent, "utcnow", lambda: NOW)
    app.dependency_overrides[require_platform] = lambda: type("I", (), {"uid": "Uk9TgS2vLmQ1"})()
    yield published
    app.dependency_overrides.pop(require_platform, None)


async def _yes(authorization):
    return True


async def call(method, path, **kw):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, path, **kw)


def push(result):
    body = {"message": {"data": base64.b64encode(json.dumps(result).encode()).decode(), "messageId": "1"},
            "subscription": SUBSCRIPTION}
    return asyncio.run(call("POST", "/internal/agent/risultati", json=body, headers={"Authorization": "Bearer x"}))


def sent_order(server):
    r = asyncio.run(call("POST", "/app/platform/agent/prova", json={"apartment_id": "lab-01"}))
    assert r.status_code == 202, r.text
    return server[-1]


def result_for(o, esito="riuscito", codice="ok", key=K_RIS, sha=None):
    out = {"op_id": o["op_id"], "operazione": o["operazione"], "apartment_id": o["apartment_id"],
           "ambiente": "staging", "seq": o["seq"], "esito": esito, "codice": codice,
           "ordine_sha256": sha or comune.order_sha256(o)}
    if key is not None:
        out["firma"] = comune.signature(key, out)
    return out


def op_state(o):
    return asyncio.run(get_repository().get_agent_op(o["op_id"])).stato


def test_every_order_is_signed_and_its_fingerprint_kept(server):
    o = sent_order(server)
    assert o["firmato_at"] == iso(NOW) and comune.signed_by([K_ORD], o)
    assert comune.check_order(json.dumps(o).encode(), "staging").op_id == o["op_id"]
    assert asyncio.run(get_repository().get_agent_op(o["op_id"])).ordine_sha256 == comune.order_sha256(o)


def test_a_success_counts_only_signed_and_for_the_order_published(server):
    o = sent_order(server)
    assert push(result_for(o, key=None)).status_code == 204 and op_state(o) == "inviato"           # unsigned
    assert push(result_for(o, key=K_ORD)).status_code == 204 and op_state(o) == "inviato"          # wrong key
    assert push(result_for(o, sha="b" * 64)).status_code == 204 and op_state(o) == "inviato"       # another order
    assert push(result_for(o)).status_code == 204 and op_state(o) == "riuscito"


def test_the_readers_own_results_are_accepted_unsigned_but_never_as_a_success(server):
    o = sent_order(server)
    late = result_for(o, esito="scartato", codice="scaduto", key=None)
    late.pop("ordine_sha256")
    assert push(late).status_code == 204 and op_state(o) == "scartato"


def test_a_result_with_another_seq_is_ignored(server):
    o = sent_order(server)
    wrong = result_for({**o, "seq": o["seq"] + 5})
    assert push(wrong).status_code == 204 and op_state(o) == "inviato"


def test_without_the_keys_the_agent_is_not_configured(server, monkeypatch):
    settings = dataclasses.replace(agent.get_settings(), agent_ordini_key="")
    monkeypatch.setattr(agent, "get_settings", lambda: settings)
    r = asyncio.run(call("POST", "/app/platform/agent/prova", json={"apartment_id": "lab-01"}))
    assert r.status_code == 503 and r.json()["error"] == "agent_not_configured"
