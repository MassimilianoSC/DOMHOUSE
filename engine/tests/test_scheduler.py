"""The scheduler (P-60 step 4): the apartment's local hours across the clock changes, a stable order, each action run
once, and actions that follow the last version of what changed them (the booking, the app).

Europe/Rome in 2026: CET -> CEST on Sunday 29 March (02:00 -> 03:00), CEST -> CET on Sunday 25 October (03:00 -> 02:00).

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

ROME = ZoneInfo("Europe/Rome")
ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"


def engine():
    return core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)


def at(monkeypatch, moment: datetime):
    """The engine's clock (utcnow) set to a moment."""
    monkeypatch.setattr(core, "utcnow", lambda: moment.astimezone(UTC))


def tick(e):
    async def main():
        e.tick()
    asyncio.run(main())


# ---- local days and hours ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("first, last, starts", [
    # October: the 25th has 25 hours
    ("2026-10-24", "2026-10-27", ["2026-10-23T22:00:00.000Z", "2026-10-24T22:00:00.000Z", "2026-10-25T23:00:00.000Z",
                                  "2026-10-26T23:00:00.000Z"]),
    # March: the 29th has 23 hours
    ("2026-03-28", "2026-03-31", ["2026-03-27T23:00:00.000Z", "2026-03-28T23:00:00.000Z", "2026-03-29T22:00:00.000Z",
                                  "2026-03-30T22:00:00.000Z"]),
])
def test_energy_days_start_at_local_midnight(monkeypatch, first, last, starts):
    at(monkeypatch, datetime(2026, 12, 1, tzinfo=UTC))
    frm = datetime.fromisoformat(first).replace(tzinfo=ROME)
    to = datetime.fromisoformat(last).replace(tzinfo=ROME) + timedelta(days=1)
    report = engine().energy({"from": core.iso(frm), "to": core.iso(to), "bucket": "day"})
    assert [s["ts"] for s in report["series"]] == starts
    for s in report["series"]:
        assert datetime.fromisoformat(s["ts"].replace("Z", "+00:00")).astimezone(ROME).time().hour == 0


@pytest.mark.parametrize("now_local, text, expected_utc", [
    # 02:30 on 29 March does not exist (02:00 -> 03:00): the action runs at 03:30 local time, 01:30 UTC
    (datetime(2026, 3, 28, 20, 0), "alle 2:30 metti eco", "2026-03-29T01:30:00.000Z"),
    # 02:30 on 25 October happens twice: the first one, in summer time (00:30 UTC)
    (datetime(2026, 10, 24, 20, 0), "alle 2:30 metti eco", "2026-10-25T00:30:00.000Z"),
    # an ordinary hour the day after the change: local time, the new offset
    (datetime(2026, 10, 25, 20, 0), "alle 18 metti eco", "2026-10-26T17:00:00.000Z"),
])
def test_assistant_hours_are_the_apartments_local_hours(monkeypatch, now_local, text, expected_utc):
    at(monkeypatch, now_local.replace(tzinfo=ROME))
    e = engine()
    monkeypatch.setattr(core.asyncio, "sleep", _no_wait)

    async def main():
        ask = e.create_ask({"text": text}, ACTOR, CORR)       # answered by a task: wait for it
        await asyncio.gather(*e.tasks)
        return ask["ask_id"]
    answer = e.asks[asyncio.run(main())]
    assert answer["status"] == "answered", answer
    item = e.schedule[answer["actions"][0]["schedule_id"]]
    assert item["run_at"] == expected_utc and item["action"] == {"type": "apartment_mode", "mode": "eco"}


async def _no_wait(_seconds):
    return None


# ---- order and once ------------------------------------------------------------------------------------------------
def test_actions_due_together_run_once_in_creation_order(monkeypatch):
    now = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    at(monkeypatch, now)
    e = engine()
    run_at = now - timedelta(minutes=1)
    first = e.add_schedule(run_at, {"type": "apartment_mode", "mode": "eco"}, "manual", "manual")
    second = e.add_schedule(run_at, {"type": "apartment_mode", "mode": "comfort"}, "manual", "manual")
    tick(e)
    tick(e)                                                        # a second pass finds nothing left to do
    assert e.schedule[first["schedule_id"]]["status"] == e.schedule[second["schedule_id"]]["status"] == "done"
    modes = [d["new_value"] for d in e.decisions if d["action"] == "set_mode"]
    assert modes == ["eco", "comfort"] and e.mode == "comfort"     # the older first, the newer wins; each once


