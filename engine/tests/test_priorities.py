"""Behaviours of step 5 that had no test of their own (P-80, D-126): the thermostat looks once a "minute" (R1); the frost
protection is never suspended by a hold (R8: safety first); an open window switches climate and boiler off after its
minutes, and in an empty apartment the frost protection stays stronger than the window (R8).

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
BOILER, SENSOR, CLIMA, WINDOW = "dev-caldaia", "dev-ambiente-soggiorno", "dev-clima-soggiorno", "dev-finestra-camera"
MINUTE = 0.02


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


def temperature(e, celsius):
    e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": celsius}}, ACTOR, CORR)


async def settle(e):
    await asyncio.gather(*list(e.tasks), return_exceptions=True)


def test_r1_the_thermostat_looks_once_a_minute(monkeypatch):
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    looked = []
    monkeypatch.setattr(e, "regulate", lambda: looked.append(1))

    async def main():
        e.tick()
        e.tick()                                             # the same "minute": no second look
        assert len(looked) == 1
        await asyncio.sleep(MINUTE * 1.5)
        e.tick()
        assert len(looked) == 2
    asyncio.run(main())


def test_r8_the_frost_protection_is_not_suspended_by_a_hold():
    async def main():
        e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
        e.ensure_started()
        cmd = e.create_command(BOILER, {"capability": "heating", "action": "turn_off"}, ACTOR, CORR)   # disabled
        while e.commands[cmd["command_id"]]["status"] not in core.FINAL:
            await asyncio.sleep(0.02)
        e.set_hold(30, "empty", ACTOR, CORR)                 # a hold keeping the apartment empty
        await settle(e)
        assert e.hold is not None and e.mode == "empty"
        assert e.devices[BOILER]["capabilities"]["heating"]["on"] is False
        temperature(e, 5.0)                                  # freezing
        await asyncio.sleep(core.DEFAULT_SETTINGS["THERMOSTAT_MIN_SWITCH_MINUTES"] * MINUTE + 0.05)
        e.regulate()
        await settle(e)
        assert e.relay[BOILER] is True
        assert any(d["actor"] == "rule:frost_protection" and "caldaia accesa" in d["reasoning"] for d in e.decisions)
    asyncio.run(main())


def test_r8_an_open_window_switches_off_and_the_frost_protection_stays_stronger():
    async def main():
        e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)      # empty, climate and boiler on
        e.ensure_started()
        e.update_rules({"rules": [{"rule_id": "window_open_off", "params": {"minutes": 1}}]}, ACTOR, CORR)
        assert e.mode == "empty" and e.devices[CLIMA]["capabilities"]["climate"]["on"] is True
        e.test_state({"device_id": WINDOW, "capability": "contact", "state": {"open": True}}, ACTOR, CORR)
        await asyncio.sleep(MINUTE * 3)
        await settle(e)
        await asyncio.sleep(0.5)
        offs = [d for d in e.decisions if d["actor"] == "rule:window_open_off" and d["action"] == "turn_off"]
        targets = {d["target"]["device_id"] for d in offs}
        assert {CLIMA, BOILER} <= targets and all("aperta da oltre 1 minuti" in d["reasoning"] for d in offs)
        boiler_off = next(d for d in offs if d["target"]["device_id"] == BOILER)
        assert "l'antigelo resta attivo" in boiler_off["reasoning"]
        temperature(e, 5.0)                                  # freezing with the window open: the frost protection acts
        await asyncio.sleep(core.DEFAULT_SETTINGS["THERMOSTAT_MIN_SWITCH_MINUTES"] * MINUTE + 0.05)
        e.regulate()
        await settle(e)
        assert e.relay[BOILER] is True
    asyncio.run(main())
