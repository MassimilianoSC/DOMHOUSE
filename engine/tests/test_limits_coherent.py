"""«Limiti del setpoint» with two ranges (1096 = a, 1098 = b, 13 Nov):
- WINTER min/max (the boiler, a climate heating: eco and comfort inside it), SUMMER summer_min/summer_max (a climate
  cooling or dehumidifying: the cooling inside it); no tie between them but comfort < cooling (D-162); first values
  16–24 and 18–28 (1099); a rule saved before keeps min/max as the winter range and gets the summer one;
- a PUT /rules that touches the rule refuses a range broken (o2's sentences, in their order), also with the rule off;
  one that touches only other rules is not refused for a rule saved before;
- a rule saved incoherent, while on: one decision «limits_modes_outside» per episode, also across restarts;
- a climate's setpoint_min/setpoint_max are the range of the mode it works in (heat winter, cool and dry summer, fan
  the device's only), after a command and after its own report (never brought inside: the remote control is not
  limited); a manual command is checked with its new mode's range; a mode change without a setpoint brings the
  current one inside the new range, with the note;
- a mode's or the regulation's temperature cut by the device's limits says so in its decision;
- narrower limits that leave a climate that is on outside them: a system command brings it inside (before only the
  engine's copy changed, the split stayed where it was), not to a device offline nor with a window open (it waits).

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "user:prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, SENSORE, FINESTRA = "dev-clima-soggiorno", "dev-ambiente-soggiorno", "dev-finestra-camera"


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "0.02")


def engine(connector=None, store=None):
    return core.ApartmentEngine("apt-prova-01", connector or SimulatedConnector(), seed=False, store=store,
                                settings={"COMPRESSOR_WAIT_SECONDS": 0})


def put(e, rule_id="setpoint_limits", enabled=None, **params):
    patch = {"rule_id": rule_id, **({"params": params} if params else {})}
    if enabled is not None:
        patch["enabled"] = enabled
    return e.update_rules({"rules": [patch]}, ACTOR, CORR)


def refused(e, **kw) -> str:
    before = dict(e.rule("setpoint_limits")["params"])
    with pytest.raises(core.MockError) as exc:
        put(e, **kw)
    assert exc.value.status == 422 and exc.value.error == "invalid_range"
    assert e.rule("setpoint_limits")["params"] == before                  # nothing saved
    return exc.value.message


def saved_before(e, **params):
    """A rule saved by an engine before the checks: written as _load would find it."""
    e.rule("setpoint_limits")["params"].update(params)
    e._save_apartment()


def outside(e):
    return [d for d in e.decisions if d["action"] == "limits_modes_outside"]


def run(coro):
    return asyncio.run(coro)


async def settle(e, timeout=10.0):
    end = asyncio.get_running_loop().time() + timeout
    await asyncio.sleep(0.05)
    while any(c["status"] not in core.FINAL for c in e.commands.values()):
        assert asyncio.get_running_loop().time() < end, e.commands
        await asyncio.sleep(0.02)


def climate_commands(e):
    return [c for c in e.commands.values() if c["device_id"] == CLIMA]


def pair(e):
    c = e.devices[CLIMA]["capabilities"]["climate"]
    return c["setpoint_min"], c["setpoint_max"]


def applied(e, cmd):
    [d] = [d for d in e.decisions if d.get("command_id") == cmd["command_id"] and d["outcome"] == "applied"]
    return d


# -------- the parameters --------
def test_the_first_values_two_ranges():
    rule = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False).rule("setpoint_limits")
    assert rule["params"] == {"min": 16, "max": 24, "comfort_celsius": 21, "eco_celsius": 18,
                              "comfort_cool_celsius": 25, "summer_min": 18, "summer_max": 28}
    assert rule["limits"]["summer_min"] == {"min": 16, "max": 28} and rule["limits"]["summer_max"] == {"min": 22, "max": 30}


def test_a_rule_saved_before_keeps_its_range_as_winter_and_gets_the_summer_one(tmp_path):
    db = tmp_path / "engine.db"
    e = engine(store=SqliteStore(db))
    for key in ("summer_min", "summer_max"):                              # an engine before 1098 = b saved this
        e.rule("setpoint_limits")["params"].pop(key)
        e.rule("setpoint_limits")["limits"].pop(key)
    e.rule("setpoint_limits")["params"].update(min=17, max=23)
    e._save_apartment()
    e.store.close()
    rule = engine(store=SqliteStore(db)).rule("setpoint_limits")
    assert (rule["params"]["min"], rule["params"]["max"]) == (17, 23)
    assert (rule["params"]["summer_min"], rule["params"]["summer_max"]) == (18, 28)
    assert rule["limits"]["summer_max"] == {"min": 22, "max": 30}


# -------- the checks of PUT /rules, o2's sentences in their order --------
@pytest.mark.parametrize("params, message", [
    ({"min": 19}, "La temperatura eco non può essere sotto il minimo invernale"),
    ({"eco_celsius": 22}, "La temperatura eco non può superare quella comfort"),
    ({"comfort_celsius": 24.5}, "La temperatura comfort non può superare il massimo invernale"),
    ({"summer_min": 27, "summer_max": 24}, "Il minimo estivo non può superare il massimo estivo"),
    ({"summer_max": 24}, "La temperatura di raffrescamento deve stare fra il minimo e il massimo estivi"),
    ({"summer_min": 26}, "La temperatura di raffrescamento deve stare fra il minimo e il massimo estivi"),
    ({"comfort_celsius": 23, "comfort_cool_celsius": 22},
     "La temperatura di raffrescamento deve essere più alta di quella comfort"),
])
@pytest.mark.parametrize("enabled", [None, False])
def test_a_range_broken_is_refused(params, message, enabled):
    assert refused(engine(), enabled=enabled, **params) == message


def test_no_tie_between_the_seasons():
    e = engine()
    put(e, max=21)                                                        # comfort 21: the winter maximum under 22
    put(e, summer_min=24)                                                 # the summer range does not care
    params = e.rule("setpoint_limits")["params"]
    assert (params["max"], params["summer_min"]) == (21, 24)


def test_a_rule_saved_before_is_not_refused_for_another_rule():
    e = engine()
    saved_before(e, max=20)                                               # comfort 21 over it
    put(e, "window_open_off", minutes=6)                                  # accepted
    assert e.rule("window_open_off")["params"]["minutes"] == 6
    assert refused(e, eco_celsius=17) == "La temperatura comfort non può superare il massimo invernale"
    put(e, max=22)                                                        # corrected
    assert e.rule("setpoint_limits")["params"]["max"] == 22


# -------- a rule saved incoherent --------
def test_a_rule_saved_incoherent_one_decision_per_episode(tmp_path):
    db = tmp_path / "engine.db"

    async def start(store):
        e = engine(store=store)
        e.ensure_started()
        await asyncio.sleep(0.05)
        return e

    e = run(start(SqliteStore(db)))
    assert outside(e) == []
    saved_before(e, max=20)
    e.store.close()
    e = run(start(SqliteStore(db)))                                       # the restart after the update
    [d] = outside(e)
    assert (d["actor"], d["target"], d["outcome"]) == ("rule:setpoint_limits", {"type": "rules"}, "informational")
    assert d["reasoning"] == ("Temperature delle modalità fuori dai limiti del setpoint: comfort 21 °C (inverno 16–20 °C). "
                              "Clima e caldaia restano dentro i limiti: correggi la regola «Limiti del setpoint»")
    put(e, "window_open_off", minutes=6)                                  # the same episode
    e.store.close()
    e = run(start(SqliteStore(db)))                                       # nor after a restart
    assert len(outside(e)) == 1
    put(e, max=24)                                                        # corrected: the episode ends
    saved_before(e, summer_max=24)                                        # cooling 25 over it: a new episode
    e.store.close()
    e = run(start(SqliteStore(db)))
    assert len(outside(e)) == 2 and outside(e)[-1]["reasoning"].startswith(
        "Temperature delle modalità fuori dai limiti del setpoint: raffrescamento 25 °C (estate 18–24 °C).")


def test_a_rule_saved_incoherent_but_off_no_decision():
    async def main():
        e = engine()
        put(e, enabled=False)
        saved_before(e, max=20)
        e.ensure_started()
        await asyncio.sleep(0.05)
        return e
    assert outside(run(main())) == []


# -------- the range of the mode the climate works in --------
async def climate_on_at(e, setpoint, mode="heat"):
    e.ensure_started()
    e.create_command(CLIMA, {"capability": "climate", "action": "set_climate",
                             "params": {"on": True, "mode": mode, "setpoint": setpoint}}, ACTOR, CORR)
    await settle(e)
    return len(climate_commands(e))


def test_the_pair_follows_the_mode_of_the_climate():
    """The simulated split is 16–24: heat 16–21 (winter after the change), cool and dry 18–24, fan 16–24."""
    async def main():
        e = engine()
        put(e, max=21)
        seen = [pair(e)]
        await climate_on_at(e, 20)
        for mode in ("cool", "dry", "fan", "heat"):
            e.create_command(CLIMA, {"capability": "climate", "action": "set_climate", "params": {"mode": mode}},
                             ACTOR, CORR)
            await settle(e)
            seen.append(pair(e))
        return e, seen
    e, seen = run(main())
    assert seen == [(16, 21), (18, 24), (18, 24), (16, 24), (16, 21)]
    last = [ev["data"]["state"] for ev in e.events if ev["event"] == "device.state" and ev["data"]["device_id"] == CLIMA]
    assert (last[-1]["setpoint_min"], last[-1]["setpoint_max"]) == (16, 21)          # the app hears it


def test_a_mode_change_brings_the_setpoint_inside_the_new_range():
    async def main():
        e = engine()
        before = await climate_on_at(e, 17)                               # heat at 17
        e.create_command(CLIMA, {"capability": "climate", "action": "set_climate", "params": {"mode": "cool"}},
                         ACTOR, CORR)
        await settle(e)
        return e, before
    e, before = run(main())
    [cmd] = climate_commands(e)[before:]
    assert cmd["params"] == {"mode": "cool", "setpoint": 18} and cmd["status"] == "acked"
    assert e.devices[CLIMA]["capabilities"]["climate"]["setpoint"] == 18
    assert e.connector._devices[CLIMA].capabilities["climate"]["setpoint"] == 18
    assert applied(e, cmd)["reasoning"] == "Comando manuale dall'app; setpoint 17 °C riportato a 18 °C (limiti 18–24)"


def test_a_manual_command_is_checked_with_its_new_modes_range():
    e = engine()
    state = e.devices[CLIMA]["capabilities"]["climate"]
    assert state["mode"] == "heat"
    with pytest.raises(core.MockError) as exc:
        e.validate_command(e.devices[CLIMA], {"capability": "climate", "action": "set_climate",
                                              "params": {"mode": "cool", "setpoint": 17}})
    assert (exc.value.status, exc.value.error, exc.value.details) == (422, "setpoint_out_of_range", {"min": 18, "max": 24})
    body, note = e._within_limits(e.devices[CLIMA], {"capability": "climate", "action": "set_climate",
                                                     "params": {"mode": "cool", "setpoint": 17}})
    assert body["params"]["setpoint"] == 18 and note == "setpoint 17 °C riportato a 18 °C (limiti 18–24)"


def test_the_remote_control_is_not_limited():
    """A split that reports its state, switched to cool at 17 with its own remote: the pair of cool, the 17 as it is,
    no command."""
    async def main():
        e = engine()
        before = await climate_on_at(e, 20)
        e.connector.set_state(CLIMA, "climate", {"mode": "cool", "setpoint": 17})
        await asyncio.sleep(0.2)
        await settle(e)
        return e, before
    e, before = run(main())
    state = e.devices[CLIMA]["capabilities"]["climate"]
    assert (state["mode"], state["setpoint"], pair(e)) == ("cool", 17, (18, 24))
    assert len(climate_commands(e)) == before and e.limits_push == {}


# -------- the device's limits say so --------
def test_the_devices_limit_cuts_the_cooling_and_the_decision_says_it():
    """Summer range 18–28, the simulated split 16–24: comfort with the room at 29 °C cools to 24, not 25."""
    async def main():
        e = engine()
        e.ensure_started()
        e.devices[SENSORE]["capabilities"]["temperature"]["celsius"] = 29.0
        e.set_mode("comfort", "system:engine", CORR, "Prova", decision_actor="system")
        await settle(e)
        return e
    e = run(main())
    [cmd] = climate_commands(e)
    assert cmd["params"] == {"on": True, "mode": "cool", "setpoint": 24}
    assert applied(e, cmd)["reasoning"] == "Modalità comfort; setpoint 25 °C riportato a 24 °C (limiti del dispositivo 16–24)"


def test_the_regulation_says_it_too():
    async def main():
        e = engine()
        e.ensure_started()
        e.devices[SENSORE]["capabilities"]["temperature"]["celsius"] = 22.0
        e.set_mode("comfort", "system:engine", CORR, "Prova", decision_actor="system")
        await settle(e)
        e.climate_switched.clear()
        e.devices[SENSORE]["capabilities"]["temperature"]["celsius"] = 29.0
        e._regulate_climates()
        await settle(e)
        return e
    e = run(main())
    cmd = climate_commands(e)[-1]
    assert cmd["params"]["setpoint"] == 24 and cmd["params"]["mode"] == "cool"
    assert applied(e, cmd)["reasoning"] == ("Climatizzatore soggiorno: 29 °C, sopra 25 °C: raffresca; setpoint 25 °C "
                                            "riportato a 24 °C (limiti del dispositivo 16–24)")


def test_the_managers_limit_keeps_the_old_note():
    e = engine()
    saved_before(e, max=23)
    e._apply_limits()
    body, note = e._within_limits(e.devices[CLIMA], {"capability": "climate", "action": "set_climate",
                                                     "params": {"setpoint": 25}})
    assert body["params"]["setpoint"] == 23 and note == "setpoint 25 °C riportato a 23 °C (limiti 16–23)"


# -------- narrower limits: a command, not only the copy --------
def test_narrower_limits_bring_a_climate_that_is_on_inside_them():
    async def main():
        e = engine()
        before = await climate_on_at(e, 17)
        put(e, min=18)
        await settle(e)
        return e, before
    e, before = run(main())
    new = climate_commands(e)[before:]
    assert [c["params"] for c in new] == [{"setpoint": 18}] and new[0]["status"] == "acked"
    assert e.connector._devices[CLIMA].capabilities["climate"]["setpoint"] == 18      # the device, not only the copy
    d = applied(e, new[0])
    assert d["actor"] == "system" and d["reasoning"] == (
        "Limiti del setpoint cambiati: Climatizzatore soggiorno portato da 17 °C a 18 °C")
    assert e.limits_push == {}


def test_narrower_summer_limits_a_climate_cooling():
    async def main():
        e = engine()
        before = await climate_on_at(e, 23, mode="cool")
        put(e, summer_max=22, comfort_cool_celsius=22)                     # the cooling inside the summer range
        await settle(e)
        return e, before
    e, before = run(main())
    assert [c["params"] for c in climate_commands(e)[before:]] == [{"setpoint": 22}]


def test_narrower_limits_a_climate_that_is_off_no_command():
    async def main():
        e = engine()
        e.ensure_started()
        e.devices[CLIMA]["capabilities"]["climate"].update(on=False, setpoint=17)
        put(e, min=18)
        await settle(e)
        return e
    e = run(main())
    assert climate_commands(e) == [] and e.devices[CLIMA]["capabilities"]["climate"]["setpoint"] == 18


def test_narrower_limits_wait_for_a_device_offline_and_for_a_window_open(tmp_path):
    db = tmp_path / "engine.db"

    async def main():
        e = engine(store=SqliteStore(db))
        before = await climate_on_at(e, 17)
        e.devices[CLIMA]["online"] = False
        put(e, min=18)
        await settle(e)
        assert len(climate_commands(e)) == before                        # offline: nothing sent
        assert e.limits_push == {CLIMA: {"from": 17, "to": 18}}
        e.devices[CLIMA]["online"] = True
        e.devices[FINESTRA]["capabilities"]["contact"]["open"] = True
        e._push_limits()
        await settle(e)
        assert len(climate_commands(e)) == before                        # a window open: it waits
        e.devices[FINESTRA]["capabilities"]["contact"]["open"] = False
        e._push_limits()
        await settle(e)
        return e, before

    e, before = run(main())
    new = climate_commands(e)[before:]
    assert [c["params"] for c in new] == [{"setpoint": 18}] and e.limits_push == {}


def test_the_pending_command_is_kept_across_a_restart(tmp_path):
    db = tmp_path / "engine.db"

    async def main():
        e = engine(store=SqliteStore(db))
        await climate_on_at(e, 17)
        e.devices[CLIMA]["online"] = False
        put(e, min=18)
        e.store.close()
    run(main())
    assert engine(store=SqliteStore(db)).limits_push == {CLIMA: {"from": 17, "to": 18}}


def test_a_command_meanwhile_replaces_the_pending_one():
    async def main():
        e = engine()
        before = await climate_on_at(e, 17)
        e.devices[CLIMA]["online"] = False
        put(e, min=18)
        e.devices[CLIMA]["online"] = True
        e.create_command(CLIMA, {"capability": "climate", "action": "set_climate", "params": {"setpoint": 20}},
                         ACTOR, CORR)
        await settle(e)
        e._push_limits()
        await settle(e)
        return e, before
    e, before = run(main())
    assert [c["params"] for c in climate_commands(e)[before:]] == [{"setpoint": 20}] and e.limits_push == {}
