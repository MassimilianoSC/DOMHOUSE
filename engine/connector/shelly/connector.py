"""ShellyConnector: the Connector of interface.py for Shelly Gen2+ devices (connector.md §2), over a Transport (§3).

Built by make_connector (__init__.py) from the checked catalog (catalog.py) and the MQTT transport; the tests build it
on tests/fake_transport.py. Only the Plug M Gen3 is supported today (translate.PROFILES).

How the events flow. One reader task takes the transport's stream (Notification and ConnectionEvent, base.py) and
puts each item in the queue of its device; one worker per device handles them in order. The order of one device is
therefore kept (§2.6: offline, online, snapshot), while the RPCs a device needs when it connects (up to two, 3 s
each) never hold back the notifications of the others: a meter that confirms a split must reach the engine within 2 s
(§2.5). Messages from a shelly_id not in the catalog are dropped with a warning, once per shelly_id (a plug sends a
reading every minute: one line, not one a minute), and no device_id is ever made up.

A device that connects (ConnectionEvent(True)): online=True goes out, then Shelly.GetDeviceInfo tells the model; if
its profile is not the one the catalog expects (another type, or without a capability of the catalog), a warning
"device model not supported" is logged once for that connection and the device goes back offline (online=False) and
stays so, its notifications ignored, until it connects again. Otherwise Shelly.GetStatus gives the full snapshot: one
"state" change for EVERY capability of the device (§2.6). If GetDeviceInfo cannot be done (timeout), the catalog's
profile is used and the check is tried again at the next connection; if GetStatus fails, the device stays online and
the next notifications fill its state.

NotifyStatus carries only what changed: translate.apply_notify_status completes it from the last known status and
gives one change per capability touched. NotifyFullStatus is a snapshot like the one above. NotifyEvent is ignored for
now. A notification from a device that was put offline by silence, while the transport still has it connected, counts
as a return: online=True and a snapshot, then the notification.

Silence (§2.6). Every message of a device updates its last_seen (our reception time); a periodic tick, put in the
device's own queue so it keeps the order, applies offline.is_offline with the device's threshold (catalog.py) and
sends online=False when the silence goes beyond it. For the Plug the broker's "false" usually comes first; the check
is there for the battery sensors to come.

The order of ts. StateChange.ts is translate.notification_ts (the device's clock when it is within the trusted skew,
else our reception time), but in the stream of changes() it NEVER goes back, not even between different devices: a
ts earlier than the last one emitted is replaced by the last one emitted. So a device whose clock is a little behind
(within translate.MAX_CLOCK_SKEW_S) gets its changes dated a little later than its own clock says; the engine needs an
ordered stream more than that precision (its consumption per hour, kwh_today).

Commands: command.run_command (set, then read back, every RPC within cmd.deadline). A device the connector has
offline fails at once with failed/device_offline, nothing queued (§2.5, §6); a device_offline outcome of a device the
connector had online puts it offline through its queue, so online=False goes out in its order (§2.6). Cancelling
execute() (the engine past the deadline) leaves nothing half done: no state of the connector is changed by a command.

No global state: everything lives in the instance, so two connectors live together in one process (§6). The logs
(engine.log) carry short stable messages and ids, never payloads nor credentials.
"""
import asyncio
import contextlib
import copy
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from engine import log
from engine.connector.interface import (CONNECTOR_API_VERSION, CommandResult, ConnectorCommand, ConnectorStatus,
                                        DeviceInfo, Room, StateChange)

from .catalog import Catalog, CatalogDevice
from .command import RPC_TIMEOUT_S, run_command
from .offline import is_offline
from .translate import (UnknownModel, apply_notify_status, capabilities_from_status, notification_ts, profile_for)
from .transport.base import ConnectionEvent, Notification, Transport, TransportError

SILENCE_CHECK_MIN_S, SILENCE_CHECK_MAX_S = 1.0, 30.0
_STOP = object()


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _Tick:
    """The silence check, handled by the device's worker in its order."""
    now: datetime


