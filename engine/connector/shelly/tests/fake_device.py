"""Fake Shelly devices (Gen2+ RPC API), for the tests of the Shelly connector (connector.md §3, §4).

Three models, with the shapes of the real devices on the bench (10 November 2026, ids invented as connector.md §5
asks). _FakeShelly holds what they share: the sinks of the transport, the queued faults, the online flag, the
notifications (only the changed fields, with a top-level "ts") and the RPCs Shelly.GetDeviceInfo and Shelly.GetStatus.
None of them has a timer: delays and timeouts belong to tests/fake_transport.py, which reads the faults queued here.
The faults: fail_next (an RPC error), hang_next (no answer), drop_next (the connection drops during that RPC); each
applies to the next call of that method only. An unknown method is RpcError -32601.

FakePlugMG3, the Plug M Gen3 (firmware 1.8.99, tests/fixtures/plugmg3_mqtt_capture.jsonl):
  - switching off: ONE NotifyStatus with output, source, apower and current (the zeros as integers, as in the JSON);
  - switching on: first output and source, then apower, then current, in separate messages;
  - a change of load: apower, then current, in separate messages.
A Switch.Set reports source "MQTT", as the real plug does when the command comes over MQTT. The world around the plug:
press_button, set_load, add_energy, reboot; protection_trips makes the relay refuse to switch on, as the overpower
protection does.

FakeS1G4, the Shelly 1 Gen4 (firmware 2.0.3, tests/fixtures/g4_relay_emmini_mqtt_capture.jsonl): a relay without
metering. Switch.Set sends one NotifyStatus with output and source "MQTT"; minute() sends the NotifyStatus of every
minute, with switch:0.counts only; reboot() sends NotifyFullStatus, as the real one does when it comes back. Its
counts.switch_on goes up at every switch on. press_button switches it from outside (source "button": not captured).

FakeMiniEMG4, the EM Mini Gen4 (firmware 1.7.0, same capture): a meter, no command (Switch.* is "method not found").
It reports only when the test asks: report_power() sends the em1:0 NotifyStatus (act_power, current, freq, voltage)
with its "ts" em1_delay_s seconds BEFORE now (13.5 s by default, as in the capture); report_energy() sends the
em1data:0 NotifyStatus and then its NotifyEvent "data", with the ts of now. set_load and add_energy change the meter
silently, as the real one waits for its next cycle. When it comes back online it sends nothing: no NotifyFullStatus.

BLU sensors (bench of 11 November 2026, tests/fixtures/blu_bridge_mqtt_capture.jsonl): any of the three can be the
bridge of FakeBluHT, FakeBluMotion and FakeBluDoorWindow. pair() adds a bthomedevice and a bthomesensor per object,
numbered by the bridge from 200 in the order of pairing (so the same sensor gets other numbers on another bridge or
after a new pairing), with a sys component_added for each; unpair() removes them with component_removed.
Shelly.GetComponents answers with the dynamic components, 10 a page, from "offset", with "total". Packets leave only
when the test says so: blu_packet() updates the components and notifies a bthomesensor only when its value changes;
blu_device_report() sends the bthomedevice notification (the real one sends it at most once a minute, with the last
packet already received). A device with nothing paired answers GetComponents with an empty list; nothing else of the
three models changes. blu_set_errors() makes the bridge unable to decode a sensor (errors ["parse_failed"] on its
bthomedevice, as the EM Mini Gen4 did with the Motion and the Door/Window on 11 November 2026), or able again.
restart_numbering() makes the next pairings take the numbers from 200 again, as the real bridge reuses the numbers
freed by an unpairing (capture of 11 November 2026: bthomedevice:201 removed and added again as 201).
Back from error the bridge notifies "errors": [] by default, an ASSUMPTION never seen on the bench;
announce_errors_gone = False makes it silent about it (the errors only disappear from GetComponents).

Every device has a clock of its own: clock_skew (0 by default) is added to ours for the "ts" of its notifications, the
last_updated_ts of its BLU packets and the sys.unixtime of its full status (whole seconds, as the real one); the
received_at of its notifications is always our clock.
"""
import copy
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from engine.connector.shelly.transport.base import Notification, RpcError

