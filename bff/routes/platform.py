"""Platform area (P-36, D-61a / D-62 / D-64 / D-65 / D-66 / D-67): organisations, their first admin, platform
managers, unattributed webhook calls and the TECHNICAL record of apartments (link to the engine).

Separation is structural: every route here depends on require_platform; nothing here goes through resolve_user,
get_tenant_apartment or the instance proxy, and the answers are built field by field, so the platform never sees
an organisation's users, bookings, decisions, energy or live data.
"""
import secrets
import string
from typing import Literal

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, EmailStr, Field

from .. import actors, audit, instances, support
from ..auth import Identity, forget_tenant, require_platform
from ..config import get_settings
from ..invites import InviteRefused, create_invitation, send_invitation, shown
from ..repository import Apartment, ExternalIds, PlatformMember, Tenant, get_repository, normalize_email
from ..logs import warn
from ..repository.base import now_iso, tenant_name_key
from ..sse_hub import hub_manager
from .admin import _check_tz, remove_apartment

router = APIRouter(prefix="/app/platform", dependencies=[Depends(require_platform)])
_ID_CHARS = string.ascii_lowercase + string.digits


def err(status: int, error: str, message: str, **details) -> JSONResponse:
    body = {"error": error, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content=body)


# ---------- organisations ----------
class TenantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    admin_email: EmailStr
    admin_display_name: str = Field(default="", max_length=80)


class TenantRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)


async def _first_admin(t: Tenant) -> dict | None:
    """Only the admin the platform invited, and only email + pending: no other user of the organisation."""
    if not t.first_admin_email:
        return None
    u = await get_repository().get_user_by_email(t.first_admin_email)
    return {"email": t.first_admin_email, "pending": u is None or u.uid.startswith("inv-")}


async def tenant_row(t: Tenant, viewer_uid: str | None = None) -> dict:
    return {"tenant_id": t.tenant_id, "name": t.name, "created_at": t.created_at, "first_admin": await _first_admin(t),
            "suspended": t.status == "suspended", "suspended_at": t.suspended_at, "suspended_reason": t.suspended_reason,
            "support_access": await _support_summary(t.tenant_id, viewer_uid)}


async def _support_summary(tenant_id: str, viewer_uid: str | None) -> dict | None:
    """The active support access, the viewer's own first: only the manager who opened it can enter (mine)."""
    active = await support.active_in(tenant_id)
    if not active:
        return None
    a = next((x for x in active if x.operator_uid == viewer_uid), active[0])
    email, name = support.operator(a, await support.operators([a]))
    return {"access_id": a.access_id, "operator_email": email, "operator_name": name,
            "expires_at": a.expires_at, "reason": a.reason, "mine": a.operator_uid == viewer_uid}


async def _name_taken(name: str, tenant_id: str) -> str | None:
    """Owner of the same normalised name, if any: the claim index plus organisations created before it existed."""
    key = tenant_name_key(name)
    for t in await get_repository().list_tenants():
        if t.tenant_id != tenant_id and tenant_name_key(t.name) == key:
            return t.tenant_id
    return None


async def _get_tenant(tenant_id: str) -> Tenant | JSONResponse:
    t = await get_repository().get_tenant(tenant_id)
    return t if t else err(404, "not_found", "Organizzazione inesistente")


@router.get("/tenants")
async def list_tenants(identity: Identity = Depends(require_platform)):
    tenants = sorted(await get_repository().list_tenants(), key=lambda t: tenant_name_key(t.name))
    return [await tenant_row(t, identity.uid) for t in tenants]


