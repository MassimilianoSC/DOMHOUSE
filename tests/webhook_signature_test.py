"""D65 (P-83 review, gravity 4): a signature header with a byte outside ASCII (h11 accepts obs-text, Starlette reads it as
latin-1) made hmac.compare_digest raise TypeError: 500 and no line in the webhook register. Now it is a signature not
valid: 401 and its entry. Whether Google's front end lets such a byte through is to be verified; the BFF holds anyway."""
import asyncio
import dataclasses
import hashlib
import hmac
import json

import httpx
import pytest

from bff.config import get_settings
from bff.main import app
from bff.repository import get_repository
from bff.routes import webhooks

SECRET = "replace-me"
BODY = json.dumps({"event": "reservation.created", "reservation": {"id": "r-d65", "apartment_id": "IW-D65"}}).encode()


@pytest.fixture
def italianway(monkeypatch):
    monkeypatch.setattr(webhooks, "get_settings", lambda: dataclasses.replace(get_settings(), italianway_webhook_secret=SECRET))


def post(signature: bytes):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.post("/webhooks/italianway", content=BODY,
                                headers=[(b"Content-Type", b"application/json"), (b"X-Signature", signature)])
    return asyncio.run(go())


@pytest.mark.parametrize("signature", ["é" * 64, "sha256=" + "à" * 64, "ü"])
def test_a_signature_outside_ascii_is_not_valid(signature):
    assert webhooks.verify_signature(BODY, signature, SECRET) is False


def test_the_call_gets_401_and_its_entry(italianway):
    before = len(asyncio.run(get_repository().list_webhook_logs(None)))
    good = hmac.new(SECRET.encode(), BODY, hashlib.sha256).hexdigest()
    r = post(("é" + good[1:]).encode("latin-1"))
    assert r.status_code == 401 and r.json()["error"] == "invalid_signature"
    logs = asyncio.run(get_repository().list_webhook_logs(None))
    assert len(logs) == before + 1 and logs[0].signature_ok is False and logs[0].status_code == 401
