"""FakeTransport: the Transport Protocol (transport/base.py) over fake devices, for the connector's tests (§3).

call() answers from the device, after the faults it queued: "rpc" raises RpcError, "hang" waits timeout_s and raises
TransportTimeout, "drop" raises TransportOffline for that call only. A device that is offline, or unknown, raises
TransportOffline. notifications() yields, in one stream, the devices' Notification items (only while they are online)
and the ConnectionEvent that set_online produces, so the order offline -> online -> snapshot of a device is the order
of the stream. No global state: two FakeTransport in one test do not see each other.

Two options, off by default: announce_on_start=True makes start() put a ConnectionEvent(True) for every online device,
as the retained "online" messages of MQTT do right after the subscription; latency_s is the time the answer takes. As
the MQTT transport, which publishes the request at once and then waits for the answer, the device handles the call
AT ONCE (a Switch.Set switches the relay and notifies) and its answer, or its error, reaches the caller latency_s
later (never, and TransportTimeout, when latency_s is not shorter than timeout_s). A command cancelled half way (the
common tests cancel after 0.1 s) has therefore already reached the device, as on the real one.
broker_connected is True between start() and stop(), or as a test sets it.
"""
import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from engine.connector.shelly.transport.base import (ConnectionEvent, Notification, RpcError, TransportEvent,
                                                    TransportOffline, TransportTimeout)

from .fake_device import _FakeShelly

_STOP = object()


class FakeTransport:
    def __init__(self, *devices: _FakeShelly, announce_on_start: bool = False, latency_s: float = 0.0):
        self.devices = {d.shelly_id: d for d in devices}
        self.calls: list[tuple[str, str, dict | None]] = []
        self.announce_on_start = announce_on_start
        self.latency_s = latency_s
        self.broker_connected = False
        self._queue: asyncio.Queue | None = None
        for device in devices:
            device.subscribe(self._on_notification)

    async def start(self) -> None:
        self._queue = asyncio.Queue()
        self.broker_connected = True
        if self.announce_on_start:
            now = datetime.now(UTC)
            for shelly_id, device in self.devices.items():
                if device.online:
                    self._put(ConnectionEvent(shelly_id=shelly_id, connected=True, received_at=now))

    async def stop(self) -> None:
        self.broker_connected = False
        if self._queue is not None:
            self._queue.put_nowait(_STOP)

    async def call(self, shelly_id: str, method: str, params: dict | None, timeout_s: float) -> dict:
        self.calls.append((shelly_id, method, params))
        device = self.devices.get(shelly_id)
        if device is None or not device.online:
            raise TransportOffline()                 # as the MQTT transport: nothing published, at once
        fault = device.next_fault(method)
        if fault is not None and fault[0] == "hang":
            await asyncio.sleep(timeout_s)
            raise TransportTimeout()
        error: Exception | None = None
        answer: dict = {}
        if fault is not None:
            error = RpcError(fault[1], fault[2]) if fault[0] == "rpc" else TransportOffline()
        else:
            try:
                answer = device.handle(method, params)      # the device acts now: the request is out
            except RpcError as exc:
                error = exc
        if self.latency_s > 0:                              # then the answer travels back
            if self.latency_s >= timeout_s:
                await asyncio.sleep(timeout_s)
                raise TransportTimeout()
            await asyncio.sleep(self.latency_s)
        if error is not None:
            raise error
        return answer

    async def notifications(self) -> AsyncIterator[TransportEvent]:
        if self._queue is None:
            raise RuntimeError("FakeTransport.notifications() before start()")
        while True:
            item = await self._queue.get()
            if item is _STOP:
                return
            yield item

    def connected(self) -> set[str]:
        return {sid for sid, d in self.devices.items() if d.online}

    # --- for the tests --------------------------------------------------------------------------------------------

    def set_online(self, shelly_id: str, online: bool) -> None:
        device = self.devices[shelly_id]
        if device.online == online:
            return
        device.online = online
        self._put(ConnectionEvent(shelly_id=shelly_id, connected=online, received_at=datetime.now(UTC)))

    def inject(self, item: TransportEvent) -> None:
        """Puts an item in the stream as it is: a notification of a test's own (e.g. from the capture), also from a
        device the transport does not know."""
        self._put(item)

    def _on_notification(self, notification: Notification) -> None:
        if self.devices[notification.shelly_id].online:
            self._put(notification)

    def _put(self, item: TransportEvent) -> None:
        if self._queue is not None:
            self._queue.put_nowait(item)
