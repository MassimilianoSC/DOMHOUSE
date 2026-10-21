import asyncio
import json
import re
import time
from datetime import UTC, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from .. import actors, audit, energy_report, energy_since, instances, push, support
from ..auth import CurrentUser, Identity, get_tenant_apartment, resolve_identity, resolve_user, scope_out, still_sees
from ..bookings import ForwardError, SimulatorTranslator, TranslationError, forward
from ..config import get_settings
from ..features import configured_features, feature_for
from .admin import tenant_out
from ..logs import ctx_apartment, ctx_correlation, info
from ..repository import get_repository
from ..sse_hub import SseEvent, hub_manager

router = APIRouter(prefix="/app")

PING_SECONDS = 25.0
ACCESS_RECHECK_SECONDS = 30.0  # D-44: an open stream notices within 30 s that its apartment is no longer visible
PROXY_BLOCKED = {"bookings", "stream", "openapi.json"}
# F1 (D-70): allow-list of the contract's first segments, instead of a deny-list
PROXY_ALLOWED = {"apartment", "devices", "commands", "energy", "schedule", "rules", "approvals", "decisions", "ask",
                 "health", "version", "_test"}


def clean_instance_path(path: str) -> bool:
    """Only plain segments: no empty, "." or ".." segment (the path arrives already percent-decoded), no leftover "%"
    (double encoding) and no backslash. Anything else could leave the apartment's /api/v1 on the instance."""
    return all(seg not in ("", ".", "..") and "%" not in seg and "\\" not in seg for seg in path.split("/"))


def err(status: int, error: str, message: str, **details) -> JSONResponse:
    body = {"error": error, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content=body)


def local_midnight_utc(tz: str) -> str:
    now = datetime.now(ZoneInfo(tz))
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@router.get("/me")
async def me(identity: Identity = Depends(resolve_identity)):
    """Also answers a platform manager without an organisation (P-36, D-61a): tenant and role null."""
    repo = get_repository()
    s = get_settings()
    env = {"app_env": s.app_env, "auth_mode": s.auth_mode, "fcm_enabled": s.fcm_enabled,
           "instance_mode": s.instance_mode}   # D-97: the simulator is per apartment (summary.simulated), not per env
    user = identity.user
    if user is None:
        return {
            "user": {"uid": identity.uid, "email": identity.email, "display_name": identity.display_name, "role": None,
                     "notification_prefs": None, "apartment_ids": "all", "platform_manager": True},
            "tenant": None,
            "role": None,
            "support": None,
            "support_access": [],
            "env": env,
        }
    tenant = await repo.get_tenant(user.tenant_id)
    if identity.support_access_id:   # P-50: the manager inside the assisted organisation; nothing of their own here
        a = await repo.get_support_access(identity.support_access_id)
        return {
            "user": {"uid": user.uid, "email": user.email, "display_name": user.display_name, "role": user.role,
                     "notification_prefs": None, "apartment_ids": "all", "platform_manager": True},
            "tenant": tenant_out(tenant, user.tenant_id),
            "role": user.role,
            "support": {"access_id": a.access_id, "tenant_id": a.tenant_id, "expires_at": a.expires_at, "reason": a.reason},
            "support_access": [],
            "env": env,
        }
    stored = await repo.get_user(user.uid)
    accesses = await support.active_in(user.tenant_id) if user.is_admin else []
    operators = await support.operators(accesses)
    return {
        "user": {
            "uid": user.uid,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "notification_prefs": (stored.notification_prefs.model_dump() if stored else None),
            "apartment_ids": scope_out(user.apartment_ids, user.role),
            "platform_manager": identity.platform_manager,
        },
        "tenant": tenant_out(tenant, user.tenant_id),
        "role": user.role,
        "support": None,
        # P-50: the admins see who from HQE is inside their organisation, and until when
        "support_access": [{"access_id": r["access_id"], "operator_email": r["operator_email"],
                            "operator_name": r["operator_name"], "expires_at": r["expires_at"], "reason": r["reason"]}
                           for r in (support.row(a, operators) for a in accesses)],
        "env": env,
    }


