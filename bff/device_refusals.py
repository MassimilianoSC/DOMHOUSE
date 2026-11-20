"""Tool A, package A5 (docs/proposta-a5.md §2, answers 1210): the refused logins of each device, for the page of the
devices' credentials.

broker-vm.sh check (every 5 minutes, on the VM) writes to syslog, for the two last complete 5-minute slots, one line
per device whose logins on 8883 were refused: "broker device refused apt=<apt> device=<device> slot=<start> count=<n>
last=<time>". The lines reach Cloud Logging (Ops Agent). A log view cannot filter on the text (only resource type, log
name and source), so a sink copies only these lines into a bucket of their own, domhouse-rifiuti (2 days), and the
server's identity may read only that bucket's view (DEVICE_REFUSALS_VIEW, its full resource name;
docs/procedura-installazione-a5.md). Here:

- each slot counts once (two rounds write it: the larger count wins), the slots of the last 24 hours are summed;
- the filter is built only from an apartment id that follows the rule, never from a user's text;
- read at most once every 5 minutes per apartment, a copy in memory (a failed read: null for a minute);
- null means «not known» (no view configured, as production until the second VM; a read that failed), never 0.

No address and no password ever reach these lines (D-231): the VM never writes them.
"""
import asyncio
import re
from datetime import UTC, datetime, timedelta

import httpx

from .config import get_settings
from .logs import warn

COPY_S = 300                        # §2 step 5: once every 5 minutes per apartment
FAILED_COPY_S = 60                  # a failed read is not retried at every page load
WINDOW = timedelta(hours=24)        # answer 1210, point 3
PAGE_SIZE = 1000
MAX_PAGES = 5                       # two lines per slot and device: 576 a day for one device always refused
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
TIME = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
LINE_RE = re.compile(rf"broker device refused apt=(\S+) device=(\S+) slot=({TIME}) count=(\d+) last=({TIME})$")
URL = "https://logging.googleapis.com/v2/entries:list"

_copies: dict[str, tuple[datetime, dict | None]] = {}
_credentials = None


def _now() -> datetime:
    return datetime.now(UTC)


def clear() -> None:
    _copies.clear()


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _token() -> str:
    """An access token of the server's identity (the same way as bff/ai_gateway.py)."""
    global _credentials
    import google.auth
    import google.auth.transport.requests
    if _credentials is None:
        _credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/logging.read"])
    if not _credentials.valid:
        _credentials.refresh(google.auth.transport.requests.Request())
    return _credentials.token


async def _entries(view: str, flt: str) -> list[str]:
    """The messages of the entries of the view that match the filter. Replaced in the tests."""
    token = await asyncio.to_thread(_token)
    out: list[str] = []
    body = {"resourceNames": [view], "filter": flt, "orderBy": "timestamp desc", "pageSize": PAGE_SIZE}
    async with httpx.AsyncClient(timeout=10) as client:
        for _ in range(MAX_PAGES):
            r = await client.post(URL, json=body, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            data = r.json()
            for e in data.get("entries", []):
                payload = e.get("jsonPayload") or {}
                message = payload.get("message") if isinstance(payload, dict) else None
                if isinstance(message, str):
                    out.append(message)
                elif isinstance(e.get("textPayload"), str):
                    out.append(e["textPayload"])
            if not data.get("nextPageToken"):
                break
            body["pageToken"] = data["nextPageToken"]
    return out


def count(apartment_id: str, messages: list[str], now: datetime) -> dict:
    """{device: {conteggio_24h, ultimo}} from the lines of this apartment only; each slot once (the larger count)."""
    since = _iso(now - WINDOW - timedelta(minutes=5))      # a slot counts when it ends inside the 24 hours
    slots: dict[tuple[str, str], tuple[int, str]] = {}
    for message in messages:
        m = LINE_RE.search(message)
        if not m:
            continue
        apt, device, slot, n, last = m.group(1), m.group(2), m.group(3), int(m.group(4)), m.group(5)
        if apt != apartment_id or not ID_RE.fullmatch(device) or slot <= since:
            continue
        before = slots.get((device, slot))
        if before is None or (n, last) > before:
            slots[(device, slot)] = (n, last)
    out: dict[str, dict] = {}
    for (device, _slot), (n, last) in slots.items():
        row = out.setdefault(device, {"conteggio_24h": 0, "ultimo": None})
        row["conteggio_24h"] += n
        if row["ultimo"] is None or last > row["ultimo"]:
            row["ultimo"] = last
    return out


async def for_apartment(apartment_id: str) -> dict | None:
    """The refusals of the apartment's devices, or None when not known."""
    view = get_settings().device_refusals_view
    if not view or not isinstance(apartment_id, str) or not ID_RE.fullmatch(apartment_id):
        return None
    now = _now()
    copy = _copies.get(apartment_id)
    if copy is not None:
        taken, value = copy
        if now - taken < timedelta(seconds=COPY_S if value is not None else FAILED_COPY_S):
            return value
    flt = (f'timestamp>="{_iso(now - WINDOW - timedelta(minutes=10))}" '
           f'AND jsonPayload.message:"broker device refused apt={apartment_id} "')
    try:
        value = count(apartment_id, await _entries(view, flt), now)
    except Exception as exc:                                     # noqa: BLE001 - the page works without the column
        warn("device refusals not read", apartment_id=apartment_id, error=type(exc).__name__)
        value = None
    _copies[apartment_id] = (now, value)
    return value


def cached(apartment_id: str) -> dict | None:
    """The copy as it is, without reading (the answers of the actions): None when there is none."""
    copy = _copies.get(apartment_id)
    return copy[1] if copy is not None else None


def view_of(refusals: dict | None, device_id: str) -> dict | None:
    """The field «rifiuti» of one device: null when not known, zero when known and none."""
    if refusals is None:
        return None
    return dict(refusals.get(device_id) or {"conteggio_24h": 0, "ultimo": None})
