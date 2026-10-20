"""Approvals expire (D-118): an approval nobody decides is closed when its expires_at passes, with its decision and
its events, and the next one in the queue opens. Duration and action at expiry are read from the approval the engine
creates (today 30 minutes and "reject", an open decision of the client): the test holds whatever they become.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

from engine import core
from engine.connector.simulated import SimulatedConnector

CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"


def test_an_undecided_approval_expires_and_the_queue_moves_on(monkeypatch):
    engine = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    first = engine.trigger_approval(CORR)
    queued = engine.trigger_approval(CORR)              # waits behind the first
    assert first["status"] == "pending" and queued is None and len(engine.approval_queue) == 1
    created, expires = core.parse_dt(first["created_at"]), core.parse_dt(first["expires_at"])
    lasts, action = expires - created, first["expires_action"]
    assert lasts > timedelta(0) and action in ("reject", "approve", "wait")
    commands_before = len(engine.commands)
    last_event = int(engine.events[-1]["id"])

    real_now = core.utcnow

    async def tick_at(moment):
        monkeypatch.setattr(core, "utcnow", lambda: moment)
        engine.tick()
        monkeypatch.setattr(core, "utcnow", real_now)

    asyncio.run(tick_at(created + lasts - timedelta(seconds=1)))   # not yet
    assert engine.approvals[0]["status"] == "pending"
    asyncio.run(tick_at(created + lasts + timedelta(seconds=1)))   # just past expires_at

    closed = next(a for a in engine.approvals if a["approval_id"] == first["approval_id"])
    assert closed["status"] == "expired"
    assert dict(engine.store.all("approvals"))[first["approval_id"]]["status"] == "expired"   # saved too
    expiry = [d for d in engine.decisions if d["approval_id"] == first["approval_id"] and d["action"] == "expire"]
    assert len(expiry) == 1 and expiry[0]["reasoning"].startswith("Approvazione scaduta senza risposta")
    new_events = [e for e in engine.events if int(e["id"]) > last_event]
    logged = [e for e in new_events if e["event"] == "decision.logged" and e["data"]["action"] == "expire"]
    assert logged and logged[0]["data"]["approval_id"] == first["approval_id"]
    # the queue moves on: the next approval opens, and the app hears it
    assert not engine.approval_queue
    opened = engine.pending_approval()
    assert opened is not None and opened["approval_id"] != first["approval_id"]
    assert any(e["event"] == "approval.pending" and e["data"]["approval_id"] == opened["approval_id"] for e in new_events)
    # what the expiry does to the proposed action follows expires_action
    if action == "approve":
        assert len(engine.commands) > commands_before
    else:
        assert len(engine.commands) == commands_before
