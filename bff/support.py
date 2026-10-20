"""Support access (P-50, D-86): a platform manager (HQE) works inside an organisation for 1 to 24 hours with the rights of
an operator (no users, apartments or features), then the access closes by itself. The organisation's admins see it and
can close it; every opening, closing and expiry is in the organisation's log, with the operator's real identity.

The manager enters by sending X-Support-Tenant: <tenant_id> (auth.resolve_user); the access is re-read on every request
and the stream closes at the exact expiry. Nothing is ever written for the manager in the organisation: no user record,
no push token, no preferences (their own account routes ignore the header).
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from . import audit
from .logs import warn
from .repository import SupportAccess, get_repository, normalize_email
from .repository.base import AuditActor, AuditPerson, AuditTarget, now_iso

MAX_HOURS = 24
_locks: dict[tuple[int, str], asyncio.Lock] = {}


def _lock(key: str) -> asyncio.Lock:
    """One opening at a time per organisation and manager in this process (one BFF instance, D-35): a double click
    cannot open two accesses."""
    k = (id(asyncio.get_running_loop()), key)
    return _locks.setdefault(k, asyncio.Lock())


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def status(a: SupportAccess, now: str | None = None) -> str:
    if a.closed_at:
        return "closed"
    return "expired" if (now or now_iso()) >= a.expires_at else "active"


async def operators(accesses: list[SupportAccess]) -> dict[str, AuditPerson]:
    """D-88: who opened each access is read from the log's people (audit_people), so it disappears with the person's
    own account (audit.forget) like every other trace."""
    return await get_repository().get_audit_people([a.operator_uid for a in accesses])


def operator(a: SupportAccess, people: dict[str, AuditPerson]) -> tuple[str | None, str | None]:
    p = people.get(a.operator_uid)
    return (p.email, p.display_name) if p else (None, None)


def row(a: SupportAccess, people: dict[str, AuditPerson]) -> dict:
    email, name = operator(a, people)
    return {"access_id": a.access_id, "tenant_id": a.tenant_id, "operator_email": email, "operator_name": name,
            "reason": a.reason, "opened_at": a.opened_at, "expires_at": a.expires_at, "closed_at": a.closed_at,
            "status": status(a)}


async def rows(accesses: list[SupportAccess]) -> list[dict]:
    people = await operators(accesses)
    return [row(a, people) for a in accesses]


def by_operator(uid: str, email: str, display_name: str, access_id: str) -> audit.Who:
    """D-88: opening and closing by the manager are support actions, with the real person shown to the organisation."""
    return audit.Who(AuditActor(kind="support", ref=uid, support_access_id=access_id),
                     [AuditPerson(ref=uid, email=email, display_name=display_name)])


def target(a: SupportAccess, tenant_name: str) -> AuditTarget:
    return AuditTarget(type="support_access", id=a.access_id, label=tenant_name)


async def _tenant_name(tenant_id: str) -> str:
    t = await get_repository().get_tenant(tenant_id)
    return t.name if t else ""


async def note_expiry(a: SupportAccess) -> SupportAccess:
    """The first time the server sees an expired access, the log gets support_access_expired (no timer runs)."""
    if status(a) == "expired" and not a.expiry_logged:
        try:   # D-88: the entry first; only once it is written is the flag set, so a failed write is retried
            await audit.record("support_access_expired", audit.SYSTEM, a.tenant_id,
                               target(a, await _tenant_name(a.tenant_id)), strict=True)
        except Exception as exc:
            warn("support: expiry not logged yet", access_id=a.access_id, error=str(exc))
            return a
        return await get_repository().update_support_access(a.access_id, {"expiry_logged": True}) or a
    return a


async def listed(tenant_id: str | None = None, operator_uid: str | None = None) -> list[SupportAccess]:
    return [await note_expiry(a) for a in await get_repository().list_support_access(tenant_id, operator_uid)]


async def active_for(tenant_id: str, operator_uid: str) -> SupportAccess | None:
    for a in await listed(operator_uid=operator_uid):
        if a.tenant_id == tenant_id and status(a) == "active":
            return a
    return None


async def active_in(tenant_id: str) -> list[SupportAccess]:
    return [a for a in await listed(tenant_id=tenant_id) if status(a) == "active"]


async def open_access(tenant_id: str, tenant_name: str, identity, hours: int, reason: str) -> SupportAccess | None:
    """None when this manager already has an active access here. The log entry is written FIRST and must succeed:
    no access is ever open without its trace."""
    async with _lock(f"{tenant_id}:{identity.uid}"):
        if await active_for(tenant_id, identity.uid):
            return None
        opened = now_iso()
        expires = (parse(opened) + timedelta(hours=hours)).astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        a = SupportAccess(access_id="sa-" + uuid.uuid4().hex[:16], tenant_id=tenant_id, operator_uid=identity.uid,
                          operator_email=identity.email, operator_name=identity.display_name, reason=reason,
                          opened_at=opened, expires_at=expires)
        who = by_operator(identity.uid, identity.email, identity.display_name, a.access_id)
        await audit.record("support_access_opened", who, tenant_id, target(a, tenant_name),
                           strict=True, hours=hours, expires_at=expires, reason=reason)
        try:
            return await get_repository().add_support_access(a)
        except Exception:
            # D-91 (F4): the log already says "opened": it must also say that it never was
            warn("support: access logged as opened but not saved", access_id=a.access_id)
            await audit.record("support_access_closed", audit.SYSTEM, tenant_id, target(a, tenant_name), not_opened=True)
            raise


async def close(a: SupportAccess, who: audit.Who, by: str) -> bool:
    """False when it was no longer active (already closed or expired): nothing to do. Two closings at the same moment
    (the admin and the manager): only the one that really closed it writes the entry (D-88)."""
    if status(a) != "active":
        return False
    if not await get_repository().close_support_access(a.access_id, now_iso(), by):
        return False
    await audit.record("support_access_closed", who, a.tenant_id, target(a, await _tenant_name(a.tenant_id)))
    return True


async def close_all_of(who: audit.Who | None, uid: str | None = None, email: str | None = None) -> int:
    """D-88: a manager removed from the platform, or deleting their own account, leaves no access open. who=None: the
    manager closes them themselves, a support action in each organisation (D-91)."""
    email = normalize_email(email) if email else None
    closed = 0
    for a in await get_repository().list_support_access(operator_uid=uid):
        if (uid is None and normalize_email(a.operator_email) != email) or status(a) != "active":
            continue
        actor = who or by_operator(a.operator_uid, a.operator_email, a.operator_name, a.access_id)
        closed += await close(a, actor, "platform")
    return closed
