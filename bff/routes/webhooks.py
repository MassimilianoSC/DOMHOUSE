"""Public webhooks (no user auth): HMAC-SHA256 over the raw body. Every call is logged (last 100) for the admin area."""
import hashlib
import hmac
import json
import time
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import instances
from ..bookings import ForwardError, ItalianwayTranslator, TranslationError, forward
from ..config import get_settings
from ..logs import ctx_correlation, info, warn
from ..repository import WebhookLog, get_repository

router = APIRouter(prefix="/webhooks")
RAW_BODY_LIMIT = 16_000
# F-5 (attack-from-outside review): every unsigned call wrote a row (about 23 Firestore operations) and a warn line, with
# no limit, and pushed real signature errors out of the platform's 20 unsigned rows. Now at most this many unsigned calls
# a minute, per instance (production up to 3), get their row and their warn line; the others the same 401, nothing
# parsed nor written, counted in one warn line a minute. Signed calls are never limited.
UNSIGNED_ROWS_PER_MINUTE = 10
_unsigned: dict = {}            # {"window": minute, "rows": rows written in it, "skipped": calls without a row}
_clock = time.monotonic
# D-90, D-91 (F2): of an Italianway call only what is useful is kept. The stored body keeps its shape, but a value
# survives only at a known PATH and of the expected TYPE; everything else, lists included, becomes OBSCURED. So guests'
# data are never kept, whatever the field is called and wherever it sits.
KEPT_TOP = {"event": str, "id": str, "sent_at": str}
KEPT_RESERVATION = {"id": str, "apartment_id": str, "checkin": str, "checkout": str, "status": str, "guests": int}
OBSCURED = "[oscurato]"


def _typed(value, kind) -> bool:
    return isinstance(value, kind) and not isinstance(value, bool)


def _blank(node):
    if isinstance(node, dict):
        return {k: _blank(v) for k, v in node.items()}
    return None if node is None else OBSCURED


def _obscure(payload):
    if not isinstance(payload, dict):
        return _blank(payload)
    out = {}
    for k, v in payload.items():
        if k in KEPT_TOP and _typed(v, KEPT_TOP[k]):
            out[k] = v
        elif k == "reservation" and isinstance(v, dict):
            out[k] = {rk: rv if rk in KEPT_RESERVATION and _typed(rv, KEPT_RESERVATION[rk]) else _blank(rv)
                      for rk, rv in v.items()}
        else:
            out[k] = _blank(v)
    return out


def obscured_body(raw: bytes, payload) -> str:
    if payload is None:
        return f"[corpo non JSON, {len(raw)} byte]"
    return json.dumps(_obscure(payload), ensure_ascii=False)[:RAW_BODY_LIMIT]


def _parse(raw: bytes):
    """F-2: also a JSON nested too deep for the parser (RecursionError) is «not JSON», never a 500 without its line."""
    try:
        return json.loads(raw)
    except (ValueError, RecursionError):
        return None


def _read(raw: bytes):
    """The payload and its obscured copy for the register. F-2: a JSON the parser accepts but nested beyond what the
    obscuring can walk (about 1000 objects) counts as not JSON too, so it gets 400 and its line, not a 500."""
    parsed = _parse(raw)
    try:
        return parsed, obscured_body(raw, parsed)
    except RecursionError:
        return None, obscured_body(raw, None)


def structured(payload) -> dict:
    """Event type, Italianway code, dates and guests, read without trusting the shape (also for unsigned calls)."""
    if not isinstance(payload, dict):
        return {}
    res = payload.get("reservation") if isinstance(payload.get("reservation"), dict) else {}

    def text(v):
        return v if isinstance(v, str) else None
    guests = res.get("guests")
    return {"event_type": text(payload.get("event")), "external_id": text(res.get("apartment_id")),
            "checkin_at": text(res.get("checkin")), "checkout_at": text(res.get("checkout")),
            "guests": guests if isinstance(guests, int) and not isinstance(guests, bool) else None}


