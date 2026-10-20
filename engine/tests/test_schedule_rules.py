"""Two decisions of the client on the scheduler (P-60 step 4b):
- D-121: a booking cancelled after its prearrival puts the apartment back to "empty", with its decision, unless another
  booking needs the warmth; another booking's planned actions stay and warm it up for that one;
- D-122: during a hold, scheduled mode actions wait for its end (holds last at most 720 minutes, the contract's
  maximum) and run then, with their decision; waited for on purpose, they are never "missed" at a restart.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import UTC, datetime, timedelta

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
NOW = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)


def at(monkeypatch, moment):
    monkeypatch.setattr(core, "utcnow", lambda: moment)


def tick(e):
    in_loop(e.tick)


def in_loop(fn, *args):
    """Runs fn inside an event loop: changing mode starts commands, which are tasks."""
    async def main():
        return fn(*args)
    return asyncio.run(main())


def booking(e, bid, kind, checkin, checkout, n):
    return e.ingest_booking({"event_id": f"evt-{bid}-{n}", "type": kind, "booking_id": bid,
                             "checkin_at": core.iso(checkin), "checkout_at": core.iso(checkout), "source": "manual",
                             "ts": core.iso(core.utcnow())}, CORR)


def mode_changes(e):
    return [d["new_value"] for d in e.decisions if d["action"] == "set_mode"]


# ---- D-121 ---------------------------------------------------------------------------------------------------------
def test_cancelled_after_the_prearrival_goes_back_to_empty(monkeypatch):
    at(monkeypatch, NOW)
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    booking(e, "bk-a", "booking_created", NOW + timedelta(hours=1), NOW + timedelta(days=2), 1)   # prearrival due
    tick(e)
    assert e.mode == "comfort"
    status, result = booking(e, "bk-a", "booking_cancelled", NOW + timedelta(hours=1), NOW + timedelta(days=2), 2)
    reset = [d for d in e.decisions if d["action"] == "booking_cancel_reset"]
    assert len(reset) == 1 and reset[0]["new_value"] == "empty" and "bk-a" in reset[0]["reasoning"]
    assert any(ev["event"] == "decision.logged" and ev["data"]["action"] == "booking_cancel_reset" for ev in e.events)
    tick(e)                                                         # the scheduler runs the "empty" action at once
    assert e.mode == "empty" and mode_changes(e)[-1] == "empty"
    item = e.schedule[result["schedule_ids"][-1]]
    assert (item["kind"], item["source"], item["booking_id"], item["status"]) == ("empty", "booking", "bk-a", "done")


def test_cancelled_before_the_prearrival_changes_nothing(monkeypatch):
    at(monkeypatch, NOW)
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    booking(e, "bk-a", "booking_created", NOW + timedelta(days=2), NOW + timedelta(days=4), 1)
    booking(e, "bk-a", "booking_cancelled", NOW + timedelta(days=2), NOW + timedelta(days=4), 2)
    tick(e)
    assert not [d for d in e.decisions if d["action"] == "booking_cancel_reset"] and not mode_changes(e)


def test_another_booking_the_same_day_keeps_its_own_schedule(monkeypatch):
    """Another booking arrives later the same day: the cancelled one's warmth goes, the other one's prearrival stays
    planned and warms the apartment up again for it."""
    at(monkeypatch, NOW)
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    booking(e, "bk-a", "booking_created", NOW + timedelta(hours=1), NOW + timedelta(hours=5), 1)
    tick(e)
    booking(e, "bk-b", "booking_created", NOW + timedelta(hours=8), NOW + timedelta(days=2), 1)
    booking(e, "bk-a", "booking_cancelled", NOW + timedelta(hours=1), NOW + timedelta(hours=5), 2)
    tick(e)
    assert e.mode == "empty"
    pre_b = [s for s in e.schedule.values() if s["booking_id"] == "bk-b" and s["kind"] == "prearrival"]
    assert [s["status"] for s in pre_b] == ["planned"]
    at(monkeypatch, core.parse_dt(pre_b[0]["run_at"]) + timedelta(seconds=1))
    tick(e)
    assert e.mode == "comfort" and pre_b[0]["status"] == "done"


def test_no_reset_while_another_booking_needs_the_warmth(monkeypatch):
    at(monkeypatch, NOW)
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    booking(e, "bk-a", "booking_created", NOW + timedelta(hours=1), NOW + timedelta(days=2), 1)
    booking(e, "bk-b", "booking_created", NOW + timedelta(hours=1), NOW + timedelta(days=1), 1)   # also warmed up
    tick(e)
    booking(e, "bk-a", "booking_cancelled", NOW + timedelta(hours=1), NOW + timedelta(days=2), 2)
    tick(e)
    assert e.mode == "comfort" and not [d for d in e.decisions if d["action"] == "booking_cancel_reset"]


# ---- D-122 ---------------------------------------------------------------------------------------------------------
def test_a_mode_action_waits_for_the_end_of_the_hold(monkeypatch):
    at(monkeypatch, NOW)
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    in_loop(e.set_hold, 60, "comfort", ACTOR, CORR)
    item = e.add_schedule(NOW + timedelta(minutes=10), {"type": "apartment_mode", "mode": "empty"}, "manual", "manual")
    at(monkeypatch, NOW + timedelta(minutes=11))
    tick(e)
    tick(e)                                                         # one decision, however many passes
    deferred = [d for d in e.decisions if d["action"] == "schedule_deferred"]
    assert len(deferred) == 1 and "rimandata per la forzatura" in deferred[0]["reasoning"]
    assert e.schedule[item["schedule_id"]]["status"] == "planned" and e.mode == "comfort"
    at(monkeypatch, NOW + timedelta(minutes=61))                    # the hold expires: the action runs in that pass
    tick(e)
    assert e.hold is None and e.mode == "empty" and e.schedule[item["schedule_id"]]["status"] == "done"
    run = [d for d in e.decisions if d["action"] == "set_mode" and d["new_value"] == "empty"]
    assert run and "rimandata per la forzatura" in run[-1]["reasoning"]


def test_a_hold_lasts_at_most_twelve_hours(monkeypatch):
    at(monkeypatch, NOW)
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    try:
        in_loop(e.set_hold, 721, "comfort", ACTOR, CORR)
        raise AssertionError("a hold over 720 minutes was accepted")
    except core.MockError as exc:
        assert exc.status == 400
    hold = in_loop(e.set_hold, 720, "comfort", ACTOR, CORR)
    assert core.parse_dt(hold["until"]) == NOW + timedelta(hours=12)


def test_a_deferred_action_is_never_missed_at_a_restart(tmp_path, monkeypatch):
    db = tmp_path / "engine.db"
    at(monkeypatch, NOW)
    first = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    in_loop(first.set_hold, 180, "comfort", ACTOR, CORR)
    item = first.add_schedule(NOW + timedelta(minutes=10), {"type": "apartment_mode", "mode": "eco"}, "manual", "manual")
    at(monkeypatch, NOW + timedelta(minutes=11))
    tick(first)
    first.store.close()
    # the engine is down well past the action's time (and the hold's end): the action was waited for on purpose
    at(monkeypatch, NOW + timedelta(hours=4))
    second = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    assert second.schedule[item["schedule_id"]]["status"] == "planned"
    assert not [d for d in second.decisions if d["action"] == "schedule_missed"]
    tick(second)
    assert second.mode == "eco" and second.schedule[item["schedule_id"]]["status"] == "done"
    second.store.close()
