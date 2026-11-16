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
SUBSCRIPTION = "projects/domotica-poc-511707/subscriptions/domhouse-staging-risultati-push"
MANAGER = Identity(uid="UpLatM4nager", email="gestore@piattaforma.it", display_name="Gestore", user=None,
                   platform_manager=True)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def server(monkeypatch):
    settings = dataclasses.replace(get_settings(), agent_ambiente="staging", agent_orders_topic=TOPIC,
                                   agent_push_audience=AUD, agent_push_email=PUSH,
                                   agent_push_subscription=SUBSCRIPTION)
    monkeypatch.setattr(agent, "get_settings", lambda: settings)
    published = []
    state = type("S", (), {"fail": False, "now": None})()

    def publish(topic, body, ordering_key):
        if state.fail:
            raise OSError("pubsub non risponde")
        published.append((topic, json.loads(body), ordering_key))
    monkeypatch.setattr(agent, "publish", publish)

    def verify(token, audience):
        token = agent.precheck(token)["kid"]                    # the name travels in the kid of a well-formed token
        g = "https://accounts.google.com"
        claims = {"buono": {"email": PUSH, "email_verified": True, "aud": audience, "iss": g},
                  "altro": {"email": "intruso@example.com", "email_verified": True, "aud": audience, "iss": g},
                  "non-verificato": {"email": PUSH, "email_verified": False, "aud": audience, "iss": g}}
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
            "subscription": SUBSCRIPTION}
    headers = {"Authorization": f"Bearer {jwt_named(token)}"} if token else {}
    return run(call("POST", "/internal/agent/risultati", json=body, headers=headers))


def jwt_named(name: str) -> str:
    """A token with the shape of Google's (precheck passes), its name in the kid; «non-un-token» stays as it is."""
    if name == "non-un-token":
        return name
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "kid": name}).encode()).decode().rstrip("=")
    return f"{header}.e30.firma"


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
    for apartment in ("a-k3f9x2qm", "lab_01", "Lab-01", "../x", "", "test-", "lab--", "lab-01-"):
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
                 headers={"Authorization": f"Bearer {jwt_named('buono')}"}))
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
    assert agent.STAGING_ID_RE.pattern == comune.STAGING_ID_RE.pattern                 # R15


