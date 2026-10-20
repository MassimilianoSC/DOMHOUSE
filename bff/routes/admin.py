"""Admin area: users, apartments, features — always scoped to the admin's tenant."""
import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field

from .. import accounts, actors, audit, instances, support
from ..auth import CurrentUser, require_admin, scope_out
from ..logs import warn
from ..features import APP_FEATURES
from ..invites import InviteRefused, create_invitation, send_invitation, shown
from ..repository import Apartment, Tenant, User, get_repository
from ..sse_hub import hub_manager

router = APIRouter(prefix="/app/admin", dependencies=[Depends(require_admin)])
Role = Literal["admin", "operator", "viewer"]


def err(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message})


def user_out(u: User) -> dict:
    return {"uid": u.uid, "email": u.email, "display_name": u.display_name, "role": u.role,
            "pending": u.uid.startswith("inv-"), "push_tokens": len(u.push_tokens),
            "apartment_ids": scope_out(u.apartment_ids, u.role)}


# P-18 (D-43): "all" or a list of the tenant's apartment ids ([] = none); null is never accepted, so an empty or
# uninitialised field sent by mistake cannot open every apartment.
ApartmentScope = Literal["all"] | list[str]


class InviteBody(BaseModel):
    email: EmailStr
    role: Role
    display_name: str = ""
    apartment_ids: ApartmentScope = "all"


class UserPatch(BaseModel):
    role: Role | None = None
    display_name: str | None = None
    apartment_ids: ApartmentScope | None = None  # missing = no change; an explicit null is refused in patch_user


async def _scope_in(value: ApartmentScope, role: str, tenant_id: str) -> tuple[list[str] | None, JSONResponse | None]:
    """API scope → stored value (None = all), or the 422 answer."""
    if value == "all":
        return None, None
    if role == "admin":
        return None, err(422, "admin_all_apartments", "Gli amministratori vedono sempre tutti gli appartamenti")
    ids = list(dict.fromkeys(value))
    known = {a.apartment_id for a in await get_repository().list_apartments(tenant_id)}
    unknown = [i for i in ids if i not in known]
    if unknown:
        return None, JSONResponse(status_code=422, content={
            "error": "unknown_apartment", "message": f"Appartamento inesistente: {', '.join(unknown)}",
            "details": {"apartment_ids": unknown}})
    return ids, None


@router.get("/users")
async def list_users(user: CurrentUser = Depends(require_admin)):
    return [user_out(u) for u in await get_repository().list_users(user.tenant_id)]


@router.post("/users", status_code=201)
async def invite_user(body: InviteBody, user: CurrentUser = Depends(require_admin)):
    apartment_ids, problem = await _scope_in(body.apartment_ids, body.role, user.tenant_id)
    if problem:
        return problem
    try:  # D-63 messages and the atomic, idempotent record live in invites.create_invitation (P-36)
        created = await create_invitation(user.tenant_id, body.email, body.role, body.display_name, apartment_ids)
    except InviteRefused as exc:
        return err(409, "already_exists", exc.message)
    await audit.record("invite_sent", audit.by_user(user), user.tenant_id, audit.user_target(created),
                       role=created.role, apartment_ids=scope_out(created.apartment_ids, created.role))
    return {**user_out(created), "email_status": await _notify(created, user)}


async def _notify(target: User, inviter: CurrentUser) -> str:
    tenant = await get_repository().get_tenant(inviter.tenant_id)
    status = await send_invitation(target.email, target.display_name, target.role, tenant.name if tenant else "",
                                   inviter.display_name or inviter.email, inviter.tenant_id)
    if status == "deferred":  # P-49: the invitation stays; only the log says why the email did not leave
        await audit.record("invite_email_deferred", audit.by_user(inviter), inviter.tenant_id, audit.user_target(target))
    return shown(status)


@router.post("/users/{uid}/invite")
async def resend_invite(uid: str, user: CurrentUser = Depends(require_admin)):
    target = await get_repository().get_user(uid)
    if not target or target.tenant_id != user.tenant_id:
        return err(404, "not_found", "Utente inesistente")
    if not target.uid.startswith("inv-"):
        return err(409, "already_active", "L'utente ha già effettuato l'accesso")
    await audit.record("invite_resent", audit.by_user(user), user.tenant_id, audit.user_target(target))
    return {**user_out(target), "email_status": await _notify(target, user)}