@router.post("/tenants", status_code=201)
async def create_tenant(body: TenantCreate, identity: Identity = Depends(require_platform)):
    """Organisation + invitation of its first admin in one call. Everything is checked before anything is created;
    the name and the invitation are claimed atomically, so a double click creates nothing twice (D-61a c, g)."""
    repo = get_repository()
    name = " ".join(body.name.split())
    if not name:
        return err(422, "invalid_name", "Scrivi il nome dell'organizzazione")
    if owner := await _name_taken(name, ""):
        return err(409, "name_taken", "Esiste già un'organizzazione con questo nome", tenant_id=owner)
    tenant_id = "t-" + "".join(secrets.choice(_ID_CHARS) for _ in range(10))
    key = tenant_name_key(name)
    if owner := await repo.claim_tenant_name(key, tenant_id):
        return err(409, "name_taken", "Esiste già un'organizzazione con questo nome", tenant_id=owner)
    try:
        invited = await create_invitation(tenant_id, body.admin_email, "admin", body.admin_display_name.strip())
    except InviteRefused as exc:
        await repo.release_tenant_name(key, tenant_id)
        return err(409, "email_taken", exc.message)
    t = await repo.upsert_tenant(Tenant(tenant_id=tenant_id, name=name, created_by=identity.email,
                                        first_admin_email=normalize_email(body.admin_email)))
    who = audit.by_platform(identity)
    await audit.record("tenant_created", who, tenant_id, audit.tenant_target(tenant_id, t.name))
    await audit.record("invite_sent", who, tenant_id, audit.user_target(invited), role="admin", apartment_ids="all")
    status = await send_invitation(t.first_admin_email, body.admin_display_name.strip(), "admin", t.name,
                                   identity.display_name or identity.email, tenant_id)
    if status == "deferred":
        await audit.record("invite_email_deferred", who, tenant_id, audit.user_target(invited))
    return {**await tenant_row(t, identity.uid), "email_status": shown(status)}


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str, identity: Identity = Depends(require_platform)):
    t = await _get_tenant(tenant_id)
    return t if isinstance(t, JSONResponse) else await tenant_row(t, identity.uid)


@router.patch("/tenants/{tenant_id}")
async def rename_tenant(tenant_id: str, body: TenantRename, identity: Identity = Depends(require_platform)):
    repo = get_repository()
    t = await _get_tenant(tenant_id)
    if isinstance(t, JSONResponse):
        return t
    name = " ".join(body.name.split())
    if not name:
        return err(422, "invalid_name", "Scrivi il nome dell'organizzazione")
    old_key, new_key = tenant_name_key(t.name), tenant_name_key(name)
    if new_key != old_key:
        if owner := await _name_taken(name, tenant_id):
            return err(409, "name_taken", "Esiste già un'organizzazione con questo nome", tenant_id=owner)
        if owner := await repo.claim_tenant_name(new_key, tenant_id):
            return err(409, "name_taken", "Esiste già un'organizzazione con questo nome", tenant_id=owner)
        await repo.release_tenant_name(old_key, tenant_id)
    old_name, t.name = t.name, name
    saved = await repo.update_tenant(tenant_id, {"name": name}) or t   # only the name: never undoes a suspension
    if old_name != name:
        await audit.record("tenant_renamed", audit.by_platform(identity), tenant_id, audit.tenant_target(tenant_id, name),
                           **{"from": old_name, "to": name})
    return await tenant_row(saved, identity.uid)


@router.post("/tenants/{tenant_id}/invite")
async def resend_first_admin_invite(tenant_id: str, identity: Identity = Depends(require_platform)):
    t = await _get_tenant(tenant_id)
    if isinstance(t, JSONResponse):
        return t
    if not t.first_admin_email:
        return err(409, "no_first_admin", "Questa organizzazione non ha un primo amministratore invitato dalla piattaforma")
    u = await get_repository().get_user_by_email(t.first_admin_email)
    if u is None or u.tenant_id != tenant_id:
        return err(409, "invite_missing", "L'invito non esiste più")
    if not u.uid.startswith("inv-"):
        return err(409, "already_active", "L'amministratore ha già effettuato l'accesso")
    await audit.record("invite_resent", audit.by_platform(identity), tenant_id, audit.user_target(u))
    status = await send_invitation(u.email, u.display_name, "admin", t.name, identity.display_name or identity.email,
                                   tenant_id)
    if status == "deferred":
        await audit.record("invite_email_deferred", audit.by_platform(identity), tenant_id, audit.user_target(u))
    return {**await tenant_row(t, identity.uid), "email_status": shown(status)}


# ---------- suspension (P-50, D-85): stops the app for the organisation; bookings keep reaching the engine ----------
class Suspension(BaseModel):
    reason: str = Field(max_length=500)


