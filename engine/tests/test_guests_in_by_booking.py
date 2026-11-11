"""D18 (P-83 review, gravity 2), the engine's part: «with guests in» (the assistant asks before «casa vuota» or switching
a climate or the boiler off) was decided only by occupancy, which becomes «occupied» only with a check-in event; a
booking in course without that event (the normal case with Italianway, which may not send it) counted as «nobody in»,
while the scheduled actions already looked at the bookings' calendar (D-170). Now a booking in course, not cancelled
and not checked out, counts as guests in for the immediate approvals and for the keywords' boiler too. (The occupancy
shown, and the site's useStays, stay as the contract says: o2 aligns the site.) Scenario of the independent
verification (V-D18/prova_d18.py), inverted.

Run: python -m pytest engine/tests -q
"""
from datetime import timedelta

from engine import core
from engine.tests.test_assistant import CLIMA, Script, ask, cmd, engine, js, mode, quick  # noqa: F401 (fixture)

CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"


def booked(e, checked_out=False):
    now = core.utcnow()
    ci, co = now - timedelta(hours=5), now + timedelta(days=2)
    e.ingest_booking({"event_id": "e1", "type": "booking_created", "booking_id": "bk-1", "checkin_at": core.iso(ci),
                      "checkout_at": core.iso(co), "source": "italianway", "ts": core.iso(now)}, CORR)
    if checked_out:
        e.ingest_booking({"event_id": "e2", "type": "checkout", "booking_id": "bk-1", "checkin_at": core.iso(ci),
                          "checkout_at": core.iso(co), "source": "italianway", "ts": core.iso(now)}, CORR)


def test_a_booking_in_course_without_check_in_asks_before_emptying_the_apartment():
    e = engine(Script(js("Casa vuota.", mode("empty"))))
    booked(e)
    assert e.apartment()["occupancy"] != "occupied"           # what is shown stays as the contract says
    a = ask(e, "metti casa vuota")
    assert a["status"] == "needs_approval" and e.pending_approval() is not None


def test_a_booking_in_course_without_check_in_asks_before_switching_the_climate_off():
    e = engine(Script(js("Spengo.", cmd(CLIMA, "climate", "turn_off"))))
    booked(e)
    a = ask(e, "spegni il clima")
    assert a["status"] == "needs_approval"


def test_after_the_check_out_it_does_not_ask():
    e = engine(Script(js("Spengo.", cmd(CLIMA, "climate", "turn_off"))))
    booked(e, checked_out=True)
    a = ask(e, "spegni il clima")
    assert a["status"] != "needs_approval"


def test_the_engines_question_says_with_guests():
    e = engine(Script())
    booked(e)
    assert e.guests_in()
