"""P-48 (D-87): what "Elimina il mio account" erases besides the user record and the Firebase account. Every place where
the BFF keeps a person's email or name, so that afterwards the person appears only as «utente rimosso»:

* the administrative log's people (audit_people) and the pseudonym towards the engine (actors);
* organisations: created_by (the manager who created it) and first_admin_email (the invited first admin);
* platform managers: added_by (who added them);
* support accesses opened by the person: operator email and name (the access itself, its times and reason stay).

Best effort per item: the account is already gone when this runs, so a failure is logged and the rest goes on.
"""
from . import actors, audit
from .logs import warn
from .repository import get_repository, normalize_email


async def erase_person(uid: str, email: str, former_emails: list[str] | tuple = ()) -> None:
    """former_emails (D-91, F3): the invitation's address and earlier ones, whose traces go too."""
    emails = list(dict.fromkeys(normalize_email(e) for e in (email, *former_emails) if e))
    repo = get_repository()
    steps = [("actors", actors.forget(uid)), ("support access", _support(repo, uid))]
    for e in emails:
        steps += [("audit", audit.forget(uid, e)), ("tenants", _tenants(repo, e)), ("managers", _managers(repo, e))]
    for name, step in steps:
        try:
            await step
        except Exception as exc:
            warn("erasure: step failed", step=name, error=str(exc))


async def _tenants(repo, email: str) -> None:
    for t in await repo.list_tenants():
        fields = {}
        if normalize_email(t.created_by or "") == email:
            fields["created_by"] = ""
        if normalize_email(t.first_admin_email or "") == email:
            fields["first_admin_email"] = None
        if fields:
            await repo.update_tenant(t.tenant_id, fields)


async def _managers(repo, email: str) -> None:
    for m in await repo.list_platform_members():
        if normalize_email(m.added_by or "") == email:
            m.added_by = ""
            await repo.add_platform_member(m)


async def _support(repo, uid: str) -> None:
    for a in await repo.list_support_access(operator_uid=uid):
        await repo.update_support_access(a.access_id, {"operator_email": "", "operator_name": ""})
