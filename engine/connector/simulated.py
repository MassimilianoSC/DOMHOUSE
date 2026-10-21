"""SimulatedConnector: simulated devices behind the connector interface (per-youssouf/connector.md, §4). Ours.

Extracted unchanged from the BFF's simulated engine (bff/mock_instance/state.py, P-60 step 1): the seeded catalog, the
timing of a command (0.3 s to "sent", 0.2 s to "verifying", 1.0 s to the outcome), the power each appliance draws.
It is what the demonstration apartments and the conformance suite run on, and the model for a real connector.

Besides the interface it has two hooks, for the engine's POST /_test/state and for the tests' harness: set_online and
set_state change the simulated world and return the resulting changes, also sent through changes() unless notify=False
(the engine applies them itself, at once, with the request's correlation_id).
changes() is a live stream: each call gets the changes pushed while it is being read, in its own event loop.
DOMOTICA_TEST_CONNECTOR_DOWN=1 makes status() report the connector down (scenario C14 of the conformance suite).
Power meters (P-60 step 6, D-130) work as connector.md §2.3 says: watts and the raw cumulative counter
energy_total_wh, which grows with the watts over real time (never the accelerated MOCK_TIME_SCALE); a meter that draws
power sends a reading every READING_EVERY_S, as a real one does, besides the reading that follows each command. The
readings are made inside changes(), in the reader's loop: no task of its own. read_meters() makes one at once (tests).
A split with `confirmation: power` behaves as one behind an infrared blaster (P-60 step 7, D-131): its commands end
"delivered", it reports nothing of its climate state, only its meter moves; lose_infrared(device_id) makes the next
frame get lost (nothing changes, still "delivered"), so the engine's "no confirmation" can be tried.
"""
import asyncio
import copy
import os
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta

from .interface import (CONNECTOR_API_VERSION, CommandResult, ConnectorCommand, ConnectorConfig, ConnectorStatus,
                        DeviceInfo, Room, StateChange)

SENT_AFTER_S, VERIFYING_AFTER_S, OUTCOME_AFTER_S = 0.3, 0.2, 1.0
READING_EVERY_S = 60.0                 # a power meter that draws power reports every minute of real time
_STOP = object()
# what a simulated device reports of each capability (connector.md §2.3: the "device" fields; the catalog's and the
# engine's stay with the engine; kwh_today and the hourly consumption are the engine's, from energy_total_wh).
DEVICE_FIELDS = {"switch": ("on",), "power_meter": ("watts", "energy_total_wh"), "climate": ("on", "mode", "setpoint", "fan"),
                 "heating": ("on",), "temperature": ("celsius",), "humidity": ("percent",), "contact": ("open", "since"),
                 "motion": ("detected", "last_seen")}


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def seed_devices(variant: int) -> tuple[list[dict], dict[str, dict]]:
    """The demonstration apartment: variant 0 is occupied and warm (Rimini), 1 is empty and cold (Bologna)."""
    now = iso(utcnow())
    rooms = [{"room_id": "soggiorno", "name": "Soggiorno"}, {"room_id": "camera", "name": "Camera"},
             {"room_id": "tecnico", "name": "Vano tecnico"}]
    warm = variant == 0
    devices = [
        # D-139: the split behind an infrared blaster and the meter that measures it, two devices as in a real
        # catalog (connector.md §6): the meter offline lets a tester see «Comando non verificato» from the Simulator
        {"device_id": "dev-clima-soggiorno", "label": "Climatizzatore soggiorno", "room_id": "soggiorno", "online": True,
         "last_seen": now, "capabilities": {
             "climate": {"on": warm, "mode": "heat", "setpoint": 21, "fan": "auto", "setpoint_min": 16,
                         "setpoint_max": 24, "confirmation": "power"}}},
        {"device_id": "dev-misura-clima", "label": "Misuratore clima", "room_id": "soggiorno", "online": True,
         "last_seen": now, "capabilities": {"power_meter": {"watts": 870 if warm else 0, "energy_total_wh": 812_400.0}}},
        {"device_id": "dev-caldaia", "label": "Caldaia", "room_id": "tecnico", "online": True, "last_seen": now,
         "capabilities": {
             "heating": {"on": warm, "setpoint": 21 if warm else 8, "setpoint_min": 7, "setpoint_max": 23},
             "power_meter": {"watts": 95 if warm else 0, "energy_total_wh": 96_300.0}}},
        {"device_id": "dev-presa-camera", "label": "Presa stufetta camera", "room_id": "camera", "online": True,
         "last_seen": now, "capabilities": {"switch": {"on": False}, "power_meter": {"watts": 0, "energy_total_wh": 41_700.0}}},
        {"device_id": "dev-finestra-camera", "label": "Finestra camera", "room_id": "camera", "online": True,
         "last_seen": now, "capabilities": {"contact": {"open": False, "since": iso(utcnow() - timedelta(hours=4))}}},
        {"device_id": "dev-ambiente-soggiorno", "label": "Sensore soggiorno", "room_id": "soggiorno", "online": True,
         "last_seen": now, "capabilities": {
             "temperature": {"celsius": 20.6 if warm else 16.9}, "humidity": {"percent": 48 if warm else 57},
             "motion": {"detected": warm, "last_seen": iso(utcnow() - timedelta(minutes=3 if warm else 2900))}}},
    ]
    return rooms, {d["device_id"]: d for d in devices}


