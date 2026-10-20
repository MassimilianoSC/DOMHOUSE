"""P-36 S2 in-process: a webhook whose Italianway code matches several apartments (old data; the admin API now refuses
duplicates) is refused, never routed to the first match, which could belong to another organisation."""
import asyncio
import dataclasses
import hashlib
import hmac
import json

import httpx

from bff.config import get_settings
from bff.main import app
from bff.repository import Apartment, ExternalIds, get_repository
from bff.routes import webhooks

SECRET = "replace-me"


def test_ambiguous_code_is_refused(monkeypatch):
    monkeypatch.setattr(webhooks, "get_settings", lambda: dataclasses.replace(get_settings(), italianway_webhook_secret=SECRET))

    async def scenario():
        repo = get_repository()
        for apt_id, tenant in (("apt-dup-a", "t-dup-1"), ("apt-dup-b", "t-dup-2")):
            await repo.upsert_apartment(Apartment(apartment_id=apt_id, tenant_id=tenant, name=apt_id, instance_url="mock://builtin",
                                                  external_ids=ExternalIds(italianway="IW-DUP-1")))
        raw = json.dumps({"event": "reservation.created", "id": "iw-ev-dup-1", "sent_at": "2026-11-01T10:00:00Z",
                          "reservation": {"id": "RES-DUP", "apartment_id": "IW-DUP-1", "checkin": "2026-12-01T15:00:00Z",
                                          "checkout": "2026-12-03T10:00:00Z", "guests": 2}}).encode()
        sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/webhooks/italianway", content=raw, headers={"X-Signature": sig, "Content-Type": "application/json"})
        assert r.status_code == 409 and r.json()["error"] == "ambiguous_apartment"
        for apt_id in ("apt-dup-a", "apt-dup-b"):                                    # booked for nobody
            assert await repo.list_bookings(apt_id) == []
    asyncio.run(scenario())