DEVICE_INFO = {"name": None, "id": "shellyplugmg3-000000000001", "mac": "000000000001", "slot": 1,
               "model": "S3PL-30110EU", "gen": 3, "fw_id": "20251209-070625/geeb7eab", "ver": "1.8.99-plugmg3prod0",
               "app": "PlugMG3", "auth_en": False, "auth_domain": None, "matter": True}
S1G4_DEVICE_INFO = {"name": None, "id": "shelly1g4-000000000002", "mac": "000000000002", "slot": 1,
                    "model": "S4SW-001X16EU", "gen": 4, "fw_id": "20261026-122228/2.0.3-g4601943", "ver": "2.0.3",
                    "app": "S1G4", "auth_en": False, "auth_domain": None, "matter": True, "provision": "complete",
                    "enhanced_security": False}
MINIEMG4_DEVICE_INFO = {"name": None, "id": "shellyemminig4-000000000003", "mac": "000000000003", "slot": 0,
                        "model": "S4EM-001PXCEU16", "gen": 4, "fw_id": "20250915-120902/gb95ce8e",
                        "ver": "1.7.0-miniemg4prod0", "app": "MiniEMG4", "auth_en": False, "auth_domain": None,
                        "matter": True}
EM1_DELAY_S = 13.5           # in the capture, em1:0's ts is about this much before its arrival
BTHOME_DEVICE, BTHOME_SENSOR = "bthomedevice", "bthomesensor"
COMPONENTS_PAGE = 10         # Shelly.GetComponents gives 10 components a page (bench of 11 November 2026)


class FakeBlu:
    """A Shelly BLU sensor: its MAC and its BTHome objects, in the order the bridge numbers them (battery first, as in
    the capture of 11 November 2026). values holds the last value of each object it sent, None before the first."""
    objects: tuple[int, ...] = ()
    model_id = 0                     # attrs.model_id of its bthomedevice
    fw_ver = ""                      # status.fw_ver of its bthomedevice, as in the real answers

    def __init__(self, addr: str):
        self.addr = addr
        self.values: dict[int, object] = {obj_id: None for obj_id in self.objects}


class FakeBluHT(FakeBlu):
    objects = (1, 46, 69)            # battery %, humidity %, temperature °C
    model_id, fw_ver = 17, "v1.1.4"


class FakeBluMotion(FakeBlu):
    objects = (1, 33, 100)           # battery %, motion, illuminance level 0-2
    model_id, fw_ver = 19, "v1.2.20"


class FakeBluDoorWindow(FakeBlu):
    objects = (1, 45, 63, 100)       # battery %, open, rotation in degrees, illuminance level 0-2
    model_id, fw_ver = 20, "v1.2.14"


def utcnow() -> datetime:
    return datetime.now(UTC)


