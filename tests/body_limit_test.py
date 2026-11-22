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


def _over_the_limit_on(path, declared: bool, monkeypatch):
    """A body over the limit on `path`, with or without Content-Length: what was sent, how many pieces were read,
    whether the app ran, and the warn lines."""
    called, reads, sent, lines = [], [], [], []

    async def inner(scope, receive, send):
        called.append(True)

    async def receive():
        reads.append(1)
        return {"type": "http.request", "body": b"x" * 1024, "more_body": True}   # an endless body

    async def send(message):
        sent.append(message)
    monkeypatch.setattr(body_limit, "warn", lambda msg, **fields: lines.append((msg, fields)))
    headers = [(b"content-length", str(160 * 1024).encode())] if declared else []
    run(body_limit.BodyLimit(inner, root_path="/api")(_scope(path, headers), receive, send))
    return sent, reads, called, lines


@pytest.mark.parametrize("declared", [True, False], ids=["content-length", "pieces"])
def test_r2_a_pubsub_push_over_the_limit_is_acknowledged_204_unread_and_logged(declared, monkeypatch):
    """Rereading R2 (agent_server_test::test_r2, the committente's full run of 22 November): Pub/Sub delivers again a
    push that does not get a 2xx, forever. So on /internal/agent/risultati a body over the limit is acknowledged with 204,
    never given to the app, read no further than the limit, and a warn line says so; every other path stays 413."""
    for path in ("/internal/agent/risultati", "/api/internal/agent/risultati"):
        sent, reads, called, lines = _over_the_limit_on(path, declared, monkeypatch)
        assert sent[0]["status"] == 204 and called == [], path
        assert reads == ([] if declared else [1] * (body_limit.DEFAULT_LIMIT // 1024 + 1)), path
        assert lines == [("agent result ignored", {"reason": "troppo_grande"})], path
    for path in ("/internal/agent/risultati-altro", "/internal/agent", "/app/me"):
        sent, _reads, called, lines = _over_the_limit_on(path, declared, monkeypatch)
        assert sent[0]["status"] == 413 and called == [] and lines == [], path


def test_the_root_path_prefix_counts_for_the_webhook_limit():
    assert body_limit.limit_for("/api/webhooks/italianway", "/api") == 64 * 1024
    assert body_limit.limit_for("/api/app/me", "/api") == body_limit.DEFAULT_LIMIT


def test_p1_a_body_in_drops_of_2_bytes_costs_about_its_size():
    """Rereading P-1: the pieces were kept in a list and joined at the end: a body sent 2 bytes at a time cost about
    21 times its size (a bytes object and its list entry per piece). Now one growing buffer."""
    import tracemalloc
    size = 60 * 1024                                              # under every limit
    left = [size // 2]
    got = []

    async def receive():
        left[0] -= 1
        piece = (left[0] % 65536).to_bytes(2, "big")              # a new object every time, as from the socket
        return {"type": "http.request", "body": piece, "more_body": left[0] > 0}

    async def inner(scope, receive_, send):
        got.append(len((await receive_())["body"]))

    tracemalloc.start()
    try:
        run(body_limit.BodyLimit(inner)(_scope("/app/me"), receive, None))
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert got == [size]
    assert peak < 4 * size, f"peak {peak} bytes for a body of {size}"


def test_a_declared_length_that_is_not_ascii_digits_is_refused_not_an_error():
    """Rereading, minor note: «²» passes str.isdigit() and breaks int(); h11 refuses it first, the middleware too."""
    sent = []

    async def send(message):
        sent.append(message)
    for value in ("²", "1²", " 12 x", "-1"):
        sent.clear()
        run(body_limit.BodyLimit(lambda *a: None)(_scope("/app/me", [(b"content-length", value.encode("latin-1"))]), None, send))
        assert sent[0]["status"] == 413, value


def test_p2_the_app_routes_parse_at_most_64_kib_before_the_access():
    """Rereading P-2: under 256 KiB a typed body of /app/* was still parsed before the access check (256 KiB of [{},…]
    about 6 MiB and 30 ms of CPU, without an account). The largest legitimate bodies, measured on 22 November: the
    assistant's request for 200 devices about 77 KiB (its own 256 KiB), every rule changed 0.7 KiB, a copy to 100
    apartments 7.5 KiB."""
    assert body_limit.DEFAULT_LIMIT == 64 * 1024
    for path in ("/app/me/notification-prefs", "/app/apartments/a/instance/rules", "/app/apartments/a/rules/copy",
                 "/internal/agent/risultati"):
        assert body_limit.limit_for(path) == 64 * 1024, path
    assert body_limit.limit_for("/internal/ai/chat") == 256 * 1024
    many = b"[" + b"{}," * 30_000 + b"{}]"                       # about 90 KiB
    _too_large(run(_put("/app/me/notification-prefs", many)))


# -------- rereading P-8: the largest legitimate body through the whole app, and a stream through the filter --------
def _request_of_200_devices(monkeypatch) -> dict:
    """The engine's own request to the model (scripts/measure_model.py, D-182) for an apartment of 200 devices, the
    agent's MAX_DEVICES, with long Italian names and 10 recent decisions with long reasons (the measure of P-4)."""
    import copy
    import sys
    import uuid
    from pathlib import Path
    from engine.connector import simulated
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    import measure_model
    real = simulated.seed_devices

    def big(variant):
        _rooms, devices = real(variant)
        rooms = [{"room_id": f"stanza-{i:02d}", "name": f"Càmera da lètto n. {i:02d} lato giardino è più"} for i in range(20)]
        out = {}
        for i in range(200):
            d = copy.deepcopy(list(devices.values())[i % len(devices)])
            d["device_id"], d["room_id"] = f"{d['device_id']}-{i:03d}", f"stanza-{i % 20:02d}"
            d["label"] = f"Climatizzatore à parete della càmera matrimoniale più grande è {i:03d}"[:60]
            out[d["device_id"]] = d
        return rooms, out
    monkeypatch.setattr(simulated, "seed_devices", big)
    e = measure_model.measure_engine()
    assert len(e.devices) == 200
    why = ("Finestra della càmera matrimoniale aperta da più di 5 minuti con il climatizzatore acceso: spento per non "
           "sprecare energia, si riaccende quando la finestra è chiusa")
    for dev in list(e.devices)[:10]:
        e.log("rule:window_open_off", {"type": "device", "device_id": dev}, "turn_off", "on", "off", why, "applied",
              str(uuid.uuid4()), emit=False)
    messages, _tools = measure_model.request_messages("Che temperatura c'è nella càmera più grande?", e)
    return {"messages": messages, "temperature": 0.2}


def test_p8a_the_largest_legitimate_body_crosses_the_whole_app(monkeypatch):
    sent = []

    async def fake(body):
        sent.append(body)
        return {"choices": [{"message": {"role": "assistant", "content": "Ciao"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
    monkeypatch.setattr(ai_gateway, "call_model", fake)
    monkeypatch.setattr(ai_gateway, "_reasoning_refused", False)
    get_repository().ai_usage = {}
    body = json.dumps(_request_of_200_devices(monkeypatch)).encode()          # ASCII-escaped with spaces: the largest
    assert 60 * 1024 < len(body) < body_limit.AI_CHAT_LIMIT / 3, len(body)     # P-4: more than 3 times of margin
    r = run(_post("/internal/ai/chat", body, {"X-Apartment-Id": "apt-bologna-01",
                                                 "X-API-Key": get_settings().instance_api_key_fallback}))
    assert r.status_code == 200, r.text[:200]
    assert sent[0]["messages"] == json.loads(body)["messages"]                 # arrived whole
    r = run(_post("/internal/ai/chat", _pieces(body, 1024), {"X-Apartment-Id": "apt-bologna-01",
                                                              "X-API-Key": get_settings().instance_api_key_fallback}))
    assert r.status_code == 200 and sent[1]["messages"] == sent[0]["messages"]   # in pieces too


def test_p8b_a_stream_opens_streams_and_ends_through_the_filter(monkeypatch):
    """The SSE stream of the app through the whole middleware chain, raw ASGI: 200 text/event-stream, «connected»,
    an event published after it, and the end when the browser goes away (the disconnect passed on after the body)."""
    from bff.sse_hub import InstanceHub, SseEvent, hub_manager
    import time as clock
    monkeypatch.setattr(InstanceHub, "start", lambda self, last: None)
    apt = run(get_repository().get_apartment("apt-rimini-01"))

    async def main():
        hub = hub_manager.hub(apt)
        gone = asyncio.Event()
        messages, given = [], []

        async def receive():
            if not given:
                given.append(True)
                return {"type": "http.request", "body": b"", "more_body": False}
            await gone.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http",
                 "path": "/app/apartments/apt-rimini-01/stream", "raw_path": b"/app/apartments/apt-rimini-01/stream",
                 "root_path": "", "query_string": b"", "server": ("t", 80), "client": ("127.0.0.1", 1),
                 "headers": [(b"host", b"t"), (b"x-dev-user", b"admin@demo.it")]}
        task = asyncio.create_task(app(scope, receive, send))

        def body():
            return b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        for _ in range(200):
            if b"connected" in body():
                break
            await asyncio.sleep(0.01)
        start = next(m for m in messages if m["type"] == "http.response.start")
        headers = {k.decode(): v.decode() for k, v in start["headers"]}
        assert start["status"] == 200 and headers["content-type"].startswith("text/event-stream")
        assert headers.get("cache-control") != "no-store"                         # the stream keeps its own
        await hub._publish(SseEvent("p8b-1", "device.state", '{"p8b": true}', clock.monotonic()))
        for _ in range(200):
            if b"p8b" in body():
                break
            await asyncio.sleep(0.01)
        assert b'"p8b": true' in body() or b'"p8b":true' in body()
        gone.set()
        await asyncio.wait_for(task, 5)                                           # ended by the disconnect
    run(main())
