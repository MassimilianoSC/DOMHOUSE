"""D30 (P-83 review, gravity 3): a window opened while the rule «Finestra aperta spegne il clima» was off: its wait
ended with the rule off and was not planned again, so turning the rule on later left the climate on with the window
open. Now turning the rule on (or changing its minutes) arms every open window again, from when it opened: past the
minutes, at once. Scenario of the independent verification (V-B1a/prova_d30.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, WINDOW = "dev-clima-soggiorno", "dev-finestra-camera"


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "0.05")            # the rule's 5 minutes are 0.25 s


async def settle(e, timeout=10.0):
    end = asyncio.get_running_loop().time() + timeout
    while any(c["status"] not in core.FINAL for c in e.commands.values()):
        assert asyncio.get_running_loop().time() < end, e.commands
        await asyncio.sleep(0.02)


def stop(e):
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


def test_turning_the_rule_on_with_a_window_open_past_its_minutes_turns_the_climate_off():
    async def main():
        e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
        e.ensure_started()
        await settle(e)
        assert e.devices[CLIMA]["capabilities"]["climate"]["on"]
        e.update_rules({"rules": [{"rule_id": "window_open_off", "enabled": False}]}, ACTOR, CORR)
        e.test_state({"device_id": WINDOW, "capability": "contact", "state": {"open": True}}, ACTOR, CORR)
        await asyncio.sleep(0.6)                              # its minutes pass with the rule off
        assert e.devices[CLIMA]["capabilities"]["climate"]["on"]
        e.update_rules({"rules": [{"rule_id": "window_open_off", "enabled": True}]}, ACTOR, CORR)
        await asyncio.sleep(0.5)
        await settle(e)
        assert not e.devices[CLIMA]["capabilities"]["climate"]["on"]
        stop(e)
    asyncio.run(main())


def test_control_with_the_rule_always_on_as_before():
    async def main():
        e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
        e.ensure_started()
        await settle(e)
        e.test_state({"device_id": WINDOW, "capability": "contact", "state": {"open": True}}, ACTOR, CORR)
        await asyncio.sleep(0.6)
        await settle(e)
        assert not e.devices[CLIMA]["capabilities"]["climate"]["on"]
        stop(e)
    asyncio.run(main())
