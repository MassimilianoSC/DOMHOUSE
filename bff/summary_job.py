"""The weekly summary's job (P-60 step 11, D-133 point 2, D-150): once an hour, for every enabled apartment, the summary
of the week that ended is computed when it is due (Monday 08:00 local) and missing, stored in Firestore (summaries,
12 months) and pushed in the category «Riepilogo» when it has something to say. A missed hour or a restart of the BFF
loses nothing: the next round finds the summary missing and makes it. The data come through the contract only:
/energy one local day at a time (the contract gives the per-device split only for the range asked; 35 days, at most
MAX_PARALLEL calls at once), /decisions, /approvals, /devices, and the bookings the BFF keeps. Computation:
bff/weekly_summary.py.
The BFF runs as one instance always on (bff/cloudrun*.yaml: minScale = maxScale = 1, CPU not throttled), so one loop
is enough; during a deploy two revisions overlap for a few minutes: the first round waits FIRST_ROUND_S and a push sent
twice carries the same tag, so the phone shows it once.
"""
import asyncio
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import instances, weekly_summary as ws
from .config import get_settings
from .logs import info, warn
from .repository import get_repository

ROUND_S = 3600
FIRST_ROUND_S = 300          # the first round 5 minutes after the start, not during it
MAX_PARALLEL = 3
ACTOR = "system:weekly-summary"
_task: asyncio.Task | None = None


async def _get(apt, path: str, **params) -> dict:
    resp = await instances.call(apt, "GET", path, actor=ACTOR, params=params or None)
    resp.raise_for_status()
    return resp.json()


async def nights(apt, tz: ZoneInfo, first_day, days: int) -> list[ws.Night]:
    gate = asyncio.Semaphore(MAX_PARALLEL)

    async def one(i: int) -> ws.Night:
        day = first_day + timedelta(days=i)
        start = datetime.combine(day, time(0, 0), tzinfo=tz)
        async with gate:
            body = await _get(apt, "/energy", **{"from": ws.iso(start), "to": ws.iso(start + timedelta(days=1)),
                                                 "bucket": "day"})
        return ws.Night(day, float(body.get("total_kwh") or 0),
                        {d["device_id"]: float(d.get("kwh") or 0) for d in body.get("by_device") or []})
    return list(await asyncio.gather(*(one(i) for i in range(days))))


async def decisions(apt, start: datetime, end: datetime) -> list[dict]:
    out, cursor = [], None
    for _ in range(50):                            # at most 10 000 decisions in a week
        params = {"from": ws.iso(start), "to": ws.iso(end), "limit": "200"}
        if cursor:
            params["cursor"] = cursor
        body = await _get(apt, "/decisions", **params)
        out += body.get("items") or []
        cursor = body.get("next_cursor")
        if not cursor:
            break
    return out


async def make(apt, now: datetime | None = None) -> dict | None:
    """The summary of the week that ended, when due; None when not due yet. Raises when the engine does not answer."""
    now = now or datetime.now(UTC)
    tz = ZoneInfo(apt.timezone)
    monday, due = ws.last_week(now, tz)
    if not due:
        return None
    start = datetime.combine(monday, time(0, 0), tzinfo=tz)
    end = start + timedelta(days=7)
    before_first = monday - timedelta(weeks=ws.WEEKS_BEFORE)
    all_nights = await nights(apt, tz, before_first, 7 * (ws.WEEKS_BEFORE + 1))
    devices = (await _get(apt, "/devices")).get("devices") or []
    labels = {d["device_id"]: d.get("label") or d["device_id"] for d in devices}
    return ws.build(apt.apartment_id, apt.timezone, monday, now,
                    nights_week=[n for n in all_nights if n.day >= monday],
                    nights_before=[n for n in all_nights if n.day < monday],
                    bookings=await get_repository().list_bookings(apt.apartment_id), devices=devices,
                    decisions=await decisions(apt, start, end),
                    approvals=(await _get(apt, "/approvals", status="all")).get("items") or [],
                    energy_since=apt.energy_since, labels=labels)


def summary_push(apt, summary: dict):
    from .push import build_push
    items = summary["items"]
    body = items[0] + (f" E altre {len(items) - 1} voci." if len(items) > 1 else "")
    return build_push("summary", apt, f"{apt.name}: riepilogo della settimana", body,
                      f"/a/{apt.apartment_id}/riepiloghi/{summary['week']}",
                      f"summary:{apt.apartment_id}:{summary['week']}", summary["generated_at"])


async def round_once(now: datetime | None = None) -> int:
    """One round over every enabled apartment; returns the number of summaries made."""
    from .push import send_to_tenant
    repo = get_repository()
    made = 0
    for apt in await repo.list_apartments():
        if not apt.enabled:
            continue
        monday, due = ws.last_week(now or datetime.now(UTC), ZoneInfo(apt.timezone))
        if not due or await repo.get_summary(apt.apartment_id, ws.week_id(monday)):
            continue
        try:
            summary = await make(apt, now)
        except Exception as exc:                   # the engine does not answer now: the next round tries again
            warn("weekly summary not made", apartment_id=apt.apartment_id, error=type(exc).__name__)
            continue
        if summary is None:
            continue
        await repo.put_summary(summary)
        made += 1
        info("weekly summary made", apartment_id=apt.apartment_id, week=summary["week"], items=len(summary["items"]))
        if summary["notable"]:                     # D-150 point 4: the push only with something to say
            await send_to_tenant(apt.tenant_id, "summary", *summary_push(apt, summary))
    return made


async def _loop() -> None:
    await asyncio.sleep(FIRST_ROUND_S)
    while True:
        try:
            await round_once()
        except Exception as exc:
            warn("weekly summary round failed", error=type(exc).__name__)
        await asyncio.sleep(ROUND_S)


def start() -> None:
    """Called at the BFF's start; SUMMARY_JOB=false keeps it off (the test runs)."""
    global _task
    if not get_settings().summary_job or (_task and not _task.done()):
        return
    _task = asyncio.get_running_loop().create_task(_loop())
