"""D09 (P-83 review, gravity 2), the expiry part only: an approval of a mode change that expires with «approve» (F1, the
check-out with movement seen) during a hold went straight to the new mode, against the hold, while a scheduled mode
change waits for the hold's end (D-122). Now it waits as well: it becomes an action that runs at the end of the hold,
with the decision «rimandata per la forzatura». (A decision by hand, or a mode change from the app, during a hold waits
for the committente's choice: not here.) Scenario of the independent verification (V-D09/test_d09.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
ACTOR = "prova@hqe.it"
SENSOR = "dev-ambiente-soggiorno"


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "0.001")


def ticks(e, n=1, gap=0.03):
    async def main():
        for _ in range(n):
            e.tick()
            await asyncio.sleep(gap)
    asyncio.run(main())


def tick_at(monkeypatch, e, when):
    async def main():
        monkeypatch.setattr(core, "utcnow", lambda: when)
        e.tick()
        await asyncio.sleep(0.03)
        monkeypatch.undo()
    asyncio.run(main())


def open_f1():
    """The check-out of bk-f1 40 minutes ago with a movement 5 minutes ago: the F1 approval, approved at expiry."""
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    now = core.utcnow()
    e.mode = "comfort"
    e.ingest_booking({"event_id": "evt-f1", "type": "booking_created", "booking_id": "bk-f1",
                      "checkin_at": core.iso(now - timedelta(days=2)), "checkout_at": core.iso(now - timedelta(minutes=40)),
                      "source": "manual", "ts": core.iso(now)}, CORR)
    e.devices[SENSOR]["capabilities"]["motion"]["last_seen"] = core.iso(now - timedelta(minutes=5))
    ticks(e)
    a = e.pending_approval()
    assert a and a["proposed_action"] == {"type": "apartment_mode", "mode": "empty"} and a["expires_action"] == "approve"
    return e, a


def test_expired_during_a_hold_it_waits_for_the_end_of_the_hold(monkeypatch):
    e, a = open_f1()
    e.set_hold(120, None, ACTOR, CORR)
    expiry = core.parse_dt(a["expires_at"]) + timedelta(seconds=1)
    tick_at(monkeypatch, e, expiry)
    tick_at(monkeypatch, e, expiry + timedelta(seconds=1))
    assert a["status"] == "expired" and e.hold is not None and e.mode == "comfort"
    assert any(d["action"] == "schedule_deferred" and "forzatura" in d["reasoning"] for d in e.decisions)
    deferred = [s for s in e.schedule.values() if s["status"] == "planned" and s["action"]["type"] == "apartment_mode"]
    assert [(s["kind"], s["source"]) for s in deferred] == [("empty", "booking")]   # values of the contract
    tick_at(monkeypatch, e, core.parse_dt(e.hold["until"]) + timedelta(seconds=1))      # the hold ends
    tick_at(monkeypatch, e, core.parse_dt(a["expires_at"]) + timedelta(minutes=121))
    assert e.hold is None and e.mode == "empty"


def test_without_a_hold_it_applies_at_expiry_as_before(monkeypatch):
    e, a = open_f1()
    tick_at(monkeypatch, e, core.parse_dt(a["expires_at"]) + timedelta(seconds=1))
    assert e.mode == "empty"
