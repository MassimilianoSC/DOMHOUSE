"""D43 and D57 (P-83 review, gravity 3): two read-modify-write of the BFF without a transaction.
D43: the booking archive read the record, folded the event and wrote it back: two events of the same booking at once
(Italianway's retries) lost one (verified with a slowed read: event_ids e0, e2, the change of e1 gone).
D57: pruning the dead push tokens (and an admin's change of a user) read the record and wrote it back: a user deleted
in between came back (verified: an operator «['vivo']», a viewer). Now both go through the repository's atomic
operations (fold_booking_event, update_user_if_present; upsert_user_keeping_an_admin refuses a record gone). The same
operations on Firestore are in tests/repository_suite_test.py, with the emulator."""
import asyncio

import pytest

from bff import push
from bff.bookings import forwarder
from bff.bookings.translator import BookingEvent
from bff.repository import User, get_repository


def run(coro):
    return asyncio.run(coro)


def event(eid, kind, checkout):
    return BookingEvent(event_id=eid, type=kind, booking_id="bk-d43", checkin_at="2026-12-01T14:00:00.000Z",
                        checkout_at=checkout, source="italianway", ts=f"2026-11-11T10:00:0{eid[-1]}.000Z")


def test_two_events_of_the_same_booking_at_once_both_count(monkeypatch):
    repo = get_repository()
    slow = repo.get_booking

    async def slowed(*a, **k):                     # between the old code's read and its write the other event slips in
        got = await slow(*a, **k)
        await asyncio.sleep(0.05)
        return got
    monkeypatch.setattr(repo, "get_booking", slowed)

    async def main():
        await forwarder._archive("apt-d43", event("e0", "booking_created", "2026-12-04T10:00:00.000Z"))
        await asyncio.gather(forwarder._archive("apt-d43", event("e1", "booking_changed", "2026-12-05T10:00:00.000Z")),
                             forwarder._archive("apt-d43", event("e2", "checkin", "2026-12-05T10:00:00.000Z")))
        monkeypatch.setattr(repo, "get_booking", slow)
        return await repo.get_booking("apt-d43", "bk-d43")
    rec = run(main())
    assert set(rec.event_ids) == {"e0", "e1", "e2"} and rec.checkout_at == "2026-12-05T10:00:00.000Z"


def test_pruning_tokens_never_brings_a_deleted_user_back(monkeypatch):
    repo = get_repository()
    run(repo.upsert_user(User(uid="u-d57", email="d57@demo.it", tenant_id="t-flatsharing-demo", role="operator",
                              push_tokens=["morto", "vivo"])))
    listed = repo.list_users

    async def listed_then_deleted(tenant_id):
        users = await listed(tenant_id)
        if any(u.uid == "u-d57" for u in users):
            await repo.delete_user("u-d57")       # the admin removes the person while the pruning runs
        return users
    monkeypatch.setattr(repo, "list_users", listed_then_deleted)
    run(push._prune_tokens(["morto"]))
    monkeypatch.setattr(repo, "list_users", listed)
    assert run(repo.get_user("u-d57")) is None


def test_an_admins_change_of_a_user_deleted_meanwhile_is_not_found():
    repo = get_repository()
    gone = User(uid="u-d57b", email="d57b@demo.it", tenant_id="t-flatsharing-demo", role="viewer")
    assert run(repo.upsert_user_keeping_an_admin(gone)) is None and run(repo.get_user("u-d57b")) is None