class _FakeShelly:
    """What every fake device shares. A model gives device_info(), full_status() and its own RPCs (_handle_own)."""

    def __init__(self, shelly_id: str, clock: Callable[[], datetime]):
        self.shelly_id = shelly_id
        self.online = True
        self._clock = clock
        self.clock_skew = timedelta(0)   # the device's clock minus ours: its ts, last_updated_ts and sys.unixtime
        self._uptime = 0
        self._faults: dict[str, deque] = defaultdict(deque)
        self._sinks: list[Callable[[Notification], None]] = []
        # BLU sensors paired with this device (pair): its dynamic components, as Shelly.GetComponents gives them
        self._components: dict[str, dict] = {}
        self._paired: dict[str, tuple["FakeBlu", list[str]]] = {}
        self._numbers = {BTHOME_DEVICE: 199, BTHOME_SENSOR: 199}
        self._reported_battery: dict[str, float] = {}
        self._errors: dict[str, list[str]] = {}            # blu_set_errors: the sensors this bridge cannot decode
        self.announce_errors_gone = True   # False: back from error, the bridge does not notify "errors": []
        self._notified_errors: dict[str, list[str]] = {}
        self._cfg_rev = 10

    # --- what the transport needs -------------------------------------------------------------------------------

    def subscribe(self, sink: Callable[[Notification], None]) -> None:
        self._sinks.append(sink)

    def next_fault(self, method: str) -> tuple | None:
        """The fault queued for this method, consumed: ("rpc", code, message), ("hang",) or ("drop",)."""
        queue = self._faults.get(method)
        return queue.popleft() if queue else None

    def handle(self, method: str, params: dict | None) -> dict:
        params = params or {}
        if method == "Shelly.GetDeviceInfo":
            return copy.deepcopy(self.device_info() | {"id": self.shelly_id, "mac": self._mac()})
        if method == "Shelly.GetStatus":
            return self.full_status()
        if method == "Shelly.GetComponents":
            return self._get_components(params)
        return self._handle_own(method, params)

    # --- BLU sensors paired with this device, its bridge (bench of 11 November 2026) ----------------------------

    def pair(self, sensor: "FakeBlu") -> None:
        """Pairs a BLU sensor: a bthomedevice and one bthomesensor per object, numbered from 200 by this bridge (the
        numbers are the bridge's, never stable), each announced by a sys component_added. Before the first packet the
        shape is the real one (tests/fixtures/blu_get_components_pages.json, never_heard): the bthomedevice has
        rssi, battery, packet_id and last_updated_ts null; a bthomesensor has value null but last_updated_ts 0."""
        device_n = self._next_number(BTHOME_DEVICE)
        self._components[f"{BTHOME_DEVICE}:{device_n}"] = {
            "status": {"id": device_n, "rssi": None, "battery": None, "packet_id": None, "last_updated_ts": None,
                       "key": False, "paired": True, "rpc": False, "rsv": -1, "fw_ver": sensor.fw_ver},
            "config": {"id": device_n, "addr": sensor.addr, "name": None, "meta": {"ui": {"view": "regular"}}},
            "attrs": {"model_id": sensor.model_id}}
        keys = [f"{BTHOME_DEVICE}:{device_n}"]
        for obj_id in sensor.objects:
            n = self._next_number(BTHOME_SENSOR)
            self._components[f"{BTHOME_SENSOR}:{n}"] = {
                "status": {"id": n, "value": None, "last_updated_ts": 0},
                "config": {"id": n, "addr": sensor.addr, "name": None, "obj_id": obj_id, "idx": 0, "meta": None}}
            keys.append(f"{BTHOME_SENSOR}:{n}")
        self._paired[sensor.addr] = (sensor, keys)
        for key in keys:
            self._component_event("component_added", key)

    def unpair(self, addr: str) -> None:
        """As the real one: the sensors' component_removed first, then the device's."""
        _, keys = self._paired.pop(addr)
        for key in keys[1:] + keys[:1]:
            del self._components[key]
            self._component_event("component_removed", key)

    def blu_packet(self, addr: str, values: dict, *, battery: float | None = None, rssi: int = -60) -> None:
        """A packet of the sensor reaches the bridge, with its objects' values ({obj_id: value}; the others keep
        theirs). Every object in the packet gets last_updated_ts = now; a bthomesensor is notified ONLY when its value
        changes. The bthomedevice is updated silently: its notification is blu_device_report()."""
        sensor, keys = self._paired[addr]
        now = int(self.device_now().timestamp())
        if self._blu_errored_packet(addr, keys[0], now, rssi):
            return
        sensor.values.update(values)
        if battery is not None and 1 in sensor.values:
            sensor.values[1] = battery                     # the obj_id 1 sensor carries the same level
        device = self._components[keys[0]]["status"]
        device["packet_id"] = (device["packet_id"] or 0) + 1
        device.update(last_updated_ts=now, rssi=rssi)
        if battery is not None:
            device["battery"] = battery
        for key in keys[1:]:
            status, obj_id = self._components[key]["status"], self._components[key]["config"]["obj_id"]
            if sensor.values.get(obj_id) is None:
                continue
            old = status["value"]
            status.update(value=sensor.values[obj_id], last_updated_ts=now)
            if old != status["value"] or type(old) is not type(status["value"]):
                self._notify("NotifyStatus", {key: {"last_updated_ts": now, "value": status["value"]}})
        if self._notified_errors.get(addr) and not self.announce_errors_gone:
            device.pop("errors", None)                     # gone from GetComponents, never notified
            self._notified_errors[addr] = []
        elif self._notified_errors.get(addr):
            # back from error, an ASSUMPTION (never seen on the bench): the packet decoded as usual, then a
            # bthomedevice NotifyStatus with "errors": [] (after the values, the order of a normal packet in the
            # capture), and the key gone from its status
            device.pop("errors", None)
            self._notified_errors[addr] = []
            self._notify("NotifyStatus", {keys[0]: {"errors": [], "last_updated_ts": now, "rssi": rssi}})

    def blu_set_errors(self, addr: str, errors: list[str]) -> None:
        """From the next packet of this sensor on, the bridge cannot decode it (["parse_failed"], bench of 11
        November 2026, tests/fixtures/blu_parse_failed.json), or can again ([]). Silent until that packet."""
        self._errors[addr] = list(errors)

    def _blu_errored_packet(self, addr: str, device_key: str, now: int, rssi: int) -> bool:
        """A packet of a sensor in error (True; nothing decoded) or not (False). In error, as the real one: only the
        bthomedevice moves (last_updated_ts, rssi; the values, packet_id and battery stay), and its NotifyStatus
        carries "errors" only when they changed since the last notified, so the report a minute later
        (blu_device_report) comes without them."""
        errors, notified = self._errors.get(addr, []), self._notified_errors.get(addr, [])
        if not errors:
            return False
        device = self._components[device_key]["status"]
        device.update(last_updated_ts=now, rssi=rssi, errors=list(errors))
        if errors != notified:
            self._notified_errors[addr] = list(errors)
            self._notify("NotifyStatus", {device_key: {"errors": list(errors), "last_updated_ts": now, "rssi": rssi}})
        return True

    def blu_device_report(self, addr: str) -> None:
        """The bthomedevice NotifyStatus (at most one a minute on the real one): the last packet already received,
        its last_updated_ts, and the battery when it changed since the last report."""
        _, keys = self._paired[addr]
        status = self._components[keys[0]]["status"]
        report = {k: status[k] for k in ("last_updated_ts", "packet_id", "rssi")}
        if status["battery"] is not None and status["battery"] != self._reported_battery.get(addr):
            report["battery"] = self._reported_battery[addr] = status["battery"]
        self._notify("NotifyStatus", {keys[0]: report})

    def blu_keys(self, addr: str) -> list[str]:
        """The component keys of a paired sensor: the bthomedevice first, then a bthomesensor per object."""
        return list(self._paired[addr][1])

    def restart_numbering(self) -> None:
        """The next pairings are numbered from 200 again (the real bridge reuses freed numbers); only with nothing
        paired, so no two components share a number."""
        assert not self._paired, "restart_numbering with sensors still paired"
        self._numbers = {BTHOME_DEVICE: 199, BTHOME_SENSOR: 199}

    def _next_number(self, kind: str) -> int:
        self._numbers[kind] += 1
        return self._numbers[kind]

    def _component_event(self, event: str, key: str) -> None:
        self._cfg_rev += 1
        now = round(self.device_now().timestamp(), 2)
        self._notify("NotifyEvent", {"events": [{"component": "sys", "event": event, "target": key,
                                                 "restart_required": False, "ts": now, "cfg_rev": self._cfg_rev}]})

    def _get_components(self, params: dict) -> dict:
        """Shelly.GetComponents: the dynamic components only (dynamic_only), 10 a page from offset, ordered by key
        type then number, as the real one."""
        if not params.get("dynamic_only"):
            raise RpcError(-103, "fake bridge: only dynamic_only is served")
        offset = params.get("offset", 0)
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise RpcError(-103, "Invalid argument 'offset'")
        ordered = sorted(self._components, key=lambda k: (k.split(":")[0], int(k.split(":")[1])))
        page = [{"key": k, **copy.deepcopy(self._components[k])} for k in ordered[offset:offset + COMPONENTS_PAGE]]
        return {"components": page, "cfg_rev": self._cfg_rev, "offset": offset, "total": len(ordered)}

    # --- faults -------------------------------------------------------------------------------------------------

    def fail_next(self, method: str, code: int = -103, message: str = "Argument 'on', value secret-ish not valid"):
        self._faults[method].append(("rpc", code, message))

    def hang_next(self, method: str) -> None:
        self._faults[method].append(("hang",))

    def drop_next(self, method: str) -> None:
        self._faults[method].append(("drop",))

    # --- for the models -----------------------------------------------------------------------------------------

    def device_info(self) -> dict:
        raise NotImplementedError

    def full_status(self) -> dict:
        raise NotImplementedError

    def _handle_own(self, method: str, params: dict) -> dict:
        raise RpcError(-32601, f"Method {method} not found")

    def device_now(self) -> datetime:
        """The device's clock: ours plus clock_skew."""
        return self._clock() + self.clock_skew

    def _unixtime(self) -> int:
        return int(self.device_now().timestamp())

    def _mac(self) -> str:
        return self.shelly_id.rsplit("-", 1)[-1].upper()

    def _check_id(self, params: dict) -> None:
        if params.get("id", 0) != 0:
            raise RpcError(-105, f"Argument 'id', value {params.get('id')} not found!")

    def _notify(self, method: str, status: dict, *, ts: datetime | None = None) -> None:
        """ts: the device's clock for the "ts" field, its now (device_now) by default; received_at is always our now."""
        now = self._clock()
        params = {"ts": round((ts or self.device_now()).timestamp(), 2)} | copy.deepcopy(status)
        for sink in self._sinks:
            sink(Notification(method=method, shelly_id=self.shelly_id, params=params, received_at=now))