@router.post("/tenants/{tenant_id}/suspend")
async def suspend_tenant(tenant_id: str, body: Suspension, identity: Identity = Depends(require_platform)):
    t = await _get_tenant(tenant_id)
    if isinstance(t, JSONResponse):
        return t
    reason = body.reason.strip()
    if not reason:
        return err(422, "invalid_reason", "Scrivi il motivo della sospensione")
    if t.status == "suspended":
        return err(409, "already_suspended", "L'organizzazione è già sospesa")
    saved = await get_repository().update_tenant(tenant_id, {"status": "suspended", "suspended_at": now_iso(),
                                                             "suspended_reason": reason})
    forget_tenant(tenant_id)   # every next request of this process sees it at once (L9)
    await audit.record("tenant_suspended", audit.by_platform(identity), tenant_id, audit.tenant_target(tenant_id, t.name),
                       reason=reason)
    for a in await support.active_in(tenant_id):   # D-91: a suspension also ends the support accesses
        await support.close(a, audit.by_platform(identity), "platform")
    return await tenant_row(saved or t, identity.uid)


@router.post("/tenants/{tenant_id}/reactivate")
async def reactivate_tenant(tenant_id: str, identity: Identity = Depends(require_platform)):
    t = await _get_tenant(tenant_id)
    if isinstance(t, JSONResponse):
        return t
    if t.status != "suspended":
        return err(409, "not_suspended", "L'organizzazione non è sospesa")
    saved = await get_repository().update_tenant(tenant_id, {"status": "active", "suspended_at": None,
                                                             "suspended_reason": None})
    forget_tenant(tenant_id)
    await audit.record("tenant_reactivated", audit.by_platform(identity), tenant_id, audit.tenant_target(tenant_id, t.name))
    return await tenant_row(saved or t, identity.uid)


# ---------- support access (P-50, D-86) ----------
class SupportOpen(BaseModel):
    hours: int
    reason: str = Field(max_length=500)


@router.post("/tenants/{tenant_id}/support-access", status_code=201)
async def open_support_access(tenant_id: str, body: SupportOpen, identity: Identity = Depends(require_platform)):
    """HQE opens it (variant A): from 1 to 24 hours, rights of an operator; the organisation's admins see it and can
    close it. The log entry is written first: without it nothing opens."""
    t = await _get_tenant(tenant_id)
    if isinstance(t, JSONResponse):
        return t
    if not 1 <= body.hours <= support.MAX_HOURS:
        return err(422, "invalid_hours", f"La durata va da 1 a {support.MAX_HOURS} ore")
    reason = body.reason.strip()
    if not reason:
        return err(422, "invalid_reason", "Scrivi il motivo dell'accesso di assistenza")
    if t.status == "suspended":
        return err(409, "tenant_suspended", "L'organizzazione è sospesa")
    try:
        a = await support.open_access(tenant_id, t.name, identity, body.hours, reason)
    except Exception as exc:
        warn("support: access not opened, log not written", error=str(exc))
        return err(503, "audit_unavailable", "Accesso non aperto: riprova tra poco")
    if a is None:
        return err(409, "support_active", "Hai già un accesso di assistenza aperto in questa organizzazione")
    return (await support.rows([a]))[0]


@router.get("/tenants/{tenant_id}/support-access")
async def list_tenant_support_access(tenant_id: str):
    t = await _get_tenant(tenant_id)
    if isinstance(t, JSONResponse):
        return t
    return await support.rows(await support.listed(tenant_id=tenant_id))


@router.delete("/tenants/{tenant_id}/support-access/{access_id}", status_code=204)
async def close_tenant_support_access(tenant_id: str, access_id: str, identity: Identity = Depends(require_platform)):
    a = await get_repository().get_support_access(access_id)
    if a is None or a.tenant_id != tenant_id:
        return err(404, "not_found", "Accesso di assistenza inesistente")
    who = (support.by_operator(identity.uid, identity.email, identity.display_name, a.access_id)
           if a.operator_uid == identity.uid else audit.by_platform(identity))
    await support.close(a, who, "platform")
    return Response(status_code=204)


