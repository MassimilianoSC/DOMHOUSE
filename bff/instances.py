import asyncio
import re
import time
import uuid
from urllib.parse import parse_qs, urlsplit, urlunsplit

import httpx

from .config import get_settings
from .features import effective_features
from .repository import Apartment, get_repository

BFF_ACTOR = "system:bff"
_http: httpx.AsyncClient | None = None
_version_cache: dict[str, tuple[float, dict]] = {}
_secret_cache: dict[str, tuple[float, str]] = {}


def http() -> httpx.AsyncClient:
    global _http
    if _http is None:
        _http = httpx.AsyncClient(timeout=get_settings().instance_timeout_s)
    return _http


MSG_USE_MOCK = "In questo ambiente di prova scrivi mock://builtin nel campo URL istanza"
MSG_BAD_URL = "Indirizzo non valido: deve cominciare con http:// o https://"


def normalize_instance_url(raw: str) -> str:
    """Trims spaces and lower-cases the scheme; a bare host[:port][/path] gets http:// (without it urlsplit puts the
    host in the path and the request fails with UnsupportedProtocol)."""
    v = raw.strip()
    if not v:
        return v
    if "://" not in v:
        return f"http://{v}"
    scheme, rest = v.split("://", 1)
    return f"{scheme.lower()}://{rest}"


def is_mock(url: str | None) -> bool:
    """The built-in simulated engine (D-97): mounted in every mode, reached on the BFF's own loopback."""
    return normalize_instance_url(url or "").startswith("mock://")


DEMO_VARIANTS = ("vuoto", "occupato")
MSG_BAD_VARIANT = "Variante sconosciuta: scrivi mock://builtin?variante=vuoto oppure mock://builtin?variante=occupato"


def demo_variant(url: str | None) -> str | None:
    """P-72 (D-154): the variant written in a demonstration's link, mock://builtin?variante=vuoto|occupato; None
    without it (the rule before P-72: empty and cold for an id containing "bologna"). Lower case, spaces trimmed."""
    v = normalize_instance_url(url or "")
    if not v.startswith("mock://") or "?" not in v:
        return None
    values = parse_qs(v.split("?", 1)[1]).get("variante")
    return values[0].strip().lower() if values else None


def instance_url_problem(raw: str) -> str | None:
    """Plain-Italian reason why an instance URL cannot work with the current INSTANCE_MODE, or None. With
    INSTANCE_MODE=mock only mock:// is reachable (staging has no VPC egress), so anything else is refused (D-28). In real
    mode mock:// is accepted too (D-97: demonstration apartments next to real ones; only the platform links engines).
    D-188: also in production, where the collaborators test until the delivery (it revises D-136 for this phase)."""
    v = normalize_instance_url(raw)
    if v.startswith("mock://"):
        variant = demo_variant(v)
        return MSG_BAD_VARIANT if variant is not None and variant not in DEMO_VARIANTS else None
    if get_settings().instance_mode == "mock":
        return MSG_USE_MOCK
    parts = urlsplit(v)
    try:
        parts.port
    except ValueError:
        return MSG_BAD_URL
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return MSG_BAD_URL
    return None


def base_url(apt: Apartment) -> str:
    s = get_settings()
    url = normalize_instance_url(apt.instance_url)
    if url.startswith("mock://"):   # D-97: in every mode, on loopback (F2: never reachable from outside)
        return f"http://127.0.0.1:{s.port}{s.root_path}/mock/{apt.apartment_id}/api/v1"
    parts = urlsplit(url.rstrip("/"))
    netloc = parts.netloc
    if apt.port and ":" not in netloc:
        netloc = f"{netloc}:{apt.port}"
    path = parts.path or "/api/v1"
    return urlunsplit((parts.scheme or "http", netloc, path, "", ""))


def _read_secret(name: str) -> str:
    from google.cloud import secretmanager

    s = get_settings()
    client = secretmanager.SecretManagerServiceClient()
    resp = client.access_secret_version(name=f"projects/{s.gcp_project_id}/secrets/{name}/versions/latest")
    return resp.payload.data.decode("utf-8").strip()


