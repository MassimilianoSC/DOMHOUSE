"""Administrative log (P-47): who invited, changed a role, changed an apartment, created or renamed an organisation,
added a manager… One log per organisation (tenants/{tid}/audit) and one for platform-level actions.

Entries keep no email or name: people are referenced by a key into audit_people, written with the entry and resolved
when the log is read. Erasing a person's own account (P-48) removes that one record, and every entry about them then
reads «utente rimosso» (removed: true) without rewriting the log.

Writing is best effort and comes AFTER the action: an action already done is never undone because its log entry could
not be written; the failure is logged instead.
"""
import hashlib
import itertools
import uuid
from dataclasses import dataclass, field

from .logs import warn
from .repository import AuditActor, AuditEntry, AuditPerson, AuditTarget, User, get_repository, normalize_email
from .repository.base import AUDIT_PAGE_MAX, AuditAction, now_iso


@dataclass
class Who:
    actor: AuditActor
    people: list[AuditPerson] = field(default_factory=list)


SYSTEM = Who(AuditActor(kind="system"))
_SEQ = itertools.count()


def by_user(user) -> Who:
    """A member of the organisation acting in it (CurrentUser), or a platform manager inside it through a support access
    (P-50): then "support", with the real person."""
    person = [AuditPerson(ref=user.uid, email=user.email, display_name=user.display_name)]
    if getattr(user, "support_access_id", None):
        return Who(AuditActor(kind="support", ref=user.uid, support_access_id=user.support_access_id), person)
    return Who(AuditActor(kind="user", ref=user.uid, role=user.role), person)


def by_platform(identity) -> Who:
    """A platform manager (Identity)."""
    return Who(AuditActor(kind="platform", ref=identity.uid),
               [AuditPerson(ref=identity.uid, email=identity.email, display_name=identity.display_name)])


def manager_ref(email: str) -> str:
    """Key of a platform manager as a TARGET: managers are known by email only, and the entry must not store it."""
    return "mgr-" + hashlib.sha256(normalize_email(email).encode()).hexdigest()[:16]


def user_target(u: User) -> tuple[AuditTarget, AuditPerson]:
    return (AuditTarget(type="user", id=u.uid, ref=u.uid, role=u.role),
            AuditPerson(ref=u.uid, email=u.email, display_name=u.display_name))


def manager_target(email: str) -> tuple[AuditTarget, AuditPerson]:
    ref = manager_ref(email)
    return AuditTarget(type="manager", id=ref, ref=ref), AuditPerson(ref=ref, email=normalize_email(email))


def apartment_target(apartment_id: str, name: str) -> AuditTarget:
    return AuditTarget(type="apartment", id=apartment_id, label=name)


def tenant_target(tenant_id: str, name: str) -> AuditTarget:
    return AuditTarget(type="tenant", id=tenant_id, label=name)


async def record(action: AuditAction, who: Who, tenant_id: str | None, target: AuditTarget | tuple[AuditTarget, AuditPerson],
                 strict: bool = False, **details) -> None:
    """strict: the action depends on its trace (opening a support access): a failed write raises instead of warning."""
    people = list(who.people)
    if isinstance(target, tuple):
        target, person = target
        people.append(person)
    try:
        repo = get_repository()
        for p in people:
            await repo.put_audit_person(p)
        at = now_iso()
        # the process counter keeps entries written in the same millisecond in order (one BFF instance, D-35); the
        # random part keeps ids unique across instances
        audit_id = f"{at}-{next(_SEQ) % 1_000_000:06d}{uuid.uuid4().hex[:4]}"
        await repo.add_audit(AuditEntry(audit_id=audit_id, at=at, tenant_id=tenant_id,
                                        action=action, actor=who.actor, target=target, details=details))
    except Exception as exc:
        if strict:
            raise
        warn("audit: entry not written", action=action, error=str(exc))


async def forget(uid: str, email: str) -> None:
    """The person's own account is gone (P-48): every key that pointed to them goes, so the log reads «utente rimosso»
    as actor and as target (their uid, the invitation they came from, their manager role)."""
    from .invites import invite_uid

    repo = get_repository()
    for ref in (uid, invite_uid(email), manager_ref(email)):
        try:
            await repo.delete_audit_person(ref)
        except Exception as exc:
            warn("audit: person not forgotten", error=str(exc))


async def _present(tenant_id: str) -> set[str]:
    """Keys of the people who still belong to the organisation: their uid and the invitations they came from."""
    from .invites import invite_uid

    users = await get_repository().list_users(tenant_id)
    return {u.uid for u in users} | {invite_uid(e) for u in users for e in (u.email, *u.former_emails)}


def _actor_out(a: AuditActor, people: dict[str, AuditPerson], viewer: str) -> dict:
    """viewer: "admin" (the organisation), "platform" (an organisation's log seen by HQE: roles, never its people,
    D-90), "platform_scope" (the platform's own log: managers)."""
    if a.kind == "system" or (a.kind == "platform" and viewer == "admin"):
        # an organisation sees "the platform (HQE)", not which manager; support access shows the real person (P-50)
        return {"kind": a.kind, "email": None, "display_name": None, "removed": False, "role": None}
    p = people.get(a.ref or "")
    if a.kind == "user" and viewer == "platform":
        return {"kind": a.kind, "email": None, "display_name": None, "removed": p is None, "role": a.role}
    return {"kind": a.kind, "email": p.email if p else None, "display_name": (p.display_name or None) if p else None,
            "removed": p is None, "role": a.role}


def _target_out(t: AuditTarget, people: dict[str, AuditPerson], viewer: str) -> dict:
    if t.ref is None:
        return {"type": t.type, "id": t.id, "label": t.label, "removed": False, "role": None}
    p = people.get(t.ref)
    hidden = t.type == "user" and viewer == "platform"
    return {"type": t.type, "id": t.id, "label": p.email if p and not hidden else None, "removed": p is None,
            "role": t.role}


async def page(tenant_id: str | None, limit: int, before: str | None, viewer: str) -> dict:
    """{items, next}: newest first; `next` is the cursor for the following page, None at the end."""
    repo = get_repository()
    limit = max(1, min(limit, AUDIT_PAGE_MAX))
    entries = await repo.list_audit(tenant_id, limit + 1, before)
    more, entries = len(entries) > limit, entries[:limit]
    people = await repo.get_audit_people([r for e in entries for r in (e.actor.ref, e.target.ref) if r])
    if tenant_id is not None:
        # D-91: a person no longer in the organisation reads «utente rimosso» (as in the decisions, bff/actors.py);
        # HQE people (platform, support) stay readable
        present = await _present(tenant_id)
        gone = {e.actor.ref for e in entries if e.actor.kind == "user" and e.actor.ref not in present}
        gone |= {e.target.ref for e in entries if e.target.type == "user" and e.target.ref not in present}
        people = {k: v for k, v in people.items() if k not in gone}
    if viewer == "platform" and tenant_id is None:
        viewer = "platform_scope"   # the platform's own log: managers are HQE people, shown
    items = [{"audit_id": e.audit_id, "at": e.at, "action": e.action, "actor": _actor_out(e.actor, people, viewer),
              "target": _target_out(e.target, people, viewer), "details": e.details}
             for e in entries]
    return {"items": items, "next": entries[-1].audit_id if more and entries else None}
