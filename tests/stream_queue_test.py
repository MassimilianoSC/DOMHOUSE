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


def stream(apt, monkeypatch, limit, last_event_id=None, buffered=0):
    """The real route, without the upstream connection: (the body, the hub, its queue)."""
    monkeypatch.setattr(apartments, "get_settings", lambda: dataclasses.replace(get_settings(), stream_queue_max=limit))
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
        return response.body_iterator, hub, next(iter(hub.subscribers))
    return open_it


def test_the_route_gives_each_stream_a_limit_and_ends_it_cleanly(apt, monkeypatch):
    opened = stream(apt, monkeypatch, 3)

    async def main():
        body, hub, queue = await opened()
        assert queue.maxsize == 3 and "connected" in await anext(body)
        for n in range(4):
            await hub._publish(event(n))
        with pytest.raises(StopAsyncIteration):               # a normal end of the response, nothing raised
            await anext(body)
        return hub
    assert asyncio.run(main()).subscribers == set()


def test_a_replay_longer_than_the_limit_fits(apt, monkeypatch):
    opened = stream(apt, monkeypatch, 2, last_event_id="0", buffered=6)       # five events to replay, limit 2

    async def main():
        _, _, queue = await opened()
        return queue
    queue = asyncio.run(main())
    assert queue.maxsize == 7 and [e.id for e in drained(queue)] == ["1", "2", "3", "4", "5"]
