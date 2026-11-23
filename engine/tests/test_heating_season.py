"""Item 15, E1 (answer 1231 = a; a6, 23 November 2026): the heating season of each apartment. Two dates, parameters of
«Limiti del setpoint» (season_start_month/day, season_end_month/day; first values zone E, 15 October – 15 April),
editable by the administrator. Out of season comfort and eco keep the boiler on the frost protection, as «casa vuota»
does (the frost protection always on); a climate of the mode does not heat. The change of season brings the mode's
boilers to their new setpoint once, with one decision; its state is kept across restarts; during a hold it waits.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import UTC, date, datetime

import pytest

from engine import core
from engine.config import DEFAULT_SETTINGS
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
BOILER, CLIMA, SENSOR = "dev-caldaia", "dev-clima-soggiorno", "dev-ambiente-soggiorno"
MINUTE = 0.02
SUMMER, WINTER = date(2026, 7, 1), date(2026, 10, 20)


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    """Minutes are fast and the simulated catalog's commands complete at once."""
    from engine.connector import simulated
    for name in ("SENT_AFTER_S", "VERIFYING_AFTER_S", "OUTCOME_AFTER_S"):
        monkeypatch.setattr(simulated, name, 0)
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


def engine(**kw):
    return core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, **kw)


def season_params(e):
    p = e.rule("setpoint_limits")["params"]
    return {k: p[k] for k in ("season_start_month", "season_start_day", "season_end_month", "season_end_day")}


def set_season(e, **params):
    e.update_rules({"rules": [{"rule_id": "setpoint_limits", "params": params}]}, ACTOR, CORR)


def temperature(e, celsius):
    e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": celsius}}, ACTOR, CORR)


def commands(e, mode):
    return {device_id: body for device_id, body in e.mode_commands(mode, CORR)}


def season_decisions(e):
    return [d for d in e.decisions if d["action"] == "heating_season"]


async def commands_done(e):
    for _ in range(200):
        if all(c["status"] in core.FINAL for c in e.commands.values()):
            return
        await asyncio.sleep(0.02)


async def regulate_and_wait(e):
    e.regulate()
    await asyncio.gather(*list(e.tasks), return_exceptions=True)


async def wait_min_switch():
    await asyncio.sleep(DEFAULT_SETTINGS["THERMOSTAT_MIN_SWITCH_MINUTES"] * MINUTE + 0.05)


# -------- the parameters --------
def test_the_first_dates_are_zone_e_and_a_rule_saved_before_gets_them(tmp_path):
    e = engine()
    assert season_params(e) == {"season_start_month": 10, "season_start_day": 15, "season_end_month": 4,
                                "season_end_day": 15}
    limits = e.rule("setpoint_limits")["limits"]
    assert limits["season_start_month"] == limits["season_end_month"] == {"min": 1, "max": 12}
    assert limits["season_start_day"] == limits["season_end_day"] == {"min": 1, "max": 31}
    db = tmp_path / "engine.db"
    e = engine(store=SqliteStore(db))
    saved = e.store.get_meta("apartment")
    for r in saved["rules"]:
        if r["rule_id"] == "setpoint_limits":
            for k in season_params(e):
                r["params"].pop(k)
                r["limits"].pop(k)
    e.store.put_meta("apartment", saved)
    e.store.close()
    e = engine(store=SqliteStore(db))
    assert season_params(e)["season_start_day"] == 15 and e.rule("setpoint_limits")["limits"]["season_end_day"]["max"] == 31


def test_1261_the_label_is_antigelo_also_for_a_rule_saved_before(tmp_path):
    db = tmp_path / "engine.db"
    e = engine(store=SqliteStore(db))
    saved = e.store.get_meta("apartment")
    for r in saved["rules"]:
        if r["rule_id"] == "frost_protection":
            r["label"] = "Antigelo a casa vuota"
    e.store.put_meta("apartment", saved)
    e.store.close()
    assert engine(store=SqliteStore(db)).rule("frost_protection")["label"] == "Antigelo"


