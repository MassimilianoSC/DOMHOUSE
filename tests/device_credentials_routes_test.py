"""A3 (docs/proposta-a3-server.md §2, §5, §8): the routes of the devices' credentials, in-process, memory repository,
dev auth (X-Dev-User), the agent configured with its keys, Pub/Sub replaced.

/app/apartments/{apt}/device-credentials for the organisation's administrators; the same calls under
/app/platform/apartments/{apt}/device-credentials for the platform managers, only in staging (and dev) and only for
lab- and test- apartments (answer 1170). The password is shown once and never kept; the order carries the complete
list of fingerprints; every «no» has its code."""
import asyncio
import base64
import dataclasses
import json

import httpx
import pytest

from bff import agent, device_credentials as dc
from bff.auth import require_platform
from bff.config import get_settings
from bff.main import app
from bff.repository import get_repository
from bff.repository.base import Apartment
from bff.repository.seed import DEMO_TENANT, OTHER_TENANT

K_ORD, K_RIS = bytes([0x31]) * 32, bytes([0x32]) * 32
ADMIN = {"X-Dev-User": "admin@demo.it"}
OPERATOR = {"X-Dev-User": "operatore@demo.it"}
APT, OTHER_APT = "lab-07", "lab-08"
BASE = f"/app/apartments/{APT}/device-credentials"
PLATFORM = f"/app/platform/apartments/{APT}/device-credentials"
SUBSCRIPTION = "projects/p/subscriptions/domhouse-staging-risultati-push"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def world(monkeypatch):
    settings = dataclasses.replace(
        get_settings(), agent_ambiente="staging", agent_orders_topic="projects/p/topics/ordini",
        agent_push_audience="https://aud", agent_push_email="push@p.iam.gserviceaccount.com",
        agent_push_subscription=SUBSCRIPTION, agent_ordini_key=K_ORD.hex(), agent_risultati_key=K_RIS.hex(),
        device_broker_address="mqtt.dh-lab.eu:8883")
    monkeypatch.setattr(agent, "get_settings", lambda: settings)
    state = type("S", (), {"settings": settings, "published": [], "fail": False})()

    def publish(topic, body, key):
        if state.fail:
            raise OSError("pubsub non risponde")
        state.published.append(json.loads(body))
    monkeypatch.setattr(agent, "publish", publish)

    async def yes(authorization):
        return True
    monkeypatch.setattr(agent, "authorised", yes)
    repo = get_repository()
    for apt_id, tenant in ((APT, DEMO_TENANT), (OTHER_APT, OTHER_TENANT)):
        repo.apartments[apt_id] = Apartment(apartment_id=apt_id, tenant_id=tenant, name=f"Laboratorio {apt_id}",
                                            instance_url="mock://builtin")
    repo.device_creds.clear()
    repo.mail_counts.clear()
    repo.audit.pop(DEMO_TENANT, None)                # each test reads only its own rows

    def configure(**changes):
        state.settings = dataclasses.replace(state.settings, **changes)
        monkeypatch.setattr(agent, "get_settings", lambda: state.settings)
    state.configure = configure
    yield state
    for apt_id in (APT, OTHER_APT):
        repo.apartments.pop(apt_id, None)
    app.dependency_overrides.pop(require_platform, None)


async def _call(method, path, **kw):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, path, **kw)


def call(method, path, headers=ADMIN, **kw):
    return run(_call(method, path, headers=headers, **kw))


def register(device="shelly-1", headers=ADMIN, base=BASE):
    return call("POST", base, headers=headers, json={"device_id": device})


def push_result(order, esito="riuscito", codice="ok"):
    result = {"op_id": order["op_id"], "operazione": order["operazione"], "apartment_id": order["apartment_id"],
              "ambiente": "staging", "seq": order["seq"], "esito": esito, "codice": codice,
              "ordine_sha256": agent.order_sha256(order)}
    result["firma"] = agent.signature(K_RIS, result)
    body = {"message": {"data": base64.b64encode(json.dumps(result).encode()).decode(), "messageId": "1"},
            "subscription": SUBSCRIPTION}
    return run(_call("POST", "/internal/agent/risultati", json=body, headers={"Authorization": "Bearer x"}))


