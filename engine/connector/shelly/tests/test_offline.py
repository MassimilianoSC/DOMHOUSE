"""Offline thresholds per device type (engine/connector/shelly/offline.py, connector.md §2.6 and §5).

Run: python -m pytest engine/connector/shelly/tests -q
"""
import pytest

from engine.connector.shelly.offline import (CONTRACT_DEFAULT_S, DEFAULT_PATH, DEVICE_TYPES, OfflineThresholdsError,
                                             is_offline, load_thresholds)

# the beacon intervals from the official Shelly BLU documentation (docs-ble, 5 November 2026), except the
# Door/Window's: the documentation said 60 s, the sensor measured on the bench sends every ~300 s (11 November 2026)
BEACON_S = {"blu_ht": 60, "blu_door_window": 300, "blu_motion": 900}
# the rule of offline_thresholds.toml: three beacon periods plus 20 s of radio delay for the third beacon
MARGIN_S = 20
# the exceptions to the rule, decided in the review of PR #7: the H&T regulates the heating, a false offline stops it
RULE_EXCEPTIONS_S = {"blu_ht": 300}


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


def test_silence_equal_to_the_threshold_is_still_online():
    """connector.md §2.6: offline when the silence goes BEYOND the threshold."""
    assert not is_offline(120.0, 120.0)
    assert is_offline(120.001, 120.0)
    assert not is_offline(0.0, 120.0)


@pytest.mark.parametrize("kind", sorted(set(BEACON_S) - set(RULE_EXCEPTIONS_S)))
def test_battery_sensors_survive_two_missed_beacons_and_go_offline_at_the_third(kind):
    """Silence counts from the last beacon received. A healthy BLU sensor misses a beacon now and then (radio): with
    two missed and the third arriving up to MARGIN_S late it stays online; when the third is missed too it goes
    offline MARGIN_S after it was due, well before the fourth. Otherwise a sane Motion (900 s beacon) would be
    declared offline several times an hour, or a dead one would stay online for an hour."""
    beacon = BEACON_S[kind]
    threshold = load_thresholds().for_device(device(kind))
    assert threshold == 3 * beacon + MARGIN_S
    assert not is_offline(2 * beacon, threshold)                  # one missed, the second arrives
    assert not is_offline(3 * beacon, threshold)                  # two missed, the third on time
    assert not is_offline(3 * beacon + MARGIN_S, threshold)       # the third late by the whole margin: the boundary
    assert is_offline(3 * beacon + MARGIN_S + 0.001, threshold)   # just past the boundary
    assert is_offline(4 * beacon - 1, threshold)                  # three missed: offline before the fourth is due


def test_ht_threshold_is_the_exception_300_s():
    """The H&T (a beacon every 60 s) is the sensor of the heating: 300 s, not the rule's 3 × 60 + 20 = 200. Four
    beacons missed and the fifth on time still online; offline only past 300 s."""
    beacon, threshold = BEACON_S["blu_ht"], load_thresholds().for_device(device("blu_ht"))
    assert threshold == RULE_EXCEPTIONS_S["blu_ht"] == 300.0
    assert threshold > 3 * beacon + MARGIN_S
    assert not is_offline(5 * beacon, threshold)                  # four missed, the fifth on time
    assert not is_offline(300.0, threshold)                       # the boundary
    assert is_offline(300.001, threshold)


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


def test_env_value_is_checked_but_decides_no_device():
    """Every device has a type, so SHELLY_OFFLINE_AFTER_S no longer reaches any threshold; it is still read."""
    th = load_thresholds(env={"SHELLY_OFFLINE_AFTER_S": "300"})
    assert th.fallback_s == 300.0
    assert th.for_device(device("relay")) == CONTRACT_DEFAULT_S  # the file, not the env
    assert th.for_device(device("blu_motion")) == 3 * BEACON_S["blu_motion"] + MARGIN_S


@pytest.mark.parametrize("shelly", [device(), None, {}, device(offline_after_s=60), device(type=None)])
def test_device_without_type_is_refused(shelly):
    """type is mandatory: no fallback to SHELLY_OFFLINE_AFTER_S or to 120 s, not even with offline_after_s."""
    for env in ({}, {"SHELLY_OFFLINE_AFTER_S": "300"}):
        with pytest.raises(OfflineThresholdsError) as err:
            load_thresholds(env=env).for_device(shelly, device_id="dev-x")
        assert str(err.value) == "catalog device dev-x: shelly.type is missing"