@pytest.mark.parametrize("params, message", [
    ({"season_start_month": 2, "season_start_day": 31}, "La data di inizio della stagione non esiste (31/2)."),
    ({"season_end_month": 4, "season_end_day": 31}, "La data di fine della stagione non esiste (31/4)."),
    ({"season_start_day": 15.5}, "La data di inizio della stagione non esiste (15,5/10)."),
    ({"season_end_month": 6.5}, "La data di fine della stagione non esiste (15/6,5)."),
], ids=["31-feb", "31-apr", "half-day", "half-month"])
def test_a_date_that_does_not_exist_is_refused(params, message):
    e = engine()
    with pytest.raises(core.MockError) as exc:
        set_season(e, **params)
    assert (exc.value.status, exc.value.error, exc.value.message) == (422, "invalid_date", message)
    assert season_params(e)["season_start_month"] == 10                 # nothing saved


def test_the_dates_change_and_29_february_exists():
    e = engine()
    set_season(e, season_start_month=11, season_start_day=1, season_end_month=2, season_end_day=29)
    assert season_params(e) == {"season_start_month": 11, "season_start_day": 1, "season_end_month": 2,
                                "season_end_day": 29}


@pytest.mark.parametrize("day, inside", [
    (date(2026, 10, 14), False), (date(2026, 10, 15), True), (date(2026, 12, 31), True), (date(2027, 1, 1), True),
    (date(2027, 4, 15), True), (date(2027, 4, 16), False), (date(2026, 7, 1), False)])
def test_a_season_across_the_new_year_both_dates_included(day, inside):
    params = {"season_start_month": 10, "season_start_day": 15, "season_end_month": 4, "season_end_day": 15}
    assert core.in_heating_season(params, day) is inside


def test_a_season_inside_the_year_and_the_whole_year():
    spring = {"season_start_month": 3, "season_start_day": 1, "season_end_month": 6, "season_end_day": 30}
    assert core.in_heating_season(spring, date(2026, 5, 10)) is True
    assert core.in_heating_season(spring, date(2026, 7, 1)) is False
    assert core.in_heating_season(spring, date(2026, 2, 28)) is False
    assert core.in_heating_season(spring, date(2026, 3, 1)) is True    # both dates included
    assert core.in_heating_season(spring, date(2026, 6, 30)) is True
    year = {"season_start_month": 1, "season_start_day": 1, "season_end_month": 12, "season_end_day": 31}
    assert all(core.in_heating_season(year, date(2026, m, 1)) for m in range(1, 13))


# -------- the modes out of season --------
def test_out_of_season_comfort_and_eco_keep_the_boiler_on_the_frost_protection():
    e = engine()
    frost = e.rule("frost_protection")["params"]["celsius"]
    e.season_on = False
    for mode in ("comfort", "eco", "empty"):
        assert commands(e, mode)[BOILER] == {"capability": "heating", "action": "set_heating",
                                             "params": {"on": True, "setpoint": frost}}, mode
    e.mode = "comfort"
    assert e._mode_heating_setpoint(e.devices[BOILER]) == frost          # the return after a closed window too
    e.season_on = True
    assert commands(e, "comfort")[BOILER]["params"]["setpoint"] == 21
    assert commands(e, "eco")[BOILER]["params"]["setpoint"] == 18
    assert e._mode_heating_setpoint(e.devices[BOILER]) == 21


def test_out_of_season_a_climate_of_the_mode_cools_but_does_not_heat():
    e = engine()
    e.devices[SENSOR]["capabilities"]["temperature"]["celsius"] = 17.0
    e.season_on = False
    assert CLIMA not in commands(e, "comfort")
    assert e._mode_would_command(e.devices[CLIMA], "comfort") is False
    e.devices[SENSOR]["capabilities"]["temperature"]["celsius"] = 27.5
    assert commands(e, "comfort")[CLIMA]["params"]["mode"] == "cool"
    e.devices[SENSOR]["capabilities"]["temperature"]["celsius"] = 17.0
    e.season_on = True
    assert commands(e, "comfort")[CLIMA]["params"]["mode"] == "heat"


