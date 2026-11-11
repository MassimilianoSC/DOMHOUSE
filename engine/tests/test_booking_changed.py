"""D06 (P-83 review, gravity 2): a booking changed after its prearrival had run. Before, the change planned a new
prearrival at the new (often already past) time and the next tick ran it: a manager's «eco» with guests in became
«comfort» again, even for a change of the guests' number alone, or after the check-out. And an arrival moved to
tomorrow left the apartment in «comfort» for nobody until then (a cancellation instead goes back to empty, D-121).
Now: a prearrival already done is not repeated when its new time is past; when the arrival moves to the future and
the guests are not in, the apartment goes back to empty now (unless another booking needs it, as for D-121) and the
prearrival is planned again at its new time. Scenarios of the independent verification
(revisione-verifiche/V-D06/test_d06.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import UTC, datetime, timedelta

from engine import core
from engine.connector.simulated import SimulatedConnector

CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
T0 = datetime(2026, 11, 2, 13, 0, tzinfo=UTC)     # 14:00 Rome: the prearrival of a 16:00 arrival


def at(monkeypatch, moment):
    monkeypatch.setattr(core, "utcnow", lambda: moment)


def in_loop(fn, *args):
    async def main():
        return fn(*args)
    return asyncio.run(main())


def tick(e):
    in_loop(e.tick)


def ev(e, bid, kind, ci, co, n):
    return in_loop(e.ingest_booking, {"event_id": f"evt-{bid}-{n}", "type": kind, "booking_id": bid,
                                      "checkin_at": core.iso(ci), "checkout_at": core.iso(co), "source": "manual",
                                      "ts": core.iso(core.utcnow())}, CORR)


def planned(e, bid, kind):
    return [s for s in e.schedule.values() if s["booking_id"] == bid and s["kind"] == kind and s["status"] == "planned"]


def warmed(monkeypatch, ci_hours=2, co_days=3):
    """bk-a created three days before; the prearrival ran at T0: comfort."""
    at(monkeypatch, T0 - timedelta(days=3))
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    for d in e.devices.values():                  # no movement: the check-out is direct, not an approval (F1)
        if "motion" in d["capabilities"]:
            d["capabilities"]["motion"]["last_seen"] = None
    ci, co = T0 + timedelta(hours=ci_hours), T0 + timedelta(days=co_days)
    ev(e, "bk-a", "booking_created", ci, co, 1)
    at(monkeypatch, T0)
    tick(e)
    assert e.mode == "comfort"
    return e, ci, co


def test_guests_in_and_eco_a_change_does_not_bring_comfort_back(monkeypatch):
    e, ci, co = warmed(monkeypatch)
    at(monkeypatch, ci + timedelta(hours=5))
    ev(e, "bk-a", "checkin", ci, co, 2)
    in_loop(e.set_mode, "eco", "user:gestore@x", CORR, "Gestore: eco")
    ev(e, "bk-a", "booking_changed", ci, co + timedelta(days=1), 3)     # the stay is one day longer
    tick(e)
    assert e.mode == "eco" and planned(e, "bk-a", "prearrival") == []
    ev(e, "bk-a", "booking_changed", ci, co + timedelta(days=1), 4)     # same dates (e.g. the guests' number)
    tick(e)
    assert e.mode == "eco"
    assert [core.parse_dt(s["run_at"]) for s in planned(e, "bk-a", "checkout")] == [
        co + timedelta(days=1, minutes=30)]                             # the check-out follows the new date


def test_arrival_moved_to_tomorrow_back_to_empty_and_warmed_again_tomorrow(monkeypatch):
    e, ci, co = warmed(monkeypatch)
    at(monkeypatch, T0 + timedelta(hours=1))
    ci2 = ci + timedelta(days=1)
    ev(e, "bk-a", "booking_changed", ci2, co, 2)
    tick(e)
    assert e.mode == "empty"
    assert [core.parse_dt(s["run_at"]) for s in planned(e, "bk-a", "prearrival")] == [ci2 - timedelta(hours=2)]
    at(monkeypatch, ci2 - timedelta(hours=2) + timedelta(seconds=1))
    tick(e)
    assert e.mode == "comfort"


def test_guests_already_in_stay_in_comfort(monkeypatch):
    e, ci, co = warmed(monkeypatch)
    at(monkeypatch, ci + timedelta(minutes=10))
    ev(e, "bk-a", "checkin", ci, co, 2)
    ev(e, "bk-a", "booking_changed", ci + timedelta(hours=3), co, 3)     # the arrival «moved» while they are in
    tick(e)
    assert e.mode == "comfort"


def test_another_booking_in_course_keeps_comfort(monkeypatch):
    e, ci, co = warmed(monkeypatch)
    ev(e, "bk-b", "booking_created", T0 - timedelta(days=1), T0 + timedelta(days=1), 1)   # in course now
    at(monkeypatch, T0 + timedelta(hours=1))
    ev(e, "bk-a", "booking_changed", ci + timedelta(days=1), co, 2)
    tick(e)
    assert e.mode == "comfort"


def test_a_change_after_the_check_out_does_not_warm_the_empty_apartment(monkeypatch):
    e, ci, co = warmed(monkeypatch, co_days=1)
    at(monkeypatch, co + timedelta(hours=1))
    ev(e, "bk-a", "checkout", ci, co, 2)
    tick(e)
    assert e.mode == "empty"
    before = len(e.decisions)
    ev(e, "bk-a", "booking_changed", ci, co, 3)
    tick(e)
    assert e.mode == "empty" and planned(e, "bk-a", "prearrival") == [] and planned(e, "bk-a", "checkout") == []
    # not even for a moment: before, the repeated prearrival and check-out both ran in the same tick
    assert [d for d in e.decisions[before:] if d["action"] == "set_mode"] == []
