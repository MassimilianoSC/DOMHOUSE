"""GET /approvals?status=all: «also the closed ones of the last 7 days» (contract) are 7 days of the apartment's
calendar, from its midnight (verification of 10 November 2026, point e). Before, 7×24 hours back from now: the weekly
summary, made on Monday from 08:00, lost the approvals of the Monday before until that hour, and in the week that ends
summer time (169 hours) one hour more.

Run: python -m pytest engine/tests -q
"""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from engine import core
from engine.connector.simulated import SimulatedConnector

ROME = ZoneInfo("Europe/Rome")


def listed(monkeypatch, now: datetime, *created: datetime) -> list[str]:
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    for i, c in enumerate(created):
        e.approvals.append({"approval_id": f"apr-{i}", "status": "expired", "created_at": core.iso(c.astimezone(UTC)),
                            "expires_at": core.iso((c + timedelta(minutes=30)).astimezone(UTC))})
    monkeypatch.setattr(core, "utcnow", lambda: now.astimezone(UTC))
    return [a["approval_id"] for a in e.list_approvals("all")["items"]]


def test_from_the_midnight_of_seven_days_ago(monkeypatch):
    got = listed(monkeypatch, datetime(2026, 11, 9, 8, 5, tzinfo=ROME),      # Monday, the summary's round
                 datetime(2026, 11, 2, 0, 30, tzinfo=ROME),                    # the Monday before, 00:30: in
                 datetime(2026, 11, 1, 23, 30, tzinfo=ROME))                   # the Sunday before it: out
    assert got == ["apr-0"]                                                    # before: [] (cut at 08:05)


def test_the_week_that_ends_summer_time(monkeypatch):
    got = listed(monkeypatch, datetime(2026, 10, 26, 8, 5, tzinfo=ROME),     # after the night of 25 October
                 datetime(2026, 10, 19, 0, 30, tzinfo=ROME))
    assert got == ["apr-0"]


def test_pending_ones_always_and_by_default_only_those(monkeypatch):
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    old = datetime(2026, 1, 5, 9, 0, tzinfo=ROME)
    e.approvals.append({"approval_id": "apr-p", "status": "pending", "created_at": core.iso(old.astimezone(UTC)),
                        "expires_at": None})
    monkeypatch.setattr(core, "utcnow", lambda: datetime(2026, 11, 9, 8, 5, tzinfo=ROME).astimezone(UTC))
    assert [a["approval_id"] for a in e.list_approvals("all")["items"]] == ["apr-p"]
    assert [a["approval_id"] for a in e.list_approvals("pending")["items"]] == ["apr-p"]