@router.patch("/users/{uid}")
async def patch_user(uid: str, body: UserPatch, user: CurrentUser = Depends(require_admin)):
    repo = get_repository()
    target = await repo.get_user(uid)
    if not target or target.tenant_id != user.tenant_id:
        return err(404, "not_found", "Utente inesistente")
    if uid == user.uid and body.role and body.role != "admin":
        return err(409, "self_demotion", "Non puoi togliere a te stesso il ruolo di amministratore")
    new_role = body.role or target.role
    # checked before the role claim changes, so a refused request leaves nothing half done
    if "apartment_ids" in body.model_fields_set:
        if body.apartment_ids is None:
            return err(422, "invalid_apartment_ids", 'Per dare accesso a tutti gli appartamenti scrivi "all"')
        apartment_ids, problem = await _scope_in(body.apartment_ids, new_role, user.tenant_id)
        if problem:
            return problem
    else:
        # promotion to admin resets the list (D-45): going back and forth must not revive a forgotten restriction
        apartment_ids = None if new_role == "admin" else target.apartment_ids
    before = target.model_copy(deep=True)
    if body.role:
        target.role = body.role
    if body.display_name is not None:
        target.display_name = body.display_name
    target.apartment_ids = apartment_ids
    # P-36 point 14b: "at least one admin" checked and written atomically (two admins demoting each other at once)
    if not await repo.upsert_user_keeping_an_admin(target):
        return err(409, "last_admin", "Deve restare almeno un amministratore nell'organizzazione")
    if body.role and body.role != before.role and not target.uid.startswith("inv-"):
        try:  # claims prevail over the app record: a role change must reach them, or it would be undone at login
            await asyncio.to_thread(accounts.set_role_claim, target.uid, body.role)
        except Exception as exc:
            warn("admin: role claim not updated", uid=target.uid, error=str(exc))
            await repo.upsert_user(before)  # back to the previous record: nothing half done
            return err(502, "auth_unavailable", "Ruolo non aggiornato, riprova tra poco")
        # F3 (D-70): a user without claims (recognised by the record) keeps a valid token with the old role; revoke the
        # sessions so the new role takes effect and any open stream ends. set_role_claim already revokes when it has claims.
        try:
            await asyncio.to_thread(accounts.revoke_sessions, target.uid)
        except Exception as exc:  # N5 (D-71): the change stays (the record rules the next request and the stream
            warn("admin: sessions not revoked after a role change", uid=target.uid, error=str(exc))  # re-check)
    who = audit.by_user(user)
    if target.role != before.role:
        await audit.record("role_changed", who, user.tenant_id, audit.user_target(target),
                           **{"from": before.role, "to": target.role})
    scope_after = scope_out(target.apartment_ids, target.role)
    if scope_after != scope_out(before.apartment_ids, before.role):
        await audit.record("scope_changed", who, user.tenant_id, audit.user_target(target), to=scope_after)
    return user_out(target)


@router.delete("/users/{uid}", status_code=204)
async def delete_user(uid: str, user: CurrentUser = Depends(require_admin)):
    repo = get_repository()
    target = await repo.get_user(uid)
    if not target or target.tenant_id != user.tenant_id:
        return err(404, "not_found", "Utente inesistente")
    if uid == user.uid:
        return err(409, "self_delete", "Non puoi eliminare il tuo stesso account")
    # P-36 point 14b: the record goes first, atomically with the "at least one admin" check
    outcome = await repo.delete_user_keeping_an_admin(uid)
    if outcome == "last_admin":
        return err(409, "last_admin", "Deve restare almeno un amministratore nell'organizzazione")
    if outcome == "not_found":
        return err(404, "not_found", "Utente inesistente")
    # F5 (D-70): never hard-delete the Firebase account of a platform manager (its email is visible to every user)
    protect = await repo.get_platform_member(target.email) is not None
    try:  # removing only the app record would leave a Firebase account (with claims, still able to sign in)
        if target.uid.startswith("inv-"):
            await asyncio.to_thread(accounts.delete_account, None, target.email, protect)
        else:
            await asyncio.to_thread(accounts.delete_account, target.uid, None, protect)
    except Exception as exc:
        warn("admin: firebase account not detached", uid=target.uid, error=str(exc))
        await repo.upsert_user(target)  # put the record back: the person is not half removed
        return err(502, "auth_unavailable", "Rimozione non riuscita, riprova tra poco")
    await audit.record("user_removed", audit.by_user(user), user.tenant_id, audit.user_target(target))


class ApartmentPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    address: str | None = None
    timezone: str | None = None
    instance_url: str | None = None
    instance_secret_name: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    enabled: bool | None = None
    italianway_id: str | None = None
    enabled_features: list[str] | None = None
    clear_features: bool = False
    energy_price_eur_kwh: float | None = None   # P-52: missing = no change; null = the organisation's price


def apt_out(a: Apartment) -> dict:
    # no instance_secret_name: the secret name is always derived from the apartment id (D-60); D-90: neither the fields
    # nobody uses (tenant_id, created_at, external_ids) nor the name of a secret in last_check
    out = {**a.model_dump(exclude={"instance_secret_name", "tenant_id", "created_at", "external_ids"}),
           "italianway_id": a.external_ids.italianway}
    out["last_check"] = instances.for_admin(out.get("last_check"))
    return out


def _code_refused(code: str | None, current: str | None = None) -> JSONResponse | None:
    """D-72 (F6): the Italianway code routes real bookings, so only the platform sets it, in every mode. An admin may
    only resend the value already saved; a new, different or removed (null, "") one is refused."""
    if ((code or "").strip() or None) != current:
        return err(403, "platform_only", "Il codice Italianway lo imposta il gestore della piattaforma")
    return None


def _platform_only(what: str) -> JSONResponse:
    """D-64/D-65, D-77: the platform creates, links and deletes apartments (their id must match the engine instance
    lb-<id> and its secret), in every mode: also in staging (mock) the admin only manages the rest."""
    return err(403, "platform_only", f"{what} spetta al gestore della piattaforma")


def _secret_name_refused(value: str | None) -> JSONResponse | None:
    """P-36, S3: an admin no longer chooses which secret the BFF sends to the instance."""
    if value and value.strip():
        return err(422, "secret_name_not_allowed", "Il nome del segreto non si sceglie")   # D-90: no naming scheme
    return None


def _check_tz(tz: str) -> bool:
    from zoneinfo import ZoneInfo

    try:
        ZoneInfo(tz)
        return True
    except Exception:
        return False


def _check_features(features: list[str] | None) -> bool:
    return features is None or all(f in APP_FEATURES for f in features)


@router.get("/apartments")
async def list_apartments(user: CurrentUser = Depends(require_admin)):
    return [apt_out(a) for a in await get_repository().list_apartments(user.tenant_id)]


@router.post("/apartments", status_code=201)
async def create_apartment(user: CurrentUser = Depends(require_admin)):
    # D-77: in every mode; the body is not even read, so nothing about the request (ids, codes) is checked or leaked
    return _platform_only("La creazione degli appartamenti")


