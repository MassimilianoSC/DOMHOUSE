"""A5 (docs/proposta-a5.md §2 steps 3-5, answers 1210): the refused logins of each device, read from the log view that
holds only the lines «broker device refused» of broker-vm.sh check. Each 5-minute slot is written by two rounds of the
check: the server counts it once. 24 hours, the last time; null when the server does not know (no view configured, a
read that failed). Read at most once every 5 minutes per apartment (a copy in memory). The filter is built only from
an id that follows the rule, never from a user's text."""
import asyncio
import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from bff import device_refusals as dr
from bff.config import get_settings

VIEW = "projects/p/locations/global/buckets/_Default/views/domhouse-rifiuti"
NOW = datetime(2026, 11, 20, 17, 12, 30, tzinfo=UTC)


def line(apt, device, slot, count, last, pid=42):
    return (f"domhouse-check[{pid}]: broker device refused apt={apt} device={device} slot={slot} count={count} "
            f"last={last}")


@pytest.fixture
def logs(monkeypatch):
    settings = dataclasses.replace(get_settings(), device_refusals_view=VIEW, gcp_project_id="p")
    monkeypatch.setattr(dr, "get_settings", lambda: settings)
    state = type("S", (), {"messages": [], "calls": [], "fail": False, "now": NOW})()

    async def entries(view, flt):
        state.calls.append((view, flt))
        if state.fail:
            raise OSError("logging non risponde")
        return list(state.messages)
    monkeypatch.setattr(dr, "_entries", entries)
    monkeypatch.setattr(dr, "_now", lambda: state.now)
    dr.clear()
    yield state
    dr.clear()


def read(apt="lab-07"):
    return asyncio.run(dr.for_apartment(apt))


def test_a_slot_written_twice_counts_once_and_devices_are_summed(logs):
    logs.messages = [
        line("lab-07", "plug", "2026-11-20T17:05:00Z", 2, "2026-11-20T17:08:20Z"),
        line("lab-07", "plug", "2026-11-20T17:05:00Z", 2, "2026-11-20T17:08:20Z", pid=43),   # the next round
        line("lab-07", "plug", "2026-11-20T17:00:00Z", 1, "2026-11-20T17:01:00Z"),
        line("lab-07", "shelly-1", "2026-11-20T16:00:00Z", 3, "2026-11-20T16:04:59Z"),
    ]
    assert read() == {"plug": {"conteggio_24h": 3, "ultimo": "2026-11-20T17:08:20Z"},
                      "shelly-1": {"conteggio_24h": 3, "ultimo": "2026-11-20T16:04:59Z"}}


def test_a_later_round_of_the_same_slot_with_more_refusals_keeps_the_larger(logs):
    logs.messages = [line("lab-07", "plug", "2026-11-20T17:05:00Z", 1, "2026-11-20T17:06:00Z"),
                     line("lab-07", "plug", "2026-11-20T17:05:00Z", 4, "2026-11-20T17:09:00Z")]
    assert read() == {"plug": {"conteggio_24h": 4, "ultimo": "2026-11-20T17:09:00Z"}}


def test_slots_older_than_24_hours_are_left_out(logs):
    logs.messages = [line("lab-07", "plug", "2026-11-19T17:10:00Z", 5, "2026-11-19T17:11:00Z"),
                     line("lab-07", "plug", "2026-11-19T17:05:00Z", 7, "2026-11-19T17:06:00Z")]
    assert read() == {"plug": {"conteggio_24h": 5, "ultimo": "2026-11-19T17:11:00Z"}}


@pytest.mark.parametrize("bad", [
    line("lab-08", "plug", "2026-11-20T17:05:00Z", 2, "2026-11-20T17:08:20Z"),             # another apartment
    line("lab-07", "Plug", "2026-11-20T17:05:00Z", 2, "2026-11-20T17:08:20Z"),             # out of the id rule
    line("lab-07", "<b>x</b>", "2026-11-20T17:05:00Z", 2, "2026-11-20T17:08:20Z"),
    line("lab-07", "plug", "ieri", 2, "2026-11-20T17:08:20Z"),
    line("lab-07", "plug", "2026-11-20T17:05:00Z", -2, "2026-11-20T17:08:20Z"),
    line("lab-07", "plug", "2026-11-20T17:05:00Z", 2, "2026-11-20T17:08:20Z") + " extra",
    "domhouse-check[42]: broker device refused other slot=2026-11-20T17:05:00Z count=9",
    "domhouse-check[42]: broker auth refused hour=101 top_ip=1.2.3.4(101) top_client=lab-07.plug(101)",
])
def test_lines_that_are_not_exactly_this_apartments_are_ignored(logs, bad):
    logs.messages = [bad]
    assert read() == {}


