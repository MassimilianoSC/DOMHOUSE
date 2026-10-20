"""User-level push subscription and notification preferences."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..auth import CurrentUser, resolve_own_user
from ..config import get_settings
from ..repository import NotificationPrefs, User, get_repository

router = APIRouter(prefix="/app")


class TokenBody(BaseModel):
    token: str = Field(min_length=10, max_length=4096)


async def _stored(user: CurrentUser) -> User:
    repo = get_repository()
    stored = await repo.get_user(user.uid)
    if stored:
        return stored
    return await repo.upsert_user(User(uid=user.uid, email=user.email, display_name=user.display_name,
                                       tenant_id=user.tenant_id, role=user.role))


@router.post("/push/subscribe")
async def subscribe(body: TokenBody, user: CurrentUser = Depends(resolve_own_user)):
    repo = get_repository()
    # P-36 point 11: a device token belongs to ONE person. If someone left without unsubscribing and another person
    # (maybe of another organisation) signs in on the same browser, the first one's pushes must stop reaching it.
    for other in await repo.users_with_push_token(body.token):
        if other.uid != user.uid:
            other.push_tokens = [t for t in other.push_tokens if t != body.token]
            await repo.upsert_user(other)
    stored = await _stored(user)
    if body.token not in stored.push_tokens:
        stored.push_tokens = (stored.push_tokens + [body.token])[-5:]
        await get_repository().upsert_user(stored)
    return {"subscribed": True, "tokens": len(stored.push_tokens), "fcm_enabled": get_settings().fcm_enabled}


@router.delete("/push/subscribe")
async def unsubscribe(body: TokenBody, user: CurrentUser = Depends(resolve_own_user)):
    repo = get_repository()
    # F4 (D-70): remove the device token from EVERY user that holds it, of any organisation. On a shared device the
    # token may still be registered to whoever used it before; signing out must stop their pushes to that device too.
    await _stored(user)  # make sure the caller has a record (first call after sign-in)
    for holder in await repo.users_with_push_token(body.token):
        holder.push_tokens = [t for t in holder.push_tokens if t != body.token]
        await repo.upsert_user(holder)
    caller = await repo.get_user(user.uid)
    return {"subscribed": False, "tokens": len(caller.push_tokens) if caller else 0}


@router.put("/me/notification-prefs")
async def set_prefs(body: NotificationPrefs, user: CurrentUser = Depends(resolve_own_user)):
    stored = await _stored(user)
    stored.notification_prefs = body
    await get_repository().upsert_user(stored)
    return body.model_dump()


@router.get("/push/status")
async def status(user: CurrentUser = Depends(resolve_own_user)):
    stored = await _stored(user)
    if not stored:
        return JSONResponse(status_code=404, content={"error": "not_found", "message": "Utente inesistente"})
    return {"fcm_enabled": get_settings().fcm_enabled, "tokens": len(stored.push_tokens), "prefs": stored.notification_prefs.model_dump()}
