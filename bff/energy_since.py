"""D-130: the date of an apartment's first real reading (`energy_since`), without touching the contract.

The engine's GET /energy counts 0 for an hour without readings (the contract has no "unknown"), so the app cannot
tell "nothing used" from "nothing measured yet". The BFF finds the first hour with kWh > 0 and keeps it in the
apartment's record: the PWA writes «consumi disponibili dal <data>» under the chart, the Excel report leaves the earlier
hours empty instead of 0.

How: GET /energy by day, in windows of 31 days (the contract's maximum) going back from now, while a window has some
consumption, at most MAX_WINDOWS (the engine keeps 24 months of telemetry); then the first day with consumption asked
by hour. A window with no consumption at all ends the search (the most recent one too: no data yet). The result only
moves back in time, never forward. Without a result it tries again at most once every RETRY_S per apartment; the
apartment list never waits for it (background), the Excel report does.
Limit, written in the guide: the date is the first hour with consumption above zero, so meters that read 0 for the
first days (everything off) give a date a little later than the real connection.
"""
import asyncio
import time
from datetime import UTC, datetime, timedelta

from . import instances
from .logs import warn
from .repository import Apartment, get_repository

WINDOW = timedelta(days=31)
MAX_WINDOWS = 24
RETRY_S = 3600.0
TIMEOUT_S = 10.0
_next_try: dict[str, float] = {}         # apartment_id -> monotonic time of the next search allowed
_tasks: set[asyncio.Task] = set()        # background searches (kept referenced until they end)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


async def _series(apt: Apartment, actor: str, frm: datetime, to: datetime, bucket: str) -> list[dict]:
    resp = await instances.call(apt, "GET", "/energy", actor=actor, timeout=TIMEOUT_S,
                                params={"from": iso(frm), "to": iso(to), "bucket": bucket})
    resp.raise_for_status()
    return resp.json().get("series") or []


def _first_with_consumption(series: list[dict]) -> datetime | None:
    found = [parse(p["ts"]) for p in series if float(p.get("kwh") or 0) > 0]
    return min(found) if found else None


async def find_first(apt: Apartment, actor: str, now: datetime) -> datetime | None:
    """The start of the first hour with consumption, or None when there is none yet."""
    first_day, to = None, now
    for _ in range(MAX_WINDOWS):
        day = _first_with_consumption(await _series(apt, actor, to - WINDOW, to, "day"))
        if day is None:
            break
        first_day, to = day, to - WINDOW
    if first_day is None:
        return None
    hour = _first_with_consumption(await _series(apt, actor, first_day, min(first_day + timedelta(hours=25), now), "hour"))
    return hour or first_day


async def search_and_save(apt: Apartment, actor: str, now: datetime | None = None, force: bool = False) -> str | None:
    """One search (at most one every RETRY_S per apartment, unless forced: the Excel report); a result earlier than
    the stored one is saved."""
    key = apt.apartment_id
    if not force and _next_try.get(key, 0.0) > time.monotonic():
        return None
    _next_try[key] = time.monotonic() + RETRY_S
    try:
        found = await find_first(apt, actor, now or datetime.now(UTC))
    except Exception as exc:                     # engine unreachable, 501, anything: try again later
        warn("energy_since search failed", apartment_id=key, error=type(exc).__name__)
        return None
    if found is None:
        return None
    repo = get_repository()
    stored = await repo.get_apartment(key)       # re-read: only energy_since changes, whatever else was saved stays
    if stored is not None and (stored.energy_since is None or found < parse(stored.energy_since)):
        stored.energy_since = iso(found)
        await repo.upsert_apartment(stored)
        _next_try.pop(key, None)
        return stored.energy_since
    return stored.energy_since if stored is not None else iso(found)


async def known(apt: Apartment, actor: str, *, wait: bool = False) -> str | None:
    """The stored date; when there is none, a search: awaited (the Excel report) or in the background (the list)."""
    if apt.energy_since:
        return apt.energy_since
    if wait:
        return await search_and_save(apt, actor, force=True)
    task = asyncio.get_running_loop().create_task(search_and_save(apt, actor))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return None
