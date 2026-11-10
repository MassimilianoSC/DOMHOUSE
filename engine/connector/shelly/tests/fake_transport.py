"""FakeTransport: the Transport Protocol (transport/base.py) over fake devices, for the connector's tests (§3).

call() answers from the device, after the faults it queued: "rpc" raises RpcError, "hang" waits timeout_s and raises
TransportTimeout, "drop" raises TransportOffline for that call only. A device that is offline, or unknown, raises
TransportOffline. notifications() yields, in one stream, the devices' Notification items (only while they are online)
and the ConnectionEvent that set_online produces, so the order offline -> online -> snapshot of a device is the order
of the stream. No global state: two FakeTransport in one test do not see each other.
"""
import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from engine.connector.shelly.transport.base import (ConnectionEvent, Notification, RpcError, TransportEvent,
                                                    TransportOffline, TransportTimeout)

from .fake_device import FakePlugMG3

_STOP = object()


class FakeTransport:
    def __init__(self, *devices: FakePlugMG3):
        self.devices = {d.shelly_id: d for d in devices}
        self.calls: list[tuple[str, str, dict | None]] = []
        self._queue: asyncio.Queue | None = None
        for device in devices:
            device.subscribe(self._on_notification)

    async def start(self) -> None:
        self._queue = asyncio.Queue()

    async def stop(self) -> None:
        if self._queue is not None:
            self._queue.put_nowait(_STOP)

    async def call(self, shelly_id: str, method: str, params: dict | None, timeout_s: float) -> dict:
        self.calls.append((shelly_id, method, params))
        device = self.devices.get(shelly_id)
        if device is None or not device.online:
            raise TransportOffline()
        fault = device.next_fault(method)
        if fault is not None:
            if fault[0] == "rpc":
                raise RpcError(fault[1], fault[2])
            if fault[0] == "hang":
                await asyncio.sleep(timeout_s)
                raise TransportTimeout()
            if fault[0] == "drop":
                raise TransportOffline()
        return device.handle(method, params)

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

    def _on_notification(self, notification: Notification) -> None:
        if self.devices[notification.shelly_id].online:
            self._put(notification)

    def _put(self, item: TransportEvent) -> None:
        if self._queue is not None:
            self._queue.put_nowait(item)
