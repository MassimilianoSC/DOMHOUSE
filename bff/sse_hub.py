"""One upstream SSE connection per instance, fanned out to browser subscribers."""
import asyncio
import contextvars
import json
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from . import instances
from .config import get_settings
from .logs import info, warn
from .repository import Apartment

BUFFER_SECONDS = 3600
QUEUE_FULL = object()        # D-198: in a browser's queue, this browser stopped reading: end its stream (None: the apartment went)


def _end_stream(q: asyncio.Queue, signal) -> None:
    """What was waiting is dropped and only the signal stays: the browser reopens the stream and reloads."""
    while not q.empty():
        q.get_nowait()
    q.put_nowait(signal)


@dataclass
class SseEvent:
    id: str | None
    event: str
    data: str
    received: float

    def encode(self) -> str:
        lines = []
        if self.id is not None:
            lines.append(f"id: {self.id}")
        lines.append(f"event: {self.event}")
        for chunk in self.data.split("\n"):
            lines.append(f"data: {chunk}")
        return "\n".join(lines) + "\n\n"


EventHook = Callable[[Apartment, SseEvent], Awaitable[None]]


def link_of(apt: Apartment) -> tuple:
    """What a connection to the engine depends on: when it changes the connection has to be made again."""
    return apt.instance_url, apt.port, apt.instance_secret_name


async def parse_sse(lines) -> "asyncio.AsyncIterator[SseEvent]":
    ev_id, ev_type, data = None, "message", []
    async for line in lines:
        if line == "":
            if data:
                yield SseEvent(ev_id, ev_type, "\n".join(data), time.monotonic())
            ev_id, ev_type, data = None, "message", []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "id":
            ev_id = value
        elif field == "event":
            ev_type = value
        elif field == "data":
            data.append(value)


class InstanceHub:
    def __init__(self, apt: Apartment, hooks: list[EventHook]):
        self.apt = apt
        self.hooks = hooks
        # D-198: an hour at most, and a number at most: 60 events a minute are 3 MB per apartment, and a storm has no limit
        self.buffer: deque[SseEvent] = deque(maxlen=get_settings().hub_buffer_max)
        self.subscribers: set[asyncio.Queue] = set()
        self.last_id: str | None = None
        self.connected = False
        self.task: asyncio.Task | None = None
        self.link: tuple | None = None               # the link the running task is connected to (push.align_hubs_once)

    def start(self, last_event_id: str | None) -> None:
        if self.task is None or self.task.done():
            if self.last_id is None:
                self.last_id = last_event_id
            self.task = asyncio.create_task(self._run())

    def _trim(self) -> None:
        cutoff = time.monotonic() - BUFFER_SECONDS
        while self.buffer and self.buffer[0].received < cutoff:
            self.buffer.popleft()

    def replay_after(self, last_event_id: str | None) -> list[SseEvent]:
        if not last_event_id:
            return []
        ids = [e.id for e in self.buffer]
        if last_event_id in ids:
            return list(self.buffer)[ids.index(last_event_id) + 1:]
        try:
            n = int(last_event_id)
            return [e for e in self.buffer if e.id is not None and e.id.isdigit() and int(e.id) > n]
        except ValueError:
            return []

    async def _publish(self, ev: SseEvent) -> None:
        self.buffer.append(ev)
        self._trim()
        if ev.id is not None:
            self.last_id = ev.id
        for q in list(self.subscribers):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:                # one browser not reading: never the others, nor the upstream
                self.subscribers.discard(q)
                _end_stream(q, QUEUE_FULL)
                # an empty context: this task's may carry the user of the request that started the hub
                contextvars.Context().run(warn, "stream closed: too many events waiting",
                                          apartment_id=self.apt.apartment_id, limit=q.maxsize)
        for hook in self.hooks:
            try:
                await hook(self.apt, ev)
            except Exception as exc:
                warn("stream hook failed", error=str(exc), apartment_id=self.apt.apartment_id)

    async def _run(self) -> None:
        apt = self.apt                               # D-201: one link for the whole life of a hub; a new link is a new hub
        self.link = link_of(apt)
        backoff = 1.0
        while True:
            try:
                headers = await instances.instance_headers(apt, instances.BFF_ACTOR)
                headers["Accept"] = "text/event-stream"
                if self.last_id:
                    headers["Last-Event-ID"] = self.last_id
                url = instances.base_url(apt) + "/stream"
                timeout = httpx.Timeout(10.0, read=90.0)
                async with instances.http().stream("GET", url, headers=headers, timeout=timeout) as resp:
                    if resp.status_code != 200:
                        raise RuntimeError(f"upstream stream status {resp.status_code}")
                    self.connected = True
                    backoff = 1.0
                    info("upstream stream connected", apartment_id=self.apt.apartment_id)
                    async for ev in parse_sse(resp.aiter_lines()):
                        await self._publish(ev)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                warn("upstream stream error", error=str(exc), apartment_id=self.apt.apartment_id)
            self.connected = False
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


class HubManager:
    def __init__(self) -> None:
        self.hubs: dict[str, InstanceHub] = {}
        self.hooks: list[EventHook] = []

    def hub(self, apt: Apartment) -> InstanceHub:
        h = self.hubs.get(apt.apartment_id)
        if h is None:
            h = InstanceHub(apt, self.hooks)
            self.hubs[apt.apartment_id] = h
        h.apt = apt
        return h

    def drop(self, apartment_id: str) -> None:
        """Deleted or reset apartment: stop its upstream stream, forget it with its replay buffer, and end every browser
        stream on it (None tells the stream route to close; the PWA reconnects and reloads)."""
        h = self.hubs.pop(apartment_id, None)
        if h is None:
            return
        if h.task:
            h.task.cancel()
        for q in list(h.subscribers):
            _end_stream(q, None)

    async def stop_all(self) -> None:
        for h in self.hubs.values():
            if h.task:
                h.task.cancel()
        self.hubs.clear()


hub_manager = HubManager()


def envelope(ev: SseEvent) -> dict:
    try:
        return json.loads(ev.data)
    except ValueError:
        return {}