def test_a_cool_summer_night_does_not_turn_the_boiler_on():
    async def main():
        e = engine()
        e._today = lambda: SUMMER
        e.ensure_started()
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await commands_done(e)
        temperature(e, 17.0)
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.season_on is False and e.relay[BOILER] is False
        heating = e.devices[BOILER]["capabilities"]["heating"]
        assert heating["on"] is True and heating["setpoint"] == e.rule("frost_protection")["params"]["celsius"]
        temperature(e, 6.0)                                            # the frost protection still acts
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.relay[BOILER] is True
        assert [d for d in e.decisions if d["action"] == "frost_heating_on"]
    asyncio.run(main())


# -------- the change of season --------
def test_the_change_of_season_moves_the_modes_boilers_once_and_survives_a_restart(tmp_path):
    db = tmp_path / "engine.db"

    async def first():
        e = engine(store=SqliteStore(db))
        e._today = lambda: WINTER
        e.ensure_started()
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await asyncio.sleep(0.3)
        await regulate_and_wait(e)
        assert season_decisions(e) == [] and e.devices[BOILER]["capabilities"]["heating"]["setpoint"] == 21
        e._today = lambda: SUMMER
        await regulate_and_wait(e)
        await regulate_and_wait(e)
        ends = season_decisions(e)
        assert len(ends) == 1
        assert ends[0]["reasoning"] == ("Fine della stagione del riscaldamento (15 aprile): "
                                        "la caldaia resta solo sull'antigelo")
        assert (ends[0]["old_value"], ends[0]["new_value"], ends[0]["outcome"]) == ("in stagione", "fuori stagione",
                                                                                    "applied")
        assert e.devices[BOILER]["capabilities"]["heating"]["setpoint"] == 8
        for task in list(e.tasks) + [t for t in (e.loop_task, e.consumer_task) if t]:
            task.cancel()
        await asyncio.sleep(0)
        e.store.close()
    asyncio.run(first())

    async def second():
        e = engine(store=SqliteStore(db))
        assert e.season_on is False                                    # kept: no second «Fine» after the restart
        before = len(season_decisions(e))                              # the decisions of before are kept too
        e._today = lambda: SUMMER
        e.ensure_started()
        await regulate_and_wait(e)
        assert len(season_decisions(e)) == before
        e._today = lambda: WINTER
        await regulate_and_wait(e)
        starts = season_decisions(e)[before:]
        assert len(starts) == 1 and starts[0]["reasoning"] == ("Inizio della stagione del riscaldamento (15 ottobre): "
                                                               "la caldaia torna a comfort ed eco")
        assert e.devices[BOILER]["capabilities"]["heating"]["setpoint"] == 21
    asyncio.run(second())


def test_a_boiler_a_person_commanded_is_left_as_it_is():
    async def main():
        e = engine()
        e._today = lambda: WINTER
        e.ensure_started()
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await asyncio.sleep(0.3)
        cmd = e.create_command(BOILER, {"capability": "heating", "action": "set_heating",
                                        "params": {"on": True, "setpoint": 23}}, ACTOR, CORR)
        while e.commands[cmd["command_id"]]["status"] not in core.FINAL:
            await asyncio.sleep(0.02)
        e._today = lambda: SUMMER
        await regulate_and_wait(e)
        assert len(season_decisions(e)) == 1 and e.devices[BOILER]["capabilities"]["heating"]["setpoint"] == 23
    asyncio.run(main())


def test_during_a_hold_the_change_waits_for_its_end():
    async def main():
        e = engine()
        e._today = lambda: WINTER
        e.ensure_started()
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await asyncio.sleep(0.3)
        e.set_hold(30, None, ACTOR, CORR)
        e._today = lambda: SUMMER
        await regulate_and_wait(e)
        assert season_decisions(e) == [] and e.season_on is True
        e.set_hold(0, None, ACTOR, CORR)
        await regulate_and_wait(e)
        assert len(season_decisions(e)) == 1 and e.season_on is False
    asyncio.run(main())


