"""Offline thresholds per device type (engine/connector/shelly/offline.py, connector.md §2.6 and §5).

Run: python -m pytest engine/connector/shelly/tests -q
"""
import pytest

from engine.connector.shelly.offline import (CONTRACT_DEFAULT_S, DEFAULT_PATH, DEVICE_TYPES, OfflineThresholdsError,
                                             load_thresholds)

# the beacon intervals from the official Shelly BLU documentation (docs-ble, 5 November 2026)
BEACON_S = {"blu_ht": 60, "blu_door_window": 60, "blu_motion": 900}


def types_toml(**override) -> str:
    """A [types] table with 120 for every known type, the given keys replaced or added (TOML refuses duplicates)."""
    values = {k: 120 for k in DEVICE_TYPES} | override
    return "[types]\n" + "\n".join(f"{k} = {v}" for k, v in values.items()) + "\n"


def device(kind=None, **extra):
    shelly = {"id": "shelly-test"}
    if kind:
        shelly["type"] = kind
    shelly.update(extra)
    return shelly


# --- the file shipped with the package ---------------------------------------------------------------------------

def test_shipped_file_covers_every_type():
    th = load_thresholds()
    assert th.source == DEFAULT_PATH
    assert set(th.by_type) == set(DEVICE_TYPES)
    assert all(v > 0 for v in th.by_type.values())


def test_powered_devices_keep_the_contract_default():
    th = load_thresholds()
    for kind in ("relay", "plug", "energy_meter", "ir_blaster"):
        assert th.for_device(device(kind)) == CONTRACT_DEFAULT_S, kind


@pytest.mark.parametrize("kind", sorted(BEACON_S))
def test_battery_sensors_survive_three_missed_beacons(kind):
    """A healthy BLU sensor misses a beacon now and then (radio): two missed must not mean offline, three plus
    a margin must. Otherwise a sane Motion (900 s beacon) would be declared offline several times an hour."""
    th = load_thresholds()
    threshold = th.for_device(device(kind))
    assert threshold > 2 * BEACON_S[kind]
    assert threshold >= 3 * BEACON_S[kind]
    assert threshold <= 3 * BEACON_S[kind] + 60


def test_motion_is_not_declared_offline_between_beacons():
    """The Motion case Massimiliano asked for: 15 minutes of silence from a BLU Motion is normal."""
    th = load_thresholds()
    motion = th.for_device(device("blu_motion"), device_id="dev-movimento-ingresso")
    assert motion > 900 + 60                      # one beacon period plus a generous radio delay
    assert motion > th.for_device(device("relay"))  # and well above a powered relay
    # while a relay silent for 15 minutes is offline long before that
    assert th.for_device(device("relay")) < 900


# --- precedence: device override > type > env > contract default -----------------------------------------------

def test_single_device_override_wins_over_its_type():
    th = load_thresholds()
    # a Motion with beacon mode on (30 s): the installer lowers it in the catalog
    assert th.for_device(device("blu_motion", offline_after_s=110)) == 110.0
    assert th.for_device(device("relay", offline_after_s=45)) == 45.0


def test_env_fallback_applies_only_to_untyped_devices():
    th = load_thresholds(env={"SHELLY_OFFLINE_AFTER_S": "300"})
    assert th.fallback_s == 300.0
    assert th.for_device(device()) == 300.0                     # no type: the process-wide value
    assert th.for_device(device("relay")) == CONTRACT_DEFAULT_S  # typed: the file wins
    assert th.for_device(device("blu_motion")) > 300


def test_untyped_device_without_env_gets_the_contract_default():
    th = load_thresholds(env={})
    assert th.for_device(device()) == CONTRACT_DEFAULT_S
    assert th.for_device(None) == CONTRACT_DEFAULT_S


def test_apartment_file_replaces_the_shipped_one(tmp_path):
    own = tmp_path / "soglie.toml"
    own.write_text(types_toml(blu_motion=3000, **{k: 10 for k in DEVICE_TYPES if k != "blu_motion"}))
    th = load_thresholds(env={"SHELLY_OFFLINE_THRESHOLDS_PATH": str(own)})
    assert th.source == own
    assert th.for_device(device("blu_motion")) == 3000.0
    assert th.for_device(device("relay")) == 10.0


# --- errors name the place, never the value (connector.md §2.7) --------------------------------------------------

@pytest.mark.parametrize("shelly", [device("blu_trv"), device(type=7), device("relay", offline_after_s=0),
                                    device("relay", offline_after_s=-5), device("relay", offline_after_s="120"),
                                    device("relay", offline_after_s=True)])
def test_bad_catalog_entry_is_refused_without_echoing_the_value(shelly):
    th = load_thresholds()
    with pytest.raises(OfflineThresholdsError) as err:
        th.for_device(shelly, device_id="dev-x")
    msg = str(err.value)
    assert "dev-x" in msg and ("shelly.type" in msg or "shelly.offline_after_s" in msg)
    assert "blu_trv" not in msg and "-5" not in msg and "120" not in msg


@pytest.mark.parametrize("text, part", [
    ("", "missing [types]"),
    ("[types]\nrelay = 120\n", "lacks"),
    (types_toml(blu_trv=100), "unknown device type"),
    (types_toml(blu_motion=0), "greater than zero"),
    (types_toml(blu_motion="'x'"), "number of seconds"),
    ("not toml at all [[[", "not valid TOML"),
])
def test_bad_file_is_refused(tmp_path, text, part):
    own = tmp_path / "soglie.toml"
    own.write_text(text)
    with pytest.raises(OfflineThresholdsError) as err:
        load_thresholds(path=own)
    assert part in str(err.value)


def test_missing_file_and_bad_env_are_refused(tmp_path):
    with pytest.raises(OfflineThresholdsError, match="not found"):
        load_thresholds(path=tmp_path / "nope.toml")
    with pytest.raises(OfflineThresholdsError, match="SHELLY_OFFLINE_AFTER_S"):
        load_thresholds(env={"SHELLY_OFFLINE_AFTER_S": "two minutes"})
    with pytest.raises(OfflineThresholdsError, match="SHELLY_OFFLINE_AFTER_S"):
        load_thresholds(env={"SHELLY_OFFLINE_AFTER_S": "0"})
