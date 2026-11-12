"""Battery level of the BLU sensors (connector.md §2.3 note on DeviceInfo.battery_percent).

Every Shelly BLU sensor (H&T ZB, Door/Window ZB, Motion ZB) puts the BTHome object 0x01 «battery %» (uint8, 0-100)
in each beacon, in the forced packets on events and in the periodic firmware-id packet. The bridging relay exposes
it as a BTHomeSensor component with obj_id 1, and every change comes out as a NotifyStatus on the transport. So the
level reaches the connector for free: no polling, no extra RPC.

This module is pure: it reads a BTHomeSensor status and says whether it is a battery reading, and it decides when to
warn. The ShellyConnector keeps the last level per device (also after the sensor goes offline: a flat battery and a
sensor out of reach look the same from the silence, the level tells them apart) and warns once per device when the
level drops to LOW_PERCENT or below. 15 % is the threshold the sensors themselves use for their Zigbee «battery low»
flag, so our log and the Shelly app agree.
"""
from dataclasses import dataclass, field

BTHOME_BATTERY_OBJ_ID = 1      # BTHome object 0x01: battery level in percent
LOW_PERCENT = 15.0             # the sensors' own «battery low» flag (Zigbee IAS Zone bit 3) is at <= 15 %


def battery_level(value) -> float | None:
    """A battery percent as reported (an integer 0-100) -> float, clamped to 0-100; None for null or another type."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(min(100, max(0, value)))


def battery_from_bthome_sensor(status: dict) -> float | None:
    """The battery level in a BTHomeSensor status (`{"id": 200, "obj_id": 1, "value": 93, ...}`), or None when the
    component is another sensor (temperature, humidity, window...) or carries no usable value."""
    if status.get("obj_id") != BTHOME_BATTERY_OBJ_ID:
        return None
    return battery_level(status.get("value"))


def battery_from_bthome_device(status: dict) -> float | None:
    """The battery level in a BTHomeDevice status (`{"id": 200, "battery": 100, "packet_id": 16, ...}`), or None when
    the status carries none (the notifications carry it only now and then). The ShellyConnector reads both sources,
    this one and the obj_id 1 BTHomeSensor (the bthomesensor's value, with battery_level), into one BatteryTracker:
    the last value that arrived counts."""
    value = status.get("battery") if isinstance(status, dict) else None
    return battery_level(value)


@dataclass
class BatteryTracker:
    """Last known level per device and the «warn once» rule.

    update() returns True when a «battery low» warning must be logged now: the level is at or below LOW_PERCENT and
    either it is the first time or the battery had meanwhile been replaced (level back above the threshold). The
    connector logs the warning with the device id and the percent; the alerts read the message."""
    low_percent: float = LOW_PERCENT
    levels: dict[str, float] = field(default_factory=dict)
    _warned: set[str] = field(default_factory=set)

    def update(self, device_id: str, percent: float) -> bool:
        self.levels[device_id] = percent
        if percent > self.low_percent:
            self._warned.discard(device_id)       # battery replaced: warn again next time it runs down
            return False
        if device_id in self._warned:
            return False
        self._warned.add(device_id)
        return True

    def level(self, device_id: str) -> float | None:
        """The last level reported, kept after the device goes offline."""
        return self.levels.get(device_id)
