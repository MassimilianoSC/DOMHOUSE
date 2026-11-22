"""F-5 (attack-from-outside review, 22 November 2026, medium): every unsigned call to POST /webhooks/italianway wrote a
row in the webhook register (about 23 Firestore operations: one write, the read of its «room» of about 21 documents, at
least one deletion), plus a warn line and CPU, with no limit: a script cost money without end, and its rows pushed out
of the platform's 20 «unsigned» rows a real signature error of Italianway. Now at most UNSIGNED_ROWS_PER_MINUTE unsigned
calls a minute (per instance) get their row and their warn line; the others get the same 401 with nothing written and
nothing parsed, and one warn line a minute counts them. Signed calls are never limited. In-process, memory repository."""
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


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def italianway(monkeypatch):
    monkeypatch.setattr(webhooks, "get_settings", lambda: dataclasses.replace(get_settings(), italianway_webhook_secret=SECRET))
    clock = [6000.0]
    monkeypatch.setattr(webhooks, "_clock", lambda: clock[0], raising=False)
    getattr(webhooks, "_unsigned", {}).clear()
    writes = []
    repo = get_repository()
    real = repo.add_webhook_log

    async def counted(log):
        writes.append(log)
        return await real(log)
    monkeypatch.setattr(repo, "add_webhook_log", counted)
    kept = list(repo.webhook_logs)
    yield clock, writes
    repo.webhook_logs[:] = kept                       # the bursts' rows leave the register to the other tests


def post(raw: bytes, signed: bool):
    headers = {"Content-Type": "application/json",
               "X-Signature": hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest() if signed else "sbagliata"}

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return [await c.post("/webhooks/italianway", content=raw, headers=headers)]
    return run(go())[0]


def burst(n: int):
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return [await c.post("/webhooks/italianway", content=json.dumps({"event": f"finto-{i}"}).encode(),
                                 headers={"Content-Type": "application/json", "X-Signature": "sbagliata"})
                    for i in range(n)]
    return run(go())


def test_100_unsigned_calls_write_at_most_the_limit_and_a_signed_one_after_is_kept(italianway):
    clock, writes = italianway
    answers = burst(100)
    assert all(r.status_code == 401 and r.json()["error"] == "invalid_signature" for r in answers)
    assert 1 <= len(writes) <= getattr(webhooks, "UNSIGNED_ROWS_PER_MINUTE", 10) <= 10
    raw = json.dumps({"event": "reservation.created", "id": "iw-f5", "reservation": {"id": "RES-F5",
                                                                                   "apartment_id": "IW-F5-NESSUNO"}}).encode()
    before = len(writes)
    assert post(raw, signed=True).status_code == 404                  # signed: always its row (unknown apartment here)
    assert len(writes) == before + 1 and writes[-1].signature_ok is True


def test_the_next_minute_gets_its_rows_again_and_one_line_counts_the_skipped(italianway, monkeypatch):
    clock, writes = italianway
    seen = []
    monkeypatch.setattr(webhooks, "warn", lambda msg, **kw: seen.append((msg, kw)))
    burst(30)
    first = len(writes)
    assert first == getattr(webhooks, "UNSIGNED_ROWS_PER_MINUTE", 10)
    assert sum(1 for m, _ in seen if m == "webhook signature rejected") == first      # one warn per row, not per call
    clock[0] += 60
    burst(1)
    assert len(writes) == first + 1
    summary = [kw for m, kw in seen if m == "webhook unsigned calls not logged"]
    assert summary == [{"source": "italianway", "calls": 30 - first}]


def test_a_skipped_unsigned_call_is_not_even_parsed(italianway, monkeypatch):
    burst(getattr(webhooks, "UNSIGNED_ROWS_PER_MINUTE", 10))

    def boom(_raw):
        raise AssertionError("parsed")
    monkeypatch.setattr(webhooks, "_read", boom)
    assert burst(5)[-1].status_code == 401
