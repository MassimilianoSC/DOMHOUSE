"""The modes' temperatures (lot 30, D-161, D-162): comfort_celsius, eco_celsius and comfort_cool_celsius are parameters
of «Limiti del setpoint» (eco <= comfort < cool); the boiler follows them; the climate in comfort follows the room's
sensor (heats under comfort, cools over the cooling temperature, nothing in between) and without a sensor does
nothing by itself, with one decision per episode; ASSISTANT_CONFIRM chooses when the assistant asks first.

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import assistant, core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, CALDAIA, SENSOR = "dev-clima-soggiorno", "dev-caldaia", "dev-ambiente-soggiorno"


def engine(**settings):
    return core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, settings=settings or None)


def room(e, celsius, online=True):
    e.devices[SENSOR]["capabilities"]["temperature"]["celsius"] = celsius
    e.devices[SENSOR]["online"] = online


def commands(e, mode):
    return {device_id: body for device_id, body in e.mode_commands(mode, CORR)}


def test_the_parameters_and_their_checks():
    e = engine()
    sl = e.rule("setpoint_limits")
    assert {k: sl["params"][k] for k in ("comfort_celsius", "eco_celsius", "comfort_cool_celsius")} == {
        "comfort_celsius": 21, "eco_celsius": 18, "comfort_cool_celsius": 25}
    assert sl["limits"]["comfort_celsius"] == {"min": 16, "max": 26} and sl["limits"]["eco_celsius"] == {"min": 10, "max": 22}
    assert sl["limits"]["comfort_cool_celsius"] == {"min": 22, "max": 28}
    for bad, message in (({"eco_celsius": 22, "comfort_celsius": 20}, "eco non può superare"),
                         ({"comfort_celsius": 24, "comfort_cool_celsius": 23}, "raffrescamento deve essere più alta")):
        with pytest.raises(core.MockError) as exc:
            e.update_rules({"rules": [{"rule_id": "setpoint_limits", "params": bad}]}, ACTOR, CORR)
        assert exc.value.error == "invalid_range" and message in exc.value.message
    e.update_rules({"rules": [{"rule_id": "setpoint_limits", "params": {"comfort_celsius": 22, "eco_celsius": 17}}]},
                   ACTOR, CORR)
    assert commands(e, "eco")[CALDAIA]["params"]["setpoint"] == 17
    assert commands(e, "comfort")[CALDAIA]["params"]["setpoint"] == 22


def test_the_climate_in_comfort_follows_the_room():
    e = engine()
    room(e, 18.0)                                                       # cold: heats to comfort
    assert commands(e, "comfort")[CLIMA] == {"capability": "climate", "action": "set_climate",
                                             "params": {"on": True, "mode": "heat", "setpoint": 21}}
    room(e, 27.5)                                                       # hot: cools, within the device's range
    c = commands(e, "comfort")[CLIMA]
    climate = e.devices[CLIMA]["capabilities"]["climate"]
    assert c["params"]["mode"] == "cool" and c["params"]["setpoint"] == min(25, climate["setpoint_max"])
    room(e, 23.0)                                                       # in between: nothing to do
    assert CLIMA not in commands(e, "comfort")
    assert commands(e, "eco")[CLIMA] == {"capability": "climate", "action": "turn_off"}
    assert commands(e, "empty")[CALDAIA]["params"]["setpoint"] == e.rule("frost_protection")["params"]["celsius"]


def test_without_a_room_sensor_nothing_by_itself_and_one_decision_per_episode():
    e = engine()
    room(e, 18.0, online=False)
    assert CLIMA not in commands(e, "comfort")
    noted = [d for d in e.decisions if d["action"] == "auto_regulation_off"]
    assert len(noted) == 1 and noted[0]["outcome"] == "informational" and noted[0]["target"]["device_id"] == CLIMA
    assert noted[0]["reasoning"] == "Climatizzatore soggiorno: sensore di temperatura mancante, regolazione automatica disattivata"
    commands(e, "comfort")                                             # the same episode: no new decision
    assert len([d for d in e.decisions if d["action"] == "auto_regulation_off"]) == 1
    commands(e, "eco")                                                  # out of comfort: the episode ends
    commands(e, "comfort")
    assert len([d for d in e.decisions if d["action"] == "auto_regulation_off"]) == 2
    room(e, 18.0, online=True)                                          # the sensor answers again: regulated
    assert commands(e, "comfort")[CLIMA]["params"]["mode"] == "heat" and CLIMA not in e.no_sensor_noted


def test_rules_saved_before_get_the_new_parameters(tmp_path):
    db = tmp_path / "engine.db"
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    e.update_rules({"rules": [{"rule_id": "setpoint_limits", "params": {"min": 17}}]}, ACTOR, CORR)
    saved = e.store.get_meta("apartment")
    for r in saved["rules"]:
        if r["rule_id"] == "setpoint_limits":
            for k in ("comfort_celsius", "eco_celsius", "comfort_cool_celsius"):
                r["params"].pop(k)
                r["limits"].pop(k)
    e.store.put_meta("apartment", saved)
    e.store.close()
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    sl = e.rule("setpoint_limits")
    assert sl["params"]["min"] == 17 and sl["params"]["comfort_celsius"] == 21 and sl["limits"]["eco_celsius"]["max"] == 22


@pytest.mark.parametrize("policy, alone_off_with_guests, alone_on_empty, together", [
    ("ospiti", True, False, True), ("sempre", True, True, True), ("multiple", False, False, True)])
def test_assistant_confirm(policy, alone_off_with_guests, alone_on_empty, together):
    e = engine(ASSISTANT_CONFIRM=policy)
    a = assistant.Assistant(e, None)
    off = {"type": "command", "device_id": CLIMA, "body": {"capability": "climate", "action": "turn_off", "params": {}}}
    on = {"type": "command", "device_id": "dev-presa-camera", "body": {"capability": "switch", "action": "turn_on",
                                                                      "params": {}}}
    real = e.apartment
    e.apartment = lambda: {**real(), "occupancy": "occupied"}
    assert a.needs_approval(off, False) is alone_off_with_guests
    e.apartment = lambda: {**real(), "occupancy": "empty"}
    assert a.needs_approval(on, False) is alone_on_empty
    assert a.needs_approval(on, True) is together
    later = core.iso(core.utcnow() + core.timedelta(days=3))              # no booking then: a scheduled action does not ask
    assert a.needs_approval({"type": "schedule", "run_at": later, "action": {"type": "apartment_mode", "mode": "eco"}},
                            True) is False


# -------- D-169: the climate in comfort is regulated every minute --------
MINUTE = 0.02


@pytest.fixture
def quick(monkeypatch):
    """Commands complete at once in the simulated catalog, minutes are fast."""
    from engine.connector import simulated
    for name in ("SENT_AFTER_S", "VERIFYING_AFTER_S", "OUTCOME_AFTER_S"):
        monkeypatch.setattr(simulated, name, 0)
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


def _climate_decisions(e):
    return [d for d in e.decisions if d["target"].get("device_id") == CLIMA and d["action"] == "set_climate"
            and d["actor"] == "system"]


async def _wait_commands(e):
    await asyncio.sleep(0.15)               # an automatic start may wait for the compressor's pause (3 «minutes»)
    for _ in range(200):
        if all(c["status"] in core.FINAL for c in e.commands.values()):
            return
        await asyncio.sleep(0.02)


def test_d169_the_room_is_followed_every_minute_and_never_against_a_person(quick):
    import asyncio as _asyncio

    async def main():
        e = engine(THERMOSTAT_MIN_SWITCH_MINUTES=60.0)                  # 1,2 s here: «too soon» is sure
        e.ensure_started()
        e.create_command(CLIMA, {"capability": "climate", "action": "turn_off"}, ACTOR, CORR)   # the split starts off
        await _wait_commands(e)
        room(e, 23.0)                                                   # in the band: comfort sends nothing
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await _wait_commands(e)
        assert CLIMA in e.climate_by_mode and not _climate_decisions(e)
        room(e, 19.0)                                                   # the room cools: heats to comfort
        e.regulate()
        await _wait_commands(e)
        c = e.devices[CLIMA]["capabilities"]["climate"]
        assert (c["on"], c["mode"], c["setpoint"]) == (True, "heat", 21)
        assert _climate_decisions(e)[-1]["reasoning"] == "Climatizzatore soggiorno: 19 °C, sotto 21 °C: scalda"
        room(e, 27.5)                                                   # too soon: at most one change per 5 minutes
        e.regulate()
        await _wait_commands(e)
        assert e.devices[CLIMA]["capabilities"]["climate"]["mode"] == "heat"
        await _asyncio.sleep(60 * MINUTE + 0.05)
        e.regulate()
        await _wait_commands(e)
        assert e.devices[CLIMA]["capabilities"]["climate"]["mode"] == "cool"
        assert "sopra 25 °C: raffresca" in _climate_decisions(e)[-1]["reasoning"]
        e.create_command(CLIMA, {"capability": "climate", "action": "turn_off"}, ACTOR, CORR)   # a person
        await _wait_commands(e)
        assert CLIMA not in e.climate_by_mode
        await _asyncio.sleep(60 * MINUTE + 0.05)
        room(e, 18.0)
        e.regulate()
        await _wait_commands(e)
        assert e.devices[CLIMA]["capabilities"]["climate"]["on"] is False       # left alone until the next mode
        e.set_mode("eco", ACTOR, CORR, "prova")
        assert e.climate_by_mode == set()
        e.set_mode("comfort", ACTOR, CORR, "prova")
        assert CLIMA in e.climate_by_mode                                       # the next comfort takes it again
    _asyncio.run(main())


def test_d169_not_during_a_hold(quick):
    import asyncio as _asyncio

    async def main():
        e = engine()
        e.ensure_started()
        room(e, 23.0)
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await _wait_commands(e)
        e.set_hold(30, None, ACTOR, CORR)                                       # comfort rules suspended
        room(e, 15.0)
        e.regulate()
        await _wait_commands(e)
        assert not _climate_decisions(e)
    _asyncio.run(main())