# --- Plug M Gen3 ----------------------------------------------------------------------------------------------------

class FakePlugMG3(_FakeShelly):
    def __init__(self, shelly_id: str = "shellyplugmg3-000000000001", *, on: bool = False, load_watts: float = 12.2,
                 energy_wh: float = 0.0, clock: Callable[[], datetime] = utcnow):
        super().__init__(shelly_id, clock)
        self.protection_trips = False
        self._on = on
        self._load = float(load_watts)        # what the appliance draws when the relay is on
        self._energy = float(energy_wh)
        self._source = "init"

    def device_info(self) -> dict:
        return DEVICE_INFO                    # the module's dict, read at every call: a test may change it

    def _handle_own(self, method: str, params: dict) -> dict:
        if method == "Switch.GetStatus":
            self._check_id(params)
            return self._switch_status()
        if method == "Switch.Set":
            self._check_id(params)
            on = params.get("on")
            if not isinstance(on, bool):
                raise RpcError(-103, f"Invalid argument 'on': {on!r}")
            was_on = self._on
            self._switch(on and not self.protection_trips, "MQTT")
            return {"was_on": was_on}
        return super()._handle_own(method, params)

    # --- the world ----------------------------------------------------------------------------------------------

    def press_button(self) -> None:
        self._switch(not self._on, "button")

    def set_load(self, watts: float) -> None:
        old = self._apower()
        self._load = float(watts)
        if self._apower() != old:
            self._notify_power()

    def add_energy(self, wh: float) -> None:
        self._energy += wh
        self._notify("NotifyStatus", {"switch:0": {"aenergy": self._aenergy()}})

    def reboot(self) -> None:
        """The counter restarts from zero (the engine recognises the drop) and the device sends its full status."""
        self._energy = 0.0
        self._uptime = 0
        self._notify("NotifyFullStatus", self.full_status())

    # --- the device's state -------------------------------------------------------------------------------------

    @property
    def on(self) -> bool:
        return self._on

    def full_status(self) -> dict:
        return {"switch:0": self._switch_status(),
                "sys": {"mac": self._mac(), "uptime": self._uptime, "restart_required": False,
                        "unixtime": self._unixtime()}}

    def _apower(self) -> float:
        return self._load if self._on else 0.0

    def _current(self) -> float:
        return round(self._apower() / 224.1, 3)

    def _aenergy(self) -> dict:
        minute_ts = int(self._clock().timestamp()) // 60 * 60
        return {"total": self._energy, "by_minute": [0.0, 0.0, 0.0], "minute_ts": minute_ts}

    def _switch_status(self) -> dict:
        return {"id": 0, "source": self._source, "output": self._on, "apower": self._apower(), "voltage": 224.1,
                "freq": 50.1, "current": self._current(), "aenergy": self._aenergy(),
                "ret_aenergy": {"total": 0.0, "by_minute": [0.0, 0.0, 0.0], "minute_ts": self._aenergy()["minute_ts"]},
                "temperature": {"tC": 46.7, "tF": 116.1}}

    def _switch(self, on: bool, source: str) -> None:
        if on == self._on:
            return
        old_power = self._apower()
        self._on, self._source = on, source
        if not on:
            self._notify("NotifyStatus", {"switch:0": {"output": False, "source": source, "apower": 0, "current": 0}})
            return
        self._notify("NotifyStatus", {"switch:0": {"output": True, "source": source}})
        if self._apower() != old_power:
            self._notify_power()

    def _notify_power(self) -> None:
        self._notify("NotifyStatus", {"switch:0": {"apower": self._apower()}})
        self._notify("NotifyStatus", {"switch:0": {"current": self._current()}})