def test_new_dates_take_effect_at_the_next_minute():
    async def main():
        e = engine()
        e._today = lambda: date(2026, 11, 10)
        e.ensure_started()
        await regulate_and_wait(e)
        assert e.season_on is True
        set_season(e, season_start_month=12, season_start_day=1, season_end_month=3, season_end_day=31)   # zone A
        await regulate_and_wait(e)
        assert e.season_on is False and len(season_decisions(e)) == 1
        assert season_decisions(e)[0]["reasoning"] == ("Date della stagione del riscaldamento cambiate (1 dicembre – "
                                                       "31 marzo): ora è fuori stagione, la caldaia resta solo "
                                                       "sull'antigelo")
        set_season(e, season_start_month=11, season_start_day=1)                    # back in season, by the dates
        await regulate_and_wait(e)
        assert season_decisions(e)[1]["reasoning"] == ("Date della stagione del riscaldamento cambiate (1 novembre – "
                                                       "31 marzo): ora è in stagione, la caldaia torna a comfort ed eco")
        set_season(e, season_end_day=30)                                         # new dates, the same season
        await regulate_and_wait(e)
        assert len(season_decisions(e)) == 2
        e._today = lambda: date(2027, 4, 1)                                      # the calendar: its own words
        await regulate_and_wait(e)
        assert season_decisions(e)[2]["reasoning"].startswith("Fine della stagione del riscaldamento (30 marzo)")
    asyncio.run(main())


# -------- the change waits for a mode's command still running --------
def test_a_modes_command_still_running_is_not_undone_by_the_change():
    async def main():
        e = engine()
        e._today = lambda: SUMMER
        e.ensure_started()
        e.season_on = True                                             # as if the date had just crossed the end
        e.set_mode("comfort", ACTOR, CORR, "prova")                    # its set_heating at 21 °C still running
        e._season_check()
        assert e.season_on is True and season_decisions(e) == []        # it waits
        await commands_done(e)
        e._season_check()
        assert e.season_on is False and e.devices[BOILER]["capabilities"]["heating"]["setpoint"] == 8
    asyncio.run(main())


def test_an_offline_boiler_gets_the_new_setpoint_in_its_intention():
    async def main():
        e = engine()
        e._today = lambda: WINTER
        e.ensure_started()
        e.test_state({"device_id": BOILER, "online": False}, ACTOR, CORR)
        e.set_mode("comfort", ACTOR, CORR, "prova")                    # D16: the intention is set now
        assert e.devices[BOILER]["capabilities"]["heating"]["setpoint"] == 21 and BOILER in e.heating_by_mode
        e._today = lambda: SUMMER
        e._season_check()
        assert e.season_on is False and e.devices[BOILER]["capabilities"]["heating"]["setpoint"] == 8
    asyncio.run(main())


# -------- answers 1256 = a and 1257 = a: a person's command out of season is obeyed --------
def test_1256_out_of_season_a_persons_command_heats_with_the_normal_regulation():
    async def main():
        e = engine()
        e._today = lambda: SUMMER
        e.ensure_started()
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await commands_done(e)
        await regulate_and_wait(e)
        assert e.season_on is False
        e.create_command(BOILER, {"capability": "heating", "action": "set_heating",
                                  "params": {"on": True, "setpoint": 22}}, ACTOR, CORR)
        await commands_done(e)
        temperature(e, 17.0)
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.devices[BOILER]["capabilities"]["heating"]["setpoint"] == 22 and e.relay[BOILER] is True
        temperature(e, 22.6)                                           # above 22 + 0.5: the normal regulation
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.relay[BOILER] is False
    asyncio.run(main())


