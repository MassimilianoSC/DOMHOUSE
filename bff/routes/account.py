"""Self-service account operations of the signed-in user. Password and email changes happen in the browser through
Firebase Auth (they need the current password); the BFF only handles what needs its records or admin rights."""
import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import accounts, audit, erasure, support
from ..auth import CurrentUser, Identity, resolve_own_identity, resolve_own_user
from ..logs import info, warn
from ..repository import User, get_repository

router = APIRouter(prefix="/app/me")


def err(status: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": error, "message": message})


class ProfilePatch(BaseModel):
    display_name: str = Field(max_length=80)


@router.patch("")
async def patch_profile(body: ProfilePatch, user: CurrentUser = Depends(resolve_own_user)):
    repo = get_repository()
    stored = await repo.get_user(user.uid) or User(uid=user.uid, email=user.email, tenant_id=user.tenant_id, role=user.role)
    stored.display_name = body.display_name.strip()
    saved = await repo.upsert_user(stored)
    return {"display_name": saved.display_name}


@router.post("/revoke-sessions", status_code=204)
async def revoke_sessions(user: CurrentUser = Depends(resolve_own_user)):
    """Signs the user out everywhere: every refresh token is revoked and current ID tokens are refused."""
    await asyncio.to_thread(accounts.revoke_sessions, user.uid)


@router.delete("", status_code=204)
async def delete_account(identity: Identity = Depends(resolve_own_identity)):
    """«Elimina il mio account» (P-48, D-87): a member, or a platform manager with or without an organisation (Fable
    note 4). Refusals come first and change nothing; afterwards every trace of the person goes (bff/erasure.py) and
    their actions stay as «utente rimosso»."""
    repo = get_repository()
    user = identity.user
    stored = await repo.get_user(user.uid) if user else None
    # D-73: a platform manager leaves the platform too. The last one is refused, atomically like every "last manager"
    # check, BEFORE anything else changes; otherwise the role goes with the account.
    manager = await repo.get_platform_member(identity.email)
    if manager is not None:
        removed = await repo.remove_platform_member_keeping_one(identity.email)
        if removed == "last":
            return err(409, "last_manager", "Sei l'ultimo gestore della piattaforma: nomina un altro gestore prima di eliminare il tuo account")
    if user is not None:
        # P-36 point 14b: atomic "at least one admin", the record first
        outcome = await repo.delete_user_keeping_an_admin(user.uid)
        if outcome == "last_admin":
            if manager is not None:
                await repo.add_platform_member(manager)  # nothing half done: the manager role comes back
            return err(409, "last_admin", "Sei l'unico amministratore: nomina un altro amministratore prima di eliminare il tuo account")
    try:
        await asyncio.to_thread(accounts.delete_account, identity.uid, None, False, True)  # owner: real deletion (N3)
    except Exception as exc:
        warn("account: firebase deletion failed", error=str(exc))
        if stored is not None:
            await repo.upsert_user(stored)  # put the record back
        if manager is not None:
            await repo.add_platform_member(manager)
        return err(502, "auth_unavailable", "Eliminazione non riuscita, riprova tra poco")
    info("account: deleted by its owner")
    if user is not None:
        who = audit.by_user(user)
        me = User(uid=user.uid, email=user.email, display_name=user.display_name, tenant_id=user.tenant_id, role=user.role)
        await audit.record("account_deleted", who, user.tenant_id, audit.user_target(me))
    else:
        who = audit.by_platform(identity)
    if manager is not None:
        # D-88: no support access outlives the account; in each organisation the closing is the manager's (D-91)
        await support.close_all_of(None, uid=identity.uid)
        # the platform's own log shows that a manager left with their account
        await audit.record("account_deleted", audit.Who(audit.AuditActor(kind="platform", ref=identity.uid)), None,
                           audit.manager_target(identity.email))
    await erasure.erase_person(identity.uid, identity.email, stored.former_emails if stored else ())   # «utente rimosso»
