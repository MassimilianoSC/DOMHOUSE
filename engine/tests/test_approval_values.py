"""D76 (P-83, gravity 4): the decision «pending_approval» of a device command always had «off» as its new value: an
approval to turn a socket on read «from off to off», a change of temperature looked like a switch-off. Now old and new
values are described like the commands' own decisions (describe), the new one from the state the command would give.

Run: python -m pytest engine/tests -q
"""
from engine import core
from engine.connector.simulated import SimulatedConnector

CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"


def pending_decision(engine, proposed):
    engine._new_approval("assistant", "prova", "prova", proposed, "reject", CORR)
    return [d for d in engine.decisions if d["outcome"] == "pending_approval"][-1]


def test_turning_a_socket_on_reads_off_to_on():
    engine = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    d = pending_decision(engine, {"type": "device_command", "device_id": "dev-presa-camera", "capability": "switch",
                                  "action": "turn_on"})
    assert (d["action"], d["old_value"], d["new_value"]) == ("turn_on", "off", "on")


def test_turning_the_split_off_reads_its_state_to_off():
    engine = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    d = pending_decision(engine, {"type": "device_command", "device_id": "dev-clima-soggiorno", "capability": "climate",
                                  "action": "turn_off"})
    assert (d["old_value"], d["new_value"]) == ("heat 21", "off")


def test_a_new_temperature_is_not_a_switch_off():
    engine = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    d = pending_decision(engine, {"type": "device_command", "device_id": "dev-caldaia", "capability": "heating",
                                  "action": "set_heating", "params": {"setpoint": 19}})
    assert (d["old_value"], d["new_value"]) == ("on 21", "on 19")