def watts_for(cap: str, state: dict) -> float:
    """What a simulated appliance draws in that state (the power meter follows the command)."""
    if not state.get("on"):
        return 0
    if cap == "climate":
        return {"heat": 870, "cool": 650, "dry": 300, "fan": 60}.get(state.get("mode"), 500)
    if cap == "heating":
        return 95
    return 1200


class SimulatedDevice:
    """One simulated device: its state as the "world" has it (the engine keeps its own copy)."""

    def __init__(self, data: dict, links: dict[str, str] | None = None):
        self.device_id = data["device_id"]
        self.label, self.room_id = data["label"], data["room_id"]
        self.online = data["online"]
        self.last_seen = data["last_seen"]           # ISO string, as in the contract
        self.capabilities = copy.deepcopy(data["capabilities"])
        self.links = dict(links or {})
        self.meter_at = utcnow()                     # the instant energy_total_wh was brought up to

    def meter_to(self, now: datetime) -> None:
        """energy_total_wh up to `now` at the current watts (real time); earlier instants change nothing."""
        meter = self.capabilities.get("power_meter")
        if meter is None or now <= self.meter_at:
            return
        hours = (now - self.meter_at).total_seconds() / 3600
        meter["energy_total_wh"] = round(float(meter.get("energy_total_wh", 0.0)) + float(meter.get("watts", 0)) * hours, 3)
        self.meter_at = now

    def info(self) -> DeviceInfo:
        self.meter_to(utcnow())
        seen = datetime.fromisoformat(self.last_seen.replace("Z", "+00:00")) if self.last_seen else None
        return DeviceInfo(device_id=self.device_id, label=self.label, room_id=self.room_id, online=self.online,
                          last_seen=seen, capabilities=copy.deepcopy(self.capabilities), links=dict(self.links))

    def reported(self, capability: str) -> dict:
        """The capability as the device reports it: its own fields only."""
        state = self.capabilities[capability]
        return {k: copy.deepcopy(state[k]) for k in DEVICE_FIELDS.get(capability, state) if k in state}

    def apply(self, capability: str, target: dict, now: datetime | None = None,
              heard: bool = True) -> list[tuple[str, dict]]:
        """The device reaches the target; its power meter (if any) follows. Returns (capability, reported state).
        heard=False: an infrared split, which never answers, so it is not "seen" by a command."""
        now = now or utcnow()
        self.meter_to(now)                             # what was used at the old power, before it changes
        self.capabilities[capability].update(copy.deepcopy(target))
        if heard or "power_meter" in self.capabilities:   # its own meter answers even for an infrared split
            self.last_seen = iso(now)                  # the same instant as the change it reports
        changed = [(capability, self.reported(capability))]
        if "power_meter" in self.capabilities:
            self.capabilities["power_meter"]["watts"] = watts_for(capability, self.capabilities[capability])
            changed.append(("power_meter", self.reported("power_meter")))
        return changed


