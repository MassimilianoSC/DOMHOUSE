"""D07 (P-83 review, gravity 2), the BFF's side: the booking archive (apply_booking_event) folds the events in the order
they arrive; an event sent again after newer ones (Italianway retries what got a 502) made a cancelled booking
«booked» again, and an old «checkin» put back a «checked_out». Now the archive keeps the time of the last event applied
and an older one only joins the list of events seen (idempotence), changing nothing else. The engine follows the same
rule (engine/tests/test_booking_order.py). The time stays out of the answer of #10 (D-90, like the other technical
fields)."""
from datetime import UTC, datetime, timedelta

from bff.repository.base import apply_booking_event

NOW = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)


def iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def ev(eid, kind, ts, cin=NOW + timedelta(days=2)):
    return {"event_id": eid, "type": kind, "booking_id": "bk-a", "checkin_at": iso(cin),
            "checkout_at": iso(cin + timedelta(days=2)), "source": "italianway", "ts": iso(ts)}


def fold(*events):
    rec = None
    for x in events:
        rec = apply_booking_event(rec, "apt-prova-01", x)
    return rec


def test_a_change_older_than_the_cancellation_leaves_it_cancelled():
    rec = fold(ev("iw-1", "booking_created", NOW - timedelta(minutes=10)),
               ev("iw-3", "booking_cancelled", NOW - timedelta(minutes=1)),
               ev("iw-2", "booking_changed", NOW - timedelta(minutes=5), cin=NOW + timedelta(days=3)))
    assert rec.status == "cancelled" and rec.checkin_at == iso(NOW + timedelta(days=2))
    assert rec.event_ids == ["iw-1", "iw-3", "iw-2"] and rec.last_event_type == "booking_cancelled"


def test_an_old_checkin_after_the_check_out_changes_nothing():
    rec = fold(ev("iw-1", "booking_created", NOW - timedelta(days=3)), ev("iw-co", "checkout", NOW),
               ev("iw-ci", "checkin", NOW - timedelta(hours=1)))
    assert rec.status == "checked_out"


def test_in_order_everything_applies_as_before():
    rec = fold(ev("iw-1", "booking_created", NOW - timedelta(minutes=10)),
               ev("iw-3", "booking_cancelled", NOW - timedelta(minutes=1)),
               ev("iw-4", "booking_changed", NOW, cin=NOW + timedelta(days=3)))
    assert rec.status == "booked" and rec.checkin_at == iso(NOW + timedelta(days=3))


def test_the_time_is_never_shown():
    from bff.routes import apartments
    import inspect
    assert "last_event_ts" in inspect.getsource(apartments.list_bookings)
