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


def utcnow() -> datetime:
    return datetime.now(UTC)


class _FakeShelly:
    """What every fake device shares. A model gives device_info(), full_status() and its own RPCs (_handle_own)."""

    def __init__(self, shelly_id: str, clock: Callable[[], datetime]):
        self.shelly_id = shelly_id
        self.online = True
        self._clock = clock
        self._uptime = 0
        self._faults: dict[str, deque] = defaultdict(deque)
        self._sinks: list[Callable[[Notification], None]] = []

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
        return self._handle_own(method, params)

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

    def _mac(self) -> str:
        return self.shelly_id.rsplit("-", 1)[-1].upper()

    def _check_id(self, params: dict) -> None:
        if params.get("id", 0) != 0:
            raise RpcError(-105, f"Argument 'id', value {params.get('id')} not found!")

    def _notify(self, method: str, status: dict, *, ts: datetime | None = None) -> None:
        """ts: the device's clock for the "ts" field, now by default; received_at is always now."""
        now = self._clock()
        params = {"ts": round((ts or now).timestamp(), 2)} | copy.deepcopy(status)
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
                "sys": {"mac": self._mac(), "uptime": self._uptime, "restart_required": False}}

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
                "sys": {"mac": self._mac(), "restart_required": False, "uptime": self._uptime, "utc_offset": 3600},
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
        self._notify("NotifyStatus", {"em1:0": em1}, ts=self._clock() - timedelta(seconds=self.em1_delay_s))

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
                "sys": {"mac": self._mac(), "restart_required": False, "uptime": self._uptime, "utc_offset": 3600},
                "wifi": {"status": "got ip", "rssi": -47}, "ws": {"connected": False}}

    def _em1(self) -> dict:
        return {"id": 0, "voltage": 224.7, "current": round(self._load / 224.7, 3), "act_power": self._load,
                "freq": 50.1, "calibration": "factory"}

    def _em1data(self) -> dict:
        return {"id": 0, "total_act_energy": self._energy, "total_act_ret_energy": 0.0}
