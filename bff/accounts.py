"""Firebase Auth account operations used by the BFF (all no-ops unless AUTH_MODE=firebase).

* session revocation: `revoke_sessions` invalidates every refresh token of a user; `token_revoked` is checked on each
  request (cached per uid for REVOCATION_CACHE_S) so revoked or deleted accounts lose access within that window
  instead of keeping a valid ID token for up to an hour;
* `delete_account`, `set_role_claim`: keep Firebase in line with what the admin does in the app.

The functions are blocking (firebase-admin is synchronous): call them through asyncio.to_thread.
"""
import time

from .config import get_settings
from .logs import info, warn

REVOCATION_CACHE_S = 60.0
_valid_after: dict[str, tuple[float, float | None]] = {}  # uid -> (checked_at, tokens_valid_after in s; None = deleted)


def _enabled() -> bool:
    return get_settings().auth_mode == "firebase"


def _auth():
    from firebase_admin import auth as fb_auth

    from .auth import firebase_app

    return fb_auth, firebase_app()


def token_revoked(uid: str, issued_at: float) -> bool:
    """True when the account was deleted or its sessions were revoked after the token was issued."""
    if not _enabled():
        return False
    now = time.monotonic()
    cached = _valid_after.get(uid)
    if cached is None or now - cached[0] > REVOCATION_CACHE_S:
        fb_auth, app = _auth()
        try:
            record = fb_auth.get_user(uid, app=app)
            valid_after = (record.tokens_valid_after_timestamp or 0) / 1000
        except fb_auth.UserNotFoundError:
            valid_after = None
        except Exception as exc:  # Auth API unreachable: do not lock everybody out
            warn("auth: revocation check failed", uid=uid, error=str(exc))
            return False
        cached = (now, valid_after)
        _valid_after[uid] = cached
    valid_after = cached[1]
    return valid_after is None or issued_at < valid_after


def revoke_sessions(uid: str) -> None:
    if not _enabled():
        return
    fb_auth, app = _auth()
    fb_auth.revoke_refresh_tokens(uid, app=app)
    _valid_after.pop(uid, None)
    info("auth: sessions revoked", uid=uid)


def delete_account(uid: str | None = None, email: str | None = None, protect: bool = False, owner: bool = False) -> bool:
    """Detaches an account removed from an organisation. Returns True only when the Firebase account was hard-deleted.

    F5 (D-70): the Firebase identity is global, so an ADMINISTRATOR's action never destroys a real one. The account is
    deleted ONLY when it was never truly used (unverified email, no tenant claims) and is not protected (a platform
    manager). Otherwise its sessions are revoked and it is kept, so the org record is gone but the identity survives.
    N3 (D-71): owner=True is the person asking to delete their own account: then the deletion is real."""
    if not _enabled():
        return False
    fb_auth, app = _auth()
    try:
        record = fb_auth.get_user(uid, app=app) if uid else fb_auth.get_user_by_email(email, app=app)
    except fb_auth.UserNotFoundError:
        return False
    has_claims = bool((record.custom_claims or {}).get("tenant_id"))
    if not owner and (protect or record.email_verified or has_claims):
        fb_auth.revoke_refresh_tokens(record.uid, app=app)
        _valid_after.pop(record.uid, None)
        info("auth: firebase account kept, sessions revoked", uid=record.uid)
        return False
    fb_auth.delete_user(record.uid, app=app)
    _valid_after[record.uid] = (time.monotonic(), None)
    info("auth: firebase account deleted", uid=record.uid)
    return True


def set_role_claim(uid: str, role: str) -> None:
    """Custom claims prevail over the app record: when the user has claims, the role change must reach them too."""
    if not _enabled():
        return
    fb_auth, app = _auth()
    try:
        record = fb_auth.get_user(uid, app=app)
    except fb_auth.UserNotFoundError:
        return
    claims = dict(record.custom_claims or {})
    if not claims.get("tenant_id"):
        return
    claims["role"] = role
    fb_auth.set_custom_user_claims(uid, claims, app=app)
    fb_auth.revoke_refresh_tokens(uid, app=app)  # forces a new ID token carrying the new role
    _valid_after.pop(uid, None)
    info("auth: role claim updated", uid=uid, role=role)
