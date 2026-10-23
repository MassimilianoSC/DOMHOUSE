import asyncio
import dataclasses
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from . import accounts
from .config import get_settings
from .logs import ctx_tenant, ctx_user, warn
from .repository import User, get_repository, normalize_email

# L9 (Fable): tenant_id -> (read at, status). Re-read after TENANT_RECHECK_SECONDS and dropped at once when the platform
# suspends or reactivates (forget_tenant), so a suspension reaches every request of this process immediately and, with
# more than one instance, within the recheck time. Missing organisations are never cached.
_known_tenants: dict[str, tuple[float, str]] = {}
TENANT_RECHECK_SECONDS = 30.0
SUSPENDED_MESSAGE = "Organizzazione sospesa: contatta l'assistenza HQE"
SUPPORT_HEADER = "X-Support-Tenant"
SUPPORT_EXPIRED = "L'accesso di assistenza è scaduto o è stato chiuso"

WRITE_ROLES = {"operator", "admin"}
ROLES = ("admin", "operator", "viewer")


@dataclass
class CurrentUser:
    uid: str
    email: str
    tenant_id: str
    role: str
    display_name: str = ""
    apartment_ids: list[str] | None = None  # from the app record, not the claims: a change applies at the next request
    issued_at: float = 0.0  # Firebase token "iat" (0 in dev): lets long-lived requests notice a revoked session
    support_access_id: str | None = None   # P-50: a platform manager inside the organisation through a support access
    support_expires_at: str | None = None

    @property
    def can_write(self) -> bool:
        return self.role in WRITE_ROLES

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def can_see(self, apartment_id: str) -> bool:
        return sees(self.role, self.apartment_ids, apartment_id)


def sees(role: str, apartment_ids: list[str] | None, apartment_id: str) -> bool:
    """P-18, the one rule for routes, stream and pushes: admins see every apartment of the tenant whatever their record
    says; otherwise None = all, [] = none."""
    return role == "admin" or apartment_ids is None or apartment_id in apartment_ids