@router.patch("/apartments/{apartment_id}")
async def patch_apartment(apartment_id: str, body: ApartmentPatch, user: CurrentUser = Depends(require_admin)):
    repo = get_repository()
    apt = await repo.get_apartment(apartment_id)
    if not apt or apt.tenant_id != user.tenant_id:
        return err(404, "not_found", "Appartamento inesistente")
    if body.timezone is not None and not _check_tz(body.timezone):
        return err(422, "invalid_timezone", "Fuso orario non valido")
    if not _check_features(body.enabled_features):
        return err(422, "invalid_feature", "Funzione sconosciuta")
    if refused := _secret_name_refused(body.instance_secret_name):
        return refused
    # the PWA form sends the whole body: only a real change of the link is refused (D-64)
    url_changes = body.instance_url is not None and instances.normalize_instance_url(body.instance_url) != apt.instance_url
    port_changes = "port" in body.model_fields_set and body.port != apt.port
    if url_changes or port_changes:  # D-77: in every mode
        return _platform_only("Il collegamento al motore (URL e porta)")
    if refused := _price_refused(body.energy_price_eur_kwh):
        return refused
    if "italianway_id" in body.model_fields_set and (refused := _code_refused(body.italianway_id, apt.external_ids.italianway)):
        return refused  # D-72: only the platform changes the code; the same value resent by the form is ignored
    data = body.model_dump(exclude_unset=True, exclude={"italianway_id", "enabled_features", "clear_features",
                                                        "instance_secret_name", "instance_url", "port",
                                                        "energy_price_eur_kwh"})
    price_before = apt.energy_price_eur_kwh
    if "energy_price_eur_kwh" in body.model_fields_set:
        apt.energy_price_eur_kwh = body.energy_price_eur_kwh
    changed = [k for k, v in data.items() if getattr(apt, k) != v]   # P-47: only real changes reach the log
    features_before = apt.enabled_features
    for k, v in data.items():
        setattr(apt, k, v)
    if body.clear_features:
        apt.enabled_features = None
    elif "enabled_features" in body.model_fields_set:
        apt.enabled_features = body.enabled_features
    saved = await repo.upsert_apartment(apt)
    instances.invalidate_version(apartment_id)
    hub_manager.hub(saved)
    target = audit.apartment_target(saved.apartment_id, saved.name)
    if changed:
        await audit.record("apartment_updated", audit.by_user(user), user.tenant_id, target, fields=changed)
    if saved.enabled_features != features_before:
        await audit.record("features_changed", audit.by_user(user), user.tenant_id, target, to=saved.enabled_features)
    if saved.energy_price_eur_kwh != price_before:
        await audit.record("energy_price_changed", audit.by_user(user), user.tenant_id, target,
                           **{"from": price_before, "to": saved.energy_price_eur_kwh})
    return apt_out(saved)


@router.delete("/apartments/{apartment_id}", status_code=204)
async def delete_apartment(apartment_id: str, user: CurrentUser = Depends(require_admin)):
    # D-77: in every mode, before any lookup, so the answer is the same for an own, a missing or another tenant's id
    return _platform_only("La cancellazione degli appartamenti")


async def remove_apartment(apt: Apartment) -> None:
    """Deletion by the platform (D-65, D-77): record, id kept as used (D-67), users' lists,
    version cache and the upstream stream."""
    repo = get_repository()
    await repo.delete_apartment(apt.apartment_id)
    await repo.reserve_apartment_id(apt.apartment_id)  # older apartments were created before the reservation
    if apt.external_ids.italianway:  # the code may be given to another apartment now
        await repo.release_external_id("italianway", apt.external_ids.italianway, apt.apartment_id)
    await instances.release_link(apt.instance_url, apt.port, apt.apartment_id)  # L8: the engine instance is free again
    # P-18: the id leaves every list, and a list stays a list even when it empties (never None, which means "all")
    for u in await repo.list_users(apt.tenant_id):
        if u.apartment_ids is not None and apt.apartment_id in u.apartment_ids:
            u.apartment_ids = [a for a in u.apartment_ids if a != apt.apartment_id]
            await repo.upsert_user(u)
    instances.invalidate_version(apt.apartment_id)
    hub_manager.drop(apt.apartment_id)


@router.post("/apartments/{apartment_id}/verify")
async def verify_apartment(apartment_id: str, user: CurrentUser = Depends(require_admin)):
    """'Verifica connessione': calls /health and /version on the instance and reports both."""
    repo = get_repository()
    apt = await repo.get_apartment(apartment_id)
    if not apt or apt.tenant_id != user.tenant_id:
        return err(404, "not_found", "Appartamento inesistente")
    # also stores last_check (D-64), stays with the admin in real mode; X-Actor is the pseudonym (P-48)
    return instances.for_admin(await instances.verify(apt, await actors.actor_for(user.uid, user.email)))


@router.get("/webhook-logs")
async def webhook_logs(user: CurrentUser = Depends(require_admin)):
    """Last 100 webhook calls (raw body included): admin only."""
    return [log.model_dump() for log in await get_repository().list_webhook_logs(user.tenant_id)]