def test_1257_at_the_end_of_the_season_a_climate_of_the_mode_stops_heating_a_persons_does_not():
    async def main():
        e = engine()
        e._today = lambda: WINTER
        e.ensure_started()
        e.devices[SENSOR]["capabilities"]["temperature"]["celsius"] = 17.0
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await commands_done(e)
        assert e.devices[CLIMA]["capabilities"]["climate"]["mode"] == "heat" and CLIMA in e.climate_by_mode
        e._today = lambda: SUMMER
        await asyncio.sleep(0.4)                                       # the compressor's pause and the minutes
        await regulate_and_wait(e)
        await commands_done(e)
        assert e.season_on is False and e.devices[CLIMA]["capabilities"]["climate"]["on"] is False
        off = [d for d in e.decisions if d["target"].get("device_id") == CLIMA and d["actor"] == "system"][-1]
        assert off["reasoning"] == "Climatizzatore soggiorno: fuori dalla stagione del riscaldamento, spento"
        e.create_command(CLIMA, {"capability": "climate", "action": "set_climate",
                                 "params": {"on": True, "mode": "heat", "setpoint": 22}}, ACTOR, CORR)   # a person
        await asyncio.sleep(0.4)
        await commands_done(e)
        await regulate_and_wait(e)
        await commands_done(e)
        c = e.devices[CLIMA]["capabilities"]["climate"]
        assert (c["on"], c["mode"]) == (True, "heat") and CLIMA not in e.climate_by_mode
    asyncio.run(main())


# -------- the frost protection out of season, everywhere «casa vuota» had it --------
def test_set_mode_out_of_season_sends_the_frost_setpoint_inside_the_devices_limits_only():
    async def main():
        e = engine()
        e._today = lambda: SUMMER
        e.ensure_started()
        for _ in range(100):                                           # the devices reachable: a real command
            if e.connector_up():
                break
            await asyncio.sleep(0.02)
        await regulate_and_wait(e)
        assert e.season_on is False
        cmd_ids = e.set_mode("eco", ACTOR, CORR, "prova")               # the manager's limits (16-23) would cut 8 to 16
        boiler = [e.commands[c] for c in cmd_ids if e.commands[c]["device_id"] == BOILER]
        assert boiler and boiler[0]["params"]["setpoint"] == 8
        await commands_done(e)
        assert e.devices[BOILER]["capabilities"]["heating"]["setpoint"] == 8
    asyncio.run(main())


def test_an_engine_made_out_of_season_starts_out_of_season(monkeypatch, tmp_path):
    monkeypatch.setattr(core.ApartmentEngine, "_today", lambda self: SUMMER)
    e = engine(store=SqliteStore(tmp_path / "engine.db"))
    assert e.season_on is False and e.store.get_meta("heating_season") is False
    assert commands(e, "comfort")[BOILER]["params"]["setpoint"] == 8
    assert season_decisions(e) == []                                   # nothing changed: no decision


def test_out_of_season_without_a_sensor_the_frost_protection_says_it_cannot_act():
    async def main():
        e = engine()
        e._today = lambda: SUMMER
        e.ensure_started()
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await commands_done(e)
        await regulate_and_wait(e)
        e.test_state({"device_id": SENSOR, "online": False}, ACTOR, CORR)
        await wait_min_switch()
        await regulate_and_wait(e)
        frost = [d for d in e.decisions if d["action"] == "frost_inactive"]
        assert len(frost) == 1 and frost[0]["reasoning"].startswith("Caldaia: sensore di temperatura mancante, antigelo")
    asyncio.run(main())


def test_a_boiler_the_window_turned_off_is_left_to_its_return():
    async def main():
        e = engine()
        e._today = lambda: WINTER
        e.ensure_started()
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await commands_done(e)
        e.window_off[BOILER] = {"cap": "heating", "by_mode": True, "state": {"on": True, "setpoint": 21}}
        e.devices[BOILER]["capabilities"]["heating"]["on"] = False
        e._today = lambda: SUMMER
        e._season_check()
        heating = e.devices[BOILER]["capabilities"]["heating"]
        assert e.season_on is False and heating["on"] is False                # not turned on with the window open
        assert e._mode_heating_setpoint(e.devices[BOILER]) == 8                # its return will bring the new one
    asyncio.run(main())


# -------- rereading of o1-stagione (a6, 23 November) --------
def test_today_is_the_apartments_local_date_and_mock_today_only_for_the_simulator(monkeypatch):
    assert core.local_today("Europe/Rome", datetime(2026, 4, 15, 22, 30, tzinfo=UTC)) == date(2026, 4, 16)
    assert core.local_today("Europe/Rome", datetime(2026, 4, 15, 21, 30, tzinfo=UTC)) == date(2026, 4, 15)
    e = engine()
    monkeypatch.setattr(core, "utcnow", lambda: datetime(2026, 4, 15, 22, 30, tzinfo=UTC))
    assert core.engine_today(e) == date(2026, 4, 16)                    # in Rome already the 16th: out of season
    monkeypatch.setenv("MOCK_TODAY", "2026-07-01")                      # the HTTP suites' simulator
    assert core.engine_today(e) == date(2026, 7, 1)

    class Real:                                                          # not the simulator: the real date
        timezone, connector = "Europe/Rome", object()
    assert core.engine_today(Real()) == date(2026, 4, 16)