def listed(device="shelly-1"):
    items = call("GET", BASE).json()["items"]
    return next(i for i in items if i["device_id"] == device)


# ---- «Registra» -----------------------------------------------------------------------------------------------------
def test_register_shows_the_password_once_and_sends_the_complete_list(world):
    r = register()
    assert r.status_code == 201, r.text
    body = r.json()
    password, cred = body["password"], body["credential"]
    assert len(password) == 32 and r.headers["cache-control"] == "no-store" and r.headers["pragma"] == "no-cache"
    assert (cred["device_id"], cred["stato"], cred["azione"], cred["version"]) == ("shelly-1", "in_attesa", "registra", 1)
    assert cred["connection"] == {"server": "mqtt.dh-lab.eu:8883", "ssl_ca": "ca.pem", "client_id": f"{APT}.shelly-1",
                                  "user": f"{APT}.shelly-1", "topic_prefix": f"{APT}/shelly-1"}
    assert cred["name"] is None and cred["engine_device_id"] is None and cred["op"]["op_id"]
    [order] = world.published
    assert order["operazione"] == "aggiorna_broker" and agent.signed_by([K_ORD], order)
    [entry] = order["parametri"]["dispositivi"]
    assert entry["id"] == "shelly-1" and dc.hash_matches(entry["impronta"], password)
    stored = get_repository().device_creds[APT]["shelly-1"]
    assert password not in json.dumps(stored) and dc.hash_matches(stored["impronta"], password)
    assert password not in json.dumps(listed()) and "impronta" not in listed()


def test_the_list_says_who_by_name_never_by_email(world):
    register()
    item = listed()
    assert item["updated_by"] == "Amministratore demo" and "@" not in json.dumps(item)


def test_register_twice_and_wrong_ids(world):
    assert register().status_code == 201
    again = register()
    assert again.status_code == 409 and again.json()["error"] == "already_registered"
    for bad in ("Shelly-1", "connector", "a" * 65, "-x"):
        r = register(bad)
        assert r.status_code == 422 and r.json()["error"] == "invalid_device_id", bad
    assert len(world.published) == 1


def test_a_register_records_one_line_in_the_activity_log(world):
    register()
    entries = run(get_repository().list_audit(DEMO_TENANT, limit=10))
    entry = next(e for e in entries if e.action == "device_credential_registered")
    assert entry.target.type == "apartment" and entry.target.id == APT and entry.details == {"device_id": "shelly-1"}


# ---- the other actions and the table of §4.3 ---------------------------------------------------------------------
def test_regenerate_needs_the_version_and_gives_a_new_password(world):
    first = register().json()
    stale = call("POST", f"{BASE}/shelly-1/rigenera", json={"version": 7})
    assert stale.status_code == 409 and stale.json()["error"] == "version_changed"
    bad = call("POST", f"{BASE}/shelly-1/rigenera", json={"version": "1"})
    assert bad.status_code == 422 and bad.json()["error"] == "invalid_version"
    r = call("POST", f"{BASE}/shelly-1/rigenera", json={"version": 1})
    assert r.status_code == 200 and r.json()["password"] != first["password"]
    assert r.json()["credential"]["stato"] == "cambio_in_corso" and r.json()["credential"]["version"] == 2


def test_a_confirmed_registration_reads_ready(world):
    register()
    assert push_result(world.published[-1]).status_code == 204
    assert listed()["stato"] == "pronto" and listed()["azione"] is None


def test_a_revocation_not_applied_closes_only_with_a_retry(world):
    register()
    push_result(world.published[-1])
    r = call("POST", f"{BASE}/shelly-1/revoca", json={"version": 1})
    assert r.status_code == 202 and r.json()["credential"]["stato"] == "revoca_in_corso"
    assert world.published[-1]["parametri"]["dispositivi"] == []
    push_result(world.published[-1], esito="fallito", codice="errore_interno")
    item = listed()
    assert (item["stato"], item["azione"]) == ("non_applicato", "revoca")
    regen = call("POST", f"{BASE}/shelly-1/rigenera", json={"version": item["version"]})
    assert regen.status_code == 409 and regen.json()["error"] == "invalid_state"
    retry = call("POST", f"{BASE}/shelly-1/riprova", json={"version": item["version"]})
    assert retry.status_code == 202 and retry.json()["credential"]["stato"] == "revoca_in_corso"
    push_result(world.published[-1])
    assert listed()["stato"] == "revocato"


