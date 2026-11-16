"""Tool A, package A1 (docs/progetto-strumento-a-base.md §3, §4.2, §6): the server's side of the order receiver,
bff/agent.py and bff/routes/agent.py. In-process, memory repository, Pub/Sub's publish and Google's token check
replaced:
  - POST /app/platform/agent/prova (platform managers only): an order «stato» with its sequence number per apartment,
    in «inviato», published on the environment's orders topic; GET /app/platform/agent/ops/{op_id} reads it back;
  - POST /internal/agent/risultati: Pub/Sub's push of the results, accepted only with Google's signature for the
    exact address and the push account of this environment (§4.2), and only for an operation waiting, of the same
    environment, apartment and operation; after 20 minutes an operation is failed and a late result is ignored."""
import asyncio
import base64
import dataclasses
import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from bff import agent
from bff.auth import Identity, require_platform
from bff.config import get_settings
from bff.main import app
from bff.repository import get_repository

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_comune_srv", ROOT / "scripts" / "agent" / "comune.py")
comune = importlib.util.module_from_spec(spec)
sys.modules["agent_comune_srv"] = comune
spec.loader.exec_module(comune)

AUD = "https://domotica-bff-staging-abc123-ew.a.run.app/internal/agent/risultati"
PUSH = "domhouse-push-staging@domotica-poc-511707.iam.gserviceaccount.com"
TOPIC = "projects/domotica-poc-511707/topics/domhouse-staging-ordini"
MANAGER = Identity(uid="UpLatM4nager", email="gestore@piattaforma.it", display_name="Gestore", user=None,
                   platform_manager=True)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def server(monkeypatch):
    settings = dataclasses.replace(get_settings(), agent_ambiente="staging", agent_orders_topic=TOPIC,
                                   agent_push_audience=AUD, agent_push_email=PUSH)
    monkeypatch.setattr(agent, "get_settings", lambda: settings)
    published = []
    state = type("S", (), {"fail": False, "now": None})()

    def publish(topic, body, ordering_key):
        if state.fail:
            raise OSError("pubsub non risponde")
        published.append((topic, json.loads(body), ordering_key))
    monkeypatch.setattr(agent, "publish", publish)

    def verify(token, audience):
        claims = {"buono": {"email": PUSH, "email_verified": True, "aud": audience},
                  "altro": {"email": "intruso@example.com", "email_verified": True, "aud": audience},
                  "non-verificato": {"email": PUSH, "email_verified": False, "aud": audience}}
        if token not in claims or audience != AUD:
            raise ValueError("firma non valida")
        return claims[token]
    monkeypatch.setattr(agent, "verify_push_token", verify)
    real_now = agent.utcnow
    monkeypatch.setattr(agent, "utcnow", lambda: state.now or real_now())
    app.dependency_overrides[require_platform] = lambda: MANAGER
    get_repository().agent_ops, get_repository().agent_seq = {}, {}
    yield type("W", (), {"published": published, "state": state})
    app.dependency_overrides.pop(require_platform, None)


async def call(method, path, **kw):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, path, **kw)


def prova(apartment="lab-01"):
    return run(call("POST", "/app/platform/agent/prova", json={"apartment_id": apartment}))


def push(result: dict, token="buono"):
    body = {"message": {"data": base64.b64encode(json.dumps(result).encode()).decode(), "messageId": "1"},
            "subscription": "projects/domotica-poc-511707/subscriptions/domhouse-staging-risultati-push"}
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return run(call("POST", "/internal/agent/risultati", json=body, headers=headers))


def answer(op: dict, esito="riuscito", codice="ok", **kw) -> dict:
    out = {"op_id": op["op_id"], "operazione": "stato", "apartment_id": op["apartment_id"], "ambiente": "staging",
           "seq": op["seq"], "esito": esito, "codice": codice, "dati": {"health": 200, "connector": "up"}}
    out.update(kw)
    return out


def get(op_id):
    return run(call("GET", f"/app/platform/agent/ops/{op_id}"))


