"""D03 (P-83 review, gravity 2): the rule «Finestra aperta spegne il clima» used to act once, when its minutes ran out.
A device offline at that moment, or whose turn_off failed or was not confirmed, stayed on with the window open, and the
thermostat could even close the boiler's relay by itself with the window open. Now the rule holds while the window
stays open: at every regulation's minute what is on and reachable is turned off again (and remembered, to come back
when the window closes), and the thermostat keeps the relay open, except for the frost protection (R8, stronger).
The scenarios are those of the independent verification (revisione-verifiche/V-D03/prova_d03.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, BOILER, WINDOW, SENSOR = "dev-clima-soggiorno", "dev-caldaia", "dev-finestra-camera", "dev-ambiente-soggiorno"
MINUTE = 0.2          # the rule's 5 minutes are 1 s; the engine's loop (and so the regulation) turns once a second


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


def ts(e, body) -> None:
    e.test_state(body, ACTOR, CORR)


def temperature(e, celsius: float) -> None:
    ts(e, {"device_id": SENSOR, "capability": "temperature", "state": {"celsius": celsius}})


def online(e, device_id: str, value: bool) -> None:
    ts(e, {"device_id": device_id, "online": value})


def open_window(e) -> None:
    ts(e, {"device_id": WINDOW, "capability": "contact", "state": {"open": True}})


def stop(e) -> None:
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


async def started(celsius: float = 15) -> core.ApartmentEngine:
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    e.ensure_started()
    temperature(e, celsius)
    e.set_mode("comfort", ACTOR, CORR, "prova")
    await settle(e)
    await minutes(2)
    await settle(e)
    return e


def off(e) -> bool:
    h, c = e.devices[BOILER]["capabilities"]["heating"], e.devices[CLIMA]["capabilities"]["climate"]
    return not h["on"] and not e.relay.get(BOILER) and not c["on"]


def test_control_the_rule_turns_both_off():
    async def main():
        e = await started()
        assert e.devices[BOILER]["capabilities"]["heating"]["on"] and e.devices[CLIMA]["capabilities"]["climate"]["on"]
        open_window(e)
        await minutes(7)
        await settle(e)
        assert off(e)
        stop(e)
    asyncio.run(main())


def test_offline_when_the_minutes_run_out_turned_off_when_back_online():
    async def main():
        e = await started()
        open_window(e)
        await minutes(1)
        online(e, BOILER, False)
        online(e, CLIMA, False)
        await minutes(6)                                  # the rule's 5 minutes run out while both are offline
        online(e, BOILER, True)
        online(e, CLIMA, True)
        await minutes(10)                                  # 2 s: the engine's loop turns once a second
        await settle(e)
        assert off(e)                                      # at the next regulations, not never
        assert set(e.window_off) == {BOILER, CLIMA}        # remembered: they come back when the window closes
        await minutes(20)
        await settle(e)
        assert off(e)                                      # and they stay off while the window is open
        stop(e)
    asyncio.run(main())


def test_the_thermostat_never_closes_the_relay_with_the_window_open():
    async def main():
        e = await started(celsius=25)                     # warm: intention on, relay open
        assert e.devices[BOILER]["capabilities"]["heating"]["on"] and not e.relay.get(BOILER)
        open_window(e)
        await minutes(1)
        online(e, BOILER, False)
        await minutes(6)
        online(e, BOILER, True)
        temperature(e, 14)                                 # the room cools, the window still open
        for _ in range(15):
            await minutes(1)
            assert not e.relay.get(BOILER), "relè chiuso dal termostato a finestra aperta"
        await settle(e)
        assert not e.devices[BOILER]["capabilities"]["heating"]["on"]
        stop(e)
    asyncio.run(main())


def test_a_turn_off_not_confirmed_is_tried_again():
    async def main():
        e = await started()
        e.connector.lose_infrared(CLIMA)                   # the first infrared frame is lost
        open_window(e)
        await minutes(6)
        await settle(e)                                    # the first turn_off ends in timeout (10 s)
        await minutes(10)                                  # 2 s: the next regulations try again
        await settle(e)
        offs = [c for c in e.commands.values() if c["device_id"] == CLIMA and c["action"] == "turn_off"]
        assert len(offs) >= 2 and offs[-1]["status"] == "acked", [(c["status"], c["reason"]) for c in offs]
        assert not e.devices[CLIMA]["capabilities"]["climate"]["on"]
        stop(e)
    asyncio.run(main())


def test_closing_the_window_still_brings_them_back():
    async def main():
        e = await started()
        open_window(e)
        await minutes(1)
        online(e, CLIMA, False)
        await minutes(6)
        online(e, CLIMA, True)
        await minutes(10)
        await settle(e)
        assert off(e)
        ts(e, {"device_id": WINDOW, "capability": "contact", "state": {"open": False}})
        await minutes(12)
        await settle(e)
        assert e.devices[BOILER]["capabilities"]["heating"]["on"]
        assert e.devices[CLIMA]["capabilities"]["climate"]["on"]
        stop(e)
    asyncio.run(main())
