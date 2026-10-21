"""A hold and an open window (P-60 step 5c, R7 strada c, D-127; scenario C11 of the conformance): during the hold an
open window does not turn the climate off and a decision says the rule is suspended; when the hold ends (cancelled or
expired) the rule is active again and turns it off if the window is still open, with a decision naming both reasons.
The rules' minutes run fast here (MOCK_TIME_SCALE = real seconds per simulated minute).

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, WINDOW = "dev-clima-soggiorno", "dev-finestra-camera"
MINUTE = 0.02


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


async def settle(e, timeout=10.0):
    end = asyncio.get_running_loop().time() + timeout
    while any(c["status"] not in core.FINAL for c in e.commands.values()):
        assert asyncio.get_running_loop().time() < end, e.commands
        await asyncio.sleep(0.02)


def window(e, open_):
    e.test_state({"device_id": WINDOW, "capability": "contact", "state": {"open": open_}}, ACTOR, CORR)


def climate_on(e) -> bool:
    return e.devices[CLIMA]["capabilities"]["climate"]["on"]


async def started_with_hold():
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)      # comfort, split on
    e.ensure_started()
    e.set_hold(60, "comfort", ACTOR, CORR)
    await settle(e)
    assert climate_on(e) and e.hold
    return e


def test_hold_then_open_window_then_end_of_hold_turns_the_split_off():
    async def main():
        e = await started_with_hold()
        minutes = e.rule("window_open_off")["params"]["minutes"]
        window(e, True)
        suspended = [d for d in e.decisions if d["action"] == "window_rule_suspended"]
        assert len(suspended) == 1 and "riparte alla sua fine" in suspended[0]["reasoning"]
        await asyncio.sleep(minutes * MINUTE + 0.1)                        # past the rule's minutes: still on
        await settle(e)
        assert climate_on(e)
        e.set_hold(0, None, ACTOR, CORR)                                   # the hold ends, the window is still open
        await settle(e)
        assert not climate_on(e)
        off = [d for d in e.decisions if d["actor"] == "rule:window_open_off" and d["action"] == "turn_off"
               and d["target"]["device_id"] == CLIMA]
        assert off and "Forzatura finita" in off[-1]["reasoning"] and "aperta da oltre" in off[-1]["reasoning"]
    asyncio.run(main())


def test_the_same_when_the_hold_expires(monkeypatch):
    async def main():
        e = await started_with_hold()
        minutes = e.rule("window_open_off")["params"]["minutes"]
        window(e, True)
        await asyncio.sleep(minutes * MINUTE + 0.1)
        later = core.utcnow() + timedelta(minutes=61)                      # the hold's end has passed
        monkeypatch.setattr(core, "utcnow", lambda: later)
        e.tick()
        await settle(e)
        assert e.hold is None and not climate_on(e)
        off = [d for d in e.decisions if d["actor"] == "rule:window_open_off" and d["target"]["device_id"] == CLIMA]
        assert "Forzatura finita" in off[-1]["reasoning"]
    asyncio.run(main())


def test_a_window_opened_just_before_the_end_waits_for_its_minutes(monkeypatch):
    async def main():
        e = await started_with_hold()
        minutes = e.rule("window_open_off")["params"]["minutes"]
        window(e, True)
        e.set_hold(0, None, ACTOR, CORR)                                   # open for less than the rule's minutes
        await settle(e)
        assert climate_on(e)                                               # not yet
        await asyncio.sleep(minutes * MINUTE + 0.1)
        await settle(e)
        assert not climate_on(e)                                           # after the minutes left
    asyncio.run(main())


def test_closed_before_the_end_of_the_hold_nothing_happens():
    async def main():
        e = await started_with_hold()
        window(e, True)
        window(e, False)
        e.set_hold(0, None, ACTOR, CORR)
        await asyncio.sleep(e.rule("window_open_off")["params"]["minutes"] * MINUTE + 0.1)
        await settle(e)
        assert climate_on(e)
    asyncio.run(main())
