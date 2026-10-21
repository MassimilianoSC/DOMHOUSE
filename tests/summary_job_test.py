"""The weekly summary's job and routes (P-60 step 11, D-150): the round makes the summary of the week that ended once
Monday 08:00 local has passed, once per apartment and week, stores it, pushes «Riepilogo» only when it has something to
say; an engine that does not answer loses nothing (the next round makes it); /energy one day at a time, never more
than MAX_PARALLEL at once; the routes show the summaries only on the apartments the user sees. In-process, dev auth,
memory repository, the instance replaced by a fake."""
import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from bff import instances, push, summary_job
from bff.main import app
from bff.repository import NotificationPrefs, get_repository

ROME = ZoneInfo("Europe/Rome")
BOLOGNA, RIMINI, ALTRA = "apt-bologna-01", "apt-rimini-01", "apt-altra-01"
ADMIN, VIEWER_ONLY_RIMINI = "admin@demo.it", "proprietario@demo.it"
BEFORE = datetime(2026, 10, 19, 7, 59, tzinfo=ROME).astimezone(UTC)     # Monday 19 October, 07:59 local
AFTER = datetime(2026, 10, 19, 8, 5, tzinfo=ROME).astimezone(UTC)
WEEK = "2026-W42"


def run(coro):
    return asyncio.run(coro)


def iso(dt):
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@pytest.fixture
def engine(monkeypatch):
    """Bologna: a device offline for 2 days (a notable week); Rimini and the other tenant: nothing to say.
    `state.down` = apartments whose engine does not answer."""
    state = type("S", (), {})()
    state.calls, state.down, state.running, state.peak = [], set(), 0, 0

    async def fake(apt, method, path, **kw):
        assert method == "GET" and kw["actor"] == summary_job.ACTOR
        state.calls.append((apt.apartment_id, path))
        if apt.apartment_id in state.down:
            raise httpx.ConnectError("down")
        state.running += 1
        state.peak = max(state.peak, state.running)
        await asyncio.sleep(0)
        state.running -= 1
        p = kw.get("params") or {}
        if path == "/energy":
            assert p["bucket"] == "day"
            body = {"total_kwh": 4.0, "by_device": [{"device_id": "m1", "kwh": 4.0}]}
        elif path == "/devices":
            offline = apt.apartment_id == BOLOGNA
            body = {"devices": [{"device_id": "m1", "label": "Presa camera", "online": not offline,
                                 "last_seen": iso(AFTER - timedelta(days=2))}]}
        elif path == "/decisions":
            body = {"items": [], "next_cursor": None}
        elif path == "/approvals":
            body = {"items": []}
        else:
            raise AssertionError(path)
        return httpx.Response(200, json=body, request=httpx.Request("GET", "http://x"))
    monkeypatch.setattr(instances, "call", fake)
    sent = []

    async def fake_send(tenant_id, pref, data, headers):
        sent.append((tenant_id, pref, data))
        return 1
    monkeypatch.setattr(push, "send_to_tenant", fake_send)
    state.sent = sent
    repo = get_repository()
    repo.summaries.clear()
    saved = [run(repo.get_apartment(apt_id)) for apt_id in (BOLOGNA, RIMINI, ALTRA)]
    for apt in saved:                                             # 5 weeks of real data and more (step 6)
        run(repo.upsert_apartment(apt.model_copy(update={"energy_since": "2026-01-01T00:00:00.000Z"})))
    yield state
    for apt in saved:                                             # the shared memory repository as it was
        run(repo.upsert_apartment(apt))
    repo.summaries.clear()


def test_made_after_monday_eight_once_per_week_pushed_only_when_notable(engine):
    assert run(summary_job.round_once(BEFORE)) == 0 and engine.calls == []        # not due yet: the engine untouched
    assert run(summary_job.round_once(AFTER)) == 3
    repo = get_repository()
    s = run(repo.get_summary(BOLOGNA, WEEK))
    assert s["items"] == ["Presa camera è offline da più di 24 ore."] and s["notable"]
    assert run(repo.get_summary(RIMINI, WEEK))["notable"] is False
    assert [(t, p, d["kind"], d["link"]) for t, p, d in engine.sent] == [
        ("t-flatsharing-demo", "summary", "summary", f"/a/{BOLOGNA}/riepiloghi/{WEEK}")]
    energy = [c for c in engine.calls if c == (BOLOGNA, "/energy")]
    assert len(energy) == 35 and engine.peak <= summary_job.MAX_PARALLEL           # 5 weeks, one day at a time
    n = len(engine.calls)
    assert run(summary_job.round_once(AFTER + timedelta(hours=1))) == 0 and len(engine.calls) == n   # already there


def test_an_engine_that_does_not_answer_loses_nothing(engine):
    engine.down = {RIMINI}
    assert run(summary_job.round_once(AFTER)) == 2
    assert run(get_repository().get_summary(RIMINI, WEEK)) is None
    engine.down = set()
    assert run(summary_job.round_once(AFTER + timedelta(hours=1))) == 1              # the next round makes it
    assert run(get_repository().get_summary(RIMINI, WEEK))["week"] == WEEK


def test_the_push_message():
    apt = run(get_repository().get_apartment(BOLOGNA))
    data, headers = summary_job.summary_push(apt, {"week": WEEK, "generated_at": iso(AFTER),
                                                   "items": ["Prima voce.", "Seconda.", "Terza."]})
    assert data["kind"] == "summary" and data["body"] == "Prima voce. E altre 2 voci."
    assert data["tag"] == f"summary:{BOLOGNA}:{WEEK}" and headers == {"Urgency": "normal", "TTL": str(7 * 86400)}
    assert NotificationPrefs().summary is True                                     # on by default


async def get(path, who=ADMIN):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(path, headers={"X-Dev-User": who})


def test_the_routes_only_on_the_apartments_the_user_sees(engine):
    run(summary_job.round_once(AFTER))
    r = run(get(f"/app/apartments/{BOLOGNA}/summaries"))
    assert r.status_code == 200 and r.json() == [{"week": WEEK, "from": "2026-10-11T22:00:00.000Z",
                                                  "to": "2026-10-18T22:00:00.000Z", "notable": True, "items": 1}]
    r = run(get(f"/app/apartments/{BOLOGNA}/summaries/{WEEK}"))
    assert r.status_code == 200 and r.json()["offline"]["now"][0]["label"] == "Presa camera"
    assert run(get(f"/app/apartments/{BOLOGNA}/summaries/2026-W41")).status_code == 404
    assert run(get(f"/app/apartments/{BOLOGNA}/summaries", VIEWER_ONLY_RIMINI)).status_code == 404
    assert run(get(f"/app/apartments/{RIMINI}/summaries/{WEEK}", VIEWER_ONLY_RIMINI)).status_code == 200
    assert run(get(f"/app/apartments/{ALTRA}/summaries")).status_code == 404       # another tenant's apartment
