"""P-51 (D-90, Fable): what each role receives. In-process, memory repository: guests' data in Italianway calls, secret
names, free texts of the engine, fields nobody uses."""
import asyncio
import dataclasses
import hashlib
import hmac
import json

import httpx
import pytest

from bff import actors, instances
from bff.auth import CurrentUser
from bff.config import get_settings
from bff.main import app
from bff.repository import Apartment, ExternalIds, Tenant, User, get_repository
from bff.routes import admin, webhooks

SECRET = "replace-me"
GUEST = {"first_name": "Giulia", "last_name": "Bianchi", "email": "giulia.bianchi@ospite.it", "phone": "+39 333 1234567",
         "document": "AX1234567", "notes": "Arrivo tardi, chiamare il 3331234567"}
PERSONAL = ("Giulia", "Bianchi", "giulia.bianchi@ospite.it", "333", "AX1234567", "Arrivo tardi")


def run(coro):
    return asyncio.run(coro)


def post_webhook(raw: bytes, signed: bool = True):
    headers = {"Content-Type": "application/json"}
    if signed:
        headers["X-Signature"] = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.post("/webhooks/italianway", content=raw, headers=headers)
    return run(go())


@pytest.fixture
def italianway(monkeypatch):
    monkeypatch.setattr(webhooks, "get_settings", lambda: dataclasses.replace(get_settings(), italianway_webhook_secret=SECRET))


def _last_log(tenant_id):
    return run(get_repository().list_webhook_logs(tenant_id))[0]


# -------- 4: guests' data are never kept --------
def test_guest_data_never_stored_structured_fields_kept(italianway):
    payload = {"event": "reservation.created", "id": "iw-ev-guest-1", "sent_at": "2026-11-01T10:00:00Z",
               "reservation": {"id": "RES-G1", "apartment_id": "IW-SCONOSCIUTO", "checkin": "2026-12-01T15:00:00Z",
                               "checkout": "2026-12-03T10:00:00Z", "guests": 2, "guest": GUEST}}
    assert post_webhook(json.dumps(payload).encode()).status_code == 404          # unattributed: kept for the platform
    log = _last_log(None)
    assert not any(p in log.raw_body for p in PERSONAL), log.raw_body
    assert json.loads(log.raw_body)["reservation"]["guest"]["email"] == "[oscurato]"
    assert json.loads(log.raw_body)["reservation"]["checkin"] == "2026-12-01T15:00:00Z"
    assert (log.event_type, log.external_id, log.checkin_at, log.checkout_at, log.guests) == (
        "reservation.created", "IW-SCONOSCIUTO", "2026-12-01T15:00:00Z", "2026-12-03T10:00:00Z", 2)


def test_unauthenticated_and_non_json_calls_are_obscured_too(italianway):
    payload = {"event": "reservation.created", "reservation": {"guest": GUEST}}
    assert post_webhook(json.dumps(payload).encode(), signed=False).status_code == 401
    assert not any(p in _last_log(None).raw_body for p in PERSONAL)
    assert post_webhook(b"Giulia Bianchi giulia.bianchi@ospite.it", signed=False).status_code == 401
    assert _last_log(None).raw_body == "[corpo non JSON, 39 byte]"


# -------- 1: secret names only for the platform --------
def test_admin_never_reads_secret_names(monkeypatch):
    from google.api_core import exceptions

    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-sec", name="Segreti")))
    run(repo.upsert_apartment(Apartment(apartment_id="apt-sec-1", tenant_id="t-sec", name="S", instance_url="http://10.198.0.2:8155")))
    real = dataclasses.replace(get_settings(), instance_mode="real")
    monkeypatch.setattr(instances, "get_settings", lambda: real)

    def refuse(name):
        raise exceptions.NotFound(name)
    monkeypatch.setattr(instances, "_read_secret", refuse)
    instances._secret_cache.clear()
    me = CurrentUser("u-sec", "a@sec.it", "t-sec", "admin")
    out = run(admin.verify_apartment("apt-sec-1", me))
    assert out["error"] == "Chiave del sistema domotico non configurata: contatta l'assistenza HQE"
    row = next(a for a in run(admin.list_apartments(me)) if a["apartment_id"] == "apt-sec-1")
    assert "langbrain" not in json.dumps(row) and row["last_check"]["error"] == out["error"]
    from bff.routes import platform
    prow = next(a for a in run(platform.list_tenant_apartments("t-sec")) if a["apartment_id"] == "apt-sec-1")
    assert "langbrain-api-key-apt-sec-1" in prow["last_check"]["error"]             # the platform keeps the detail


def test_secret_name_refusal_does_not_explain_the_naming_scheme():
    r = admin._secret_name_refused("qualcosa")
    assert r.status_code == 422 and b"langbrain" not in r.body and b"identificativo" not in r.body


# -------- 6: pseudonyms in the engine's free texts --------
def test_pseudonyms_in_free_texts_are_rewritten():
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-txt", name="Testi")))
    run(repo.upsert_user(User(uid="u-txt", email="carla@testi.it", tenant_id="t-txt", role="operator")))
    actors._resolved.clear()
    carla = run(actors.actor_for("u-txt", "carla@testi.it"))
    gone = actors.new_ref()
    payload = {"items": [{"reasoning": f"Richiesto da {carla} alle 10", "description": f"Proposta di {gone}",
                          "reason": carla, "note": f"ok {carla}", "answer": f"{carla} e {gone}", "other": carla}]}
    out = run(actors.rewrite(payload, "t-txt"))["items"][0]
    assert out["reasoning"] == "Richiesto da carla@testi.it alle 10"
    assert out["description"] == "Proposta di utente rimosso"
    assert out["reason"] == "carla@testi.it" and out["note"] == "ok carla@testi.it"
    assert out["answer"] == "carla@testi.it e utente rimosso"
    assert out["other"] == carla                                                    # only the known text fields


# -------- 5: fields nobody uses --------
def test_unused_fields_are_gone():
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-f", name="Campi")))
    run(repo.upsert_apartment(Apartment(apartment_id="apt-f-1", tenant_id="t-f", name="F", instance_url="mock://builtin",
                                        external_ids=ExternalIds(italianway="IW-F"))))
    row = next(a for a in run(admin.list_apartments(CurrentUser("u-f", "f@f.it", "t-f", "admin"))))
    assert not {"tenant_id", "created_at", "external_ids"} & set(row) and row["italianway_id"] == "IW-F"
    health = {"status": "ok", "connector": {"status": "up"}, "devices": [1], "uptime_s": 9, "database": "ok",
              "checked_at": "x", "apartment_id": "apt-f-1", "implementation": {"name": "n"}}
    assert set(instances.health_out(health)) == {"status", "connector", "implementation"}
