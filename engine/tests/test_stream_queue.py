"""D-198: the engine's stream has a queue with a limit (STREAM_QUEUE_MAX). Full, that stream alone ends; the reader, the
BFF, reconnects from its last event and loses nothing."""
import asyncio
from types import SimpleNamespace

import pytest

from engine import core
from engine.api import create_contract_app
from engine.config import ConfigError, load_config
from engine.connector.simulated import SimulatedConnector

BASE = {"APARTMENT_ID": "apt-prova-01", "API_KEY": "k" * 16, "CONNECTOR": "simulated"}


def engine(limit=1000):
    return core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, settings={"STREAM_QUEUE_MAX": limit})


def drained(q):
    return [q.get_nowait() for _ in range(q.qsize())]


def test_the_setting_has_a_default_and_limits():
    assert load_config(BASE).settings["STREAM_QUEUE_MAX"] == 1000
    with pytest.raises(ConfigError, match="STREAM_QUEUE_MAX"):
        load_config({**BASE, "STREAM_QUEUE_MAX": "1"})


def test_a_full_queue_ends_that_reader_only():
    async def main():
        e = engine()
        slow, reading = asyncio.Queue(maxsize=1), asyncio.Queue()
        e.subscribers |= {slow, reading}
        for n in range(3):
            e.emit("device.online", {"device_id": str(n)}, None)
        return e, slow, reading
    e, slow, reading = asyncio.run(main())
    assert drained(slow) == [core.QUEUE_FULL] and slow not in e.subscribers
    assert len(drained(reading)) == 3 and reading in e.subscribers


def every_route(routes):
    """The routes one by one: from FastAPI 0.16x (D58) include_router keeps the router whole (original_router)."""
    for r in routes:
        inner = getattr(r, "original_router", None)
        yield from every_route(inner.routes) if inner is not None else (r,)


def stream_route(e):
    app = create_contract_app(lambda apartment_id: e, "k" * 16, features=core.ALL_FEATURES, simulated=True,
                              implementation={"name": "prova", "version": "0"}, ping_seconds=5)
    return next(r for r in every_route(app.routes) if getattr(r, "path", "").endswith("/stream")).endpoint


def request(last_id=None):
    async def connected():
        return False
    return SimpleNamespace(headers={"Last-Event-ID": last_id} if last_id else {}, is_disconnected=connected)


def test_the_stream_has_the_limit_and_ends_normally():
    async def main():
        e = engine(limit=2)
        response = await stream_route(e)(request(), apartment_id="apt-prova-01")
        body = response.body_iterator
        queue = next(iter(e.subscribers))
        assert queue.maxsize == 2 and "connected" in await anext(body)
        for n in range(3):
            e.emit("device.online", {"device_id": str(n)}, None)
        with pytest.raises(StopAsyncIteration):
            await anext(body)
        return e
    assert asyncio.run(main()).subscribers == set()


def test_a_replay_longer_than_the_limit_fits():
    async def main():
        e = engine(limit=1)
        first = e.emit("device.online", {"device_id": "0"}, None)
        for n in range(1, 4):
            e.emit("device.online", {"device_id": str(n)}, None)
        await stream_route(e)(request(first["id"]), apartment_id="apt-prova-01")
        return next(iter(e.subscribers))
    queue = asyncio.run(main())
    assert queue.maxsize == 4 and len(drained(queue)) == 3
