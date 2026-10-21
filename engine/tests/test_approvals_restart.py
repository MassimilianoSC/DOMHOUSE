"""P-60 step 8d (D-137): approvals across a restart on the same engine.db: the open one and the queue come back as they were, one that expired
while the engine was down is closed at the first tick and the next one opens, a decision after the restart works.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
ACTOR = "prova@hqe.it"


def engine(db):
    return core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))


def test_the_open_approval_and_the_queue_come_back(tmp_path):
    db = tmp_path / "engine.db"
    first = engine(db)
    opened = first.trigger_approval(CORR)
    assert first.trigger_approval(CORR) is None and len(first.approval_queue) == 1
    first.store.close()
    second = engine(db)
    assert second.restored
    again = second.pending_approval()
    assert again == opened                                       # same id, times, texts, proposed action
    assert len(second.approval_queue) == 1 and second.approval_queue[0]["status"] == "pending"
    assert [a["approval_id"] for a in second.list_approvals("pending")["items"]] == [opened["approval_id"]]
    second.store.close()


def test_one_that_expired_while_down_closes_at_the_first_tick_and_the_next_opens(tmp_path, monkeypatch):
    db = tmp_path / "engine.db"
    first = engine(db)
    opened = first.trigger_approval(CORR)
    first.trigger_approval(CORR)
    first.store.close()
    later = core.parse_dt(opened["expires_at"]) + timedelta(minutes=5)   # the engine was down past the expiry
    monkeypatch.setattr(core, "utcnow", lambda: later)
    second = engine(db)

    async def tick():
        second.tick()
    asyncio.run(tick())
    closed = next(a for a in second.approvals if a["approval_id"] == opened["approval_id"])
    assert closed["status"] == "expired"
    nxt = second.pending_approval()
    assert nxt is not None and nxt["approval_id"] != opened["approval_id"] and not second.approval_queue
    assert core.parse_dt(nxt["created_at"]) == later                     # its 30 minutes start when it opens
    second.store.close()


def test_a_decision_after_the_restart_runs_the_proposed_action(tmp_path):
    db = tmp_path / "engine.db"
    first = engine(db)
    opened = first.trigger_approval(CORR)
    first.store.close()

    async def main():
        second = engine(db)
        second.ensure_started()
        decided = second.decide(opened["approval_id"], {"decision": "approve"}, ACTOR, CORR)
        assert decided["status"] == "approved" and decided["decided_by"] == ACTOR
        assert any(c["device_id"] == opened["proposed_action"]["device_id"] for c in second.commands.values())
        second.store.close()
        third = engine(db)
        assert next(a for a in third.approvals if a["approval_id"] == opened["approval_id"])["status"] == "approved"
        third.store.close()
    asyncio.run(main())