class SimulatedConnector:
    api_version = CONNECTOR_API_VERSION

    def __init__(self, variant: int = 0):
        rooms, devices = seed_devices(variant)
        # the split is confirmed by its own meter and the boiler regulated on the living-room sensor (§2.2)
        links = {"dev-clima-soggiorno": {"confirmation_device_id": "dev-misura-clima"},
                 "dev-caldaia": {"sensor_device_id": "dev-ambiente-soggiorno"}}
        self._rooms = [Room(**r) for r in rooms]
        self._devices = {k: SimulatedDevice(d, links.get(k)) for k, d in devices.items()}
        self._readers: set[asyncio.Queue] = set()
        self._stopped = False
        self._last_event_at: datetime | None = None
        self.reading_every_s = READING_EVERY_S
        self._last_reading = utcnow()
        self._lost_frames: set[str] = set()

    # ---- interface ----------------------------------------------------------------------------------------------
    async def start(self) -> None:
        self._stopped = False

    async def stop(self) -> None:
        self._stopped = True
        for q in list(self._readers):
            q.put_nowait(_STOP)

    def rooms(self) -> list[Room]:
        return list(self._rooms)

    def devices(self) -> list[DeviceInfo]:
        return [d.info() for d in self._devices.values()]

    def status(self) -> ConnectorStatus:
        up = os.environ.get("DOMOTICA_TEST_CONNECTOR_DOWN") != "1"
        online = sum(1 for d in self._devices.values() if d.online)
        return ConnectorStatus(up=up, connected_devices=online if up else 0, last_event_at=self._last_event_at,
                               detail=None if up else "simulated: DOMOTICA_TEST_CONNECTOR_DOWN=1")

    async def changes(self) -> AsyncIterator[StateChange]:
        # a queue per reader, made in the reader's loop: the tests run each case in a new event loop
        queue: asyncio.Queue = asyncio.Queue()
        self._readers.add(queue)
        try:
            while not self._stopped:
                wait = self.reading_every_s - (utcnow() - self._last_reading).total_seconds()
                try:
                    change = await asyncio.wait_for(queue.get(), timeout=max(wait, 0.0))
                except TimeoutError:
                    self.read_meters()                 # pushed to every reader, this one included
                    continue
                if change is _STOP:
                    return
                yield change
        finally:
            self._readers.discard(queue)

    async def execute(self, cmd: ConnectorCommand, on_progress: Callable[[str], None]) -> CommandResult:
        device = self._devices.get(cmd.device_id)
        if device is None:
            return CommandResult("failed", "internal_error", detail="unknown device")
        await asyncio.sleep(SENT_AFTER_S)
        on_progress("sent")
        await asyncio.sleep(VERIFYING_AFTER_S)
        on_progress("verifying")
        await asyncio.sleep(OUTCOME_AFTER_S)
        if not device.online:
            return CommandResult("failed", "device_offline", detail="went offline while verifying")
        now = utcnow()
        infrared = cmd.capability == "climate" and device.capabilities["climate"].get("confirmation") == "power"
        if infrared and cmd.device_id in self._lost_frames:
            self._lost_frames.discard(cmd.device_id)
            return CommandResult("delivered", detail="infrared frame lost (simulated)")
        for cap, state in device.apply(cmd.capability, cmd.target, now, heard=not infrared):
            if not (infrared and cap == "climate"):        # an infrared split says nothing; its meter does
                self._push(StateChange(device.device_id, "state", now, capability=cap, state=state))
        meter = self._devices.get(device.links.get("confirmation_device_id", ""))
        if meter is not None and meter is not device and "power_meter" in meter.capabilities:
            meter.meter_to(now)                            # the separate meter follows the split it measures
            meter.capabilities["power_meter"]["watts"] = watts_for(cmd.capability, device.capabilities[cmd.capability])
            if meter.online:
                meter.last_seen = iso(now)
                self._push(StateChange(meter.device_id, "state", now, capability="power_meter",
                                       state=meter.reported("power_meter")))
        await asyncio.sleep(0)   # let the engine take the changes before it hears the outcome (same order as before)
        if infrared:
            return CommandResult("delivered")
        return CommandResult("confirmed", state=device.reported(cmd.capability))

    # ---- hooks of POST /_test/state and of the tests (simulated only) --------------------------------------------
    def lose_infrared(self, device_id: str) -> None:
        """The next infrared frame to this split gets lost: the command ends "delivered" and nothing moves."""
        self._lost_frames.add(device_id)

    def read_meters(self, notify: bool = True) -> list[StateChange]:
        """A reading of every online meter that draws power (a meter at 0 W has nothing new to say)."""
        now = utcnow()
        self._last_reading = now
        out = []
        for device in self._devices.values():
            meter = device.capabilities.get("power_meter")
            if meter is None or not device.online or not meter.get("watts"):
                continue
            device.meter_to(now)
            device.last_seen = iso(now)
            out.append(StateChange(device.device_id, "state", now, capability="power_meter",
                                   state=device.reported("power_meter")))
        for c in out:
            self._push(c, notify)
        return out

    def set_online(self, device_id: str, online: bool, notify: bool = True) -> list[StateChange]:
        """The device goes away or comes back; back online it sends a full snapshot, as a real connector does."""
        device = self._devices[device_id]
        now = utcnow()
        device.meter_to(now)
        device.online = online
        if online:
            device.last_seen = iso(now)
        out = [StateChange(device_id, "online", now, online=online)]
        if online:
            out += [StateChange(device_id, "state", now, capability=c, state=device.reported(c))
                    for c in device.capabilities]
        for c in out:
            self._push(c, notify)
        return out

    def set_state(self, device_id: str, capability: str, state: dict, notify: bool = True) -> StateChange:
        """Something changes in the world (a window opens, the temperature drops)."""
        device = self._devices[device_id]
        current = device.capabilities[capability]
        was_open = current.get("open")
        now = utcnow()
        device.meter_to(now)                           # a new power from now on
        current.update(state)
        if capability == "contact" and current.get("open") != was_open:
            current["since"] = iso(now)
        device.last_seen = iso(now)
        change = StateChange(device_id, "state", now, capability=capability, state=device.reported(capability))
        self._push(change, notify)
        return change

    def _push(self, change: StateChange, notify: bool = True) -> None:
        self._last_event_at = change.ts
        if notify:
            for q in list(self._readers):
                q.put_nowait(change)


def make_connector(config: ConnectorConfig) -> SimulatedConnector:
    """CONNECTOR=simulated: the demonstration catalog, the cold empty one for a "bologna" apartment."""
    return SimulatedConnector(variant=1 if "bologna" in config.apartment_id else 0)
