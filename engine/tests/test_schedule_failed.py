"""A scheduled action the engine refuses at its time (D-198, the same defect as point c of the verification of 10
November 2026): before, it became «failed» without a word, and the manager did not know why the boiler had not gone
off. Now a decision with outcome failed says so, with the engine's reason; also for an unexpected error. And the next
approval in the queue opens even when the expiring one fails unexpectedly (o1's review of 5287e4b).

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "gestore@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"


def engine():
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    e.ensure_started()
    return e


def socket(e) -> str:
    return next(d["device_id"] for d in e.devices.values() if "switch" in d["capabilities"])


def stop(e):
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


def due_command(e, device_id: str) -> dict:
    """A manual action whose time has just come."""
    return e.add_schedule(core.utcnow() - timedelta(seconds=1), {
        "type": "device_command", "device_id": device_id, "capability": "switch", "action": "turn_off"}, "manual", "manual")


def failures(e, n: int) -> list[tuple]:
    return [(d["actor"], d["target"], d["action"], d["outcome"], d["reasoning"]) for d in e.decisions[n:]
            if d["action"] == "schedule_failed"]


def test_a_scheduled_command_refused_at_its_time_says_why():
    async def main():
        e = engine()
        dev = socket(e)
        e.test_state({"device_id": dev, "online": False}, ACTOR, CORR)
        item = due_command(e, dev)
        n = len(e.decisions)
        e.tick()
        stop(e)
        return e.schedule[item["schedule_id"]], failures(e, n), item["run_at"]
    item, rows, run_at = asyncio.run(main())
    assert item["status"] == "failed"
    assert rows == [("system", {"type": "schedule"}, "schedule_failed", "failed",
                     "Azione programmata (manuale) non eseguita: Il dispositivo non è raggiungibile; riprova quando torna online")]


def test_an_unexpected_error_of_a_scheduled_action_is_said_too(monkeypatch):
    async def main():
        e = engine()
        item = due_command(e, socket(e))

        def broken(*_):
            raise RuntimeError("guasto di prova")
        monkeypatch.setattr(e, "_run_scheduled", broken)
        n = len(e.decisions)
        e.tick()
        e.tick()                                          # closed: a second pass does nothing more
        stop(e)
        return e.schedule[item["schedule_id"]], failures(e, n)
    item, rows = asyncio.run(main())
    assert item["status"] == "failed"
    assert rows == [("system", {"type": "schedule"}, "schedule_failed", "failed",
                     "Azione programmata (manuale) non eseguita: errore interno del motore")]


def test_the_next_approval_opens_even_when_the_expiring_one_fails_unexpectedly(monkeypatch):
    async def main():
        e = engine()
        dev = socket(e)
        for what in ("Spegnere la presa", "Riaccendere la presa"):
            e._new_approval("rule", what, "Prova", {"type": "device_command", "device_id": dev, "capability": "switch",
                                                     "action": "turn_off"}, "approve", CORR)
        first = e.pending_approval()
        assert first["description"] == "Spegnere la presa" and len(e.approval_queue) == 1
        first["expires_at"] = core.iso(core.utcnow() - timedelta(seconds=1))

        def broken(*_):
            raise RuntimeError("guasto di prova")
        monkeypatch.setattr(e, "_execute_proposed", broken)
        e.tick()
        stop(e)
        return first, e.pending_approval()
    first, now_pending = asyncio.run(main())
    assert first["status"] == "expired"
    assert now_pending is not None and now_pending["description"] == "Riaccendere la presa"