def test_an_unknown_device(world):
    r = call("POST", f"{BASE}/nessuno/revoca", json={"version": 1})
    assert r.status_code == 404 and r.json()["error"] == "not_found"


# ---- permissions ----------------------------------------------------------------------------------------------------
def test_only_the_organisations_administrators(world):
    assert register(headers=OPERATOR).status_code == 403
    assert call("GET", BASE, headers=OPERATOR).status_code == 403
    other = call("GET", f"/app/apartments/{OTHER_APT}/device-credentials")
    assert other.status_code == 404                                      # another organisation's: as if it did not exist


def test_the_platform_managers_only_in_staging_and_only_for_lab_and_test(world):
    app.dependency_overrides[require_platform] = lambda: type(
        "I", (), {"uid": "Pm9TgS2vLmQ1", "email": "gestore@hqe.example", "display_name": "Gestore"})()
    world.configure(app_env="staging")
    assert register(base=PLATFORM).status_code == 201
    assert call("GET", PLATFORM).json()["items"][0]["device_id"] == "shelly-1"
    assert call("GET", "/app/platform/apartments/apt-rimini-01/device-credentials").status_code == 404
    world.configure(app_env="production")
    assert call("GET", PLATFORM).status_code == 404


def test_an_apartment_the_agent_does_not_accept(world):
    r = call("POST", "/app/apartments/apt-rimini-01/device-credentials", json={"device_id": "shelly-1"})
    assert r.status_code == 422 and r.json()["error"] == "invalid_apartment" and world.published == []


# ---- what is checked before the password exists ------------------------------------------------------------------
def test_without_the_agent_or_the_brokers_address_nothing_is_created(world):
    world.configure(agent_ordini_key="")
    r = register()
    assert r.status_code == 503 and r.json()["error"] == "agent_not_configured"
    world.configure(agent_ordini_key=K_ORD.hex(), device_broker_address="")
    r = register()
    assert r.status_code == 503 and r.json()["error"] == "broker_address_missing"
    assert world.published == [] and APT not in get_repository().device_creds


def test_the_list_without_the_brokers_address_says_null(world):
    register()
    world.configure(device_broker_address="")
    assert listed()["connection"]["server"] is None


def test_too_many_actions_in_an_hour(world):
    for n in range(30):
        assert register(f"shelly-{n:02d}").status_code == 201
    r = register("shelly-99")
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"


# ---- a failed publish ---------------------------------------------------------------------------------------------
def test_a_failed_publish_still_gives_the_password_of_a_registration(world):
    world.fail = True
    r = register()
    assert r.status_code == 201 and len(r.json()["password"]) == 32
    cred = r.json()["credential"]
    assert cred["stato"] == "non_applicato" and "Riprova" in cred["op"]["messaggio"]


def test_a_failed_publish_of_a_revocation_is_a_502_with_a_system_line(world):
    register()
    world.fail = True
    r = call("POST", f"{BASE}/shelly-1/revoca", json={"version": 1})
    assert r.status_code == 502 and r.json()["error"] == "agent_publish_failed"
    assert r.json()["details"]["op"]["op_id"]
    entries = run(get_repository().list_audit(DEMO_TENANT, limit=20))
    line = next(e for e in entries if e.action == "device_credential_revoke_not_applied")
    assert line.actor.kind == "system" and line.details["device_id"] == "shelly-1"


# ---- piece 4 (§8.4, answer 1175, review point 3, N2): the row and the alarm without anyone on the page ------------
def _system_rows():
    entries = run(get_repository().list_audit(DEMO_TENANT, limit=50))
    return [e for e in entries if e.action == "device_credential_revoke_not_applied"]


