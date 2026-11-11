"""The inner loop never hides an error (verification of 10 November 2026, point b): before, _tick_loop had «except
Exception: pass», so a step that failed every second stopped the steps after it (end of the holds, expiry of the
approvals, scheduled actions) without a line in the log. Now each step is guarded, the error is written as "engine loop
step failed" (level error, read by the alert «Motori: righe di errore») at most once per step and kind every
TICK_ERROR_EVERY_S, and the other steps go on. The errors of the background tasks are written the same way.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"


@pytest.fixture
def lines(monkeypatch):
    written: list[tuple[str, dict]] = []
    monkeypatch.setattr(core.logs, "error", lambda msg, **fields: written.append((msg, fields)))
    return written


def engine():
    return core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)


def broken(*_args):
    raise KeyError("guasto simulato")


def test_a_failing_step_is_written_and_the_others_go_on(lines):
    async def main():
        e = engine()
        e.set_hold(60, "comfort", ACTOR, CORR)
        e.hold["until"] = core.iso(core.utcnow() - timedelta(minutes=1))       # the hold has just ended
        e.regulate = broken                                                     # a step before it fails
        e.last_regulation = float("-inf")
        e.tick()
        return e
    e = asyncio.run(main())
    assert e.hold is None                                                       # before: still on, every second
    assert [d for d in e.decisions if d["action"] == "hold_expired"]
    assert lines == [("engine loop step failed", {
        "apartment_id": "apt-prova-01", "step": "regulate", "error_type": "KeyError", "error": "'guasto simulato'",
        "at": f"broken:{broken.__code__.co_firstlineno + 1}", "unwritten_before": 0})]


def test_one_line_per_step_and_kind_every_ten_minutes(lines, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(core.time, "monotonic", lambda: clock[0])
    e = engine()
    e.regulate = broken
    for _ in range(5):                                                          # five failures in a few seconds
        e.last_regulation = float("-inf")
        e.tick()
        clock[0] += 1
    assert len(lines) == 1
    clock[0] += core.TICK_ERROR_EVERY_S
    e.last_regulation = float("-inf")
    e.tick()
    assert len(lines) == 2 and lines[1][1]["unwritten_before"] == 4             # the line says how many were left out


def test_a_scheduled_action_that_breaks_does_not_stop_the_next_and_does_not_run_again(lines):
    async def main():
        e = engine()
        e.ensure_started()
        when = core.iso(core.utcnow() - timedelta(seconds=5))
        first = e.create_schedule({"run_at": core.iso(core.utcnow() + timedelta(minutes=5)),
                                   "action": {"type": "apartment_mode", "mode": "eco"}}, ACTOR, CORR)
        second = e.create_schedule({"run_at": core.iso(core.utcnow() + timedelta(minutes=6)),
                                    "action": {"type": "apartment_mode", "mode": "comfort"}}, ACTOR, CORR)
        e.schedule[first["schedule_id"]].update(run_at=when, kind="sconosciuto")   # its label is missing: KeyError
        e.schedule[second["schedule_id"]]["run_at"] = when
        e.tick()
        e.tick()
        for t in [e.loop_task, e.consumer_task, *e.tasks]:
            t.cancel()
        return e, first["schedule_id"], second["schedule_id"]
    e, first, second = asyncio.run(main())
    assert e.schedule[first]["status"] == "failed" and e.schedule[second]["status"] == "done"
    assert [f["step"] for _, f in lines] == ["schedule"]                         # the second tick does not run it again


def test_an_error_in_a_background_task_is_written(lines):
    async def main():
        e = engine()

        async def window_reflex():
            raise core.MockError(409, "device_offline", "Collegamento ai dispositivi non disponibile")
        e.spawn(window_reflex())
        await asyncio.sleep(0.05)
    asyncio.run(main())
    assert [(m, f["step"], f["error_type"]) for m, f in lines] == [
        ("engine loop step failed", "task window_reflex", "MockError")]