@router.get("/dev/users")
async def dev_users():
    if get_settings().auth_mode != "dev":
        return err(404, "not_found", "Disponibile solo in modalità sviluppo")
    repo = get_repository()
    users = []
    for t in await repo.list_tenants():
        users += await repo.list_users(t.tenant_id)
    out = [{"email": u.email, "display_name": u.display_name, "role": u.role} for u in users]
    known = {u.email for u in users}
    # platform managers without an organisation (P-36): role null, so the dev login page can offer them too
    out += [{"email": m.email, "display_name": "Gestore della piattaforma", "role": None}
            for m in await repo.list_platform_members() if m.email not in known]
    return out


@router.get("/apartments")
async def list_apartments(user: CurrentUser = Depends(resolve_user)):
    apts = [a for a in await get_repository().list_apartments(user.tenant_id) if user.can_see(a.apartment_id)]
    actor = await actors.actor_for(user.uid, user.email)   # P-48 (D-87): the engine never gets the email
    out = await asyncio.gather(*(instances.summary(a, actor, local_midnight_utc(a.timezone)) for a in apts))
    return await actors.rewrite(list(out), user.tenant_id)


@router.get("/apartments/{apartment_id}")
async def get_apartment_summary(apartment_id: str, user: CurrentUser = Depends(resolve_user)):
    apt = await get_tenant_apartment(user, apartment_id)
    out = await instances.summary(apt, await actors.actor_for(user.uid, user.email), local_midnight_utc(apt.timezone))
    return await actors.rewrite(out, user.tenant_id)