@dataclass(frozen=True)
class _Lost:
    """A command found the device offline: the worker sends online=False in the device's order."""
    at: datetime


class _Device:
    """What the connector knows of one catalog device. Changed by its worker only."""

    def __init__(self, entry: CatalogDevice):
        self.entry = entry
        self.online = False
        self.rejected = False            # its model is not the catalog's: offline until it connects again
        self.last_seen: datetime | None = None
        self.status: dict = {}           # the last known full Shelly status
        self.reported: dict[str, dict] = {}   # capability -> the device fields last emitted
        self.queue: asyncio.Queue | None = None
        self.task: asyncio.Task | None = None


class ShellyConnector:
    api_version = CONNECTOR_API_VERSION

    def __init__(self, catalog: Catalog, transport: Transport, *, clock: Callable[[], datetime] = utcnow,
                 silence_check_s: float | None = None, rpc_timeout_s: float = RPC_TIMEOUT_S):
        self._catalog = catalog
        self._transport = transport
        self._clock = clock
        self._rpc_timeout_s = rpc_timeout_s
        self._devices = {d.device_id: _Device(d) for d in catalog.devices}
        self._by_shelly = {d.entry.shelly_id: d for d in self._devices.values()}
        shortest = min((d.offline_after_s for d in catalog.devices), default=SILENCE_CHECK_MAX_S * 4)
        self._silence_check_s = silence_check_s or min(max(shortest / 4, SILENCE_CHECK_MIN_S), SILENCE_CHECK_MAX_S)
        self._readers: set[asyncio.Queue] = set()
        self._tasks: list[asyncio.Task] = []
        self._started = False
        self._stopped = False
        self._last_ts: datetime | None = None          # the last ts emitted: the stream never goes back
        self._last_event_at: datetime | None = None
        self._unknown_warned: set[str] = set()

    # ---- interface ----------------------------------------------------------------------------------------------
    async def start(self) -> None:
        if self._started and not self._stopped:
            return
        self._started, self._stopped = True, False
        await self._transport.start()
        loop = asyncio.get_running_loop()
        for device in self._devices.values():
            device.queue = asyncio.Queue()
            device.task = loop.create_task(self._worker(device), name=f"shelly-device-{device.entry.device_id}")
            self._tasks.append(device.task)
        self._tasks.append(loop.create_task(self._reader(), name="shelly-reader"))
        self._tasks.append(loop.create_task(self._silence_loop(), name="shelly-silence"))
        log.info("shelly connector started", devices=len(self._devices))

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self._started:
            with contextlib.suppress(Exception):
                await self._transport.stop()
        for device in self._devices.values():
            device.queue, device.task = None, None
        for q in list(self._readers):
            q.put_nowait(_STOP)
        log.info("shelly connector stopped")

    def rooms(self) -> list[Room]:
        return list(self._catalog.rooms)

    def devices(self) -> list[DeviceInfo]:
        return [self._info(d) for d in self._devices.values()]

    def status(self) -> ConnectorStatus:
        running = self._started and not self._stopped
        up = running and bool(getattr(self._transport, "broker_connected", False))
        if not running:
            detail = "stopped" if self._stopped else "not started"
        else:
            detail = None if up else "mqtt broker not connected"
        online = sum(1 for d in self._devices.values() if d.online and not d.rejected)
        return ConnectorStatus(up=up, connected_devices=online if up else 0, last_event_at=self._last_event_at,
                               detail=detail)

    async def changes(self) -> AsyncIterator[StateChange]:
        # a queue per reader, made in the reader's loop, as in simulated.py; the engine is the one consumer
        queue: asyncio.Queue = asyncio.Queue()
        self._readers.add(queue)
        try:
            while not self._stopped:
                change = await queue.get()
                if change is _STOP:
                    return
                yield change
        finally:
            self._readers.discard(queue)

    async def execute(self, cmd: ConnectorCommand, on_progress: Callable[[str], None]) -> CommandResult:
        ids = {"correlation_id": cmd.correlation_id, "command_id": cmd.command_id, "device_id": cmd.device_id}
        device = self._devices.get(cmd.device_id)
        if device is None:
            return self._result(CommandResult("failed", "internal_error", detail="unknown device"), ids)
        entry = device.entry
        if cmd.capability not in entry.capabilities or cmd.capability not in entry.profile.commands:
            return self._result(CommandResult("failed", "internal_error",
                                              detail="capability not commandable on this device"), ids)
        if not device.online or device.rejected:
            return self._result(CommandResult("failed", "device_offline", detail="device offline"), ids)

        def progress(step: str) -> None:
            if step == "sent":
                log.info("command sent", capability=cmd.capability, **ids)
            on_progress(step)

        try:
            result = await run_command(self._transport, entry.shelly_id, entry.profile, cmd.capability,
                                       dict(cmd.target), deadline=cmd.deadline, on_progress=progress,
                                       channel=entry.channel, rpc_timeout_s=self._rpc_timeout_s, now=self._clock)
        except asyncio.CancelledError:
            log.info("command cancelled", **ids)
            raise
        if result.reason == "device_offline" and device.online and device.queue is not None:
            device.queue.put_nowait(_Lost(self._clock()))       # online=False in the device's order (§2.6)
        return self._result(result, ids)

    # ---- the stream of the transport -----------------------------------------------------------------------------
    async def _reader(self) -> None:
        try:
            async for item in self._transport.notifications():
                device = self._by_shelly.get(item.shelly_id)
                if device is None:
                    if item.shelly_id not in self._unknown_warned:
                        self._unknown_warned.add(item.shelly_id)
                        log.warn("unknown shelly device ignored", shelly_id=item.shelly_id)
                    continue
                self._last_event_at = item.received_at
                if device.queue is not None:
                    device.queue.put_nowait(item)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.error("shelly transport stream failed", error_type=type(exc).__name__)

    async def _silence_loop(self) -> None:
        while True:
            await asyncio.sleep(self._silence_check_s)
            now = self._clock()
            for device in self._devices.values():
                if device.online and device.queue is not None:
                    device.queue.put_nowait(_Tick(now))

    async def _worker(self, device: _Device) -> None:
        queue = device.queue
        while True:
            item = await queue.get()
            try:
                await self._handle(device, item)
            except asyncio.CancelledError:
                raise
            except Exception as exc:             # one bad message never stops the device's worker
                log.error("device event handling failed", device_id=device.entry.device_id,
                          error_type=type(exc).__name__)

    async def _handle(self, device: _Device, item) -> None:
        if isinstance(item, _Tick):
            self._check_silence(device, item.now)
            return
        if isinstance(item, _Lost):
            if device.online:
                self._go_offline(device, item.at)
            return
        if isinstance(item, ConnectionEvent):
            if item.connected:
                device.last_seen = item.received_at
                await self._connected(device, item.received_at)
            elif device.online or device.rejected:
                device.rejected = False
                self._go_offline(device, item.received_at)
            return
        if not isinstance(item, Notification):
            return
        if device.rejected:
            return                                  # not the catalog's model: ignored until it connects again
        device.last_seen = item.received_at
        if not device.online:
            if item.shelly_id not in self._transport.connected():
                return                              # it came before its "offline": the stream says the rest
            await self._connected(device, item.received_at)    # back after a silence: online and a snapshot first
            if not device.online:
                return
        profile, channel = device.entry.profile, device.entry.channel
        ts = notification_ts(item.params, item.received_at)
        if item.method == "NotifyStatus":
            device.status, changed = apply_notify_status(profile, device.status, item.params, channel)
            for cap in device.entry.capabilities:
                if cap in changed:
                    self._emit_state(device, cap, changed[cap], ts)
        elif item.method == "NotifyFullStatus":
            self._snapshot(device, {k: v for k, v in item.params.items() if k != "ts"}, ts)
        # NotifyEvent: nothing for now (its last_seen is already counted)

    # ---- connection, snapshot, silence ---------------------------------------------------------------------------
    async def _connected(self, device: _Device, at: datetime) -> None:
        entry = device.entry
        device.rejected = False
        if not device.online:
            device.online = True
            log.info("device online", device_id=entry.device_id)
        self._emit(StateChange(entry.device_id, "online", at, online=True))
        try:
            info = await self._transport.call(entry.shelly_id, "Shelly.GetDeviceInfo", None, self._rpc_timeout_s)
        except TransportError as exc:
            log.warn("device model check failed", device_id=entry.device_id, error_type=type(exc).__name__)
        else:
            try:
                profile = profile_for(info.get("app") if isinstance(info, dict) else None)
            except UnknownModel:
                profile = None
            if profile is None or not profile.covers(entry.device_type, entry.capabilities):
                # once for this connection: the device's notifications are ignored until it connects again
                log.warn("device model not supported", device_id=entry.device_id, device_type=entry.device_type)
                device.rejected = True
                self._go_offline(device, self._clock())
                return
        try:
            status = await self._transport.call(entry.shelly_id, "Shelly.GetStatus", None, self._rpc_timeout_s)
        except TransportError as exc:
            log.warn("device snapshot failed", device_id=entry.device_id, error_type=type(exc).__name__)
            return
        device.last_seen = self._clock()
        self._snapshot(device, status if isinstance(status, dict) else {}, device.last_seen)

    def _snapshot(self, device: _Device, status: dict, ts: datetime) -> None:
        """A full status: one "state" change for every capability of the device (§2.6)."""
        device.status = copy.deepcopy(status)
        found = capabilities_from_status(device.entry.profile, device.status, device.entry.channel)
        for cap in device.entry.capabilities:
            if cap in found:
                self._emit_state(device, cap, found[cap], ts)
            elif cap in device.reported:              # not in this status: what was last known, so none is missing
                self._emit_state(device, cap, device.reported[cap], ts)
            else:
                log.warn("capability missing from device status", device_id=device.entry.device_id, capability=cap)

    def _check_silence(self, device: _Device, now: datetime) -> None:
        if not device.online or device.last_seen is None:
            return
        silence = (now - device.last_seen).total_seconds()
        if is_offline(silence, device.entry.offline_after_s):
            log.warn("device silent beyond threshold", device_id=device.entry.device_id,
                     silence_s=round(silence, 1), threshold_s=device.entry.offline_after_s)
            self._go_offline(device, now)

    def _go_offline(self, device: _Device, at: datetime) -> None:
        if device.online:
            log.info("device offline", device_id=device.entry.device_id)
        device.online = False
        self._emit(StateChange(device.entry.device_id, "online", at, online=False))

    # ---- emission ------------------------------------------------------------------------------------------------
    def _emit_state(self, device: _Device, cap: str, state: dict, ts: datetime) -> None:
        device.reported[cap] = copy.deepcopy(state)
        self._emit(StateChange(device.entry.device_id, "state", ts, capability=cap, state=copy.deepcopy(state)))

    def _emit(self, change: StateChange) -> None:
        """The one way out: the ts of the stream never goes back (see the module's docstring)."""
        if self._last_ts is not None and change.ts < self._last_ts:
            change = StateChange(change.device_id, change.kind, self._last_ts, capability=change.capability,
                                 state=change.state, online=change.online)
        self._last_ts = change.ts
        for q in list(self._readers):
            q.put_nowait(change)

    # ---- helpers -------------------------------------------------------------------------------------------------
    def _info(self, device: _Device) -> DeviceInfo:
        entry = device.entry
        caps = {cap: {**copy.deepcopy(dict(values)), **copy.deepcopy(device.reported.get(cap, {}))}
                for cap, values in entry.capabilities.items()}
        return DeviceInfo(device_id=entry.device_id, label=entry.label, room_id=entry.room_id,
                          online=device.online and not device.rejected, last_seen=device.last_seen,
                          capabilities=caps, links=dict(entry.links), battery_percent=None)

    @staticmethod
    def _result(result: CommandResult, ids: dict) -> CommandResult:
        log.info("command result", outcome=result.outcome, reason=result.reason, detail=result.detail, **ids)
        return result
