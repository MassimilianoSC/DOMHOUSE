"""D11 (P-83 review, gravity 2): the compressor's minimum pause (rule compressor_min_off, R4) was checked when a command
was created or started, outside the device's lock, while the pause itself begins when a turn_off is settled. A start
sent while a turn_off was still running (two people, the app's mode switch enabled again before the commands end, an
automatic start right after a mode's turn_off) waited for the lock and then ran: the climate went back on at once,
with almost the whole pause still to go. Now the pause is checked again inside the lock, just before the device is
asked: a person's start is refused (or waited for, within COMPRESSOR_WAIT_SECONDS), an automatic one is put off until
the pause ends; and an automatic start counts a climate with a turn_off running as off. Real time (MOCK_TIME_SCALE=60,
as in production), scenarios of the independent verification (V-D11/prova_d11.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

USER, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA = "dev-clima-soggiorno"
ON = {"capability": "climate", "action": "set_climate", "params": {"on": True}}
OFF = {"capability": "climate", "action": "turn_off"}


@pytest.fixture(autouse=True)
def real_time(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "60")


async def wait_final(e, timeout=40.0):
    end = asyncio.get_running_loop().time() + timeout
    while any(c["status"] not in core.FINAL for c in e.commands.values()):
        assert asyncio.get_running_loop().time() < end, e.commands
        await asyncio.sleep(0.05)


def on(e) -> bool:
    return e.devices[CLIMA]["capabilities"]["climate"]["on"]


async def started_on() -> core.ApartmentEngine:
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    e.ensure_started()
    if not on(e):
        e.create_command(CLIMA, ON, USER, CORR)
        await wait_final(e)
    e.compressor_off.pop(CLIMA, None)
    assert on(e) and e.compressor_wait(CLIMA) == 0
    return e


def stop(e) -> None:
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


def test_control_off_then_on_after_its_outcome_is_refused():
    async def main():
        e = await started_on()
        e.create_command(CLIMA, OFF, USER, CORR)
        await wait_final(e)
        b = e.create_command(CLIMA, ON, USER, CORR)
        await wait_final(e)
        assert e.commands[b["command_id"]]["status"] == "failed" and not on(e)
        stop(e)
    asyncio.run(main())


@pytest.mark.parametrize("delay", [0.0, 0.4, 1.0])
def test_a_persons_start_sent_while_the_turn_off_runs_is_refused(delay):
    async def main():
        e = await started_on()
        a = e.create_command(CLIMA, OFF, USER, CORR)
        await asyncio.sleep(delay)
        b = e.create_command(CLIMA, ON, USER, CORR)
        await wait_final(e)
        assert e.commands[a["command_id"]]["status"] == "acked"
        assert e.commands[b["command_id"]]["status"] == "failed", e.commands[b["command_id"]]
        assert e.commands[b["command_id"]]["reason"] == "blocked_by_rule"
        assert not on(e) and e.compressor_wait(CLIMA) > 60
        assert any("Pausa minima del compressore" in (d["reasoning"] or "") and d["outcome"] == "rejected"
                   for d in e.decisions)
        stop(e)
    asyncio.run(main())


def test_an_automatic_start_right_after_the_modes_turn_off_waits_for_the_pause():
    async def main():
        e = await started_on()
        e.set_mode("eco", "system:engine", CORR, "prova", "system")       # its turn_off of the climate is running
        e._auto_climate = True
        try:
            b = e.create_command(CLIMA, ON, "system:engine", CORR, decision_actor="system", reasoning="Modalità comfort")
        finally:
            e._auto_climate = False
        await wait_final(e)
        assert b is None                                                   # put off, not sent
        assert any(d["actor"] == "rule:compressor_min_off" for d in e.decisions)
        assert not on(e) and e.compressor_wait(CLIMA) > 60
        stop(e)
    asyncio.run(main())
