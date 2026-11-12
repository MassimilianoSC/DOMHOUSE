"""D05 (P-83 review, gravity 2): bookings back to back. Guest A leaves, guest B arrives soon after: A's check-out
action (minutes_after, default 30) used to put the apartment to «casa vuota» even when B's prearrival had already
warmed it up or B was about to arrive, and nothing put it back: B found it cold. Now the check-out action, direct or
approved at the expiry of its approval, does not empty the apartment when another booking needs it (in course, its
prearrival done, or its arrival within the prearrival's hours); it says so in a decision. Scenarios of the independent
verification (revisione-verifiche/V-D05/test_d05.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
SENSOR = "dev-ambiente-soggiorno"
DAY = datetime(2026, 12, 5, 0, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "0.001")


def at(monkeypatch, moment):
    monkeypatch.setattr(core, "utcnow", lambda: moment)


def tick(e):
    async def main():
        e.tick()
        await asyncio.sleep(0.02)
    asyncio.run(main())


def ev(e, bid, kind, ci, co, n):
    return e.ingest_booking({"event_id": f"evt-{bid}-{n}", "type": kind, "booking_id": bid,
                             "checkin_at": core.iso(ci), "checkout_at": core.iso(co), "source": "manual",
                             "ts": core.iso(core.utcnow())}, CORR)


def no_motion(e):
    for d in e.devices.values():
        if "motion" in d["capabilities"]:
            d["capabilities"]["motion"]["last_seen"] = None


def walk(monkeypatch, gap_hours, motion_after_checkout=False):
    """Default rules (prearrival 2 h, checkout_eco 30 min). A: 2/12 -> 5/12 10:00Z; B arrives gap_hours later.
    Returns the engine and the mode when B arrives and three hours later."""
    at(monkeypatch, DAY - timedelta(days=4))
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    no_motion(e)
    a_ci, a_co = DAY - timedelta(days=3), DAY + timedelta(hours=10)
    b_ci, b_co = a_co + timedelta(hours=gap_hours), DAY + timedelta(days=3)
    ev(e, "bk-a", "booking_created", a_ci, a_co, 1)
    ev(e, "bk-b", "booking_created", b_ci, b_co, 1)
    plan = sorted((s["run_at"], s["booking_id"], s["kind"]) for s in e.schedule.values())
    at(monkeypatch, a_ci - timedelta(hours=2) + timedelta(seconds=1)); tick(e)
    at(monkeypatch, a_ci); ev(e, "bk-a", "checkin", a_ci, a_co, 2); tick(e)
    at(monkeypatch, a_co); ev(e, "bk-a", "checkout", a_ci, a_co, 3); tick(e)
    for run_at, bid, kind in plan:
        t = core.parse_dt(run_at)
        if t <= a_co or t >= b_ci:
            continue
        if motion_after_checkout and bid == "bk-a" and kind == "checkout":
            e.devices[SENSOR]["capabilities"]["motion"]["last_seen"] = core.iso(t - timedelta(minutes=10))
        at(monkeypatch, t + timedelta(seconds=1)); tick(e)
    at(monkeypatch, b_ci); ev(e, "bk-b", "checkin", b_ci, b_co, 2); tick(e)
    on_arrival = e.mode
    if (a := e.pending_approval()) is not None:
        at(monkeypatch, core.parse_dt(a["expires_at"]) + timedelta(seconds=1)); tick(e)
    for m in range(0, 180, 10):
        at(monkeypatch, b_ci + timedelta(minutes=m)); tick(e)
    at(monkeypatch, b_ci + timedelta(hours=3)); tick(e)
    return e, on_arrival, e.mode


@pytest.mark.parametrize("gap", [0.5, 1, 2, 2.5, 3, 5])
def test_the_next_guest_finds_the_apartment_warm(monkeypatch, gap):
    e, on_arrival, later = walk(monkeypatch, gap)
    assert (on_arrival, later) == ("comfort", "comfort"), gap


def test_with_movement_after_the_departure_the_approval_does_not_empty_it_either(monkeypatch):
    e, on_arrival, later = walk(monkeypatch, 2, motion_after_checkout=True)
    assert (on_arrival, later) == ("comfort", "comfort")


def test_the_kept_comfort_is_a_decision(monkeypatch):
    e, _, _ = walk(monkeypatch, 2)
    kept = [d for d in e.decisions if d["action"] == "checkout_kept_comfort"]
    assert len(kept) == 1 and "bk-b" in kept[0]["reasoning"] and "bk-a" in kept[0]["reasoning"]


def test_alone_the_check_out_still_empties_the_apartment(monkeypatch):
    """The control: no other booking, or the next one far away (beyond the prearrival's hours): empty as before."""
    at(monkeypatch, DAY - timedelta(days=4))
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    no_motion(e)
    a_ci, a_co = DAY - timedelta(days=3), DAY + timedelta(hours=10)
    ev(e, "bk-a", "booking_created", a_ci, a_co, 1)
    ev(e, "bk-far", "booking_created", a_co + timedelta(days=2), a_co + timedelta(days=4), 1)
    at(monkeypatch, a_ci - timedelta(hours=2) + timedelta(seconds=1)); tick(e)
    at(monkeypatch, a_co); ev(e, "bk-a", "checkout", a_ci, a_co, 2); tick(e)
    at(monkeypatch, a_co + timedelta(minutes=31)); tick(e)
    assert e.mode == "empty"