def test_no_refusals_is_an_empty_map_not_null(logs):
    assert read() == {}
    assert dr.view_of({}, "plug") == {"conteggio_24h": 0, "ultimo": None}
    assert dr.view_of(None, "plug") is None


def test_the_filter_names_the_view_the_apartment_and_24_hours(logs):
    read()
    (view, flt), = logs.calls
    assert view == VIEW
    assert '"broker device refused apt=lab-07 "' in flt
    assert 'timestamp>="2026-11-19T17:' in flt


def test_read_at_most_once_every_5_minutes_per_apartment(logs):
    read()
    read()
    assert len(logs.calls) == 1
    read("lab-08")
    assert len(logs.calls) == 2
    logs.now = NOW + timedelta(minutes=5, seconds=1)
    read()
    assert len(logs.calls) == 3
    assert dr.cached("lab-07") == {}
    assert dr.cached("lab-09") is None


def test_without_a_view_the_answer_is_null_and_nothing_is_read(logs, monkeypatch):
    monkeypatch.setattr(dr, "get_settings", lambda: dataclasses.replace(get_settings(), device_refusals_view=""))
    assert read() is None
    assert logs.calls == []


def test_a_failed_read_is_null_and_is_not_retried_at_once(logs):
    logs.fail = True
    assert read() is None
    assert read() is None
    assert len(logs.calls) == 1
    logs.fail = False
    logs.now = NOW + timedelta(minutes=1, seconds=1)
    assert read() == {}


@pytest.mark.parametrize("apt", ['lab-07" OR "x', "Lab-07", "", "a" * 65, "lab 07"])
def test_an_id_out_of_the_rule_never_reaches_the_filter(logs, apt):
    assert read(apt) is None
    assert logs.calls == []


REAL_ENTRIES = dr._entries


def test_review_1_pages_that_end_before_the_data_are_null_not_a_partial_count(logs, monkeypatch):
    """Review A5, point 1: with nextPageToken still there after the last page read, the count would be cut silently."""
    monkeypatch.setattr(dr, "_entries", REAL_ENTRIES)
    monkeypatch.setattr(dr, "_token", lambda: "t")
    pages = []

    async def page(client, body, token):
        pages.append(dict(body))
        return {"entries": [{"jsonPayload": {"message": line("lab-07", "plug", "2026-11-20T17:05:00Z", 1,
                                                             "2026-11-20T17:06:00Z")}}], "nextPageToken": "again"}
    monkeypatch.setattr(dr, "_page", page)
    assert read() is None
    assert len(pages) == dr.MAX_PAGES


def test_review_1_a_complete_reading_over_two_pages_counts(logs, monkeypatch):
    monkeypatch.setattr(dr, "_entries", REAL_ENTRIES)
    monkeypatch.setattr(dr, "_token", lambda: "t")
    answers = [
        {"entries": [{"jsonPayload": {"message": line("lab-07", "plug", "2026-11-20T17:05:00Z", 2,
                                                      "2026-11-20T17:06:00Z")}}], "nextPageToken": "p2"},
        {"entries": [{"jsonPayload": {"message": line("lab-07", "plug", "2026-11-20T17:00:00Z", 1,
                                                      "2026-11-20T17:01:00Z")}}]},
    ]

    async def page(client, body, token):
        return answers.pop(0)
    monkeypatch.setattr(dr, "_page", page)
    assert read() == {"plug": {"conteggio_24h": 3, "ultimo": "2026-11-20T17:06:00Z"}}


def test_review_5_a_slow_reading_stops_at_the_total_limit_and_is_null(logs, monkeypatch):
    async def slow(view, flt):
        await asyncio.sleep(2)
        return []
    monkeypatch.setattr(dr, "_entries", slow)
    monkeypatch.setattr(dr, "READ_TIMEOUT_S", 0.05)
    assert read() is None
    assert dr.READ_TIMEOUT_S <= 8