def _err(status: int, error: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": error, "message": message})


async def tenant_status(repo, tenant_id: str) -> str | None:
    """"active", "suspended", or None when the organisation has no record (not active, D-63)."""
    cached = _known_tenants.get(tenant_id)
    if cached and time.monotonic() - cached[0] < TENANT_RECHECK_SECONDS:
        return cached[1]
    t = await repo.get_tenant(tenant_id)
    if t is None:
        _known_tenants.pop(tenant_id, None)
        return None
    _known_tenants[tenant_id] = (time.monotonic(), t.status)
    return t.status


def forget_tenant(tenant_id: str) -> None:
    _known_tenants.pop(tenant_id, None)


async def _tenant_gate(repo, tenant_id: str, allow_suspended: bool = False) -> str:
    status = await tenant_status(repo, tenant_id)
    if status is None:
        # D-63 (D4): organisations are created by the platform, never implicitly at login
        raise _err(403, "tenant_inactive", "Organizzazione non attiva")
    if status == "suspended" and not allow_suspended:
        raise _err(403, "tenant_suspended", SUSPENDED_MESSAGE)
    return status


_firebase_app = None


def firebase_app():
    global _firebase_app
    import firebase_admin

    if _firebase_app is None:
        _firebase_app = firebase_admin.get_app() if firebase_admin._apps else firebase_admin.initialize_app(
            options={"projectId": get_settings().firebase_project_id}
        )
    return _firebase_app


def _verify_firebase_token(token: str) -> dict:
    from firebase_admin import auth as fb_auth

    return fb_auth.verify_id_token(token, app=firebase_app())


def env_claims(claims: dict | None) -> dict:
    """P-67 (D-136): one Firebase Auth for both environments, so tenant and role are kept per environment in the custom
    claims, {"prod": {"tenant_id", "role"}, "staging": {...}}, and each BFF reads only its own (APP_ENV). The old flat
    claims (tenant_id, role at the top, before P-67) still count outside staging, until scripts/set_claims.py rewrites
    them: a staging-only account is refused in production, a production-only one in staging."""
    from .config import get_settings
    claims = claims or {}
    env = get_settings().app_env
    own = claims.get(env)
    if isinstance(own, dict):
        return own
    if env != "staging" and claims.get("tenant_id"):
        return {"tenant_id": claims.get("tenant_id"), "role": claims.get("role")}
    return {}


async def _from_claims(repo, claims: dict, allow_suspended: bool = False) -> CurrentUser:
    """Custom claims (tenant_id, role) are the source of truth; an invited user without claims yet is
    recognised by email and its `inv-*` record is migrated to the real uid on first login."""
    uid, email = claims["uid"], (claims.get("email") or "").lower()
    stored = await repo.get_user(uid)
    if stored is None and email:
        invited = await repo.get_user_by_email(email)
        if invited and invited.uid.startswith("inv-"):
            # The invite is bound to the mailbox: without a verified email anyone could register that address
            # first and take the invitation. Google sign-in and the password link of the invitation verify it.
            if not claims.get("email_verified"):
                raise _err(403, "email_not_verified", "Conferma il tuo indirizzo email per completare l'accesso")
            stored = invited.model_copy(update={"uid": uid, "former_emails": [invited.email]})   # D-91 (F3)
            await repo.upsert_user(stored)
            await repo.delete_user(invited.uid)
    own = env_claims(claims)                     # P-67: this environment's tenant and role only
    tenant_id, role = own.get("tenant_id"), own.get("role")
    if (not tenant_id or role not in ROLES) and stored:
        tenant_id, role = stored.tenant_id, stored.role
    if not tenant_id or role not in ROLES:
        raise _err(403, "forbidden", "Account non abilitato: mancano tenant o ruolo")
    # before any record is created: an inactive or suspended organisation gains nothing from a sign-in (P-50)
    await _tenant_gate(repo, tenant_id, allow_suspended)
    if stored is None:
        # Account enabled by custom claims only (e.g. the first admin from scripts/set_claims.py): give it an app
        # record so it appears in the admin area and can keep a display name and notification preferences.
        stored = await repo.upsert_user(User(uid=uid, email=email, display_name=claims.get("name", "") or "",
                                             tenant_id=tenant_id, role=role))
    if (stored.tenant_id != tenant_id or stored.role != role) and own.get("tenant_id"):
        stored.tenant_id, stored.role = tenant_id, role
        await repo.upsert_user(stored)
    if email and stored.email != email:  # email changed in Firebase (verifyBeforeUpdateEmail)
        # L6 (D-70): an email maps to one uid only. If another record already has it (an invite or a user in another
        # organisation), do not adopt it, or two records would share an email and a delete-by-email could hit the wrong
        # account. The record keeps its previous email; access still works by uid.
        clash = await repo.get_user_by_email(email)
        if clash is None or clash.uid == uid:
            if stored.email not in stored.former_emails:   # D-91 (F3): the previous address is erased with the person
                stored.former_emails = [*stored.former_emails, stored.email]
            stored.email = email
            await repo.upsert_user(stored)
        else:
            warn("auth: email change not adopted, already used by another account", uid=uid)
            email = stored.email
    return CurrentUser(uid=uid, email=email, tenant_id=tenant_id, role=role,
                       display_name=(stored.display_name if stored else claims.get("name", "")) or "",
                       apartment_ids=stored.apartment_ids, issued_at=float(claims.get("iat", 0)))


async def _verified_claims(request: Request) -> dict:
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else None
    if not token:
        raise _err(401, "unauthorized", "Accesso richiesto")
    try:
        claims = _verify_firebase_token(token)
    except Exception:
        raise _err(401, "unauthorized", "Sessione non valida o scaduta")
    if await asyncio.to_thread(accounts.token_revoked, claims["uid"], float(claims.get("iat", 0))):
        raise _err(401, "unauthorized", "Sessione non valida o scaduta")
    return claims


async def _caller(request: Request) -> tuple[str, str, bool, str, float]:
    """(uid, email, email verified, name, token iat) of whoever is calling, without any organisation."""
    if get_settings().auth_mode == "dev":
        email = (request.headers.get("X-Dev-User") or "").lower()
        if not email:
            raise _err(401, "unauthorized", "Accesso richiesto")
        stored = await get_repository().get_user_by_email(email)
        return (stored.uid if stored else f"dev-{email}"), email, True, (stored.display_name if stored else ""), 0.0
    claims = await _verified_claims(request)
    return (claims["uid"], (claims.get("email") or "").lower(), bool(claims.get("email_verified")),
            claims.get("name", "") or "", float(claims.get("iat", 0)))


async def _support_user(request: Request, tenant_id: str) -> CurrentUser:
    """P-50 (D-86): the caller must be a platform manager with an access to this organisation that THEY opened and that
    is still open; re-read on every request. Any other case is support_expired, so the PWA leaves the organisation."""
    from . import support

    uid, email, verified, name, iat = await _caller(request)
    access = await support.active_for(tenant_id, uid)
    if access is None or not await _is_platform_member(email, verified, name):
        raise _err(403, "support_expired", SUPPORT_EXPIRED)
    await _tenant_gate(get_repository(), tenant_id)
    # D-189: the manager's current name (the managers' list, D-178, or the account's); the copy taken when the access was
    # opened stays in the access for the log, and is used only when there is no other
    member = await get_repository().get_platform_member(normalize_email(email))
    current = (member.display_name if member is not None and member.display_name else name) or access.operator_name
    return CurrentUser(uid=uid, email=email, tenant_id=tenant_id, role="operator", display_name=current,
                       apartment_ids=None, issued_at=iat, support_access_id=access.access_id,
                       support_expires_at=access.expires_at)


def _support_tenant(request: Request) -> str:
    return (request.headers.get(SUPPORT_HEADER) or "").strip()


async def resolve_user(request: Request) -> CurrentUser:
    """Every organisation route: a member of a tenant, or a platform manager inside it through a support access
    (X-Support-Tenant, P-50). The platform role alone plays no part here (P-36)."""
    tenant_id = _support_tenant(request)
    current = await _support_user(request, tenant_id) if tenant_id else await _member(request)
    ctx_user.set(current.uid)
    ctx_tenant.set(current.tenant_id)
    return current


async def resolve_own_user(request: Request) -> CurrentUser:
    """The person's own account (profile, sessions, deletion, push and preferences): X-Support-Tenant is ignored, so
    nothing is ever tied to an organisation being assisted."""
    current = await _member(request)
    ctx_user.set(current.uid)
    ctx_tenant.set(current.tenant_id)
    return current


async def _member(request: Request) -> CurrentUser:
    settings = get_settings()
    repo = get_repository()
    if settings.auth_mode == "dev":
        email = request.headers.get("X-Dev-User")
        if not email:
            raise _err(401, "unauthorized", "Accesso richiesto")
        user: User | None = await repo.get_user_by_email(email)
        if not user:
            raise _err(401, "unauthorized", "Utente di sviluppo sconosciuto")
        await _tenant_gate(repo, user.tenant_id)   # same gate as in production (P-50)
        current = CurrentUser(user.uid, user.email, user.tenant_id, user.role, user.display_name, user.apartment_ids)
    else:
        current = await _from_claims(repo, await _verified_claims(request))
    return current   # the callers set the log context: the uid, never the email (P-48, C-4)


@dataclass
class Identity:
    """Who is calling, for /app/me and /app/platform/*: the organisation membership (None if the person has none) and the
    platform role, kept apart so that one never widens the other."""
    uid: str
    email: str
    display_name: str
    user: CurrentUser | None
    platform_manager: bool
    tenant_suspended: bool = False   # only for a platform manager whose own organisation is suspended (P-50)
    support_access_id: str | None = None   # /app/me inside an organisation through a support access (P-50)


async def _is_platform_member(email: str, verified: bool, display_name: str) -> bool:
    # bound to the mailbox, like invitations: an unverified address could be registered by anyone
    if not email or not verified:
        return False
    repo = get_repository()
    member = await repo.get_platform_member(normalize_email(email))
    if member is None:
        return False
    if member.first_seen_at is None:  # "active" in the managers list; one write per person, ever
        from .repository.base import now_iso

        member.first_seen_at, member.display_name = now_iso(), display_name or member.display_name
        await repo.add_platform_member(member)
    return True


async def resolve_identity(request: Request) -> Identity:
    """/app/me: with X-Support-Tenant, the manager inside the assisted organisation (P-50)."""
    if tenant_id := _support_tenant(request):
        user = await _support_user(request, tenant_id)
        ctx_user.set(user.uid)
        ctx_tenant.set(tenant_id)
        return Identity(uid=user.uid, email=user.email, display_name=user.display_name, user=user, platform_manager=True,
                        support_access_id=user.support_access_id)
    return await _identity(request)


async def resolve_own_identity(request: Request) -> Identity:
    """DELETE /app/me (P-48, Fable note 4): the person whoever they are, a member or a platform manager without an
    organisation, also when their organisation is suspended (erasing one's own data is never refused for that).
    X-Support-Tenant is ignored, like on every own-account route."""
    return await _identity(request, allow_suspended=True)


async def _identity(request: Request, allow_suspended: bool = False) -> Identity:
    settings = get_settings()
    repo = get_repository()
    if settings.auth_mode == "dev":
        email = (request.headers.get("X-Dev-User") or "").lower()
        if not email:
            raise _err(401, "unauthorized", "Accesso richiesto")
        stored = await repo.get_user_by_email(email)
        user = CurrentUser(stored.uid, stored.email, stored.tenant_id, stored.role, stored.display_name,
                           stored.apartment_ids) if stored else None
        if user is not None:
            await _tenant_gate(repo, user.tenant_id, allow_suspended=True)
        uid, name, verified = (stored.uid if stored else f"dev-{email}"), (stored.display_name if stored else ""), True
    else:
        claims = await _verified_claims(request)
        email, uid, verified = (claims.get("email") or "").lower(), claims["uid"], bool(claims.get("email_verified"))
        try:
            user = await _from_claims(repo, claims, allow_suspended=True)
        except HTTPException as exc:
            if exc.detail.get("error") != "forbidden":  # unverified invitation, inactive tenant: same answer as resolve_user
                raise
            user = None
        name = (user.display_name if user else claims.get("name", "")) or ""
    platform = await _is_platform_member(email, verified, name)
    if user is None and platform:                 # D-178: the name saved in the managers' list
        member = await repo.get_platform_member(normalize_email(email))
        if member is not None and member.display_name:
            name = member.display_name
    if user is None and not platform:
        if settings.auth_mode == "dev":
            raise _err(401, "unauthorized", "Utente di sviluppo sconosciuto")
        raise _err(403, "forbidden", "Account non abilitato: mancano tenant o ruolo")
    suspended = user is not None and await tenant_status(repo, user.tenant_id) == "suspended"
    if suspended and not platform and not allow_suspended:
        raise _err(403, "tenant_suspended", SUSPENDED_MESSAGE)
    # a manager of a suspended organisation keeps /app/me (with suspended: true) and the platform, to reactivate it;
    # every organisation route still refuses them through resolve_user
    ctx_user.set(uid)
    ctx_tenant.set(user.tenant_id if user else None)
    return Identity(uid=uid, email=email, display_name=name, user=user, platform_manager=platform,
                    tenant_suspended=suspended)


async def require_platform(request: Request) -> Identity:
    identity = await _identity(request)   # X-Support-Tenant plays no part in the platform area
    if not identity.platform_manager:
        raise _err(403, "forbidden", "Operazione riservata ai gestori della piattaforma")
    return identity


async def require_admin(request: Request) -> CurrentUser:
    user = await resolve_user(request)
    if not user.is_admin:
        raise _err(403, "forbidden", "Operazione riservata agli amministratori")
    return user


def scope_out(apartment_ids: list[str] | None, role: str) -> str | list[str]:
    """API form of a user's apartments (D-43): "all" or a list, never null. Admins are always "all"."""
    return "all" if role == "admin" or apartment_ids is None else list(apartment_ids)


async def still_sees(user: CurrentUser, apartment_id: str) -> bool:
    """Re-reads the app record: for long-lived requests (the SSE stream) after an admin changed the user's role or
    apartments, or removed the user (F3, D-70). Both role and apartments come from the record, not the request claims:
    an invited user (no claims) demoted to viewer with no apartments must stop seeing the stream."""
    repo = get_repository()
    if user.support_access_id:
        return await _support_still_open(repo, user)
    stored = await repo.get_user(user.uid)
    if stored is None or stored.tenant_id != user.tenant_id:
        return False
    if await tenant_status(repo, user.tenant_id) != "active":   # P-50: a suspension closes open streams too
        return False
    # P-36 point 10: "Esci da tutti i dispositivi" (or a role change) revokes the sessions; an open stream must end too
    if user.issued_at and await asyncio.to_thread(accounts.token_revoked, user.uid, user.issued_at):
        return False
    return dataclasses.replace(user, role=stored.role, apartment_ids=stored.apartment_ids).can_see(apartment_id)


async def _support_still_open(repo, user: CurrentUser) -> bool:
    """A support stream: the access still open (not closed by the admin, not expired), the person still a manager,
    the organisation active and the session not revoked."""
    from . import support

    a = await repo.get_support_access(user.support_access_id)
    if a is None or a.operator_uid != user.uid or support.status(a) != "active":
        return False
    if await tenant_status(repo, user.tenant_id) != "active" or await repo.get_platform_member(user.email) is None:
        return False
    return not (user.issued_at and await asyncio.to_thread(accounts.token_revoked, user.uid, user.issued_at))


async def get_tenant_apartment(user: CurrentUser, apartment_id: str):
    """Single gate of every /app/apartments/{id}/... route: another tenant's apartment and one outside the user's list
    (P-18) get the same 404, so the answer does not reveal that the apartment exists."""
    apt = await get_repository().get_apartment(apartment_id)
    if not apt or apt.tenant_id != user.tenant_id or not user.can_see(apt.apartment_id):
        raise _err(404, "not_found", "Appartamento inesistente")
    return apt
