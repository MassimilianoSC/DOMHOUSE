"""D67 and D68 (P-83 review, gravity 4), the booking events of the BFF.
D67: BookingEvent.model_dump() always has guests (None when the event does not say it) and the archive took it: a
check-in without guests erased the 3 of the booking, and the export read «Ospiti: non indicato» (the engine keeps no
guests: the archive is the only source). Now a missing number leaves the one known.
D68: an Italianway reservation without id (or with id null) became booking_id '' or 'None', and its event_id
iw-None-<type>-<sent_at>: two such bookings sent at the same moment, the second dropped as a duplicate. Now refused,
422 untranslatable, the engine never called."""
import pytest

from bff.bookings.translator import BookingEvent, ItalianwayTranslator, TranslationError
from bff.repository.base import apply_booking_event


def event(eid, kind, guests=None):
    return BookingEvent(event_id=eid, type=kind, booking_id="bk-d67", checkin_at="2026-12-01T14:00:00.000Z",
                        checkout_at="2026-12-04T10:00:00.000Z", guests=guests, source="italianway",
                        ts=f"2026-11-11T10:00:0{eid[-1]}.000Z").model_dump()


def test_an_event_without_guests_keeps_the_known_number():
    rec = apply_booking_event(None, "apt-d67", event("e1", "booking_created", guests=3))
    rec = apply_booking_event(rec, "apt-d67", event("e2", "checkin"))
    assert rec.guests == 3 and rec.status == "checked_in"
    rec = apply_booking_event(rec, "apt-d67", event("e3", "booking_changed", guests=2))
    assert rec.guests == 2                                  # a number said replaces it


def italianway(reservation):
    return {"event": "reservation.created", "sent_at": "2026-11-11T10:00:00.000Z",
            "reservation": {"apartment_id": "IW-1", "checkin": "2026-12-01T14:00:00.000Z",
                            "checkout": "2026-12-04T10:00:00.000Z", **reservation}}


@pytest.mark.parametrize("reservation", [{}, {"id": None}, {"id": ""}, {"id": "  "}])
def test_a_reservation_without_id_is_refused(reservation):
    with pytest.raises(TranslationError, match="id"):
        ItalianwayTranslator().translate(italianway(reservation))


def test_a_reservation_with_its_id_is_translated():
    ext, ev = ItalianwayTranslator().translate(italianway({"id": 4711}))
    assert ext == "IW-1" and ev.booking_id == "4711"
