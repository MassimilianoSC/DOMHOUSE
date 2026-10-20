"""Sets Firebase custom claims (tenant_id, role) for a user, creating the account if needed.

Usage (ADC or GOOGLE_APPLICATION_CREDENTIALS must point at the Firebase project):
  python scripts/set_claims.py --email nome@azienda.it --tenant t-flatsharing-demo --role operator
  python scripts/set_claims.py --email nome@azienda.it --tenant t-flatsharing-demo --role admin --create --send-reset-link
  python scripts/set_claims.py --from-repo            # all invited (inv-*) users of the configured REPOSITORY
  REPOSITORY=firestore GCP_PROJECT_ID=<project> python scripts/set_claims.py --tenant t-flatsharing-demo --tenant-name "Flatsharing"

The BFF reads the claims from the ID token; the user must sign out/in (or refresh the token) to pick them up.
--tenant-name only creates or renames the tenant record in the repository: no claims, no session revoked.
  REPOSITORY=firestore GCP_PROJECT_ID=<project> python scripts/set_claims.py --platform-add persona@esempio.it
  REPOSITORY=firestore GCP_PROJECT_ID=<project> python scripts/set_claims.py --platform-list
--platform-add gives the platform manager role (P-36, D-62), matched with the verified email at sign-in; then the role
is managed from the app. No claims, no session revoked.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import firebase_admin
from firebase_admin import auth

ROLES = ("admin", "operator", "viewer")


def init() -> None:
    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": os.environ.get("FIREBASE_PROJECT_ID") or None})


def set_claims(email: str, tenant_id: str, role: str, create: bool, send_reset_link: bool) -> str:
    if role not in ROLES:
        raise SystemExit(f"role must be one of {ROLES}")
    try:
        user = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        if not create:
            raise SystemExit(f"{email}: user not found in Firebase Auth (use --create)")
        user = auth.create_user(email=email, email_verified=False)
    auth.set_custom_user_claims(user.uid, {"tenant_id": tenant_id, "role": role})
    auth.revoke_refresh_tokens(user.uid)
    print(f"{email}: uid={user.uid} tenant_id={tenant_id} role={role}")
    if send_reset_link:
        print(f"  password setup link: {auth.generate_password_reset_link(email)}")
    return user.uid


async def from_repo(create: bool, send_reset_link: bool) -> None:
    from bff.repository import get_repository

    repo = get_repository()
    for tenant in await repo.list_tenants():
        for u in await repo.list_users(tenant.tenant_id):
            if u.uid.startswith("inv-"):
                set_claims(u.email, u.tenant_id, u.role, create, send_reset_link)


async def set_tenant_name(repo, tenant_id: str, name: str) -> str:
    """Creates the tenant record if missing (as the BFF does at first login) and sets its name; returns the old one."""
    from bff.repository import Tenant

    name = name.strip()
    if not 1 <= len(name) <= 120:  # same limits as PATCH /app/admin/tenant
        raise SystemExit("--tenant-name: da 1 a 120 caratteri")
    from bff import audit

    t = await repo.get_tenant(tenant_id)
    old = t.name if t else None
    t = t or Tenant(tenant_id=tenant_id, name=name)
    t.name = name
    await repo.upsert_tenant(t)
    target = audit.tenant_target(tenant_id, name)
    if old is None:
        await audit.record("tenant_created", audit.SYSTEM, tenant_id, target)
    elif old != name:
        await audit.record("tenant_renamed", audit.SYSTEM, tenant_id, target, **{"from": old, "to": name})
    return old


def _firestore_repository(option: str):
    from bff.config import get_settings
    from bff.repository import get_repository

    if get_settings().repository != "firestore":
        # with the default memory repository the change would vanish when the script ends
        raise SystemExit(f"{option} usa il repository Firestore: lancialo con REPOSITORY=firestore GCP_PROJECT_ID=<progetto>")
    return get_repository()


async def platform_add(repo, email: str) -> bool:
    """Adds a platform manager; returns False if the email already had the role."""
    from bff.repository import PlatformMember, normalize_email

    email = normalize_email(email)
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise SystemExit("--platform-add: email non valida")
    if await repo.get_platform_member(email):
        return False
    from bff import audit

    await repo.add_platform_member(PlatformMember(email=email, added_by="scripts/set_claims.py"))
    await audit.record("manager_added", audit.SYSTEM, None, audit.manager_target(email))
    return True


def platform_command(add: str | None) -> None:
    repo = _firestore_repository("--platform-add" if add else "--platform-list")

    async def go():
        # one event loop for the whole command: the async Firestore client is bound to the loop of its first call, so a
        # second asyncio.run fails with "Event loop is closed" (D-76)
        return (await platform_add(repo, add) if add else None), await repo.list_platform_members()

    added, members = asyncio.run(go())
    if add:
        print(f"{add.strip().lower()}: {'ruolo di gestore della piattaforma assegnato' if added else 'aveva già il ruolo'}")
    for m in members:
        print(f"gestore: {m.email} (aggiunto da {m.added_by or '?'} il {m.added_at[:10]})")


def tenant_name_command(tenant_id: str, name: str) -> None:
    from bff.repository import get_repository  # noqa: F401  (kept for the tests that patch it)

    repo = _firestore_repository("--tenant-name")
    old = asyncio.run(set_tenant_name(repo, tenant_id, name))
    # plain quotes: the Windows console of the person running it may not print «» correctly
    print(f"tenant {tenant_id}: nome {repr(old) if old is not None else '(record creato)'} -> {name.strip()!r}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--email")
    p.add_argument("--tenant")
    p.add_argument("--tenant-name", help="create or rename the tenant record (needs --tenant; claims untouched)")
    p.add_argument("--platform-add", metavar="EMAIL", help="give the platform manager role (claims untouched)")
    p.add_argument("--platform-list", action="store_true", help="list the platform managers")
    p.add_argument("--role", choices=ROLES)
    p.add_argument("--create", action="store_true", help="create the Firebase user if missing")
    p.add_argument("--send-reset-link", action="store_true", help="print a password setup link")
    p.add_argument("--from-repo", action="store_true", help="process every invited (inv-*) user in the repository")
    a = p.parse_args()
    if a.platform_add or a.platform_list:
        if a.email or a.tenant or a.role or a.from_repo or a.tenant_name is not None:
            p.error("--platform-add e --platform-list vanno usati da soli")
        platform_command(a.platform_add)
        return
    if a.tenant_name is not None:
        if not a.tenant or a.email or a.role or a.from_repo:
            p.error("--tenant-name va usato solo con --tenant")
        tenant_name_command(a.tenant, a.tenant_name)
        return
    init()
    if a.from_repo:
        asyncio.run(from_repo(a.create, a.send_reset_link))
    elif a.email and a.tenant and a.role:
        set_claims(a.email, a.tenant, a.role, a.create, a.send_reset_link)
    else:
        p.error("--email, --tenant and --role are required (or --from-repo)")


if __name__ == "__main__":
    main()