# ---------- platform managers ----------
class ManagerAdd(BaseModel):
    email: EmailStr


def manager_row(m: PlatformMember) -> dict:
    return {"email": m.email, "display_name": m.display_name, "active": m.first_seen_at is not None}


@router.get("/managers")
async def list_managers():
    return [manager_row(m) for m in await get_repository().list_platform_members()]


@router.post("/managers", status_code=201)
async def add_manager(body: ManagerAdd, identity: Identity = Depends(require_platform)):
    repo = get_repository()
    if await repo.get_platform_member(body.email):
        return err(409, "already_manager", "Ha già il ruolo di gestore della piattaforma")
    added = await repo.add_platform_member(PlatformMember(email=body.email, added_by=identity.email))
    await audit.record("manager_added", audit.by_platform(identity), None, audit.manager_target(added.email))
    return manager_row(added)


@router.post("/managers/remove", status_code=204)
async def remove_manager(body: dict = Body(...), identity: Identity = Depends(require_platform)):
    """P-71 (D-142): the email in the body, never in the path (paths end up in access logs). Was DELETE
    /managers/{email}, gone in the same lot."""
    email = body.get("email") if isinstance(body, dict) else None
    if not isinstance(email, str) or not email.strip():
        return err(422, "bad_request", "Indica l'email del gestore da rimuovere")
    email = email.strip().lower()
    outcome = await get_repository().remove_platform_member_keeping_one(email)   # atomic (P-36 point 14c)
    if outcome == "not_found":
        return err(404, "not_found", "Non è un gestore della piattaforma")
    if outcome == "last":
        return err(409, "last_manager", "È l'ultimo gestore della piattaforma: nomina prima qualcun altro")
    await audit.record("manager_removed", audit.by_platform(identity), None, audit.manager_target(email))
    await support.close_all_of(audit.by_platform(identity), email=email)   # D-88: no access outlives the role
    return Response(status_code=204)


# ---------- administrative log (P-47) ----------
@router.get("/audit")
async def audit_log(tenant_id: str | None = None, scope: Literal["platform"] | None = None,
                    limit: int = Query(50, ge=1, le=100), before: str | None = None):
    """One organisation's log (tenant_id) or the platform-level actions (scope=platform), newest first."""
    if (tenant_id is None) == (scope is None):
        return err(422, "bad_request", "Indica tenant_id oppure scope=platform")
    if tenant_id is not None:
        t = await _get_tenant(tenant_id)
        if isinstance(t, JSONResponse):
            return t
    return await audit.page(tenant_id, limit, before, viewer="platform")


# ---------- unattributed webhook calls (P-36 S1) ----------
@router.get("/webhook-logs")
async def unattributed_webhook_logs():
    """Calls that reached no organisation (bad signature, unknown or ambiguous Italianway code): platform only."""
    return [log.model_dump() for log in await get_repository().list_webhook_logs(None)]


# ---------- apartments: technical record only (D-66) ----------
class ApartmentCreate(BaseModel):
    apartment_id: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
    name: str = Field(min_length=1, max_length=120)
    instance_url: str = Field(min_length=1)
    port: int | None = Field(default=None, ge=1, le=65535)
    timezone: str = "Europe/Rome"
    enabled: bool = True
    italianway_id: str | None = Field(default=None, max_length=120)   # D-72: set by the platform only
    simulated: bool = False   # D-97: a real engine in simulated mode; always true on mock://


class ApartmentLink(BaseModel):
    instance_url: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    italianway_id: str | None = Field(default=None, max_length=120)   # missing = no change; null or "" = remove
    simulated: bool | None = None   # D-97: missing = the rule (mock:// true, leaving mock:// false, else unchanged)


def _demo_code_refused(url: str, code: str | None) -> JSONResponse | None:
    """D-98 (d3): in production a demonstration apartment (mock://) never gets an Italianway code, which would route
    real bookings into a simulated engine. In staging it stays allowed."""
    if code and instances.is_mock(url) and get_settings().instance_mode == "real":
        return err(409, "italianway_on_demo", "In produzione un appartamento dimostrativo non può avere un codice Italianway")
    return None