@pytest.fixture
def alarms(monkeypatch):
    from bff import device_alarms
    seen = []
    monkeypatch.setattr(device_alarms, "warn", lambda msg, **fields: seen.append((msg, fields)))
    return seen


def test_a_revocation_refused_by_the_agent_writes_the_row_and_the_alarm_at_once(world, alarms):
    register()
    push_result(world.published[-1])
    call("POST", f"{BASE}/shelly-1/revoca", json={"version": 1})
    revoke = world.published[-1]
    push_result(revoke, esito="fallito", codice="errore_interno")
    [row] = _system_rows()
    assert row.details["device_id"] == "shelly-1" and row.details["seq"] == revoke["seq"]
    assert [m for m, _ in alarms] == ["agent alarm codice=revoca_non_applicata"]
    push_result(revoke, esito="fallito", codice="errore_interno")            # the same result again: nothing more
    assert len(_system_rows()) == 1


def test_a_new_password_not_applied_raises_the_alarm_but_writes_no_row(world, alarms):
    register()
    push_result(world.published[-1])
    call("POST", f"{BASE}/shelly-1/rigenera", json={"version": 1})
    push_result(world.published[-1], esito="rifiutato", codice="parametri_non_validi")
    assert _system_rows() == [] and [m for m, _ in alarms] == ["agent alarm codice=rigenera_non_applicata"]


def test_the_hourly_round_finds_an_order_without_answer_once(world, alarms, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from bff import device_alarms
    register()
    push_result(world.published[-1])
    call("POST", f"{BASE}/shelly-1/revoca", json={"version": 1})
    later = datetime.now(UTC) + timedelta(minutes=25)
    assert run(device_alarms.round_once(now=later)) == 1
    assert run(device_alarms.round_once(now=later)) == 0
    assert len(_system_rows()) == 1


def test_a_revocation_not_published_is_not_counted_twice_by_the_round(world, alarms):
    from datetime import UTC, datetime, timedelta
    from bff import device_alarms
    register()
    push_result(world.published[-1])
    world.fail = True
    assert call("POST", f"{BASE}/shelly-1/revoca", json={"version": 1}).status_code == 502
    assert run(device_alarms.round_once(now=datetime.now(UTC) + timedelta(minutes=25))) == 0
    assert len(_system_rows()) == 1


def test_the_two_new_alarms_of_a1():
    from pathlib import Path
    folder = Path(__file__).resolve().parent.parent / "scripts" / "agent" / "allarmi"
    server = json.loads((folder / "server-allarme.json").read_text(encoding="utf-8"))
    log_filter = server["conditions"][0]["conditionMatchedLog"]["filter"]
    assert 'resource.type="cloud_run_revision"' in log_filter and "domotica-bff-staging" in log_filter
    assert "agent alarm" in log_filter and server["notificationChannels"] == ["__CHANNEL__"]
    unread = json.loads((folder / "ordini-non-letti.json").read_text(encoding="utf-8"))
    threshold = unread["conditions"][0]["conditionThreshold"]
    assert "subscription/oldest_unacked_message_age" in threshold["filter"]
    assert "domhouse-staging-ordini-vm" in threshold["filter"] and threshold["thresholdValue"] == 1200


# ---- code review of A3, point 7: an error after the transaction never loses the password ------------------------
def test_review_7_the_password_is_given_even_if_the_log_or_the_names_fail(world, monkeypatch):
    from bff import audit as audit_module

    async def broken(*a, **k):
        raise RuntimeError("Firestore non risponde")
    monkeypatch.setattr(audit_module, "record", broken)
    monkeypatch.setattr(get_repository(), "get_audit_people", broken)
    r = register()
    assert r.status_code == 201 and len(r.json()["password"]) == 32
    assert world.published and r.json()["credential"]["updated_by"] is None       # the order left all the same
    world.fail = True
    r = call("POST", f"{BASE}/shelly-1/revoca", json={"version": 1})
    assert r.status_code == 502 and r.json()["error"] == "agent_publish_failed"       # not a 500