class TenantPatch(BaseModel):
    # no name here (L1, D-70): the organisation's name is set only by the platform (rename_tenant), which enforces
    # uniqueness; the admin area never sent it. The admin edits the enabled features and the energy price (P-52).
    enabled_features: list[str] | None = None
    clear_features: bool = False
    energy_price_eur_kwh: float | None = None   # missing = no change; null = not set


MAX_PRICE = 10.0


def _price_refused(value: float | None) -> JSONResponse | None:
    """P-52: from 0 to 10 €/kWh (a cap against typing 100 for 0,100), at most 4 decimals."""
    if value is None:
        return None
    if not 0 <= value <= MAX_PRICE or abs(value * 10_000 - round(value * 10_000)) > 1e-6:
        return err(422, "invalid_price", f"Prezzo non valido: da 0 a {MAX_PRICE:.0f} € al kWh, al massimo 4 decimali")
    return None


def tenant_out(t: Tenant | None, tenant_id: str) -> dict:
    """Field by field (F5, D-70): created_by and first_admin_email never leave the platform area."""
    if t is None:
        return {"tenant_id": tenant_id, "name": "", "enabled_features": None, "suspended": False,
                "energy_price_eur_kwh": None}
    return {"tenant_id": t.tenant_id, "name": t.name, "enabled_features": t.enabled_features,
            "suspended": t.status == "suspended", "energy_price_eur_kwh": t.energy_price_eur_kwh}


@router.get("/tenant")
async def get_tenant(user: CurrentUser = Depends(require_admin)):
    t = await get_repository().get_tenant(user.tenant_id)
    return {**tenant_out(t, user.tenant_id), "all_features": APP_FEATURES}


@router.patch("/tenant")
async def patch_tenant(body: TenantPatch, user: CurrentUser = Depends(require_admin)):
    repo = get_repository()
    t = await repo.get_tenant(user.tenant_id)
    if not t:  # organisations are created by the platform (D-63); a missing record means not active
        return err(404, "not_found", "Organizzazione inesistente")
    if not _check_features(body.enabled_features):
        return err(422, "invalid_feature", "Funzione sconosciuta")
    if refused := _price_refused(body.energy_price_eur_kwh):
        return refused
    features_before, price_before = t.enabled_features, t.energy_price_eur_kwh
    if body.clear_features:
        t.enabled_features = None
    elif "enabled_features" in body.model_fields_set:
        t.enabled_features = body.enabled_features
    fields = {"enabled_features": t.enabled_features}
    if "energy_price_eur_kwh" in body.model_fields_set:
        fields["energy_price_eur_kwh"] = body.energy_price_eur_kwh
    # only these fields: a suspension written in between is never undone (P-50)
    saved = await repo.update_tenant(t.tenant_id, fields) or t
    target = audit.tenant_target(saved.tenant_id, saved.name)
    if saved.enabled_features != features_before:
        await audit.record("features_changed", audit.by_user(user), user.tenant_id, target, to=saved.enabled_features)
    if saved.energy_price_eur_kwh != price_before:
        await audit.record("energy_price_changed", audit.by_user(user), user.tenant_id, target,
                           **{"from": price_before, "to": saved.energy_price_eur_kwh})
    return {**tenant_out(saved, user.tenant_id), "all_features": APP_FEATURES}


@router.get("/support-access")
async def list_support_access(user: CurrentUser = Depends(require_admin)):
    """P-50: every support access to this organisation, newest first, with its status."""
    return await support.rows(await support.listed(tenant_id=user.tenant_id))


@router.delete("/support-access/{access_id}", status_code=204)
async def close_support_access(access_id: str, user: CurrentUser = Depends(require_admin)):
    """«Chiudi accesso»: effective at the next request of the manager (the access is re-read every time)."""
    a = await get_repository().get_support_access(access_id)
    if a is None or a.tenant_id != user.tenant_id:
        return err(404, "not_found", "Accesso di assistenza inesistente")
    await support.close(a, audit.by_user(user), "admin")


@router.get("/audit")
async def audit_log(limit: int = Query(50, ge=1, le=100), before: str | None = None,
                    user: CurrentUser = Depends(require_admin)):
    """P-47: the organisation's administrative log, newest first ({items, next})."""
    return await audit.page(user.tenant_id, limit, before, viewer="admin")