# ---- second reading, 16 November (security review of A1: R1, R2, R5, R18) ----------------------------------------
def b64url(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


GOOD_TOKEN = f"{b64url({'alg': 'RS256', 'kid': 'k1', 'typ': 'JWT'})}.{b64url({'sub': 'x'})}.firma"


def test_r1_a_cheap_check_before_any_certificate_and_the_certificates_cached(monkeypatch):
    fetched, decoded = [], []

    def fetch():
        fetched.append(1)
        return {"k1": "PEM"}, 3600
    monkeypatch.setattr(agent, "_fetch_certs", fetch)
    monkeypatch.setattr(agent, "_decode", lambda token, certs, audience: decoded.append(certs) or {"aud": audience})
    agent._CERTS.update(certs=None, until=0.0, refreshed=0.0, failed=0.0)
    monkeypatch.setattr(agent.time, "monotonic", lambda: 1000.0)
    for junk in ("", "abc", "a.b", "a.b.c.d", "x" * 5000 + ".a.b",
                 f"{b64url({'alg': 'none', 'kid': 'k1'})}.e30.x", f"{b64url({'alg': 'RS256'})}.e30.x",
                 f"{b64url({'alg': 'HS256', 'kid': 'k1'})}.e30.x", "!!!.???.***"):
        with pytest.raises(ValueError):
            agent.verify_push_token(junk, AUD)
    assert fetched == [] and decoded == []                         # nothing fetched for a token that cannot be one
    agent.verify_push_token(GOOD_TOKEN, AUD)
    agent.verify_push_token(GOOD_TOKEN, AUD)
    assert fetched == [1] and decoded == [{"k1": "PEM"}, {"k1": "PEM"}]   # one fetch, cached for its max-age


def test_r1_r18_google_is_called_outside_the_event_loop(server, monkeypatch):
    threads = []
    real = agent.asyncio.to_thread

    async def spy(fn, *args, **kw):
        threads.append({agent.publish: "publish", agent.verify_push_token: "verify_push_token"}.get(fn, fn))
        return await real(fn, *args, **kw)
    monkeypatch.setattr(agent.asyncio, "to_thread", spy)
    op = prova().json()
    push(answer(op))
    assert "publish" in threads and "verify_push_token" in threads


def test_r2_whatever_the_push_carries_the_server_answers_204(server):
    op = prova().json()
    deep = base64.b64encode(b"[" * 60_000 + b"]" * 60_000).decode()
    for body in (["lista"], {"message": "testo"}, {"message": {"data": deep}}, {"message": {"data": None}},
                 {"message": {"data": base64.b64encode(b'{"op_id": 1, "esito": []}').decode()}}):
        r = run(call("POST", "/internal/agent/risultati", json={**body, "subscription": SUBSCRIPTION}
                     if isinstance(body, dict) else body, headers={"Authorization": f"Bearer {jwt_named('buono')}"}))
        assert r.status_code == 204, body
    assert get(op["op_id"]).json()["stato"] == "inviato"


def test_r5_a_result_from_another_subscription_is_ignored(server):
    op = prova().json()
    body = {"message": {"data": base64.b64encode(json.dumps(answer(op)).encode()).decode()},
            "subscription": "projects/domotica-poc-511707/subscriptions/un-altra"}
    r = run(call("POST", "/internal/agent/risultati", json=body, headers={"Authorization": f"Bearer {jwt_named('buono')}"}))
    assert r.status_code == 204 and get(op["op_id"]).json()["stato"] == "inviato"


# ---- third reading, 16 November (N2-N5) ---------------------------------------------------------------------------
REAL_VERIFY = agent.verify_push_token
def test_n2_a_repository_failure_is_a_5xx_so_that_pubsub_retries(server, monkeypatch):
    op = prova().json()

    async def broken(*a, **k):
        raise RuntimeError("Firestore non risponde")
    monkeypatch.setattr(get_repository(), "finish_agent_op", broken)
    assert push(answer(op)).status_code == 503
    monkeypatch.setattr(get_repository(), "get_agent_op", broken)
    assert push(answer(op)).status_code == 503
    r = run(call("POST", "/internal/agent/risultati", json=["lista"], headers={"Authorization": f"Bearer {jwt_named('buono')}"}))
    assert r.status_code == 204                                        # unreadable: acknowledged, never retried


def test_n3_the_issuer_must_be_google(server, monkeypatch):
    monkeypatch.setattr(agent, "verify_push_token", lambda token, audience: {
        "email": PUSH, "email_verified": True, "aud": audience, "iss": "https://evil.example"})
    op = prova().json()
    assert push(answer(op)).status_code == 401
    monkeypatch.setattr(agent, "verify_push_token", lambda token, audience: {
        "email": PUSH, "email_verified": True, "aud": audience, "iss": "accounts.google.com"})
    assert push(answer(op)).status_code == 204


def certs_world(monkeypatch, answers):
    """_fetch_certs answering from a list: a dict of certificates, or an exception to raise."""
    calls = []

    def fetch():
        calls.append(1)
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a, 3600
    monkeypatch.setattr(agent, "_fetch_certs", fetch)
    monkeypatch.setattr(agent, "_decode", lambda token, certs, audience: {"aud": audience, "certs": dict(certs)})
    clock = {"t": 1000.0}
    monkeypatch.setattr(agent.time, "monotonic", lambda: clock["t"])
    agent._CERTS.update(certs=None, until=0.0, refreshed=0.0, failed=0.0)
    return calls, clock


def token_with(kid):
    return f"{b64url({'alg': 'RS256', 'kid': kid})}.{b64url({'sub': 'x'})}.firma"


def test_n4_an_unknown_kid_forces_one_refresh_a_minute(monkeypatch):
    calls, clock = certs_world(monkeypatch, [{"k1": "A"}, {"k1": "A", "k2": "B"}, {"k3": "C"}])
    agent.verify_push_token(token_with("k1"), AUD)
    assert agent.verify_push_token(token_with("k2"), AUD)["certs"] == {"k1": "A", "k2": "B"}   # refreshed for k2
    with pytest.raises(ValueError):
        agent.verify_push_token(token_with("k9"), AUD)                  # unknown again, within the minute: no fetch
    assert len(calls) == 2
    clock["t"] += 61
    with pytest.raises(ValueError):
        agent.verify_push_token(token_with("k9"), AUD)                  # after a minute: one more fetch
    assert len(calls) == 3


def test_n5_old_certificates_are_kept_and_a_failed_download_waits(monkeypatch):
    calls, clock = certs_world(monkeypatch, [{"k1": "A"}, OSError("rete"), {"k1": "A2"}])
    agent.verify_push_token(token_with("k1"), AUD)
    clock["t"] += 3601                                                  # expired
    assert agent.verify_push_token(token_with("k1"), AUD)["certs"] == {"k1": "A"}   # download failed: the old ones
    clock["t"] += 10
    agent.verify_push_token(token_with("k1"), AUD)
    assert len(calls) == 2                                              # within 30 s of the failure: no new try
    clock["t"] += 31
    assert agent.verify_push_token(token_with("k1"), AUD)["certs"] == {"k1": "A2"}


def test_n5_the_cheap_check_happens_before_the_thread(server, monkeypatch):
    monkeypatch.setattr(agent, "verify_push_token", REAL_VERIFY)
    threads = []
    real = agent.asyncio.to_thread

    async def spy(fn, *args, **kw):
        threads.append(fn)
        return await real(fn, *args, **kw)
    monkeypatch.setattr(agent.asyncio, "to_thread", spy)
    op = prova().json()
    threads.clear()
    assert push(answer(op), token="non-un-token").status_code == 401
    assert threads == []


# ---- fourth reading, 16 November (op_id as a UUID only, certificates from boot) -----------------------------------
def test_an_op_id_that_is_not_a_uuid_is_never_looked_up(server, monkeypatch):
    looked = []
    real = get_repository().get_agent_op

    async def spy(op_id):
        looked.append(op_id)
        return await real(op_id)
    monkeypatch.setattr(get_repository(), "get_agent_op", spy)
    op = prova().json()
    for bad in ("a/b", "..", "x" * 36):
        assert push(answer(op, op_id=bad)).status_code == 204
    assert looked == []


def test_certificates_are_downloaded_right_after_boot(monkeypatch):
    calls = []
    monkeypatch.setattr(agent, "_fetch_certs", lambda: calls.append(1) or ({"k1": "A"}, 3600))
    monkeypatch.setattr(agent, "_decode", lambda token, certs, audience: {"aud": audience})
    monkeypatch.setattr(agent.time, "monotonic", lambda: 5.0)            # the VM, or the container, just started
    agent._CERTS.clear()
    agent._CERTS.update(agent.CERTS_INITIAL)
    agent.verify_push_token(token_with("k1"), AUD)
    assert calls == [1]