def link_key(instance_url: str, port: int | None) -> str | None:
    """host:port actually called (port from the URL, else the port field, else the scheme default); None for mock://,
    which every staging apartment shares (P-36 point 8)."""
    url = normalize_instance_url(instance_url)
    if url.startswith("mock://"):
        return None
    parts = urlsplit(url)
    try:
        effective = parts.port or port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return None
    return f"{(parts.hostname or '').lower()}:{effective}"


async def link_in_use(instance_url: str, port: int | None, apartment_id: str) -> bool:
    """Read-based check: also covers apartments saved before the claim index existed (friendly message)."""
    key = link_key(instance_url, port)
    if key is None:
        return False
    return any(a.apartment_id != apartment_id and link_key(a.instance_url, a.port) == key
               for a in await get_repository().list_apartments())


async def claim_link(instance_url: str, port: int | None, apartment_id: str) -> bool:
    """Reserve the engine instance (host:port) for this apartment, atomically (L8, D-70): two apartments on the same
    instance would show one organisation the devices of another. True when claimed (or mock://, nothing to reserve)."""
    key = link_key(instance_url, port)
    if key is None:
        return True
    return await get_repository().claim_external_id("link", key, apartment_id) is None


async def release_link(instance_url: str, port: int | None, apartment_id: str) -> None:
    key = link_key(instance_url, port)
    if key:
        await get_repository().release_external_id("link", key, apartment_id)


def secret_name(apartment_id: str) -> str:
    return f"{get_settings().secret_manager_prefix}{apartment_id}"


async def api_key(apt: Apartment) -> str:
    s = get_settings()
    if s.instance_mode == "mock" or is_mock(apt.instance_url):   # D-97: the mock's random key of this process
        return s.instance_api_key_fallback
    # Always derived from the apartment id, never chosen by an admin: the BFF can read other secrets too (SMTP password,
    # webhook HMAC) and would send the chosen one as X-API-Key to the admin's instance_url (P-36, S3).
    name = secret_name(apt.apartment_id)
    cached = _secret_cache.get(name)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    value = await asyncio.to_thread(_read_secret, name)
    _secret_cache[name] = (time.monotonic() + 300, value)
    return value


UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def correlation_id(incoming: str | None) -> str:
    """The engine contract wants X-Correlation-Id as a UUID: an incoming value that is not one (Italianway's own id, an
    empty header) would be refused with 400 and, for a webhook, cost a booking. Keep a valid one, else make our own."""
    value = (incoming or "").strip()
    return value if UUID_RE.match(value) else str(uuid.uuid4())


async def instance_headers(apt: Apartment, actor: str, correlation_id: str | None = None) -> dict[str, str]:
    headers = {
        "X-API-Key": await api_key(apt),
        "X-Actor": actor,
        "X-Correlation-Id": correlation_id or str(uuid.uuid4()),
    }
    if is_mock(apt.instance_url) and (variant := demo_variant(apt.instance_url)) in DEMO_VARIANTS:
        headers["X-Demo-Variant"] = variant      # P-72: internal, only towards the built-in demonstration engine
    if is_mock(apt.instance_url):
        headers["X-Demo-Timezone"] = apt.timezone   # D-177: the built-in engine has no VM: its TIMEZONE is the copy
    return headers


async def call(
    apt: Apartment,
    method: str,
    path: str,
    *,
    actor: str = BFF_ACTOR,
    correlation_id: str | None = None,
    params=None,
    json=None,
    content: bytes | None = None,
    content_type: str | None = None,
    timeout: float | None = None,
) -> httpx.Response:
    if any(seg in (".", "..") for seg in path.split("/")):  # F1: defence in depth, the routes already refuse them
        raise ValueError("dot segment in instance path")
    headers = await instance_headers(apt, actor, correlation_id)
    if content_type:
        headers["Content-Type"] = content_type
    return await http().request(
        method,
        base_url(apt) + "/" + path.lstrip("/"),
        headers=headers,
        params=params,
        json=json,
        content=content,
        timeout=timeout or get_settings().instance_timeout_s,
    )


