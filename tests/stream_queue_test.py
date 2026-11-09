"""D-198: each browser stream has a queue with a limit (STREAM_QUEUE_MAX). Full, that stream alone ends, with one log line
without personal data; the other browsers, the hooks and the connection to the engine carry on."""
import asyncio
import dataclasses
import json
import logging
import time
from types import SimpleNamespace

import pytest

from bff.auth import CurrentUser
from bff.config import get_settings
from bff.logs import JsonFormatter, ctx_user
from bff.repository import get_repository
from bff.routes import apartments
from bff.sse_hub import QUEUE_FULL, HubManager, InstanceHub, SseEvent, hub_manager

APT = "apt-rimini-01"


def event(n: int) -> SseEvent:
    return SseEvent(str(n), "device.state", "{}", time.monotonic())


def drained(q: asyncio.Queue) -> list:
    return [q.get_nowait() for _ in range(q.qsize())]


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


def test_a_full_queue_ends_that_stream_only(apt, lines):
    seen = []

    async def hook(_apt, ev):
        seen.append(ev.id)

    async def main():
        ctx_user.set("uid-di-una-persona")                   # the task's context may carry a user
        hub = InstanceHub(apt, [hook])
        slow, reading = asyncio.Queue(maxsize=2), asyncio.Queue()
        hub.subscribers |= {slow, reading}
        for n in range(3):
            await hub._publish(event(n))
        return hub, slow, reading
    hub, slow, reading = asyncio.run(main())
    assert drained(slow) == [QUEUE_FULL] and slow not in hub.subscribers       # what waited is dropped, only the signal
    assert [e.id for e in drained(reading)] == ["0", "1", "2"] and reading in hub.subscribers
    assert seen == ["0", "1", "2"]                                             # the hooks (pushes) carry on
    [line] = [x for x in lines if x["msg"] == "stream closed: too many events waiting"]
    assert line["level"] == "warning" and line["apartment_id"] == APT and line["limit"] == 2 and line["user"] is None
    assert "uid-di-una-persona" not in json.dumps(line)


def test_removing_an_apartment_also_ends_a_full_stream(apt):
    async def main():
        manager = HubManager()
        hub = manager.hub(apt)
        full = asyncio.Queue(maxsize=1)
        full.put_nowait(event(0))
        hub.subscribers.add(full)
        manager.drop(apt.apartment_id)
        return full
    assert drained(asyncio.run(main())) == [None]


def stream(apt, monkeypatch, limit, last_event_id=None, buffered=0, stream_max=240.0):
    """The real route, without the upstream connection: (the body, the hub, its queue)."""
    monkeypatch.setattr(apartments, "get_settings", lambda: dataclasses.replace(get_settings(), stream_queue_max=limit,
                                                                                stream_max_s=stream_max))
    monkeypatch.setattr(InstanceHub, "start", lambda self, last: None)
    hub = hub_manager.hub(apt)
    monkeypatch.setattr(hub, "hooks", [])
    monkeypatch.setattr(hub, "subscribers", set())
    monkeypatch.setattr(hub, "buffer", type(hub.buffer)(event(n) for n in range(buffered)))

    async def open_it():
        user = CurrentUser("dev-admin", "admin@demo.it", apt.tenant_id, "admin", "Amministratore")

        async def connected():
            return False
        request = SimpleNamespace(headers={"Last-Event-ID": last_event_id} if last_event_id else {}, is_disconnected=connected)
        response = await apartments.stream(APT, request, user=user)
        return response.body_iterator, hub
    return open_it


def test_the_route_gives_each_stream_a_limit_and_ends_it_cleanly(apt, monkeypatch):
    opened = stream(apt, monkeypatch, 3)

    async def main():
        body, hub = await opened()
        assert "connected" in await anext(body)
        assert next(iter(hub.subscribers)).maxsize == 3
        for n in range(4):
            await hub._publish(event(n))
        with pytest.raises(StopAsyncIteration):               # a normal end of the response, nothing raised
            await anext(body)
        return hub
    assert asyncio.run(main()).subscribers == set()


def test_a_replay_longer_than_the_limit_fits(apt, monkeypatch):
    opened = stream(apt, monkeypatch, 2, last_event_id="0", buffered=6)       # five events to replay, limit 2

    async def main():
        body, hub = await opened()
        await anext(body)
        return next(iter(hub.subscribers))
    queue = asyncio.run(main())
    assert queue.maxsize == 7 and [e.id for e in drained(queue)] == ["1", "2", "3", "4", "5"]


def test_a_stream_ends_by_itself_within_its_limit(apt, monkeypatch):
    """D-197 (E-27): a normal end of the response before Cloud Run cuts it, with no event and no ping needed."""
    opened = stream(apt, monkeypatch, 3, stream_max=0.05)

    async def main():
        body, hub = await opened()
        await anext(body)
        started = time.monotonic()
        with pytest.raises(StopAsyncIteration):
            await anext(body)
        return hub, time.monotonic() - started
    hub, took = asyncio.run(main())
    assert took < 1.0 and hub.subscribers == set()


def test_a_stream_full_of_events_ends_at_its_limit_too(apt, monkeypatch):
    opened = stream(apt, monkeypatch, 500, stream_max=0.05)

    async def main():
        body, hub = await opened()
        await anext(body)
        await asyncio.sleep(0.1)                                  # the time is up with an event waiting
        await hub._publish(event(1))
        with pytest.raises(StopAsyncIteration):
            await anext(body)
        return hub
    assert asyncio.run(main()).subscribers == set()


def test_a_browser_gone_before_the_first_step_leaves_nothing(apt, monkeypatch):
    opened = stream(apt, monkeypatch, 3)

    async def main():
        body, hub = await opened()
        assert hub.subscribers == set()                           # subscribed only when the response really starts
        await body.aclose()
        return hub
    assert asyncio.run(main()).subscribers == set()


def test_a_browser_gone_after_the_first_step_leaves_nothing(apt, monkeypatch):
    opened = stream(apt, monkeypatch, 3)

    async def main():
        body, hub = await opened()
        await anext(body)
        assert len(hub.subscribers) == 1
        await body.aclose()
        return hub
    assert asyncio.run(main()).subscribers == set()


def test_the_replay_buffer_has_a_limit_too(apt, monkeypatch):
    """D-198: an event costs about 800 bytes in memory: an hour of a busy apartment is megabytes, a storm has no limit."""
    from bff import sse_hub
    monkeypatch.setattr(sse_hub, "get_settings", lambda: dataclasses.replace(get_settings(), hub_buffer_max=3))
    hub = InstanceHub(apt, [])

    async def main():
        for n in range(5):
            await hub._publish(event(n))
    asyncio.run(main())
    assert [e.id for e in hub.buffer] == ["2", "3", "4"] and [e.id for e in hub.replay_after("3")] == ["4"]

