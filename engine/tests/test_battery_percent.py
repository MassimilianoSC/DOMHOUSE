"""battery_percent (contract 1.0.6, risposta 1143, 16 November 2026): the level a battery-powered device last sent,
from DeviceInfo.battery_percent of the connector, as an integer 0-100 in GET /devices and in the device.state and
device.online events of that device. Absent when the connector has no level (a mains-powered device, or a battery one
not heard yet). The engine reads the levels again once a minute (housekeeping): a new level is in GET /devices from
then, and in the next event of the device; it makes no event of its own.

Run: python -m pytest engine/tests/test_battery_percent.py -q
"""
from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
SENSOR, WINDOW, SOCKET = "dev-ambiente-soggiorno", "dev-finestra-camera", "dev-presa-camera"


def engine() -> tuple[core.ApartmentEngine, SimulatedConnector]:
    connector = SimulatedConnector()
    return core.ApartmentEngine("apt-prova-01", connector, seed=False), connector


def last(e, event: str, device_id: str) -> dict:
    return next(x["data"] for x in reversed(e.events) if x["event"] == event and x["data"]["device_id"] == device_id)


def test_get_devices_has_the_level_of_battery_devices_only_as_an_integer():
    e, _ = engine()
    assert e.devices[WINDOW]["battery_percent"] == 88 and type(e.devices[WINDOW]["battery_percent"]) is int
    assert e.devices[SENSOR]["battery_percent"] == 64
    assert "battery_percent" not in e.devices[SOCKET]                  # mains-powered: absent


def test_a_new_level_is_read_once_a_minute_and_travels_with_the_device_events():
    e, connector = engine()
    connector._devices[SENSOR].battery_percent = 15.4
    n = len(e.events)
    e.housekeeping()
    assert e.devices[SENSOR]["battery_percent"] == 15
    assert len(e.events) == n                                           # no event of its own
    e.test_state({"device_id": SENSOR, "online": False}, ACTOR, CORR)
    assert last(e, "device.online", SENSOR)["battery_percent"] == 15
    e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": 19.5}}, ACTOR, CORR)
    assert last(e, "device.state", SENSOR)["battery_percent"] == 15


def test_a_mains_device_has_no_battery_in_its_events():
    e, _ = engine()
    e.test_state({"device_id": SOCKET, "online": False}, ACTOR, CORR)
    assert "battery_percent" not in last(e, "device.online", SOCKET)


def test_out_of_range_is_bounded_and_a_level_no_longer_known_goes_away():
    e, connector = engine()
    connector._devices[SENSOR].battery_percent = 104.0
    connector._devices[WINDOW].battery_percent = None
    e.housekeeping()
    assert e.devices[SENSOR]["battery_percent"] == 100
    assert "battery_percent" not in e.devices[WINDOW]


def test_the_level_after_a_restart_is_the_connectors(tmp_path):
    from engine.store import SqliteStore
    db = tmp_path / "engine.db"
    first = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    first.store.close()
    connector = SimulatedConnector()
    connector._devices[WINDOW].battery_percent = 40.0
    again = core.ApartmentEngine("apt-prova-01", connector, seed=False, store=SqliteStore(db))
    assert again.devices[WINDOW]["battery_percent"] == 40
    again.store.close()
