"""F-2 (attack-from-outside review, 22 November 2026, serious): a huge JSON body was read and parsed before the
signature or the access check (Italianway webhook, /internal/ai/chat, every route with a typed body): a few large bodies
used up the 512 MiB of an instance. Now a size limit refuses it (413) BEFORE the body is read, on Content-Length and on
the bytes as they arrive; a deeply nested JSON gives 400 and its line in the webhook register, never a 500.
In-process, memory repository."""
import asyncio
import dataclasses
import hashlib
import hmac
import json

import httpx
import pytest

from bff import ai_gateway, body_limit
from bff.config import get_settings
from bff.main import app
from bff.repository import get_repository
from bff.routes import webhooks

SECRET = "replace-me"
BIG = b"[" + b"1," * (1024 * 1024) + b"1]"                     # about 2 MiB of valid JSON


def run(coro):
    return asyncio.run(coro)


async def _post(path, content, headers=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.post(path, content=content, headers={"Content-Type": "application/json", **(headers or {})})


async def _put(path, content):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.put(path, content=content, headers={"Content-Type": "application/json"})


def _pieces(data: bytes, size: int = 64 * 1024):
    async def gen():                                             # httpx sends no Content-Length for a stream
        for i in range(0, len(data), size):
            yield data[i:i + size]
    return gen()


@pytest.fixture
def italianway(monkeypatch):
    monkeypatch.setattr(webhooks, "get_settings", lambda: dataclasses.replace(get_settings(), italianway_webhook_secret=SECRET))


@pytest.fixture
def nothing_read(monkeypatch):
    """Whatever comes after the limit must not run: parsing, the register, the key check."""
    def boom(*_a, **_k):
        raise AssertionError("called after a body over the limit")

    async def aboom(*_a, **_k):
        boom()
    monkeypatch.setattr(webhooks, "_parse", boom)
    monkeypatch.setattr(get_repository(), "add_webhook_log", aboom)
    monkeypatch.setattr(ai_gateway, "authenticate", aboom)


def _logs():
    return run(get_repository().list_webhook_logs(None))


def _too_large(r):
    assert r.status_code == 413, (r.status_code, r.text[:200])
    assert r.json()["error"] == "payload_too_large"


# -------- (a) (b) the webhook: 413 before parsing, with and without Content-Length --------
def test_a_a_2_mib_webhook_is_refused_before_it_is_parsed(italianway, nothing_read):
    _too_large(run(_post("/webhooks/italianway", BIG)))


def test_b_the_same_body_in_pieces_without_content_length(italianway, nothing_read):
    _too_large(run(_post("/webhooks/italianway", _pieces(BIG))))


def test_the_webhook_limit_is_64_kib(italianway):
    assert body_limit.limit_for("/webhooks/italianway") == 64 * 1024
    over = b'{"event": "' + b"x" * (64 * 1024) + b'"}'
    _too_large(run(_post("/webhooks/italianway", over)))
    before = len(_logs())
    r = run(_post("/webhooks/italianway", b'{"event": "' + b"x" * 60_000 + b'"}'))   # under it: the usual 401
    assert r.status_code == 401 and len(_logs()) == before + 1


# -------- (c) a typed body without a token: 413 before the access check --------
def test_c_a_2_mib_body_without_token_is_refused_before_the_access(nothing_read):
    _too_large(run(_put("/app/me/notification-prefs", BIG)))
    _too_large(run(_put("/app/me/notification-prefs", _pieces(BIG))))


def test_the_engines_way_to_the_model_too(nothing_read):
    assert body_limit.limit_for("/internal/ai/chat") == 256 * 1024
    _too_large(run(_post("/internal/ai/chat", BIG, {"X-Apartment-Id": "apt-1", "X-API-Key": "x"})))


def test_the_ai_key_is_checked_before_the_body_is_parsed(monkeypatch):
    """F-2: /internal/ai/chat parsed `body: dict = Body(...)` before the key; now the key first, then the JSON."""
    def boom(*_a, **_k):
        raise AssertionError("parsed before the key")
    monkeypatch.setattr(json, "loads", boom)
    r = run(_post("/internal/ai/chat", b'{"messages": [{"role": "user", "content": "x"}]}',
                  {"X-Apartment-Id": "apt-che-non-esiste", "X-API-Key": "x"}))
    assert r.status_code in (401, 404)


# -------- (d) nested JSON: 400 and its line, never a 500 --------
def _signed(raw):
    return {"X-Signature": hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()}


@pytest.mark.parametrize("raw", [
    b"[" * 5000 + b"]" * 5000,                                   # json.loads gives RecursionError
    b'{"a":' * 5000 + b"1" + b"}" * 5000,
    b'{"a":' * 1200 + b"1" + b"}" * 1200,                        # json.loads passes, the obscuring recursed to death
], ids=["list-5000", "dict-5000", "dict-1200"])
def test_d_a_signed_nested_json_gives_400_and_its_line(italianway, raw):
    before = len(_logs())
    r = run(_post("/webhooks/italianway", raw, _signed(raw)))
    assert r.status_code == 400 and r.json()["error"] == "bad_request", (r.status_code, r.text[:200])
    logs = _logs()
    assert len(logs) == before + 1 and logs[0].status_code == 400 and logs[0].signature_ok is True
    assert logs[0].raw_body == f"[corpo non JSON, {len(raw)} byte]"


def test_an_unsigned_nested_json_gives_401_and_its_line(italianway):
    raw = b'{"a":' * 1200 + b"1" + b"}" * 1200
    before = len(_logs())
    r = run(_post("/webhooks/italianway", raw, {"X-Signature": "sbagliata"}))
    assert r.status_code == 401
    assert len(_logs()) == before + 1


# -------- the middleware itself, pure ASGI --------
def _scope(path, headers=()):
    return {"type": "http", "method": "POST", "path": path, "headers": list(headers), "query_string": b""}


def test_in_pieces_it_stops_reading_at_the_limit_and_never_calls_the_app():
    called, reads, sent = [], [], []

    async def inner(scope, receive, send):
        called.append(True)

    async def receive():
        reads.append(1)
        return {"type": "http.request", "body": b"x" * 1024, "more_body": True}   # an endless body

    async def send(message):
        sent.append(message)
    run(body_limit.BodyLimit(inner)(_scope("/app/me"), receive, send))
    assert called == [] and sent[0]["status"] == 413
    assert len(reads) == body_limit.DEFAULT_LIMIT // 1024 + 1                    # one piece past the limit, no more


def test_a_declared_length_over_the_limit_is_refused_without_reading():
    reads, sent = [], []

    async def receive():
        reads.append(1)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)
    headers = [(b"content-length", str(64 * 1024 + 1).encode())]
    run(body_limit.BodyLimit(lambda *a: None)(_scope("/webhooks/italianway", headers), receive, send))
    assert reads == [] and sent[0]["status"] == 413


def test_under_the_limit_the_app_gets_the_whole_body_then_the_disconnect():
    pieces = [{"type": "http.request", "body": b"ab", "more_body": True},
              {"type": "http.request", "body": b"cd", "more_body": False},
              {"type": "http.disconnect"}]
    got = []

    async def inner(scope, receive, send):
        got.append(await receive())
        got.append(await receive())

    async def receive():
        return pieces.pop(0)
    run(body_limit.BodyLimit(inner)(_scope("/app/me"), receive, None))
    assert got == [{"type": "http.request", "body": b"abcd", "more_body": False}, {"type": "http.disconnect"}]


def test_the_root_path_prefix_counts_for_the_webhook_limit():
    assert body_limit.limit_for("/api/webhooks/italianway", "/api") == 64 * 1024
    assert body_limit.limit_for("/api/app/me", "/api") == body_limit.DEFAULT_LIMIT == 256 * 1024
