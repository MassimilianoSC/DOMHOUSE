"""D07 (P-83 review, gravity 2): booking events out of order. An event that failed (the BFF answered 502 after three
tries) is sent again by Italianway later, after newer ones: before, a «booking_changed» older than the cancellation
brought the cancelled booking back (its prearrival warmed the apartment for nobody), and a «checkin» older than the
check-out made the guests «in» again. Now each booking keeps the time (ts) of the last event applied, and an older one
is acknowledged (200, so it is not sent again), written in a decision, and changes nothing. The BFF's archive follows
the same rule (tests/booking_order_test.py). Scenarios of the independent verification (V-D07/prova_d07.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import UTC, datetime, timedelta

from engine import core
from engine.connector.simulated import SimulatedConnector

CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
NOW = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)


def ev(eid, kind, ts, cin=NOW + timedelta(days=2), cout=NOW + timedelta(days=4)):
    return {"event_id": eid, "type": kind, "booking_id": "bk-a", "checkin_at": core.iso(cin),
            "checkout_at": core.iso(cout), "source": "italianway", "ts": core.iso(ts)}


def engine(monkeypatch):
    monkeypatch.setattr(core, "utcnow", lambda: NOW)
    return core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)


def planned(e):
    return [s for s in e.schedule.values() if s["booking_id"] == "bk-a" and s["status"] == "planned"]


def test_a_change_older_than_the_cancellation_does_not_bring_it_back(monkeypatch):
    e = engine(monkeypatch)
    e.ingest_booking(ev("iw-1", "booking_created", NOW - timedelta(minutes=10)), CORR)
    e.ingest_booking(ev("iw-3", "booking_cancelled", NOW - timedelta(minutes=1)), CORR)
    late = ev("iw-2", "booking_changed", NOW - timedelta(minutes=5), cin=NOW + timedelta(days=3),
              cout=NOW + timedelta(days=5))
    code, result = e.ingest_booking(late, CORR)
    assert code == 200 and result["accepted"] and not result["duplicate"] and result["schedule_ids"] == []
    assert e.bookings["bk-a"]["cancelled"] and planned(e) == []
    assert e.bookings["bk-a"]["checkin"] == NOW + timedelta(days=2)              # the dates did not move either
    stale = [d for d in e.decisions if d["action"] == "booking_event_stale"]
    assert len(stale) == 1 and "bk-a" in stale[0]["reasoning"]
    code, again = e.ingest_booking(late, CORR)                                   # the same event once more: duplicate
    assert code == 200 and again["duplicate"]


def test_a_checkin_older_than_the_check_out_does_not_put_the_guests_back_in(monkeypatch):
    e = engine(monkeypatch)
    e.ingest_booking(ev("iw-1", "booking_created", NOW - timedelta(days=3)), CORR)
    e.ingest_booking(ev("iw-co", "checkout", NOW), CORR)
    e.ingest_booking(ev("iw-ci", "checkin", NOW - timedelta(hours=1)), CORR)
    b = e.bookings["bk-a"]
    assert (b["checked_in"], b["checked_out"]) == (False, True)


def test_events_in_order_still_apply_and_the_same_time_counts_as_newer(monkeypatch):
    e = engine(monkeypatch)
    e.ingest_booking(ev("iw-1", "booking_created", NOW - timedelta(minutes=10)), CORR)
    e.ingest_booking(ev("iw-2", "booking_changed", NOW - timedelta(minutes=10), cin=NOW + timedelta(days=3),
                        cout=NOW + timedelta(days=5)), CORR)
    assert e.bookings["bk-a"]["checkin"] == NOW + timedelta(days=3)
    e.ingest_booking(ev("iw-3", "booking_cancelled", NOW), CORR)
    e.ingest_booking(ev("iw-4", "booking_changed", NOW + timedelta(minutes=1)), CORR)   # newer: revived on purpose
    assert not e.bookings["bk-a"]["cancelled"] and planned(e)


def test_the_last_time_survives_a_restart(monkeypatch, tmp_path):
    from engine.store import SqliteStore
    monkeypatch.setattr(core, "utcnow", lambda: NOW)
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(tmp_path / "e.db"))
    e.ingest_booking(ev("iw-1", "booking_created", NOW - timedelta(minutes=10)), CORR)
    e.ingest_booking(ev("iw-3", "booking_cancelled", NOW - timedelta(minutes=1)), CORR)
    again = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(tmp_path / "e.db"))
    again.ingest_booking(ev("iw-2", "booking_changed", NOW - timedelta(minutes=5)), CORR)
    assert again.bookings["bk-a"]["cancelled"]