def test_a_demo_made_in_summer_does_not_heat(monkeypatch):
    monkeypatch.setattr(core.ApartmentEngine, "_today", lambda self: SUMMER)

    async def main():
        e = core.ApartmentEngine("apt-rimini-01")                       # the demonstration, in comfort
        assert e.mode == "comfort" and e.season_on is False
        heating = e.devices[BOILER]["capabilities"]["heating"]
        assert heating["setpoint"] == 8 and BOILER in e.heating_by_mode
        e.ensure_started()
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.relay[BOILER] is False and season_decisions(e) == []
    asyncio.run(main())


def test_a_crash_during_the_change_does_not_lose_it(tmp_path):
    db = tmp_path / "engine.db"

    async def first():
        e = engine(store=SqliteStore(db))
        e._today = lambda: WINTER
        e.ensure_started()
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await commands_done(e)
        e._today = lambda: SUMMER

        def crash(*a, **k):
            raise RuntimeError("crash")
        e.emit = crash                                                  # dies while moving the boilers
        with pytest.raises(RuntimeError):
            e._season_check()
        for task in list(e.tasks) + [t for t in (e.loop_task, e.consumer_task) if t]:
            task.cancel()
        await asyncio.sleep(0)
        e.store.close()
    asyncio.run(first())
    e = engine(store=SqliteStore(db))
    assert e.season_on is True                                          # not saved: the change is made again
    e._today = lambda: SUMMER
    e._season_check()
    assert e.season_on is False and e.devices[BOILER]["capabilities"]["heating"]["setpoint"] == 8


def test_a_climate_waiting_for_its_heat_command_does_not_get_it_out_of_season():
    async def main():
        e = engine()
        e._today = lambda: WINTER
        e.ensure_started()
        e.devices[SENSOR]["capabilities"]["temperature"]["celsius"] = 17.0
        e.test_state({"device_id": CLIMA, "online": False}, ACTOR, CORR)
        e.set_mode("comfort", ACTOR, CORR, "prova")
        assert e.mode_pending[CLIMA]["body"]["params"]["mode"] == "heat"
        e._today = lambda: SUMMER
        await regulate_and_wait(e)
        e.test_state({"device_id": CLIMA, "online": True}, ACTOR, CORR)
        await regulate_and_wait(e)
        await commands_done(e)
        sent = [c for c in e.commands.values() if c["device_id"] == CLIMA and c["params"].get("mode") == "heat"]
        assert e.season_on is False and sent == [] and CLIMA not in e.mode_pending
    asyncio.run(main())


def test_an_error_in_the_season_check_does_not_stop_the_thermostat():
    async def main():
        e = engine()
        e._today = lambda: WINTER
        e.ensure_started()
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await commands_done(e)

        def broken():
            raise RuntimeError("guasto")
        e._season_check = broken
        temperature(e, 23.0)                                           # above 21 + 0.5: the relay goes off
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.relay[BOILER] is False
    asyncio.run(main())


def test_out_of_season_the_window_keeps_the_frost_protection_and_says_it():
    async def main():
        e = engine()
        e._today = lambda: SUMMER
        e.ensure_started()
        await regulate_and_wait(e)
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await commands_done(e)
        e._window_turn_off("dev-finestra-camera", "Finestra camera aperta da oltre 5 minuti")
        await commands_done(e)                                         # the decision comes with the command's outcome
        off = [d for d in e.decisions if d["target"].get("device_id") == BOILER and d["actor"] == "rule:window_open_off"]
        assert off and off[-1]["reasoning"].endswith("; l'antigelo resta attivo")
    asyncio.run(main())
