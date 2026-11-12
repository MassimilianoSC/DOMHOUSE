"""D10 (P-83 review, gravity 3): an approval approved at its expiry (F1, the check-out with movement) that expired while
the engine was down ran at the first tick after the restart, hours late, while a scheduled action as late is closed as
missed (MISSED_AFTER_MINUTES). Now such an approval, expired longer ago than that, is closed without running its action,
with a «failed» decision that says why. (The independent verification's scenario, V-D10/test_d10.py, with the next
guest already in, is now kept in comfort by D05; here the case without another booking.)

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
SENSOR = "dev-ambiente-soggiorno"


def engine(db):
    return core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))


def tick(e):
    async def main():
        e.tick()
        await asyncio.sleep(0.05)
    asyncio.run(main())


def pending_f1(db, t0):
    first = engine(db)
    first.mode = "comfort"
    first.ingest_booking({"event_id": "e1", "type": "booking_created", "booking_id": "bk-out",
                          "checkin_at": core.iso(t0 - timedelta(days=2)), "checkout_at": core.iso(t0 - timedelta(minutes=31)),
                          "source": "manual", "ts": core.iso(t0)}, CORR)
    first.devices[SENSOR]["capabilities"]["motion"]["last_seen"] = core.iso(t0 - timedelta(minutes=5))
    tick(first)
    f1 = first.pending_approval()
    assert f1 is not None and f1["expires_action"] == "approve" and first.mode == "comfort"
    first._save_apartment()
    first.store.close()
    return f1


def test_expired_hours_ago_during_an_outage_it_is_not_run(tmp_path, monkeypatch):
    db = tmp_path / "engine.db"
    t0 = core.utcnow()
    f1 = pending_f1(db, t0)
    monkeypatch.setattr(core, "utcnow", lambda: t0 + timedelta(hours=4))
    second = engine(db)
    tick(second)
    a = next(x for x in second.approvals if x["approval_id"] == f1["approval_id"])
    assert a["status"] == "expired" and second.mode == "comfort"
    late = [d for d in second.decisions if d["outcome"] == "failed" and "non eseguita" in (d["reasoning"] or "")]
    assert len(late) == 1 and late[0]["approval_id"] == f1["approval_id"]
    second.store.close()


def test_expired_just_now_it_is_run_as_before(tmp_path, monkeypatch):
    db = tmp_path / "engine.db"
    t0 = core.utcnow()
    f1 = pending_f1(db, t0)
    monkeypatch.setattr(core, "utcnow", lambda: core.parse_dt(f1["expires_at"]) + timedelta(seconds=5))
    second = engine(db)
    tick(second)
    assert second.mode == "empty"
    second.store.close()
