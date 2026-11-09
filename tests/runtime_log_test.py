"""D-198 (E-27): bff/runtime.py: the process's own lines in the log. Who it is, when it starts and stops, each stream with
why it ended, and every minute how busy it is; never a token, an email or a person."""
import asyncio
import json
import logging
import os
import signal
import time

import httpx
import pytest

from bff import instances, main, push, runtime, summary_job
from bff.logs import JsonFormatter, ctx_user
from bff.repository import get_repository
from bff.routes import apartments
from bff.sse_hub import hub_manager
from tests.stream_queue_test import APT, event, stream


@pytest.fixture
def apt():
    return asyncio.run(get_repository().get_apartment(APT))


@pytest.fixture
def lines():
    logger, got = logging.getLogger("bff"), []

    class Keep(logging.Handler):
        def emit(self, record):
            got.append(json.loads(JsonFormatter().format(record)))
    handler, level = Keep(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield got
    logger.removeHandler(handler)
    logger.setLevel(level)


def only(lines, message):
    found = [x for x in lines if x["msg"] == message]
    assert len(found) == 1, (message, found)
    return found[0]


def clean(line):
    """Nothing about a person: the fields a request's context would add are empty."""
    assert line["user"] is None and line["tenant_id"] is None and "@" not in json.dumps(line)


@pytest.fixture
def quiet_start(monkeypatch):
    async def nothing(*a, **k):
        return None
    monkeypatch.setattr(instances, "http", lambda: None)
    monkeypatch.setattr(main.webhooks, "report_demo_codes", nothing)
    monkeypatch.setattr(push, "start_background_hubs", nothing)
    monkeypatch.setattr(summary_job, "start", lambda: None)


def test_a_process_says_who_it_is_when_it_starts_and_stops(lines, quiet_start, monkeypatch):
    monkeypatch.setenv("K_REVISION", "domotica-bff-00099-abc")

    async def run_it():
        async with main.app.router.lifespan_context(main.app):
            pass
    asyncio.run(run_it())
    started, stopping = only(lines, "process started"), only(lines, "process stopping")
    assert started["boot_id"] == stopping["boot_id"] == runtime.BOOT_ID and len(runtime.BOOT_ID) == 8
    assert started["revision"] == "domotica-bff-00099-abc" and started["pid"] == os.getpid()
    assert stopping["uptime_s"] >= 0 and stopping["streams_open"] == 0
    clean(started)
    clean(stopping)


def test_sigterm_is_written_and_uvicorn_still_gets_it(lines, quiet_start):
    called = []
    before = signal.signal(signal.SIGTERM, lambda s, f: called.append(s))
    mine = signal.getsignal(signal.SIGTERM)

    async def run_it():
        async with main.app.router.lifespan_context(main.app):
            signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    try:
        asyncio.run(run_it())
        assert called == [signal.SIGTERM] and only(lines, "process got SIGTERM")["boot_id"] == runtime.BOOT_ID
        assert signal.getsignal(signal.SIGTERM) is mine                          # put back at the end
    finally:
        signal.signal(signal.SIGTERM, before)


def closed_line(lines, apartment=APT):
    line = only(lines, "stream closed")
    opened = only(lines, "stream opened")
    assert line["stream_id"] == opened["stream_id"] and len(line["stream_id"]) == 8 and line["boot_id"] == runtime.BOOT_ID
    assert line["apartment_id"] == apartment and line["seconds"] >= 0
    clean(line)
    clean(opened)
    return line


def run_with_person(coro):
    async def main_():
        ctx_user.set("uid-di-una-persona")
        return await coro
    return asyncio.run(main_())


def test_a_stream_at_its_limit(apt, lines, monkeypatch):
    opened = stream(apt, monkeypatch, 3, stream_max=0.05)

    async def go():
        body, _ = await opened()
        await anext(body)
        with pytest.raises(StopAsyncIteration):
            await anext(body)
    run_with_person(go())
    assert closed_line(lines)["reason"] == "max_duration" and not runtime._streams


def test_a_stream_with_a_full_queue(apt, lines, monkeypatch):
    opened = stream(apt, monkeypatch, 2)

    async def go():
        body, hub = await opened()
        await anext(body)
        for n in range(3):
            await hub._publish(event(n))
        with pytest.raises(StopAsyncIteration):
            await anext(body)
    run_with_person(go())
    assert closed_line(lines)["reason"] == "queue_full"


def test_a_browser_that_goes_away(apt, lines, monkeypatch):
    opened = stream(apt, monkeypatch, 3)

    async def go():
        body, _ = await opened()
        await anext(body)
        await body.aclose()
    run_with_person(go())
    assert closed_line(lines)["reason"] == "client_disconnect" and not runtime._streams


def test_a_stream_that_breaks(apt, lines, monkeypatch):
    opened = stream(apt, monkeypatch, 3)

    async def broken(*a):
        raise RuntimeError("guasto")
    monkeypatch.setattr(apartments, "_event", broken)

    async def go():
        body, hub = await opened()
        await anext(body)
        await hub._publish(event(1))
        with pytest.raises(RuntimeError):
            await anext(body)
    run_with_person(go())
    assert closed_line(lines)["reason"] == "error" and not runtime._streams


def test_the_status_line_measures_a_stalled_event_loop(lines):
    async def go():
        task = asyncio.create_task(runtime.status_loop(0.2, tick_s=0.02))
        await asyncio.sleep(0.05)
        time.sleep(0.15)                                                         # the event loop held
        await asyncio.sleep(0.3)
        task.cancel()
    asyncio.run(go())
    line = next(x for x in lines if x["msg"] == "process status")
    assert line["boot_id"] == runtime.BOOT_ID and line["loop_lag_ms"] >= 100 and line["user"] is None
    assert line["streams_open"] == 0 and line["requests_active"] == 0 and line["queue_max"] == 0


def test_the_status_line_says_the_longest_queue(apt, lines, monkeypatch):
    hub = hub_manager.hub(apt)
    monkeypatch.setattr(hub, "subscribers", {asyncio.Queue(), asyncio.Queue()})
    q = next(iter(hub.subscribers))
    for n in range(4):
        q.put_nowait(n)
    assert runtime._queue_max() == 4


def test_requests_are_counted_but_not_the_built_in_engine():
    seen = []

    async def inner(scope, receive, send):
        seen.append(runtime.requests_active())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})
    counter = runtime.RequestCounter(inner)

    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=counter), base_url="http://t") as c:
            await c.get("/app/me")
            await c.get("/mock/apt/api/v1/stream")
    asyncio.run(go())
    assert seen == [1, 0] and runtime.requests_active() == 0
    assert any(m.cls is runtime.RequestCounter for m in main.app.user_middleware)


def test_the_user_is_not_in_the_person_free_lines_even_inside_a_request(lines):
    async def go():
        ctx_user.set("uid-di-una-persona")
        stream_id = runtime.stream_opened(APT)
        runtime.stream_closed(stream_id, APT, "max_duration")
    asyncio.run(go())
    assert "uid-di-una-persona" not in json.dumps(lines)


@pytest.mark.skipif(os.name == "nt", reason="add_signal_handler esiste solo su Linux, dove gira il servizio")
def test_with_uvicorns_real_handler_both_see_sigterm(lines):
    """On Linux uvicorn 0.25 listens with loop.add_signal_handler before the application starts: the signal must reach it
    (its shutdown) and also our line."""
    async def go():
        loop = asyncio.get_running_loop()
        heard = asyncio.Event()
        loop.add_signal_handler(signal.SIGTERM, heard.set)        # what uvicorn does, before the lifespan
        put_back = runtime.watch_sigterm()
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.wait_for(heard.wait(), timeout=5)
        put_back()
        loop.remove_signal_handler(signal.SIGTERM)
    asyncio.run(go())
    assert only(lines, "process got SIGTERM")["boot_id"] == runtime.BOOT_ID