ADMIN_SECRET_MESSAGE = "Chiave dell'istanza non configurata: contatta l'assistenza HQE"
HEALTH_UNUSED = ("devices", "uptime_s", "database", "checked_at", "apartment_id")


def health_out(body):
    """D-90: the instance's /health without what the app never shows (device list, uptime, database, ids)."""
    if not isinstance(body, dict):
        return body
    return {k: v for k, v in body.items() if k not in HEALTH_UNUSED}


def for_admin(check: dict | None) -> dict | None:
    """D-90: an organisation never reads the name of a secret; the platform keeps the detail."""
    if not check:
        return check
    out = {k: v for k, v in check.items() if k != "secret_problem"}
    if check.get("secret_problem"):
        out["error"] = ADMIN_SECRET_MESSAGE
    return out


async def _secret_problem(apt: Apartment) -> str | None:
    """D-67 (N3): a missing or unreadable key otherwise looks like a network problem ("Istanza non raggiungibile")."""
    if get_settings().instance_mode == "mock" or is_mock(apt.instance_url):
        return None
    try:
        await api_key(apt)
        return None
    except Exception as exc:
        from google.api_core.exceptions import NotFound, PermissionDenied

        name = secret_name(apt.apartment_id)
        if isinstance(exc, NotFound):
            return f"Chiave dell'istanza non trovata in Secret Manager: crea il segreto {name}"
        if isinstance(exc, PermissionDenied):
            return f"Chiave dell'istanza non leggibile dal server: manca il permesso su {name}"
        return None  # anything else: let the calls report it


async def verify(apt: Apartment, actor: str) -> dict:
    """'Verifica connessione' (admin and platform, same answer): calls /health and /version on the instance, reports
    both and stores the outcome as the apartment's last_check."""
    from .logs import warn
    from .repository.base import LastCheck, now_iso

    invalidate_version(apt.apartment_id)
    out: dict = {"apartment_id": apt.apartment_id, "reachable": False, "health": None, "version": None, "error": None,
                 "contract_version": None, "features": [], "ok": False}
    if problem := instance_url_problem(apt.instance_url):
        out["error"] = problem  # saved before the check existed: no call would work, say what to write instead
    elif problem := await _secret_problem(apt):
        out["error"], out["secret_problem"] = problem, True
    else:
        for key in ("health", "version"):
            try:
                resp = await call(apt, "GET", f"/{key}", actor=actor, timeout=5.0)
                out[key] = {"status_code": resp.status_code, "body": resp.json() if resp.content else None}
                out["reachable"] = True
            except Exception as exc:
                warn("verify failed", apartment_id=apt.apartment_id, step=key, error=type(exc).__name__)
                out["error"] = "Istanza non raggiungibile"
        v = (out["version"] or {}).get("body") or {}
        out["contract_version"] = v.get("contract_version")
        out["features"] = v.get("features", [])
        out["ok"] = out["reachable"] and (out["health"] or {}).get("status_code") == 200 and bool(v)
    repo = get_repository()
    stored = await repo.get_apartment(apt.apartment_id)
    if stored is not None:  # re-read: only last_check changes, whatever else was saved meanwhile stays
        stored.last_check = LastCheck(ok=out["ok"], checked_at=now_iso(), error=out["error"],
                                      secret_problem=bool(out.get("secret_problem")))
        await repo.upsert_apartment(stored)
    return out