# --- Shelly 1 Gen4 --------------------------------------------------------------------------------------------------

class FakeS1G4(_FakeShelly):
    def __init__(self, shelly_id: str = "shelly1g4-000000000002", *, on: bool = False,
                 clock: Callable[[], datetime] = utcnow):
        super().__init__(shelly_id, clock)
        self._on = on
        self._source = "init"
        self._switch_on = 0           # counts.switch_on

    def device_info(self) -> dict:
        return S1G4_DEVICE_INFO

    def _handle_own(self, method: str, params: dict) -> dict:
        if method == "Switch.GetStatus":
            self._check_id(params)
            return self._switch_status()
        if method == "Switch.Set":
            self._check_id(params)
            on = params.get("on")
            if not isinstance(on, bool):
                raise RpcError(-103, f"Invalid argument 'on': {on!r}")
            was_on = self._on
            self._switch(on, "MQTT")
            return {"was_on": was_on}
        return super()._handle_own(method, params)

    # --- the world ----------------------------------------------------------------------------------------------

    def press_button(self) -> None:
        self._switch(not self._on, "button")

    def minute(self) -> None:
        """The NotifyStatus the real one sends every minute: switch:0.counts only."""
        self._notify("NotifyStatus", {"switch:0": {"counts": self._counts()}})

    def reboot(self) -> None:
        """Back from a restart: source "init" and the full status, as in the capture."""
        self._uptime, self._source = 0, "init"
        self._notify("NotifyFullStatus", self.full_status())

    # --- the device's state -------------------------------------------------------------------------------------

    @property
    def on(self) -> bool:
        return self._on

    def full_status(self) -> dict:
        return {"ble": {"addr": "02:00:00:00:01:02,p", "flags": ["advertising"]}, "bthome": {},
                "cloud": {"connected": False}, "input:0": {"id": 0, "state": False}, "knx": {},
                "matter": {"num_fabrics": 0, "commissionable": True}, "modbus": {}, "mqtt": {"connected": True},
                "switch:0": self._switch_status(),
                "sys": {"mac": self._mac(), "restart_required": False, "uptime": self._uptime, "utc_offset": 3600,
                        "unixtime": self._unixtime()},
                "wifi": {"status": "got ip", "rssi": -38}, "ws": {"connected": False}}

    def _counts(self) -> dict:
        return {"on_time": 0, "on_time_rst_ts": 0, "switch_on": self._switch_on, "switch_on_rst_ts": 0}

    def _switch_status(self) -> dict:
        return {"id": 0, "source": self._source, "tag": None, "output": self._on, "counts": self._counts(),
                "temperature": {"tC": 50.9, "tF": 123.7}}

    def _switch(self, on: bool, source: str) -> None:
        if on == self._on:
            return
        self._on, self._source = on, source
        if on:
            self._switch_on += 1
        self._notify("NotifyStatus", {"switch:0": {"output": on, "source": source}})


