"""D08 (P-83 review, gravity 2): the mode changed while a window was open for less than the rule's minutes (cleaning at
the check-out, airing before an arrival). The mode's commands that turn heating or climate on are refused with the
window open (the rule's block), and since the rule never fired nothing came back when the window closed: the boiler
kept the old mode's setpoint without a time limit (21 °C in «casa vuota», 8 °C after the prearrival). Now a mode's
command refused by the window is remembered: a lower boiler setpoint applies at once (lowering is always safe), the
rest when the windows are closed again, with the mode of that moment. Scenarios of the independent verification
(revisione-verifiche/V-D08/prova_d08.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, BOILER, WINDOW, SENSOR = "dev-clima-soggiorno", "dev-caldaia", "dev-finestra-camera", "dev-ambiente-soggiorno"
MINUTE = 0.2          # the rule's 5 minutes are 1 s; the engine's loop turns once a second


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


async def settle(e, timeout=20.0):
    end = asyncio.get_running_loop().time() + timeout
    while any(c["status"] not in core.FINAL for c in e.commands.values()) or e.relay_busy:
        assert asyncio.get_running_loop().time() < end, e.commands
        await asyncio.sleep(0.02)


async def minutes(n: float) -> None:
    await asyncio.sleep(n * MINUTE)


def window(e, open_: bool) -> None:
    e.test_state({"device_id": WINDOW, "capability": "contact", "state": {"open": open_}}, ACTOR, CORR)


def stop(e) -> None:
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


async def started(mode: str) -> core.ApartmentEngine:
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    e.ensure_started()
    e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": 15}}, ACTOR, CORR)
    e.set_mode(mode, ACTOR, CORR, "prova")
    await settle(e)
    await minutes(2)
    await settle(e)
    return e


def boiler(e) -> dict:
    return e.devices[BOILER]["capabilities"]["heating"]


async def changed_with_the_window_open_a_moment(old: str, new: str) -> core.ApartmentEngine:
    e = await started(old)
    window(e, True)
    await asyncio.sleep(0.1)
    e.set_mode(new, ACTOR, CORR, "cambio")                 # its commands start now, with the window open
    await asyncio.sleep(0.2)
    window(e, False)                                       # closed after 0.3 s, 1.5 of the rule's 5 minutes
    await settle(e)
    await minutes(15)                                      # a minute closed, then the regulations (3 s)
    await settle(e)
    assert not any(d["actor"] == "rule:window_open_off" and d["action"] == "turn_off" for d in e.decisions)
    return e


def test_check_out_with_a_window_open_the_boiler_goes_to_the_frost_threshold():
    async def main():
        e = await changed_with_the_window_open_a_moment("comfort", "empty")
        frost = e.rule("frost_protection")["params"]["celsius"]
        assert e.mode == "empty" and boiler(e)["setpoint"] == frost and not e.relay.get(BOILER)
        stop(e)
    asyncio.run(main())


def test_prearrival_with_a_window_open_the_boiler_goes_to_comfort_after_it_closes():
    async def main():
        e = await changed_with_the_window_open_a_moment("empty", "comfort")
        comfort = e.rule("setpoint_limits")["params"]["comfort_celsius"]
        assert e.mode == "comfort" and boiler(e)["on"] and boiler(e)["setpoint"] == comfort and e.relay.get(BOILER)
        stop(e)
    asyncio.run(main())


def test_comfort_to_eco_with_a_window_open_the_boiler_goes_to_eco():
    async def main():
        e = await changed_with_the_window_open_a_moment("comfort", "eco")
        eco = e.rule("setpoint_limits")["params"]["eco_celsius"]
        assert e.mode == "eco" and boiler(e)["setpoint"] == eco
        stop(e)
    asyncio.run(main())


def test_the_lower_setpoint_applies_at_once_not_only_after_closing():
    async def main():
        e = await started("comfort")
        window(e, True)
        await asyncio.sleep(0.1)
        e.set_mode("empty", ACTOR, CORR, "cambio")
        await settle(e)                                    # the mode's commands done, the window never closed
        assert e.window_open() is not None
        assert boiler(e)["setpoint"] == e.rule("frost_protection")["params"]["celsius"]
        stop(e)
    asyncio.run(main())


def test_a_climate_the_mode_is_turning_off_is_not_turned_on_again_when_the_window_closes():
    """The side note of the verification (dump_d.py): the rule fired while the mode's turn_off of the climate was still
    running, remembered the climate as «on, a person's», and brought it back at 21 °C in «casa vuota»."""
    async def main():
        e = await started("comfort")
        window(e, True)
        await minutes(1)
        e.set_mode("empty", ACTOR, CORR, "check-out")
        await settle(e)                                    # the mode's commands take longer than the rule's minutes
        await minutes(6)
        await settle(e)
        window(e, False)
        await minutes(15)
        await settle(e)
        assert e.mode == "empty" and not e.devices[CLIMA]["capabilities"]["climate"]["on"]
        stop(e)
    asyncio.run(main())


def test_control_the_window_open_past_the_rule_the_new_mode_applies_after_closing():
    async def main():
        e = await started("comfort")
        window(e, True)
        await minutes(6)
        await settle(e)
        e.set_mode("empty", ACTOR, CORR, "check-out")
        await settle(e)
        window(e, False)
        await minutes(15)
        await settle(e)
        assert boiler(e)["setpoint"] == e.rule("frost_protection")["params"]["celsius"] and not e.relay.get(BOILER)
        stop(e)
    asyncio.run(main())
