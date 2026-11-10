"""A fake Shelly Plug M Gen3 (Gen2+ RPC API), for the tests of the Shelly connector (connector.md §3, §4).

It answers the RPCs the connector uses with the shapes of the real plug on the bench (firmware 1.8.99, sample of
10 November 2026, ids invented as connector.md §5 asks) and sends NotifyStatus with only the changed fields, as the
real device does in tests/fixtures/plugmg3_mqtt_capture.jsonl:
  - switching off: ONE NotifyStatus with output, source, apower and current (the zeros as integers, as in the JSON);
  - switching on: first output and source, then apower, then current, in separate messages;
  - a change of load: apower, then current, in separate messages.
A Switch.Set reports source "MQTT", as the real plug does when the command comes over MQTT. It is synchronous and has
no timer: delays and timeouts belong to tests/fake_transport.py, which reads the faults queued here.

The world around the plug: press_button, set_load, add_energy, reboot. The faults: fail_next (an RPC error),
hang_next (no answer), drop_next (the connection drops during that RPC), protection_trips (the relay refuses to switch
on, as the overpower protection does). Each queued fault applies to the next call of that method only.
"""
import copy
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime

from engine.connector.shelly.transport.base import Notification, RpcError

DEVICE_INFO = {"name": None, "id": "shellyplugmg3-000000000001", "mac": "000000000001", "slot": 1,
               "model": "S3PL-30110EU", "gen": 3, "fw_id": "20251209-070625/geeb7eab", "ver": "1.8.99-plugmg3prod0",
               "app": "PlugMG3", "auth_en": False, "auth_domain": None, "matter": True}


def utcnow() -> datetime:
    return datetime.now(UTC)


class FakePlugMG3:
    def __init__(self, shelly_id: str = "shellyplugmg3-000000000001", *, on: bool = False, load_watts: float = 12.2,
                 energy_wh: float = 0.0, clock: Callable[[], datetime] = utcnow):
        self.shelly_id = shelly_id
        self.online = True
        self.protection_trips = False
        self._clock = clock
        self._on = on
        self._load = float(load_watts)        # what the appliance draws when the relay is on
        self._energy = float(energy_wh)
        self._source = "init"
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
            return copy.deepcopy(DEVICE_INFO | {"id": self.shelly_id, "mac": self.shelly_id.rsplit("-", 1)[-1].upper()})
        if method == "Shelly.GetStatus":
            return self.full_status()
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
        raise RpcError(-32601, f"Method {method} not found")

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

    # --- faults -------------------------------------------------------------------------------------------------

    def fail_next(self, method: str, code: int = -103, message: str = "Argument 'on', value secret-ish not valid"):
        self._faults[method].append(("rpc", code, message))

    def hang_next(self, method: str) -> None:
        self._faults[method].append(("hang",))

    def drop_next(self, method: str) -> None:
        self._faults[method].append(("drop",))

    # --- the device's state -------------------------------------------------------------------------------------

    @property
    def on(self) -> bool:
        return self._on

    def full_status(self) -> dict:
        return {"switch:0": self._switch_status(),
                "sys": {"mac": self.shelly_id.rsplit("-", 1)[-1].upper(), "uptime": self._uptime,
                        "restart_required": False}}

    def _check_id(self, params: dict) -> None:
        if params.get("id", 0) != 0:
            raise RpcError(-105, f"Argument 'id', value {params.get('id')} not found!")

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

    def _notify(self, method: str, status: dict) -> None:
        now = self._clock()
        params = {"ts": round(now.timestamp(), 2)} | copy.deepcopy(status)
        for sink in self._sinks:
            sink(Notification(method=method, shelly_id=self.shelly_id, params=params, received_at=now))