def apartment_row(a: Apartment) -> dict:
    return {"apartment_id": a.apartment_id, "name": a.name, "instance_url": a.instance_url, "port": a.port,
            "enabled": a.enabled, "timezone": a.timezone, "italianway_id": a.external_ids.italianway,
            "simulated": a.simulated, "last_check": a.last_check.model_dump() if a.last_check else None}


def _code(value: str | None) -> str | None:
    return (value or "").strip() or None


async def _claim_code(code: str | None, apartment_id: str) -> bool:
    """D-72: the Italianway code routes real bookings; one apartment in the whole system. Read check (also covers
    records saved before the claim index) + atomic claim. True when free for this apartment (or no code)."""
    if code is None:
        return True
    repo = get_repository()
    if any(a.apartment_id != apartment_id for a in await repo.find_apartments_by_external_id("italianway", code)):
        return False
    return await repo.claim_external_id("italianway", code, apartment_id) is None


async def _tenant_apartment(tenant_id: str, apartment_id: str) -> Apartment | JSONResponse:
    apt = await get_repository().get_apartment(apartment_id)
    if not apt or apt.tenant_id != tenant_id:
        return err(404, "not_found", "Appartamento inesistente")
    return apt


@router.get("/tenants/{tenant_id}/apartments")
async def list_tenant_apartments(tenant_id: str):
    t = await _get_tenant(tenant_id)
    if isinstance(t, JSONResponse):
        return t
    return [apartment_row(a) for a in await get_repository().list_apartments(tenant_id)]


@router.post("/tenants/{tenant_id}/apartments", status_code=201)
async def create_tenant_apartment(tenant_id: str, body: ApartmentCreate, identity: Identity = Depends(require_platform)):
    """The id must match the engine instance lb-<id> and its secret langbrain-api-key-<id> (D-64)."""
    repo = get_repository()
    t = await _get_tenant(tenant_id)
    if isinstance(t, JSONResponse):
        return t
    if not _check_tz(body.timezone):
        return err(422, "invalid_timezone", "Fuso orario non valido")
    if problem := instances.instance_url_problem(body.instance_url):
        return err(422, "invalid_instance_url", problem)
    if refused := _demo_code_refused(body.instance_url, _code(body.italianway_id)):
        return refused
    if (await instances.link_in_use(body.instance_url, body.port, body.apartment_id)
            or not await instances.claim_link(body.instance_url, body.port, body.apartment_id)):   # L8: read + atomic
        return err(409, "link_in_use", "Collegamento già usato da un altro appartamento")
    code = _code(body.italianway_id)
    if not await _claim_code(code, body.apartment_id):
        await instances.release_link(body.instance_url, body.port, body.apartment_id)
        return err(409, "external_id_in_use", "Codice Italianway già in uso")
    if await repo.get_apartment(body.apartment_id) or not await repo.reserve_apartment_id(body.apartment_id):
        await instances.release_link(body.instance_url, body.port, body.apartment_id)
        if code:
            await repo.release_external_id("italianway", code, body.apartment_id)
        return err(409, "already_exists", "Identificativo non disponibile")   # in use, or used before (D-67)
    apt = Apartment(apartment_id=body.apartment_id, tenant_id=tenant_id, name=body.name.strip(), timezone=body.timezone,
                    instance_url=instances.normalize_instance_url(body.instance_url), port=body.port, enabled=body.enabled,
                    external_ids=ExternalIds(italianway=code), simulated=body.simulated)
    saved = await repo.upsert_apartment(apt)
    who, target = audit.by_platform(identity), audit.apartment_target(saved.apartment_id, saved.name)
    await audit.record("apartment_created", who, tenant_id, target)
    if code:
        await audit.record("italianway_changed", who, tenant_id, target, **{"from": None, "to": code})
    return apartment_row(saved)