def test_override_still_needs_a_known_type():
    with pytest.raises(OfflineThresholdsError, match="dev-x: shelly.type is not one of the known device types"):
        load_thresholds().for_device(device("blu_trv", offline_after_s=60), device_id="dev-x")


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
                                    device("relay", offline_after_s=True), device("relay", offline_after_s=[120]),
                                    device("relay", offline_after_s={"s": 120}),
                                    device("relay", offline_after_s=None)])
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


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), 10 ** 400])
def test_catalog_threshold_must_be_finite(value):
    """nan or inf would keep the device online forever; the message names the device and the field, not the value."""
    with pytest.raises(OfflineThresholdsError) as err:
        load_thresholds().for_device(device("relay", offline_after_s=value), device_id="dev-x")
    msg = str(err.value)
    assert "dev-x" in msg and "shelly.offline_after_s" in msg and "finite" in msg
    assert "nan" not in msg.lower() and "inf" not in msg.lower().replace("finite", "")


@pytest.mark.parametrize("shelly", [["relay"], "relay", 7])
def test_shelly_section_that_is_not_a_mapping_is_refused(shelly):
    with pytest.raises(OfflineThresholdsError, match="dev-x: the shelly section must be a mapping"):
        load_thresholds().for_device(shelly, device_id="dev-x")


@pytest.mark.parametrize("value", ["inf", "-inf", "nan"])
def test_file_threshold_must_be_finite(tmp_path, value):
    own = tmp_path / "soglie.toml"
    own.write_text(types_toml(relay=value))        # TOML accepts inf and nan as floats
    with pytest.raises(OfflineThresholdsError) as err:
        load_thresholds(path=own)
    msg = str(err.value)
    assert "types.relay" in msg and "finite" in msg
    assert "nan" not in msg.lower() and "inf" not in msg.lower().replace("finite", "")


@pytest.mark.parametrize("value", ["inf", "nan", "1e999", "Infinity"])
def test_env_threshold_must_be_finite(value):
    with pytest.raises(OfflineThresholdsError) as err:
        load_thresholds(env={"SHELLY_OFFLINE_AFTER_S": value})
    msg = str(err.value)
    assert "SHELLY_OFFLINE_AFTER_S" in msg and "finite" in msg
    assert value.lower() not in msg.lower().replace("finite", "")


def _clean(err) -> None:
    """Our message alone: no chained exception (no raw traceback in the log)."""
    assert err.value.__cause__ is None
    assert err.value.__context__ is None or err.value.__suppress_context__


def test_file_that_is_not_utf8_is_refused(tmp_path):
    own = tmp_path / "soglie.toml"
    own.write_bytes(types_toml().encode() + b"# soglie del caff\xe8\n")    # latin-1, not UTF-8
    with pytest.raises(OfflineThresholdsError) as err:
        load_thresholds(path=own)
    assert str(err.value) == "offline thresholds file is not valid UTF-8"
    _clean(err)


def test_path_that_is_a_folder_is_refused(tmp_path):
    with pytest.raises(OfflineThresholdsError) as err:
        load_thresholds(path=tmp_path)
    assert str(err.value) == "offline thresholds path is a folder, not a file"
    _clean(err)


def test_missing_file_from_the_env_names_the_variable_not_the_path(tmp_path):
    missing = tmp_path / "segreto-nome-file.toml"
    with pytest.raises(OfflineThresholdsError) as err:
        load_thresholds(env={"SHELLY_OFFLINE_THRESHOLDS_PATH": str(missing)})
    assert str(err.value) == "offline thresholds file not found (SHELLY_OFFLINE_THRESHOLDS_PATH)"
    assert "segreto-nome-file" not in str(err.value)
    _clean(err)


def test_folder_and_bad_encoding_from_the_env_name_the_variable(tmp_path):
    with pytest.raises(OfflineThresholdsError, match=r"folder, not a file \(SHELLY_OFFLINE_THRESHOLDS_PATH\)"):
        load_thresholds(env={"SHELLY_OFFLINE_THRESHOLDS_PATH": str(tmp_path)})
    own = tmp_path / "soglie.toml"
    own.write_bytes(b"[types]\nrelay = 120 # \xe8\n")
    with pytest.raises(OfflineThresholdsError, match=r"not valid UTF-8 \(SHELLY_OFFLINE_THRESHOLDS_PATH\)"):
        load_thresholds(env={"SHELLY_OFFLINE_THRESHOLDS_PATH": str(own)})


def test_invalid_toml_does_not_leak_the_content(tmp_path):
    own = tmp_path / "soglie.toml"
    own.write_text("relay = password-like-value [[[")
    with pytest.raises(OfflineThresholdsError) as err:
        load_thresholds(path=own)
    assert "password" not in str(err.value)
    _clean(err)


def test_missing_file_and_bad_env_are_refused(tmp_path):
    with pytest.raises(OfflineThresholdsError, match="not found"):
        load_thresholds(path=tmp_path / "nope.toml")
    with pytest.raises(OfflineThresholdsError, match="SHELLY_OFFLINE_AFTER_S"):
        load_thresholds(env={"SHELLY_OFFLINE_AFTER_S": "two minutes"})
    with pytest.raises(OfflineThresholdsError, match="SHELLY_OFFLINE_AFTER_S"):
        load_thresholds(env={"SHELLY_OFFLINE_AFTER_S": "0"})
