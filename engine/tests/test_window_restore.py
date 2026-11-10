"""The window closed again (D-218 point 1, answer 811): before, the rule «Finestra aperta spegne il clima» turned the
boiler and the climate off as if a person had, so they left the mode's regulation and stayed off after the window was
closed, also in the cold. Now, when no window is open any more (and no hold): a boiler or a climate of the mode goes
back to the mode's regulation, one turned on by a person goes back as it was, one a person commanded meanwhile stays
as it is. The return goes through the usual limits: the boiler's relay through the thermostat (at most one switch
every THERMOSTAT_MIN_SWITCH_MINUTES), the climate through the regulation (its pause and the compressor's). A window
closed and opened again within seconds sends no burst of commands, and the rule's minutes start again from the last
opening. The rule's minutes run fast here (MOCK_TIME_SCALE = real seconds per simulated minute).

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, BOILER, WINDOW, SENSOR = "dev-clima-soggiorno", "dev-caldaia", "dev-finestra-camera", "dev-ambiente-soggiorno"
MINUTE = 0.2          # the rule's 5 minutes are 1 s; the boiler's 5 minutes between switches 1 s; the compressor 0.6 s


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


async def settle(e, timeout=15.0):
    end = asyncio.get_running_loop().time() + timeout
    while any(c["status"] not in core.FINAL for c in e.commands.values()) or e.relay_busy:
        assert asyncio.get_running_loop().time() < end, e.commands
        await asyncio.sleep(0.02)


async def minutes(n: float) -> None:
    await asyncio.sleep(n * MINUTE)


def window(e, open_: bool) -> None:
    e.test_state({"device_id": WINDOW, "capability": "contact", "state": {"open": open_}}, ACTOR, CORR)


def cold(e, celsius: float = 15) -> None:
    e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": celsius}}, ACTOR, CORR)


def boiler(e) -> dict:
    return e.devices[BOILER]["capabilities"]["heating"]


def climate(e) -> dict:
    return e.devices[CLIMA]["capabilities"]["climate"]


def stop(e) -> None:
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


async def started(mode: str = "comfort", store=None, connector=None) -> core.ApartmentEngine:
    e = core.ApartmentEngine("apt-prova-01", connector or SimulatedConnector(), seed=False,
                             **({"store": store} if store else {}))
    e.ensure_started()
    cold(e)
    e.set_mode(mode, ACTOR, CORR, "prova")
    await settle(e)
    await minutes(2)
    await settle(e)
    return e


async def window_turns_off(e) -> None:
    window(e, True)
    await minutes(e.rule("window_open_off")["params"]["minutes"] + 1)
    await settle(e)
    assert not boiler(e)["on"] and not e.relay.get(BOILER)


def restored(e, device_id: str) -> list[str]:
    return [d["reasoning"] for d in e.decisions if d["actor"] == "rule:window_open_off" and d["action"] == "window_restore"
            and d["target"].get("device_id") == device_id]


def test_comfort_boiler_and_climate_go_back_to_the_mode():
    async def main():
        e = await started("comfort")
        assert boiler(e)["on"] and e.relay.get(BOILER) and climate(e)["on"]
        await window_turns_off(e)
        assert not climate(e)["on"]
        window(e, False)
        await minutes(8)
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    sl = e.rule("setpoint_limits")["params"]
    assert boiler(e)["on"] and boiler(e)["setpoint"] == sl["comfort_celsius"] and BOILER in e.heating_by_mode
    assert e.relay.get(BOILER)                                          # 15 °C: the thermostat switched it on
    assert climate(e)["on"] and climate(e)["mode"] == "heat" and CLIMA in e.climate_by_mode
    assert restored(e, BOILER) == ["Finestra chiusa: Caldaia riacceso (comfort)"]
    assert restored(e, CLIMA) == ["Finestra chiusa: Climatizzatore soggiorno riacceso (comfort)"]


def test_eco_the_boiler_back_at_eco_and_the_climate_stays_off():
    async def main():
        e = await started("eco")
        await window_turns_off(e)
        window(e, False)
        await minutes(8)
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert boiler(e)["on"] and boiler(e)["setpoint"] == e.rule("setpoint_limits")["params"]["eco_celsius"]
    assert not climate(e)["on"] and restored(e, CLIMA) == []            # in eco the mode keeps it off


def test_a_boiler_turned_on_by_a_person_goes_back_as_it_was():
    async def main():
        e = await started("comfort")
        e.create_command(BOILER, {"capability": "heating", "action": "set_heating", "params": {"on": True, "setpoint": 23}},
                         ACTOR, CORR)
        await settle(e)
        assert BOILER not in e.heating_by_mode
        await window_turns_off(e)
        window(e, False)
        await minutes(8)
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert boiler(e)["on"] and boiler(e)["setpoint"] == 23 and BOILER not in e.heating_by_mode
    assert restored(e, BOILER) == ["Finestra chiusa: Caldaia riacceso come prima"]


def test_one_a_person_commanded_meanwhile_stays_as_it_is():
    async def main():
        e = await started("comfort")
        await window_turns_off(e)
        e.create_command(BOILER, {"capability": "heating", "action": "turn_off"}, ACTOR, CORR)   # with the window open
        await settle(e)
        window(e, False)
        await minutes(8)
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert not boiler(e)["on"] and restored(e, BOILER) == []
    assert climate(e)["on"]                                             # the other one goes back


def test_closed_during_a_hold_nothing_goes_back():
    async def main():
        e = await started("comfort")
        await window_turns_off(e)
        e.set_hold(60, "eco", ACTOR, CORR)
        await settle(e)
        window(e, False)
        await minutes(8)
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert restored(e, BOILER) == [] and restored(e, CLIMA) == []


def test_the_return_respects_the_boiler_switch_minimum_and_the_compressor_pause():
    """Closed at once after the rule turned them off: the relay waits THERMOSTAT_MIN_SWITCH_MINUTES since that switch,
    the climate the compressor's pause and the regulation's minutes between changes."""
    async def main():
        e = await started("comfort")
        await window_turns_off(e)
        window(e, False)
        await minutes(0.5)
        early = (e.relay.get(BOILER), climate(e)["on"],
                 [c for c in e.commands.values() if c["device_id"] == CLIMA and c["action"] == "set_climate"
                  and c["status"] not in core.FINAL])
        await minutes(8)
        await settle(e)
        late = (e.relay.get(BOILER), climate(e)["on"])
        stop(e)
        return early, late
    early, late = asyncio.run(main())
    assert early == (False, False, [])                                  # not at once
    assert late == (True, True)


def test_closed_and_opened_again_within_seconds_no_burst_and_the_minutes_start_again():
    async def main():
        e = await started("comfort")
        await window_turns_off(e)
        n = len(e.commands)
        for _ in range(3):                                              # a window that bangs in the wind
            window(e, False)
            e.regulate()                                                # a regulation's round in the instant it is closed
            await asyncio.sleep(0.05)
            window(e, True)
            await asyncio.sleep(0.05)
        await minutes(2)
        await settle(e)
        burst = len(e.commands) - n                                     # devices already off: nothing to send
        assert restored(e, BOILER) == [] and not boiler(e)["on"], "brought back while the window was banging"
        window(e, False)                                                # closed for good: they come back
        await minutes(8)
        await settle(e)
        assert boiler(e)["on"] and climate(e)["on"]
        opened = asyncio.get_running_loop().time()
        window(e, True)
        await minutes(2)
        window(e, False)                                                # closed before the rule's 5 minutes,
        await asyncio.sleep(0.05)
        window(e, True)                                                 # and opened again: the 5 start again
        await minutes(4)
        still_on = boiler(e)["on"] and climate(e)["on"]                 # 6 minutes after the first opening
        await minutes(3)
        await settle(e)
        off = not boiler(e)["on"] and not climate(e)["on"]              # past 5 from the last opening
        stop(e)
        return burst, still_on, off, asyncio.get_running_loop().time() - opened
    burst, still_on, off, _ = asyncio.run(main())
    assert burst == 0
    assert still_on, "the reflex of the first opening was not cancelled when the window closed"
    assert off


def test_after_a_restart_the_return_is_still_known(tmp_path):
    db, conn = tmp_path / "e.db", SimulatedConnector()

    async def first_life():
        e = await started("comfort", store=SqliteStore(db), connector=conn)
        await window_turns_off(e)
        stop(e)
        e.store.close()
    asyncio.run(first_life())
    conn.set_state(WINDOW, "contact", {"open": False}, notify=False)      # closed while the engine was down

    async def second_life():
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False, store=SqliteStore(db))
        e.ensure_started()
        await minutes(8)
        await settle(e)
        stop(e)
        e.store.close()
        return e
    e = asyncio.run(second_life())
    assert boiler(e)["on"] and BOILER in e.heating_by_mode and restored(e, BOILER)