# ---- what changes an action while it is planned ---------------------------------------------------------------------
def booking(e, kind, checkin, checkout, n):
    return e.ingest_booking({"event_id": f"evt-sched-{n}", "type": kind, "booking_id": "bk-sched",
                             "checkin_at": core.iso(checkin), "checkout_at": core.iso(checkout), "source": "manual",
                             "ts": core.iso(core.utcnow())}, CORR)


def items_of(e, kind):
    return [i for i in e.schedule.values() if i["booking_id"] == "bk-sched" and i["kind"] == kind]


def test_booking_changed_before_the_prearrival_moves_it(monkeypatch):
    now = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    at(monkeypatch, now)
    e = engine()
    booking(e, "booking_created", now + timedelta(days=2), now + timedelta(days=4), 1)
    booking(e, "booking_changed", now + timedelta(days=3), now + timedelta(days=5), 2)
    pre = items_of(e, "prearrival")
    hours = e.rule("prearrival")["params"]["hours_before"]
    assert len(pre) == 1 and pre[0]["run_at"] == core.iso(now + timedelta(days=3) - timedelta(hours=hours))
    assert [i["run_at"] for i in items_of(e, "checkout") if i["status"] == "planned"] == \
        [core.iso(now + timedelta(days=5) + timedelta(minutes=e.rule("checkout_eco")["params"]["minutes_after"]))]


def test_booking_changed_after_the_prearrival_plans_a_new_one(monkeypatch):
    now = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    at(monkeypatch, now)
    e = engine()
    booking(e, "booking_created", now + timedelta(hours=1), now + timedelta(days=2), 1)   # prearrival already due
    tick(e)
    assert [i["status"] for i in items_of(e, "prearrival")] == ["done"]
    booking(e, "booking_changed", now + timedelta(days=1), now + timedelta(days=3), 2)   # arrival moved a day later
    statuses = sorted(i["status"] for i in items_of(e, "prearrival"))
    assert statuses == ["done", "planned"]                         # the done one stays done, a new one is planned


def test_booking_cancelled_cancels_what_is_still_planned(monkeypatch):
    now = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    at(monkeypatch, now)
    e = engine()
    booking(e, "booking_created", now + timedelta(days=2), now + timedelta(days=4), 1)
    booking(e, "booking_cancelled", now + timedelta(days=2), now + timedelta(days=4), 2)
    assert {i["status"] for i in e.schedule.values() if i["booking_id"] == "bk-sched"} == {"cancelled"}
    at(monkeypatch, now + timedelta(days=5))
    tick(e)                                                        # nothing runs any more
    assert not [d for d in e.decisions if d["action"] == "set_mode"]


def test_app_move_then_booking_change_follows_the_booking(monkeypatch):
    """The app may move an action planned by a booking; a later change of the booking recalculates it (the app warns
    about it when moving: «sarà ricalcolata a una modifica della prenotazione»)."""
    now = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
    at(monkeypatch, now)
    e = engine()
    booking(e, "booking_created", now + timedelta(days=2), now + timedelta(days=4), 1)
    pre = items_of(e, "prearrival")[0]
    e.move_schedule(pre["schedule_id"], {"run_at": core.iso(now + timedelta(days=1))}, ACTOR, CORR)
    assert e.schedule[pre["schedule_id"]]["run_at"] == core.iso(now + timedelta(days=1))
    booking(e, "booking_changed", now + timedelta(days=3), now + timedelta(days=4), 2)
    hours = e.rule("prearrival")["params"]["hours_before"]
    assert e.schedule[pre["schedule_id"]]["run_at"] == core.iso(now + timedelta(days=3) - timedelta(hours=hours))
