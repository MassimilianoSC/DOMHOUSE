"""D13 (P-83 review, gravity 2): an automatic start put off for the compressor's pause (R4) was repeated as it was when
the pause ended, whatever had happened meanwhile: «casa vuota» set, a hold started, a person who turned the climate off
or chose another mode. The climate went on (or back to heat 21) against all of them. Now, when the pause ends, the
start goes only if the situation is the one it was made for (same mode, same hold, the climate still the mode's) and
no one commanded the climate meanwhile; otherwise a decision says it was not done. Scenarios of the independent
verification (V-D13/prova_d13.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio
import time

import pytest

from engine import core
from engine.connector import simulated
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, SENSOR = "dev-clima-soggiorno", "dev-ambiente-soggiorno"
MINUTE = 0.02                         # the compressor's 3 minutes are 0.06 s


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))
    for name in ("SENT_AFTER_S", "VERIFYING_AFTER_S", "OUTCOME_AFTER_S"):
        monkeypatch.setattr(simulated, name, 0)


def room(e, celsius):
    e.devices[SENSOR]["capabilities"]["temperature"]["celsius"] = celsius


async def settle(e):
    for _ in range(300):
        if all(c["status"] in core.FINAL for c in e.commands.values()):
            return
        await asyncio.sleep(0.02)


def climate(e) -> dict:
    return e.devices[CLIMA]["capabilities"]["climate"]


async def deferred(tmp_path, monkeypatch) -> core.ApartmentEngine:
    """Comfort, the climate just turned off (its pause running), the room cold: the regulation's start is put off."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False,
                             settings={"THERMOSTAT_MIN_SWITCH_MINUTES": 0.0})
    e.ensure_started()
    e.create_command(CLIMA, {"capability": "climate", "action": "turn_off"}, ACTOR, CORR)
    await settle(e)
    room(e, 23.0)
    e.set_mode("comfort", ACTOR, CORR, "prova")
    await settle(e)
    room(e, 19.0)
    e.compressor_off[CLIMA] = time.monotonic()
    e.regulate()
    assert any(d["actor"] == "rule:compressor_min_off" for d in e.decisions)
    return e


async def after_the_pause(e):
    await asyncio.sleep(e.compressor_wait(CLIMA) + 0.3)
    await settle(e)


def stop(e):
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


def test_control_nothing_changed_it_starts_after_the_pause(tmp_path, monkeypatch):
    async def main():
        e = await deferred(tmp_path, monkeypatch)
        await after_the_pause(e)
        assert climate(e)["on"] and climate(e)["mode"] == "heat"
        stop(e)
    asyncio.run(main())


@pytest.mark.parametrize("change", ["empty", "manual_off", "hold_eco"])
def test_the_situation_changed_it_stays_off(tmp_path, monkeypatch, change):
    async def main():
        e = await deferred(tmp_path, monkeypatch)
        if change == "empty":
            e.set_mode("empty", ACTOR, CORR, "check-out")
        elif change == "manual_off":
            e.create_command(CLIMA, {"capability": "climate", "action": "turn_off"}, ACTOR, CORR)
        else:
            e.set_hold(60, "eco", ACTOR, CORR)
        await settle(e)
        await after_the_pause(e)
        assert not climate(e)["on"], change
        assert any("non eseguita" in (d["reasoning"] or "") for d in e.decisions if d["actor"] == "rule:compressor_min_off")
        stop(e)
    asyncio.run(main())


def test_a_persons_choice_meanwhile_is_not_overwritten(tmp_path, monkeypatch):
    async def main():
        e = await deferred(tmp_path, monkeypatch)
        e.create_command(CLIMA, {"capability": "climate", "action": "set_climate",
                                 "params": {"on": True, "mode": "cool", "setpoint": 24}}, ACTOR, CORR)
        await settle(e)
        await asyncio.sleep(0.3)
        await after_the_pause(e)
        await after_the_pause(e)
        assert climate(e)["mode"] == "cool" and climate(e)["setpoint"] == 24
        stop(e)
    asyncio.run(main())