async def get_version(apt: Apartment, *, timeout: float | None = None) -> dict:
    cached = _version_cache.get(apt.apartment_id)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    resp = await call(apt, "GET", "/version", timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    _version_cache[apt.apartment_id] = (time.monotonic() + 60, data)
    return data


def invalidate_version(apartment_id: str) -> None:
    _version_cache.pop(apartment_id, None)


async def _safe_json(coro):
    try:
        resp = await coro
        return resp.status_code, resp.json()
    except Exception as exc:  # unreachable, timeout or non-JSON
        return None, {"error": type(exc).__name__}


_tz_locks: dict[str, asyncio.Lock] = {}


def _valid_timezone(name) -> bool:
    from zoneinfo import ZoneInfo
    if not isinstance(name, str) or not name or name.startswith("/") or ".." in name:
        return False
    try:
        ZoneInfo(name)
    except (ValueError, KeyError, OSError):
        return False
    return True


async def sync_timezone(apt: Apartment, engine_apartment) -> None:
    """D-177 (D-183 points 126-127): the apartment's time zone is the engine's (TIMEZONE, in /apartment.timezone); the
    registry keeps a copy only as the fallback for when the engine does not answer. A different, valid one is saved
    (apt too, for the caller) and written to the organisation's log by the system: timezone_changed {from, to}."""
    tz = engine_apartment.get("timezone") if isinstance(engine_apartment, dict) else None
    if tz == apt.timezone or not _valid_timezone(tz):
        return
    from . import audit
    from .logs import info

    lock = _tz_locks.setdefault(apt.apartment_id, asyncio.Lock())
    async with lock:                         # two cards read at once: one save, one entry
        repo = get_repository()
        stored = await repo.get_apartment(apt.apartment_id)
        apt.timezone = tz
        if stored is None or stored.timezone == tz:
            return
        before = stored.timezone
        stored.timezone = tz
        await repo.upsert_apartment(stored)
        info("apartment timezone from the engine", apartment_id=apt.apartment_id, **{"from": before, "to": tz})
        await audit.record("timezone_changed", audit.SYSTEM, stored.tenant_id,
                           audit.apartment_target(stored.apartment_id, stored.name), **{"from": before, "to": tz})


async def summary(apt: Apartment, actor: str, tz_midnight_utc: str | None = None, timeout: float = 3.0) -> dict:
    """Aggregated card data; offline instances are reported, never fatal."""
    tenant = await get_repository().get_tenant(apt.tenant_id)
    out: dict = {
        "apartment_id": apt.apartment_id,
        "name": apt.name,
        "address": apt.address,
        "timezone": apt.timezone,
        "enabled": apt.enabled,
        "simulated": apt.simulated,   # D-97: the PWA shows the simulator to admins only here
        "online": False,
        "apartment": None,
        "health": None,
        "contract_version": None,
        "features": [],
        "pending_approvals": None,
        "kwh_today": None,
        "energy_since": apt.energy_since,   # D-130: «consumi disponibili dal …» under the chart
    }
    if not apt.enabled:
        return out
    try:
        version = await get_version(apt, timeout=timeout)
    except Exception:
        version = None
    health_code, health = await _safe_json(call(apt, "GET", "/health", actor=actor, timeout=timeout))
    reachable = health_code in (200, 503)
    out["health"] = health_out(health) if reachable else None
    out["online"] = health_code == 200 and version is not None
    if not version:
        return out
    out["contract_version"] = version.get("contract_version")
    feats = effective_features(version.get("features", []), tenant.enabled_features if tenant else None, apt.enabled_features)
    out["features"] = feats

    tasks = {}
    if "apartment" in feats:
        tasks["apartment"] = call(apt, "GET", "/apartment", actor=actor, timeout=timeout)
    if "approvals" in feats:
        tasks["approvals"] = call(apt, "GET", "/approvals", actor=actor, timeout=timeout)
    if "energy" in feats and not apt.energy_since:
        from . import energy_since           # not at the top: energy_since imports this module
        await energy_since.known(apt, actor)   # a search in the background; the list never waits for it
    if "energy" in feats and tz_midnight_utc:
        now = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        tasks["energy"] = call(
            apt, "GET", "/energy", actor=actor, timeout=timeout,
            params={"from": tz_midnight_utc, "to": now, "bucket": "day"},
        )
    results = await asyncio.gather(*(_safe_json(c) for c in tasks.values()))
    for key, (code, body) in zip(tasks.keys(), results):
        if code != 200:
            continue
        if key == "apartment":
            out["apartment"] = body
            await sync_timezone(apt, body)       # D-177: the engine's time zone, the copy only as a fallback
            out["timezone"] = apt.timezone
        elif key == "approvals":
            out["pending_approvals"] = len(body.get("items", []))
        elif key == "energy":
            out["kwh_today"] = body.get("total_kwh")
    return out