def _unsigned_row_allowed() -> bool:
    window = int(_clock() // 60)
    if _unsigned.get("window") != window:
        if _unsigned.get("skipped"):
            warn("webhook unsigned calls not logged", source="italianway", calls=_unsigned["skipped"])
        _unsigned.update(window=window, rows=0, skipped=0)
    if _unsigned["rows"] < UNSIGNED_ROWS_PER_MINUTE:
        _unsigned["rows"] += 1
        return True
    _unsigned["skipped"] += 1
    return False


def verify_signature(raw: bytes, header_value: str | None, secret: str) -> bool:
    if not secret or not header_value:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    provided = header_value.strip()
    if provided.lower().startswith("sha256="):
        provided = provided[7:]
    if not provided.isascii():                     # D65 (P-83): compare_digest raised TypeError on it (500, no entry)
        return False
    return hmac.compare_digest(expected.lower().encode(), provided.lower().encode())


async def report_demo_codes() -> None:
    """D-99 F1: in production, list in the log at startup every demonstration apartment that still has an Italianway
    code, so the platform removes it (the webhook refuses its bookings anyway)."""
    if get_settings().app_env != "prod":             # D66 (P-83): staging is INSTANCE_MODE=real too
        return
    for apt in await get_repository().list_apartments():
        if apt.external_ids.italianway and instances.is_mock(apt.instance_url):
            warn("demo apartment with an Italianway code", apartment_id=apt.apartment_id)


@router.post("/italianway")
async def italianway(request: Request):
    s = get_settings()
    raw = await request.body()
    incoming = request.headers.get("X-Correlation-Id")
    correlation_id = instances.correlation_id(incoming)  # Fable D-75 note 2: the engine wants a UUID
    ctx_correlation.set(correlation_id)
    if incoming and incoming.strip() != correlation_id:
        info("webhook correlation id replaced", source="italianway", original=incoming[:120])
    # F-2: the size is already limited (bff/body_limit.py, 64 KiB, before the body is read); the signature is checked
    # on the raw bytes before they are parsed. An unsigned call keeps its obscured body and fields in the register
    # (decision of 22 November, a6: the platform sees an Italianway call with the wrong secret); its volume is F-5
    signature_ok = verify_signature(raw, request.headers.get(s.italianway_signature_header), s.italianway_webhook_secret)
    if not signature_ok and not _unsigned_row_allowed():                 # F-5: over the minute's rows
        return JSONResponse(status_code=401, content={"error": "invalid_signature", "message": "Firma non valida"})
    parsed, kept = _read(raw)
    log = WebhookLog(log_id=f"wh-{uuid.uuid4().hex[:12]}", signature_ok=signature_ok, status_code=0, outcome="",
                     correlation_id=correlation_id, raw_body=kept, **structured(parsed))

    async def done(status: int, outcome: str, body: dict):
        log.status_code, log.outcome = status, outcome
        await get_repository().add_webhook_log(log)
        return JSONResponse(status_code=status, content=body)

    if not log.signature_ok:
        warn("webhook signature rejected", source="italianway")
        return await done(401, "invalid_signature", {"error": "invalid_signature", "message": "Firma non valida"})
    if parsed is None:
        return await done(400, "bad_request", {"error": "bad_request", "message": "JSON non valido"})
    payload = parsed
    try:
        ext_id, ev = ItalianwayTranslator().translate(payload)
    except TranslationError as exc:
        return await done(422, "untranslatable", {"error": "untranslatable", "message": exc.message})
    log.event_id, log.booking_id = ev.event_id, ev.booking_id
    matches = await get_repository().find_apartments_by_external_id("italianway", ext_id)
    if not matches:
        warn("webhook for unknown apartment", external_id=ext_id)
        return await done(404, "unknown_apartment", {"error": "unknown_apartment", "message": "Appartamento non collegato a questo identificativo Italianway"})
    if len(matches) > 1:
        # P-36 S2: never pick one of several apartments (possibly of different tenants) for a booking
        warn("webhook for an ambiguous Italianway code", external_id=ext_id, apartments=len(matches))
        return await done(409, "ambiguous_apartment", {"error": "ambiguous_apartment", "message": "Codice Italianway collegato a più appartamenti"})
    apt = matches[0]
    log.tenant_id, log.apartment_id = apt.tenant_id, apt.apartment_id
    if s.app_env == "prod" and instances.is_mock(apt.instance_url):     # D66 (P-83): not INSTANCE_MODE
        # D-99 F1: in production a demonstration apartment (allowed a code in staging, or saved before D-98) must
        # never receive the real bookings: refused, logged for its organisation, nothing reaches the simulated engine
        warn("webhook refused: Italianway code on a demo apartment", apartment_id=apt.apartment_id)
        return await done(409, "italianway_on_demo", {"error": "italianway_on_demo",
                                                     "message": "Codice Italianway collegato a un appartamento dimostrativo"})
    if not apt.enabled:
        return await done(409, "apartment_disabled", {"error": "apartment_disabled", "message": "Appartamento disattivato"})
    stats: dict = {}
    try:
        result = await forward(apt, ev, correlation_id, stats)
    except ForwardError as exc:
        log.forward_status, log.forward_attempts = stats.get("status"), stats.get("attempts", 0)
        return await done(exc.status, exc.body.get("error", "forward_failed"), exc.body)
    log.forward_status, log.forward_attempts = stats.get("status"), stats.get("attempts", 0)
    info("webhook processed", source="italianway", apartment_id=apt.apartment_id, event_id=ev.event_id)
    return await done(200, "duplicate" if result.get("duplicate") else "accepted",
                      {"apartment_id": apt.apartment_id, "correlation_id": correlation_id, **result})
