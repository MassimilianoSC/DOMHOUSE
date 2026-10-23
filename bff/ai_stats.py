"""The assistant's weekly counters (lot 31, decision 120, D-183 point 129): per apartment and week (Monday to Sunday in
Europe/Rome, «2026-W43»), in Firestore ai_stats/{apartment}__{week}, kept 12 months (TTL, bff/retention.py).

- asks: every question once (its ask_id is remembered in the document), when the site reads its final state through
  the proxy (answered, needs_approval or failed);
- quick: the answers of the quick assistant by cause, from the ask's reason «risposta_rapida:<cause>» (D-182 point 4);
- timeouts: the questions the full assistant did not answer in time (reason «risposta_rapida:timeout», or failed with
  reason «timeout»): the engine gives up before the model call ends, so the gateway alone would miss them;
- twins: the second identical requests the gateway started (D-182 layer 1).

GET /app/admin/assistant-stats sums the organisation's apartments: the weeks from the most recent (the current one,
in progress, first), zeros included, and over_threshold when each of the last two complete weeks has timeouts above
THRESHOLD_PERCENT of its questions (the measure of D-182 that reopens the choice of the model).

Counting is best effort: a failed write never touches the answer the person gets; it leaves a warning.
"""
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from .logs import warn
from .repository import get_repository

ROME = ZoneInfo("Europe/Rome")
CAUSES = ("timeout", "model_unavailable", "monthly_cap", "json_invalid")
FINAL = ("answered", "needs_approval", "failed")
QUICK_PREFIX = "risposta_rapida:"
THRESHOLD_PERCENT = 10
MAX_WEEKS = 26


def week_of(moment: datetime) -> str:
    """The ISO week of the moment in Rome: «2026-W43»."""
    year, week, _ = moment.astimezone(ROME).date().isocalendar()
    return f"{year}-W{week:02d}"


def bounds(week: str) -> tuple[str, str]:
    """(Monday, Sunday) of the week, as dates «2026-10-19»."""
    year, number = week.split("-W")
    monday = date.fromisocalendar(int(year), int(number), 1)
    return monday.isoformat(), (monday + timedelta(days=6)).isoformat()


def last_weeks(n: int, now: datetime) -> list[str]:
    """The n weeks up to the current one, the current first."""
    today = now.astimezone(ROME).date()
    return [week_of(datetime.combine(today - timedelta(weeks=i), datetime.min.time(), ROME)) for i in range(n)]


def _when(created_at) -> datetime:
    try:
        return datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)


async def count_ask(apartment_id: str, ask) -> None:
    """A question's final state as the engine gave it (AskStatus): counted once per ask_id."""
    if not isinstance(ask, dict) or ask.get("status") not in FINAL or not ask.get("ask_id"):
        return
    reason = str(ask.get("reason") or "")
    quick = reason[len(QUICK_PREFIX):] if reason.startswith(QUICK_PREFIX) else None
    timeout = quick == "timeout" or (ask["status"] == "failed" and reason == "timeout")
    week = week_of(_when(ask.get("created_at")))
    try:
        await get_repository().add_ai_stats(apartment_id, week, bounds(week), asks=1, timeouts=int(timeout),
                                            quick=quick if quick in CAUSES else None, ask_id=str(ask["ask_id"]))
    except Exception as exc:
        warn("assistant stats not written", apartment_id=apartment_id, error=type(exc).__name__)


async def count_twin(apartment_id: str) -> None:
    week = week_of(datetime.now(UTC))
    try:
        await get_repository().add_ai_stats(apartment_id, week, bounds(week), twins=1)
    except Exception as exc:
        warn("assistant stats not written", apartment_id=apartment_id, error=type(exc).__name__)


def _over(row: dict) -> bool:
    return row["asks"] > 0 and row["timeouts"] * 100 > THRESHOLD_PERCENT * row["asks"]


async def report(apartment_ids: list[str], weeks: int, now: datetime | None = None) -> dict:
    """The organisation's totals week by week (the current first, zeros included) and the threshold."""
    names = last_weeks(max(weeks, 3), now or datetime.now(UTC))
    docs = await get_repository().get_ai_stats([f"{a}__{w}" for a in apartment_ids for w in names])
    rows = []
    for w in names:
        frm, to = bounds(w)
        row = {"week": w, "from": frm, "to": to, "asks": 0, "timeouts": 0, "twins": 0,
               "quick": {c: 0 for c in CAUSES}}
        for a in apartment_ids:
            d = docs.get(f"{a}__{w}")
            if not d:
                continue
            for k in ("asks", "timeouts", "twins"):
                row[k] += int(d.get(k) or 0)
            for c in CAUSES:
                row["quick"][c] += int((d.get("quick") or {}).get(c) or 0)
        rows.append(row)
    return {"weeks": rows[:weeks], "threshold_percent": THRESHOLD_PERCENT,
            "over_threshold": _over(rows[1]) and _over(rows[2])}