# --- EM Mini Gen4 ---------------------------------------------------------------------------------------------------

class FakeMiniEMG4(_FakeShelly):
    def __init__(self, shelly_id: str = "shellyemminig4-000000000003", *, load_watts: float = 0.0,
                 energy_wh: float = 0.0, em1_delay_s: float = EM1_DELAY_S, clock: Callable[[], datetime] = utcnow):
        super().__init__(shelly_id, clock)
        self.em1_delay_s = em1_delay_s
        self._load = float(load_watts)
        self._energy = float(energy_wh)

    def device_info(self) -> dict:
        return MINIEMG4_DEVICE_INFO

    def _handle_own(self, method: str, params: dict) -> dict:
        if method == "EM1.GetStatus":
            self._check_id(params)
            return self._em1()
        if method == "EM1Data.GetStatus":
            self._check_id(params)
            return self._em1data()
        return super()._handle_own(method, params)

    # --- the world ----------------------------------------------------------------------------------------------

    def set_load(self, watts: float) -> None:
        """Silent: the real meter tells it at its next em1:0 (report_power)."""
        self._load = float(watts)

    def add_energy(self, wh: float) -> None:
        """Silent: the real meter tells it at its next em1data:0 (report_energy)."""
        self._energy += wh

    def report_power(self) -> None:
        """The em1:0 NotifyStatus, with its ts em1_delay_s before now (the reception)."""
        em1 = {k: v for k, v in self._em1().items() if k in ("act_power", "current", "freq", "voltage")}
        self._notify("NotifyStatus", {"em1:0": em1}, ts=self.device_now() - timedelta(seconds=self.em1_delay_s))

    def report_energy(self) -> None:
        """The em1data:0 NotifyStatus, then its NotifyEvent "data" (the last minute's record), as in the capture."""
        self._notify("NotifyStatus", {"em1data:0": {"total_act_energy": self._energy, "total_act_ret_energy": 0.0}})
        minute = int(self._clock().timestamp()) // 60 * 60 - 60
        self._notify("NotifyEvent", {"events": [{"component": "em1data:0", "id": 0, "event": "data",
                                                 "ts": float(minute),
                                                 "data": {"ts": minute, "period": 60, "values": [[0.0] * 14]}}]})

    # --- the device's state -------------------------------------------------------------------------------------

    def full_status(self) -> dict:
        return {"ble": {}, "bthome": {}, "cloud": {"connected": False}, "em1:0": self._em1(),
                "em1data:0": self._em1data(), "matter": {"num_fabrics": 0, "commissionable": True}, "modbus": {},
                "mqtt": {"connected": True},
                "sys": {"mac": self._mac(), "restart_required": False, "uptime": self._uptime, "utc_offset": 3600,
                        "unixtime": self._unixtime()},
                "wifi": {"status": "got ip", "rssi": -47}, "ws": {"connected": False}}

    def _em1(self) -> dict:
        return {"id": 0, "voltage": 224.7, "current": round(self._load / 224.7, 3), "act_power": self._load,
                "freq": 50.1, "calibration": "factory"}

    def _em1data(self) -> dict:
        return {"id": 0, "total_act_energy": self._energy, "total_act_ret_energy": 0.0}
