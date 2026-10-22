"""The modes' temperatures (lot 30, D-161, D-162): comfort_celsius, eco_celsius and comfort_cool_celsius are parameters
of «Limiti del setpoint» (eco <= comfort < cool); the boiler follows them; the climate in comfort follows the room's
sensor (heats under comfort, cools over the cooling temperature, nothing in between) and without a sensor does
nothing by itself, with one decision per episode; ASSISTANT_CONFIRM chooses when the assistant asks first.

Run: python -m pytest engine/tests -q
"""
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
    assert a.needs_approval({"type": "schedule"}, True) is False          # a scheduled action never asks
