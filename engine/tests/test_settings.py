"""The rules' thresholds as settings of the engine per apartment (P-60 step 7e, D-133): defaults, limits (out of range,
the engine does not start) and the effect of each one. The thresholds the app changes stay in /rules.

Run: python -m pytest engine/tests -q
"""
from datetime import UTC, datetime, timedelta

import pytest

from engine import core
from engine.config import DEFAULT_SETTINGS, SETTINGS, ConfigError, load_config
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

BASE = {"APARTMENT_ID": "apt-prova-01", "API_KEY": "k" * 16, "CONNECTOR": "simulated"}
NEW = {"THERMOSTAT_HYSTERESIS_C": (0.5, 0.1, 3), "THERMOSTAT_MIN_SWITCH_MINUTES": (5, 1, 60),
       "COMPRESSOR_MIN_OFF_MINUTES": (3, 1, 15), "COMPRESSOR_WAIT_SECONDS": (7, 0, 60),
       "MISSED_AFTER_MINUTES": (30, 5, 720), "APPROVAL_EXPIRES_MINUTES": (30, 5, 720)}


def test_the_six_new_settings_their_defaults_and_limits():
    assert {k: SETTINGS[k] for k in NEW} == NEW
    assert {k: v for k, v in load_config(BASE).settings.items() if k in NEW} == {k: v[0] for k, v in NEW.items()}
    given = {"THERMOSTAT_HYSTERESIS_C": "1.5", "THERMOSTAT_MIN_SWITCH_MINUTES": "10", "COMPRESSOR_MIN_OFF_MINUTES": "4",
             "COMPRESSOR_WAIT_SECONDS": "0", "MISSED_AFTER_MINUTES": "60", "APPROVAL_EXPIRES_MINUTES": "45"}
    settings = load_config({**BASE, **given}).settings
    assert {k: settings[k] for k in given} == {k: float(v) for k, v in given.items()}
    assert not set(NEW) & set(load_config({**BASE, **given}).for_connector().env)   # never to the connector


@pytest.mark.parametrize("name", list(NEW))
def test_out_of_range_or_not_a_number_stops_the_engine(name):
    default, low, high = NEW[name]
    for bad in (str(low - 1), str(high + 1), "tanti"):
        with pytest.raises(ConfigError, match=f"{name} must be a number between {low:g} and {high:g}"):
            load_config({**BASE, name: bad})


def test_the_compressor_pause_comes_from_the_setting_also_after_a_restart(tmp_path):
    db = tmp_path / "engine.db"
    first = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    rule = next(r for r in first.ruleset()["rules"] if r["rule_id"] == "compressor_min_off")
    assert rule["params"] == {"minutes": 3} and rule["limits"] == {"minutes": {"min": 3, "max": 3}} and not rule["editable"]
    first.store.close()
    second = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db),
                                  settings={"COMPRESSOR_MIN_OFF_MINUTES": 4.0})
    rule = next(r for r in second.ruleset()["rules"] if r["rule_id"] == "compressor_min_off")
    assert rule["params"] == {"minutes": 4} and rule["limits"] == {"minutes": {"min": 4, "max": 4}}
    second.store.close()


def test_the_hysteresis_of_the_thermostat():
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, settings={"THERMOSTAT_HYSTERESIS_C": 2.0})
    boiler = e.devices["dev-caldaia"]
    e.relay["dev-caldaia"] = True
    sensor = e.devices["dev-ambiente-soggiorno"]["capabilities"]["temperature"]
    setpoint = 21.0
    sensor["celsius"] = setpoint + 1.5                        # above setpoint + 0.5, below setpoint + 2: stays on
    assert e.thermostat(boiler, {"on": True, "setpoint": setpoint})[0] is True
    sensor["celsius"] = setpoint + 2.1
    assert e.thermostat(boiler, {"on": True, "setpoint": setpoint})[0] is False


def test_approvals_expire_after_the_apartments_minutes(monkeypatch):
    now = datetime(2026, 10, 21, 10, tzinfo=UTC)
    monkeypatch.setattr(core, "utcnow", lambda: now)
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, settings={"APPROVAL_EXPIRES_MINUTES": 45})
    approval = e.trigger_approval("2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10")
    assert approval["expires_at"] == core.iso(now + timedelta(minutes=45))
    assert DEFAULT_SETTINGS["APPROVAL_EXPIRES_MINUTES"] == 30                  # D-119


def test_a_restart_runs_or_misses_by_the_apartments_minutes(tmp_path):
    db = tmp_path / "engine.db"
    first = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    now = core.utcnow()
    item = first.add_schedule(now - timedelta(minutes=45), {"type": "apartment_mode", "mode": "eco"}, "manual", "manual")
    first.store.close()
    second = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db),
                                  settings={"MISSED_AFTER_MINUTES": 60})
    assert second.schedule[item["schedule_id"]]["status"] == "planned"      # 45 minutes late: within 60, runs
    second.store.close()


# ---- D-177: TIMEZONE -------------------------------------------------------------------------------------------------
def test_timezone_a_setting_of_the_engine_checked_at_start_and_declared_in_apartment():
    assert load_config(BASE).settings["TIMEZONE"] == "Europe/Rome"                    # the default
    config = load_config({**BASE, "TIMEZONE": "Europe/London"})
    assert config.settings["TIMEZONE"] == "Europe/London"                             # kept as written
    assert "TIMEZONE" not in config.for_connector().env                               # never to the connector
    for bad in ("Fake/Zone", "europe/nowhere", "../etc/passwd"):
        with pytest.raises(ConfigError, match="TIMEZONE must be a time zone name"):
            load_config({**BASE, "TIMEZONE": bad})
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, settings={"TIMEZONE": "Europe/London"})
    assert e.apartment()["timezone"] == "Europe/London" and e.timezone == "Europe/London"


def test_timezone_of_a_demonstration_from_the_bff_header():
    from starlette.testclient import TestClient

    from bff.mock_instance.app import create_mock_app
    app = create_mock_app("k" * 16)
    with TestClient(app) as client:
        h = {"X-API-Key": "k" * 16, "X-Actor": "system:prova", "X-Correlation-Id": "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"}
        r = client.get("/apt-prova-01/api/v1/apartment", headers={**h, "X-Demo-Timezone": "Europe/Lisbon"})
        assert r.status_code == 200 and r.json()["timezone"] == "Europe/Lisbon"
        r = client.get("/apt-prova-01/api/v1/apartment", headers={**h, "X-Demo-Timezone": "Fake/Zone"})
        assert r.json()["timezone"] == "Europe/Lisbon"                                 # not a time zone: ignored
        r = client.get("/apt-prova-01/api/v1/apartment", headers={**h, "X-Demo-Timezone": "Europe/Madrid"})
        assert r.json()["timezone"] == "Europe/Madrid"                                 # an engine already built too