def test_the_button_sends_an_order_the_agent_accepts(server):
    r = prova()
    assert r.status_code == 202, r.text
    op = r.json()
    assert (op["operazione"], op["apartment_id"], op["stato"], op["seq"]) == ("stato", "lab-01", "inviato", 1)
    [(topic, order, key)] = server.published
    assert topic == TOPIC and key == "lab-01"
    checked = comune.check_order(json.dumps(order).encode(), "staging")        # the VM's own rules accept it
    assert (checked.op_id, checked.seq, checked.richiesto_da) == (op["op_id"], 1, MANAGER.uid)
    assert "@" not in json.dumps(order)                                         # never an email in the order
    assert prova().json()["seq"] == 2 and prova("dev").json()["seq"] == 1      # per apartment


def test_what_the_button_refuses(server):
    for apartment in ("a-k3f9x2qm", "lab_01", "Lab-01", "../x", ""):
        assert prova(apartment).status_code == 422, apartment
    assert server.published == []


def test_without_the_agent_configured_nothing_is_sent(server, monkeypatch):
    monkeypatch.setattr(agent, "get_settings", lambda: dataclasses.replace(get_settings(), agent_ambiente=""))
    r = prova()
    assert r.status_code == 503 and r.json()["error"] == "agent_not_configured" and server.published == []


def test_a_failed_publish_leaves_the_operation_failed(server):
    server.state.fail = True
    r = prova()
    assert r.status_code == 502 and r.json()["error"] == "agent_publish_failed"
    op = r.json()["details"]["op"]
    assert (get(op["op_id"]).json()["stato"], get(op["op_id"]).json()["codice"]) == ("fallito", "non_inviato")


def test_a_signed_result_closes_the_operation_with_its_words(server):
    op = prova().json()
    assert push(answer(op)).status_code == 204
    seen = get(op["op_id"]).json()
    assert (seen["stato"], seen["codice"], seen["dati"]) == ("riuscito", "ok", {"health": 200, "connector": "up"})
    assert seen["messaggio"] and seen["finito_at"]
    r = push(answer(op, esito="rifiutato", codice="seq_vecchia"))                 # a second result: ignored
    assert r.status_code == 204 and get(op["op_id"]).json()["stato"] == "riuscito"


@pytest.mark.parametrize("token", [None, "altro", "non-verificato", "falso"])
def test_a_result_without_the_right_signature_is_refused(server, token):
    op = prova().json()
    assert push(answer(op), token=token).status_code == 401
    assert get(op["op_id"]).json()["stato"] == "inviato"


def test_a_result_that_does_not_match_its_operation_is_ignored(server):
    op = prova().json()
    for wrong in (dict(apartment_id="lab-02"), dict(operazione="capienza"), dict(ambiente="prod"),
                  dict(op_id="00000000-0000-4000-8000-000000000000"), dict(codice="testo libero"),
                  dict(esito="andato")):
        assert push(answer(op, **wrong)).status_code == 204, wrong
        assert get(op["op_id"]).json()["stato"] == "inviato", wrong
    r = run(call("POST", "/internal/agent/risultati", json={"message": {"data": "non base64!"}},
                 headers={"Authorization": "Bearer buono"}))
    assert r.status_code == 204                                                   # acknowledged, never retried


def test_after_20_minutes_the_operation_is_failed_and_a_late_result_ignored(server):
    op = prova().json()
    server.state.now = datetime.now(UTC) + timedelta(minutes=21)
    seen = get(op["op_id"]).json()
    assert (seen["stato"], seen["codice"]) == ("fallito", "tempo_scaduto")
    assert push(answer(op)).status_code == 204 and get(op["op_id"]).json()["stato"] == "fallito"


def test_an_unknown_operation_and_a_non_manager(server):
    assert get("8b2f6a3e-4c1d-4e5f-9a0b-1c2d3e4f5a6b").status_code == 404
    app.dependency_overrides.pop(require_platform)
    assert prova().status_code in (401, 403)


def test_the_server_knows_the_agents_lists():
    assert agent.OUTCOMES == comune.OUTCOMES and set(agent.CODES) >= set(comune.CODES)
    assert all(agent.MESSAGES.get(code) for code in agent.CODES)
    assert agent.STAGING_ID_RE.pattern == comune.GENERIC_ID_RE.pattern
