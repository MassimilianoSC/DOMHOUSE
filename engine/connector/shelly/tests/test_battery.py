"""Battery level of the BLU sensors (engine/connector/shelly/battery.py).

Run: python -m pytest engine/connector/shelly/tests -q
"""
import pytest

from engine.connector.shelly.battery import LOW_PERCENT, BatteryTracker, battery_from_bthome_sensor


def bthome(obj_id, value, cid=200):
    """A BTHomeSensor status as the bridging relay notifies it."""
    return {"id": cid, "obj_id": obj_id, "value": value, "last_updated_ts": 1_762_000_000}


# --- reading the BTHome object -------------------------------------------------------------------------------------

def test_battery_object_is_read_as_percent():
    assert battery_from_bthome_sensor(bthome(1, 93)) == 93.0
    assert battery_from_bthome_sensor(bthome(1, 0)) == 0.0
    assert battery_from_bthome_sensor(bthome(1, 100)) == 100.0


@pytest.mark.parametrize("obj_id, value", [(2, 21.5), (3, 48), (0x2D, 1), (0x21, 1), (0x64, 2)])
def test_other_bthome_objects_are_not_a_battery(obj_id, value):
    """temperature, humidity, window, motion, light level: all carry a value, none is the battery."""
    assert battery_from_bthome_sensor(bthome(obj_id, value)) is None


@pytest.mark.parametrize("value", [None, "93", True, [93]])
def test_unusable_values_are_ignored(value):
    assert battery_from_bthome_sensor(bthome(1, value)) is None


def test_out_of_range_values_are_clamped():
    assert battery_from_bthome_sensor(bthome(1, 130)) == 100.0
    assert battery_from_bthome_sensor(bthome(1, -3)) == 0.0


# --- the tracker: last known level and «warn once» ----------------------------------------------------------------

def test_level_is_kept_per_device_and_survives_silence():
    """A Motion that stops beaconing with 4 % left: the level stays readable, that is the whole point."""
    t = BatteryTracker()
    t.update("dev-movimento-ingresso", 4.0)
    t.update("dev-finestra-camera", 88.0)
    assert t.level("dev-movimento-ingresso") == 4.0
    assert t.level("dev-finestra-camera") == 88.0
    assert t.level("dev-caldaia") is None        # mains powered, never reported


def test_warns_once_when_crossing_the_sensors_own_threshold():
    t = BatteryTracker()
    assert t.update("dev-x", 40.0) is False
    assert t.update("dev-x", 16.0) is False       # above 15: the sensors' flag is not up yet
    assert t.update("dev-x", 15.0) is True        # the Zigbee «battery low» flag is at <= 15 %
    assert t.update("dev-x", 14.0) is False       # the Motion beacons every 15 min: no log flood
    assert t.update("dev-x", 3.0) is False


def test_warns_again_after_the_battery_is_replaced():
    t = BatteryTracker()
    assert t.update("dev-x", 10.0) is True
    assert t.update("dev-x", 100.0) is False      # new battery
    assert t.update("dev-x", 12.0) is True        # ran down again, months later


def test_devices_are_independent():
    t = BatteryTracker()
    assert t.update("dev-a", 5.0) is True
    assert t.update("dev-b", 5.0) is True
    assert t.update("dev-a", 5.0) is False


def test_threshold_matches_the_sensors_flag():
    assert LOW_PERCENT == 15.0