@router.patch("/tenants/{tenant_id}/apartments/{apartment_id}")
async def relink_tenant_apartment(tenant_id: str, apartment_id: str, body: ApartmentLink,
                                  identity: Identity = Depends(require_platform)):
    """The link to the engine and the Italianway code (D-64, D-72); name, enabled and the rest stay with the admin.
    Order: every check and claim first, then the save, and only after the save the old link and code are released,
    so a refusal leaves the claim indexes exactly as they were."""
    apt = await _tenant_apartment(tenant_id, apartment_id)
    if isinstance(apt, JSONResponse):
        return apt
    repo = get_repository()
    old_url, old_port, old_code, old_sim = apt.instance_url, apt.port, apt.external_ids.italianway, apt.simulated
    if body.instance_url is not None:
        if problem := instances.instance_url_problem(body.instance_url):
            return err(422, "invalid_instance_url", problem)
        apt.instance_url = instances.normalize_instance_url(body.instance_url)
    if "port" in body.model_fields_set:
        apt.port = body.port
    new_code = _code(body.italianway_id) if "italianway_id" in body.model_fields_set else old_code
    if refused := _demo_code_refused(apt.instance_url, new_code):
        return refused
    # D-97: mock:// is always simulated; leaving mock:// for a real address makes it real unless said otherwise
    if instances.is_mock(apt.instance_url):
        apt.simulated = True
    elif body.simulated is not None:
        apt.simulated = body.simulated
    elif instances.is_mock(old_url):
        apt.simulated = False
    link_changes = instances.link_key(apt.instance_url, apt.port) != instances.link_key(old_url, old_port)
    if link_changes and (await instances.link_in_use(apt.instance_url, apt.port, apartment_id)
                         or not await instances.claim_link(apt.instance_url, apt.port, apartment_id)):   # L8
        return err(409, "link_in_use", "Collegamento già usato da un altro appartamento")
    if new_code != old_code and not await _claim_code(new_code, apartment_id):
        if link_changes:
            await instances.release_link(apt.instance_url, apt.port, apartment_id)   # undo the new link claim
        return err(409, "external_id_in_use", "Codice Italianway già in uso")
    apt.external_ids.italianway = new_code
    saved = await repo.upsert_apartment(apt)
    if link_changes:
        await instances.release_link(old_url, old_port, apartment_id)
    if old_code and old_code != new_code:  # the old code is free again
        await repo.release_external_id("italianway", old_code, apartment_id)
    instances.invalidate_version(apartment_id)
    hub_manager.hub(saved)
    who, target = audit.by_platform(identity), audit.apartment_target(saved.apartment_id, saved.name)
    if (saved.instance_url, saved.port) != (old_url, old_port):   # also for mock://, where link_key ignores the port
        await audit.record("apartment_relinked", who, tenant_id, target)
    if new_code != old_code:
        await audit.record("italianway_changed", who, tenant_id, target, **{"from": old_code, "to": new_code})
    if saved.simulated != old_sim:
        await audit.record("apartment_simulated_changed", who, tenant_id, target, **{"from": old_sim, "to": saved.simulated})
    return apartment_row(saved)


@router.post("/tenants/{tenant_id}/apartments/{apartment_id}/verify")
async def verify_tenant_apartment(tenant_id: str, apartment_id: str, identity: Identity = Depends(require_platform)):
    apt = await _tenant_apartment(tenant_id, apartment_id)
    if isinstance(apt, JSONResponse):
        return apt
    full = await instances.verify(apt, await actors.actor_for(identity.uid, identity.email))  # stores last_check
    # L4 (D-70): only the technical outcome; the instance's /health body (device list, …) is organisation data
    return {"apartment_id": apartment_id, "ok": full["ok"], "error": full["error"],   # the detail: platform only
            "contract_version": full["contract_version"]}


@router.delete("/tenants/{tenant_id}/apartments/{apartment_id}", status_code=204)
async def delete_tenant_apartment(tenant_id: str, apartment_id: str, identity: Identity = Depends(require_platform)):
    apt = await _tenant_apartment(tenant_id, apartment_id)
    if isinstance(apt, JSONResponse):
        return apt
    await remove_apartment(apt)
    await audit.record("apartment_deleted", audit.by_platform(identity), tenant_id,
                       audit.apartment_target(apt.apartment_id, apt.name))
    return Response(status_code=204)