@router.api_route("/apartments/{apartment_id}/instance/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(apartment_id: str, path: str, request: Request, user: CurrentUser = Depends(resolve_user)):
    apt = await get_tenant_apartment(user, apartment_id)
    ctx_apartment.set(apartment_id)
    correlation_id = instances.correlation_id(request.headers.get("X-Correlation-Id"))
    ctx_correlation.set(correlation_id)
    method = request.method.upper()
    if not clean_instance_path(path):
        return err(404, "not_found", "Endpoint inesistente")
    top = path.split("/")[0]
    if top in PROXY_BLOCKED:
        return err(403, "forbidden", "Endpoint non disponibile per l'app")
    if top not in PROXY_ALLOWED:
        return err(404, "not_found", "Endpoint inesistente")
    if top == "_test":
        if refused := _simulator_refused(user, apt):
            return refused
    elif top == "version" and not user.is_admin:   # D-90: technical details of the instance, for the admin
        return err(403, "forbidden", "Informazione riservata agli amministratori")
    elif (method != "GET" or top == "ask") and not user.can_write:   # D-90: a reader does not read others' questions
        return err(403, "forbidden", "Il tuo ruolo consente solo la lettura")
    if not apt.enabled:
        return err(409, "apartment_disabled", "Appartamento disattivato")

    feature = feature_for(method, path)
    if feature:
        tenant = await get_repository().get_tenant(apt.tenant_id)
        allowed = configured_features(tenant.enabled_features if tenant else None, apt.enabled_features)
        if feature not in allowed and feature not in ("bookings", "stream"):
            return err(501, "not_implemented", "Funzione non disponibile su questa istanza")

    body = await request.body()
    try:
        resp = await instances.call(
            apt, method, path,
            actor=await actors.actor_for(user.uid, user.email),
            correlation_id=correlation_id,
            params=await _engine_params(request, user.tenant_id),
            content=body or None,
            content_type=request.headers.get("Content-Type") if body else None,
        )
    except Exception as exc:
        info("instance unreachable", error=type(exc).__name__, path=path)
        return err(502, "instance_unreachable", "Istanza non raggiungibile")
    info("proxied", method=method, path=path, status=resp.status_code)
    headers = {}
    if "content-type" in resp.headers:
        headers["Content-Type"] = resp.headers["content-type"]
    return Response(content=await _shown(resp, user.tenant_id, path), status_code=resp.status_code, headers=headers)


async def _engine_params(request: Request, tenant_id: str) -> list[tuple[str, str]]:
    """A filter by person (?actor=user:<email> on /decisions) reaches the engine as that person's pseudonym (P-48); an
    email that is not a member of the organisation is sent as is and simply finds nothing."""
    out = []
    for k, v in request.query_params.multi_items():
        if k == "actor" and v.startswith("user:") and "@" in v and not actors.is_pseudonym(v[5:]):
            member = await get_repository().get_user_by_email(v[5:])
            if member is not None and member.tenant_id == tenant_id:
                v = "user:" + await actors.actor_for(member.uid, member.email)
        out.append((k, v))
    return out


async def _shown(resp, tenant_id: str, path: str = "") -> bytes:
    """P-48 (D-87): every actor in the engine's JSON becomes an email the organisation may see, or "removed"; D-90:
    /health without the details the app never shows."""
    if "json" not in resp.headers.get("content-type", ""):
        return resp.content
    is_health = path.strip("/") == "health"
    if not is_health and not any(m.encode() in resp.content for m in actors.MARKERS):
        return resp.content
    try:
        payload = resp.json()
    except ValueError:
        return resp.content
    if is_health:
        payload = instances.health_out(payload)
    return json.dumps(await actors.rewrite(payload, tenant_id), ensure_ascii=False).encode()


async def _event(ev: SseEvent, tenant_id: str) -> str:
    """The same rewrite for the stream (decision.logged, approval.*, the apartment's hold)."""
    if not any(m in ev.data for m in actors.MARKERS):
        return ev.encode()
    try:
        payload = json.loads(ev.data)
    except ValueError:
        return ev.encode()
    data = json.dumps(await actors.rewrite(payload, tenant_id), ensure_ascii=False)
    return SseEvent(id=ev.id, event=ev.event, data=data, received=ev.received).encode()


MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


@router.get("/apartments/{apartment_id}/summaries")
async def list_summaries(apartment_id: str, user: CurrentUser = Depends(resolve_user)):
    """P-60 step 11 (D-150): the weekly summaries of an apartment, newest first (at most 20): week, period, how many
    items. Every role, on the apartments it sees."""
    apt = await get_tenant_apartment(user, apartment_id)
    return [{"week": s["week"], "from": s["from"], "to": s["to"], "notable": s["notable"], "items": len(s["items"])}
            for s in await get_repository().list_summaries(apt.apartment_id)]


@router.get("/apartments/{apartment_id}/summaries/{week}")
async def get_summary(apartment_id: str, week: str, user: CurrentUser = Depends(resolve_user)):
    apt = await get_tenant_apartment(user, apartment_id)
    summary = await get_repository().get_summary(apt.apartment_id, week)
    return summary if summary else err(404, "not_found", "Riepilogo inesistente")


@router.get("/apartments/{apartment_id}/energy/export")
async def energy_export(apartment_id: str, month: str | None = None, booking_id: str | None = None,
                        user: CurrentUser = Depends(resolve_user)):
    """P-52 (D-92): the consumption report as an Excel file, for a month (in the apartment's time zone) or for a stay
    (from arrival to departure, to the hour). Every role, on the apartments it sees."""
    apt = await get_tenant_apartment(user, apartment_id)
    if (month is None) == (booking_id is None):
        return err(422, "bad_request", "Indica month oppure booking_id")
    if not apt.enabled:
        return err(409, "apartment_disabled", "Appartamento disattivato")
    repo = get_repository()
    tenant = await repo.get_tenant(apt.tenant_id)
    if "energy" not in configured_features(tenant.enabled_features if tenant else None, apt.enabled_features):
        return err(501, "not_implemented", "Funzione non disponibile su questa istanza")
    tz = ZoneInfo(apt.timezone)
    now = datetime.now(UTC)
    stay = None
    if month is not None:
        m = MONTH_RE.match(month)
        if not m:
            return err(422, "invalid_month", "Mese non valido: scrivi AAAA-MM")
        year, mon = int(m.group(1)), int(m.group(2))
        start = datetime(year, mon, 1, tzinfo=tz).astimezone(UTC)
        end = datetime(year + mon // 12, mon % 12 + 1, 1, tzinfo=tz).astimezone(UTC)
        if start > now:
            return err(422, "invalid_month", "Il mese non è ancora iniziato")
        title, period, name = "Rendiconto mensile", energy_report.month_label(year, mon), f"consumi-{apt.apartment_id}-{month}.xlsx"
    else:
        b = await repo.get_booking(apt.apartment_id, booking_id)
        if b is None or b.status == "cancelled":
            return err(404, "not_found", "Soggiorno inesistente")
        start, end = energy_report.parse(b.checkin_at), energy_report.parse(b.checkout_at)
        if start > now:
            return err(422, "invalid_period", "Il soggiorno non è ancora iniziato")
        stay = {"booking_id": b.booking_id, "guests": b.guests, "status": b.status}   # never guests' data
        title, period = "Rendiconto del soggiorno", f"soggiorno {b.booking_id}"
        name = f"consumi-{apt.apartment_id}-{b.booking_id}.xlsx"
    in_progress = end > now
    end = min(end, now)
    if end - start > energy_report.MAX_SPAN:
        return err(422, "invalid_period", "Periodo troppo lungo: al massimo un anno")
    actor = await actors.actor_for(user.uid, user.email)
    try:
        usage = await energy_report.collect(apt, actor, start, end)
    except energy_report.EnergyUnavailable:
        return err(501, "not_implemented", "Funzione non disponibile su questa istanza")
    except Exception as exc:
        info("energy export failed", error=type(exc).__name__)
        return err(502, "instance_unreachable", "Istanza non raggiungibile")
    price = apt.energy_price_eur_kwh if apt.energy_price_eur_kwh is not None else (tenant.energy_price_eur_kwh if tenant else None)
    report = energy_report.Report(organisation=tenant.name if tenant else "", apartment=apt.name, apartment_id=apt.apartment_id,
                                  timezone=apt.timezone, start=start, end=end, in_progress=in_progress, price=price,
                                  title=title, period=period, stay=stay,
                                  energy_since=await energy_since.known(apt, actor, wait=True))   # D-130
    content = energy_report.workbook(report, usage, now)
    disposition = f'attachment; filename="{name}"; filename*=UTF-8\'\'{quote(name)}'
    return Response(content=content, media_type=energy_report.XLSX, headers={"Content-Disposition": disposition})


def _simulator_refused(user: CurrentUser, apt) -> JSONResponse | None:
    """D-97: the simulator is for admins, on demonstration apartments only, in every environment (also production)."""
    if not user.is_admin:
        return err(403, "forbidden", "Il simulatore è riservato agli amministratori")
    if not apt.simulated:
        return err(403, "not_simulated", "Questo appartamento non è un'istanza simulata")
    return None


@router.post("/apartments/{apartment_id}/simulator/reset", status_code=204)
async def simulator_reset(apartment_id: str, request: Request, user: CurrentUser = Depends(resolve_user)):
    """D-97: back to the initial state of the built-in simulated engine for this apartment. Not an operation of the
    contract: the BFF rebuilds its own mock in-process, so only mock:// apartments can be reset."""
    apt = await get_tenant_apartment(user, apartment_id)
    if refused := _simulator_refused(user, apt):
        return refused
    if not instances.is_mock(apt.instance_url):
        return err(409, "reset_not_available", "Il ripristino è possibile solo con il motore simulato integrato")
    request.app.state.mock_registry.reset(apt.apartment_id)   # devices, rules, schedule, decisions… from the seed
    await get_repository().delete_bookings(apt.apartment_id)   # the BFF's stays, or they would disagree with the mock
    instances.invalidate_version(apt.apartment_id)
    push.forget_apartment(apt.apartment_id)
    hub_manager.drop(apt.apartment_id)   # browser streams end; reconnecting, the PWA reloads from the fresh engine
    if get_settings().fcm_enabled and apt.enabled:   # D-99 N2: the pushes' own upstream stream, as at startup
        hub_manager.hub(apt).start(None)
    await audit.record("simulator_reset", audit.by_user(user), apt.tenant_id, audit.apartment_target(apt.apartment_id, apt.name))
    return Response(status_code=204)


@router.get("/apartments/{apartment_id}/bookings")
async def list_bookings(apartment_id: str, booking_id: str | None = None, user: CurrentUser = Depends(resolve_user)):
    """Booking archive kept by the BFF (every event it forwarded); empty when the booking predates the BFF."""
    apt = await get_tenant_apartment(user, apartment_id)
    repo = get_repository()
    unused = {"event_ids", "last_event_type", "updated_at", "source"}   # D-90: technical, never shown
    if booking_id:
        b = await repo.get_booking(apt.apartment_id, booking_id)
        return {"items": [b.model_dump(exclude=unused)] if b else []}
    return {"items": [b.model_dump(exclude=unused) for b in await repo.list_bookings(apt.apartment_id)]}


@router.post("/apartments/{apartment_id}/simulator/booking")
async def simulator_booking(apartment_id: str, request: Request, user: CurrentUser = Depends(resolve_user)):
    """Simulator: our BookingEvent goes through SimulatorTranslator and the same forwarder as the real webhook."""
    apt = await get_tenant_apartment(user, apartment_id)
    if refused := _simulator_refused(user, apt):
        return refused
    correlation_id = instances.correlation_id(request.headers.get("X-Correlation-Id"))
    ctx_correlation.set(correlation_id)
    try:
        payload = await request.json()
    except ValueError:
        return err(400, "bad_request", "JSON non valido")
    try:
        _, ev = SimulatorTranslator().translate({**payload, "apartment_id": apartment_id, "source": "simulator"})
    except TranslationError as exc:
        return err(422, "untranslatable", exc.message)
    try:
        result = await forward(apt, ev, correlation_id)
    except ForwardError as exc:
        return JSONResponse(status_code=exc.status, content=exc.body)
    return {"correlation_id": correlation_id, **result}


@router.get("/apartments/{apartment_id}/stream")
async def stream(apartment_id: str, request: Request, user: CurrentUser = Depends(resolve_user)):
    apt = await get_tenant_apartment(user, apartment_id)
    last_event_id = request.headers.get("Last-Event-ID")
    hub = hub_manager.hub(apt)
    hub.start(last_event_id)
    queue: asyncio.Queue = asyncio.Queue()
    for ev in hub.replay_after(last_event_id):
        queue.put_nowait(ev)
    hub.subscribers.add(queue)

    # P-50: a support stream ends at the exact expiry of the access, not at the next periodic check
    deadline = support.parse(user.support_expires_at).timestamp() if user.support_expires_at else None

    async def gen():
        checked = time.monotonic()
        try:
            yield "retry: 3000\n: connected\n\n"
            while True:
                wait = PING_SECONDS if deadline is None else min(PING_SECONDS, max(0.0, deadline - time.time()))
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=wait)
                    if ev is None:   # the hub was dropped (apartment deleted or reset, D-97): end this stream
                        info("stream closed: apartment reset or removed")
                        break
                    item = await _event(ev, user.tenant_id)
                except TimeoutError:
                    if await request.is_disconnected():
                        break
                    item = ": ping\n\n"
                if deadline is not None and time.time() >= deadline:
                    info("stream closed: support access expired")
                    break
                # P-18: checked on every event and ping, with the user record re-read at most every 30 s; the event
                # that reveals the change is not delivered, and on reconnection the stream answers 404
                if time.monotonic() - checked >= ACCESS_RECHECK_SECONDS:
                    checked = time.monotonic()
                    if not await still_sees(user, apt.apartment_id):
                        info("stream closed: apartment no longer visible to the user")
                        break
                yield item
        finally:
            hub.subscribers.discard(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
