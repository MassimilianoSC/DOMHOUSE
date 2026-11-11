"""ShellyConnector: the Connector of interface.py for Shelly Gen2+ devices (connector.md §2), over a Transport (§3).

Built by make_connector (__init__.py) from the checked catalog (catalog.py) and the MQTT transport; the tests build it
on tests/fake_transport.py. The models are the rows of translate.PROFILES: Plug M Gen3, Shelly 1 Gen4 (switch or
heating), EM Mini Gen4 (power_meter only).

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

BLU sensors (translate.py, «Shelly BLU sensors»; catalog: shelly {addr, bridge, type}). They have no worker: their
events are the bridge's notifications, handled in the bridge's worker, so the order bridge offline -> sensors offline
holds. Read only: execute() refuses them (no command). In detail:
  - when a bridge with sensors in the catalog connects, after Shelly.GetStatus, Shelly.GetComponents (every page)
    gives the map number -> (addr, obj_id) and each sensor's last values: a sensor whose last packet (the newest
    last_updated_ts of all its components, bthomedevice included) is within its threshold goes online=True with a
    snapshot of the values it has (a null value sends nothing); an older one stays offline. A bridge without sensors
    in the catalog is never asked. A failed GetComponents is warned once and tried again at the silence checks;
  - a sys component_added/component_removed of a bthomedevice or bthomesensor reads the map again (the numbers
    change at every pairing); a sensor that becomes reachable is online with its snapshot, one removed is offline;
  - a bthomesensor:<n> NotifyStatus of a mapped measure is a "state" change dated last_updated_ts (with the rules of
    notification_ts and of the stream below); obj_id 1, 63, 100 and unknown ones are ignored silently. bthomedevice
    only refreshes the last packet and the battery (BatteryTracker, «battery low» once);
  - offline: at once when the bridge goes offline (or is rejected); with the bridge online, when the last packet is
    older than the threshold of the sensor's type (checked with the bridge's silence tick). A packet that arrives
    afterwards brings it back online, with a snapshot;
  - a catalog sensor missing from its bridge's components is offline, warned once; a sensor paired with the bridge but
    not in the catalog is ignored, warned once.

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

from .battery import BatteryTracker, battery_from_bthome_device
from .catalog import Catalog, CatalogDevice
from .command import RPC_TIMEOUT_S, run_command
from .offline import is_offline
from .translate import (BTHOME_DEVICE, BTHOME_SENSOR, BthomeComponent, UnknownModel, apply_notify_status,
                        blu_reading, bthome_components, bthome_ts, capabilities_from_status, component_event_targets,
                        notification_ts, profile_for)
from .transport.base import ConnectionEvent, Notification, Transport, TransportError

SILENCE_CHECK_MIN_S, SILENCE_CHECK_MAX_S = 1.0, 30.0
GET_COMPONENTS_MAX_PAGES = 20      # 10 components a page: far more than a bridge carries; stops a bridge that loops
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
        # a bridge: the catalog's BLU sensors it carries, by MAC, and its bthome components (None until read)
        self.sensors: dict[str, "_Device"] = {}
        self.components: dict[str, BthomeComponent] | None = None
        self.components_failed = False   # the last GetComponents failed: tried again at the next silence check
        self.unknown_addrs: set[str] = set()   # sensors on the bridge but not in the catalog, already warned
        # a BLU sensor: last_seen is its last packet (last_updated_ts); missing_warned: not on its bridge, warned
        self.missing_warned = False


class ShellyConnector:
    api_version = CONNECTOR_API_VERSION

    def __init__(self, catalog: Catalog, transport: Transport, *, clock: Callable[[], datetime] = utcnow,
                 silence_check_s: float | None = None, rpc_timeout_s: float = RPC_TIMEOUT_S):
        self._catalog = catalog
        self._transport = transport
        self._clock = clock
        self._rpc_timeout_s = rpc_timeout_s
        self._devices = {d.device_id: _Device(d) for d in catalog.devices}
        self._by_shelly = {d.entry.shelly_id: d for d in self._devices.values() if d.entry.blu is None}
        for device in self._devices.values():
            if device.entry.blu is not None:      # the catalog checked that the bridge is one of its Shelly
                self._by_shelly[device.entry.blu.bridge].sensors[device.entry.blu.addr] = device
        self._battery = BatteryTracker()
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
            if device.entry.blu is not None:
                continue                         # a BLU sensor lives in the worker of its bridge
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
        if (cmd.capability not in entry.capabilities or entry.profile is None
                or cmd.capability not in entry.profile.commands):
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
            if device.sensors and device.online:
                if device.components_failed:
                    await self._read_components(device, item.now, snapshot=True)
                self._check_blu_silence(device, item.now)
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
            if device.sensors:
                self._blu_notify(device, item)
        elif item.method == "NotifyFullStatus":
            self._snapshot(device, {k: v for k, v in item.params.items() if k != "ts"}, ts)
        elif device.sensors and component_event_targets(item.params):
            # a BLU sensor paired or removed on this bridge: the numbers changed, the map is read again
            await self._read_components(device, item.received_at, snapshot=False)
        # any other NotifyEvent: nothing (its last_seen is already counted)

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
        else:
            device.last_seen = self._clock()
            self._snapshot(device, status if isinstance(status, dict) else {}, device.last_seen)
        if device.sensors:                       # a bridge of BLU sensors of the catalog: their map and snapshot
            await self._read_components(device, self._clock(), snapshot=True)

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
        for sensor in device.sensors.values():   # a bridge: its BLU sensors cannot be reached any more (§2.6)
            self._blu_offline(sensor, at)

    # ---- BLU sensors, in the worker of their bridge (translate.py, «Shelly BLU sensors») ------------------------
    async def _get_components(self, shelly_id: str) -> dict[str, BthomeComponent]:
        """Shelly.GetComponents {"dynamic_only": true}, every page (10 components a page), -> the bthome ones."""
        found: list = []
        offset = 0
        for _ in range(GET_COMPONENTS_MAX_PAGES):
            page = await self._transport.call(shelly_id, "Shelly.GetComponents",
                                              {"dynamic_only": True, "offset": offset}, self._rpc_timeout_s)
            components = page.get("components") if isinstance(page, dict) else None
            if not isinstance(components, list) or not components:
                break
            found.extend(components)
            offset += len(components)
            total = page.get("total")
            if isinstance(total, bool) or not isinstance(total, int) or offset >= total:
                break
        return bthome_components(found)

    async def _read_components(self, bridge: _Device, at: datetime, *, snapshot: bool) -> None:
        """Reads the bridge's map and brings its sensors up to date. snapshot=True (the bridge is back): every
        sensor online sends online=True and its snapshot; False (a sensor paired or removed): only the changes."""
        try:
            components = await self._get_components(bridge.entry.shelly_id)
        except TransportError as exc:
            if not bridge.components_failed:     # once until it succeeds: the silence check tries again
                log.warn("blu components read failed", device_id=bridge.entry.device_id,
                         error_type=type(exc).__name__)
            bridge.components_failed = True
            return
        bridge.components_failed = False
        bridge.components = components
        addrs = {c.addr for c in components.values()}
        for addr in sorted(addrs - set(bridge.sensors) - bridge.unknown_addrs):
            bridge.unknown_addrs.add(addr)
            log.warn("unknown blu sensor ignored", device_id=bridge.entry.device_id, addr=addr)
        for addr, sensor in bridge.sensors.items():
            mine = [c for c in components.values() if c.addr == addr]
            if not mine:
                if not sensor.missing_warned:
                    sensor.missing_warned = True
                    log.warn("blu sensor not paired with its bridge", device_id=sensor.entry.device_id,
                             bridge_device_id=bridge.entry.device_id)
                self._blu_offline(sensor, at)
                continue
            sensor.missing_warned = False
            for component in mine:
                self._blu_packet(sensor, component, at)
            was_online = sensor.online
            if self._blu_fresh(sensor, at):
                if snapshot or not was_online:
                    self._blu_online(sensor, at, force=True)
                    self._blu_snapshot(sensor, mine, at)
            else:
                self._blu_offline(sensor, at)

    def _blu_notify(self, bridge: _Device, item: Notification) -> None:
        """The bthome part of a NotifyStatus of the bridge: numbers -> (addr, obj_id) through the map."""
        if bridge.components is None:
            return
        for key, change in item.params.items():
            if key.split(":", 1)[0] not in (BTHOME_DEVICE, BTHOME_SENSOR) or not isinstance(change, dict):
                continue
            component = bridge.components.get(key)
            if component is None:
                continue                         # not in the map (yet): the component_added reads it again
            component = bridge.components[key] = component.updated(change)
            sensor = bridge.sensors.get(component.addr)
            if sensor is None:
                continue                         # on the bridge, not in the catalog: warned once with the map
            self._blu_packet(sensor, component, item.received_at)
            if not sensor.online:
                if self._blu_fresh(sensor, self._clock()):
                    # back after a silence: online, then the snapshot (it carries this change too)
                    at = bthome_ts(component.last_updated_ts, item.received_at) or item.received_at
                    self._blu_online(sensor, at)
                    self._blu_snapshot(sensor, [c for c in bridge.components.values()
                                                if c.addr == component.addr], item.received_at)
                continue
            if component.obj_id is None or "value" not in change:
                continue
            reading = blu_reading(sensor.entry.blu.model, component.obj_id, component.status.get("value"))
            if reading is not None and reading[0] in sensor.entry.capabilities:
                at = bthome_ts(component.last_updated_ts, item.received_at) or item.received_at
                self._emit_state(sensor, reading[0], reading[1], at)

    def _blu_packet(self, sensor: _Device, component: BthomeComponent, received_at: datetime) -> None:
        """A component of the sensor as last known: its last_updated_ts may be the sensor's latest packet (the
        bthomedevice too, the only one a Motion at rest sends), and the bthomedevice carries the battery."""
        packet_at = bthome_ts(component.last_updated_ts, received_at)
        if packet_at is not None and (sensor.last_seen is None or packet_at > sensor.last_seen):
            sensor.last_seen = packet_at
        if component.obj_id is None:
            level = battery_from_bthome_device(dict(component.status))
            if level is not None and self._battery.update(sensor.entry.device_id, level):
                log.warn("battery low", device_id=sensor.entry.device_id, percent=level)

    def _blu_fresh(self, sensor: _Device, now: datetime) -> bool:
        """Its last packet is within the threshold of its type (offline.is_offline)."""
        return sensor.last_seen is not None and not is_offline((now - sensor.last_seen).total_seconds(),
                                                               sensor.entry.offline_after_s)

    def _blu_snapshot(self, sensor: _Device, components: list[BthomeComponent], received_at: datetime) -> None:
        """One "state" change for every capability of the sensor that has a value (§2.6). A measure that never
        had a packet (value null) sends nothing: no state is made up."""
        model = sensor.entry.blu.model
        for cap in sensor.entry.capabilities:
            obj_id = model.obj_id_of(cap)
            component = next((c for c in components if c.obj_id == obj_id), None)
            reading = None if component is None else blu_reading(model, obj_id, component.status.get("value"))
            if reading is not None:
                at = bthome_ts(component.last_updated_ts, received_at) or received_at
                self._emit_state(sensor, cap, reading[1], at)

    def _check_blu_silence(self, bridge: _Device, now: datetime) -> None:
        for sensor in bridge.sensors.values():
            if sensor.online and not self._blu_fresh(sensor, now):
                silence = (now - sensor.last_seen).total_seconds()
                log.warn("device silent beyond threshold", device_id=sensor.entry.device_id,
                         silence_s=round(silence, 1), threshold_s=sensor.entry.offline_after_s)
                self._blu_offline(sensor, now)

    def _blu_online(self, sensor: _Device, at: datetime, *, force: bool = False) -> None:
        if not sensor.online:
            sensor.online = True
            log.info("device online", device_id=sensor.entry.device_id)
        elif not force:
            return
        self._emit(StateChange(sensor.entry.device_id, "online", at, online=True))

    def _blu_offline(self, sensor: _Device, at: datetime) -> None:
        """Only when it changes: a sensor that was not online has nothing to say (its bridge said it already)."""
        if not sensor.online:
            return
        sensor.online = False
        log.info("device offline", device_id=sensor.entry.device_id)
        self._emit(StateChange(sensor.entry.device_id, "online", at, online=False))

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
                          capabilities=caps, links=dict(entry.links),
                          battery_percent=self._battery.level(entry.device_id) if entry.blu is not None else None)

    @staticmethod
    def _result(result: CommandResult, ids: dict) -> CommandResult:
        log.info("command result", outcome=result.outcome, reason=result.reason, detail=result.detail, **ids)
        return result
