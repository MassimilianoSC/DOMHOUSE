"""User-level push subscription and notification preferences."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..auth import CurrentUser, Identity, resolve_own_identity, resolve_own_user
from ..config import get_settings
from ..repository import NotificationPrefs, get_repository

router = APIRouter(prefix="/app")


class TokenBody(BaseModel):
    token: str = Field(min_length=10, max_length=4096)


def _gone() -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": "not_found", "message": "Utente inesistente"})


def _without(token: str):
    return lambda cur: cur.model_copy(update={"push_tokens": [t for t in cur.push_tokens if t != token]})


# F-1 (attack-from-outside review): these routes change only a record that exists. The record is made at sign-in
# (bff/auth.py, with Firebase's confirmation); writing back a copy read earlier made again a person removed meanwhile.


@router.post("/push/subscribe")
async def subscribe(body: TokenBody, user: CurrentUser = Depends(resolve_own_user)):
    repo = get_repository()
    # P-36 point 11: a device token belongs to ONE person. If someone left without unsubscribing and another person
    # (maybe of another organisation) signs in on the same browser, the first one's pushes must stop reaching it.
    for other in await repo.users_with_push_token(body.token):
        if other.uid != user.uid:
            await repo.update_user_if_present(other.uid, _without(body.token))
    stored = await repo.get_user(user.uid)
    if stored is not None and body.token not in stored.push_tokens:
        stored = await repo.update_user_if_present(
            user.uid, lambda cur: cur.model_copy(update={"push_tokens": (
                cur.push_tokens if body.token in cur.push_tokens else cur.push_tokens + [body.token])[-5:]}))
    if stored is None:
        return _gone()
    return {"subscribed": True, "tokens": len(stored.push_tokens), "fcm_enabled": get_settings().fcm_enabled}


@router.delete("/push/subscribe")
async def unsubscribe(body: TokenBody, identity: Identity = Depends(resolve_own_identity)):
    """Also for a platform manager without an organisation (lot 27): a device used before by a member must stop
    receiving that member's pushes whoever signs in on it, so the removal is never refused for lack of a tenant."""
    repo = get_repository()
    # F4 (D-70): remove the device token from EVERY user that holds it, of any organisation. On a shared device the
    # token may still be registered to whoever used it before; signing out must stop their pushes to that device too.
    for holder in await repo.users_with_push_token(body.token):
        await repo.update_user_if_present(holder.uid, _without(body.token))
    caller = await repo.get_user(identity.uid)
    return {"subscribed": False, "tokens": len(caller.push_tokens) if caller else 0}


@router.put("/me/notification-prefs")
async def set_prefs(body: NotificationPrefs, user: CurrentUser = Depends(resolve_own_user)):
    stored = await get_repository().update_user_if_present(
        user.uid, lambda cur: cur.model_copy(update={"notification_prefs": body}))
    if stored is None:
        return _gone()
    return body.model_dump()


@router.get("/push/status")
async def status(user: CurrentUser = Depends(resolve_own_user)):
    stored = await get_repository().get_user(user.uid)
    if not stored:
        return _gone()
    return {"fcm_enabled": get_settings().fcm_enabled, "tokens": len(stored.push_tokens), "prefs": stored.notification_prefs.model_dump()}
