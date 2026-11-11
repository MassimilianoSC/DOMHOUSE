"""Sets Firebase custom claims (tenant_id, role) for a user, creating the account if needed.

Usage (ADC or GOOGLE_APPLICATION_CREDENTIALS must point at the Firebase project):
  python scripts/set_claims.py --email nome@azienda.it --tenant t-flatsharing-demo --role operator
  python scripts/set_claims.py --email nome@azienda.it --tenant t-flatsharing-demo --role admin --create --send-reset-link
  python scripts/set_claims.py --from-repo            # all invited (inv-*) users of the configured REPOSITORY
  REPOSITORY=firestore GCP_PROJECT_ID=<project> python scripts/set_claims.py --tenant t-flatsharing-demo --tenant-name "Flatsharing"

The BFF reads the claims from the ID token; the user must sign out/in (or refresh the token) to pick them up.
P-67 (D-136): one Firebase Auth for production and staging, so the claims are per environment, {"prod": {tenant_id,
role}, "staging": {...}}: --env prod (default) or --env staging writes only that one and keeps the other. In staging no
session is revoked (it would sign the person out of production too). The flat claims of before P-67 are rewritten:
  python scripts/set_claims.py --migrate-claims            # says what would change
  python scripts/set_claims.py --migrate-claims --apply    # adds {"prod": {...}} next to the flat tenant_id/role
The flat claims are never removed: the production BFF of before P-67 reads only those, so the commands can run in any
order, also before the new BFF is published (which reads the per-environment ones first, and staging never the flat).
--tenant-name only creates or renames the tenant record in the repository: no claims, no session revoked.
  REPOSITORY=firestore GCP_PROJECT_ID=<project> python scripts/set_claims.py --platform-add persona@esempio.it
  REPOSITORY=firestore GCP_PROJECT_ID=<project> python scripts/set_claims.py --platform-list
--platform-add gives the platform manager role (P-36, D-62), matched with the verified email at sign-in; then the role
is managed from the app. No claims, no session revoked.
R4-1 (P-83): before 82759e9 a person removed by an administrator kept the claims, and came back at the next sign-in.
--orphan-claims lists, READ ONLY, the accounts whose claims of this environment name an organisation where they have
no record (nor an invitation waiting): the people removed before the fix, and also anyone enabled with --create who
never signed in (legitimate: the committente chooses name by name). --apply --email removes this environment's claims
of ONE of them (and revokes its sessions in production, so a token already issued cannot use them for its last hour):
  REPOSITORY=firestore GCP_PROJECT_ID=<project> python scripts/set_claims.py --orphan-claims
  REPOSITORY=firestore GCP_PROJECT_ID=<project> python scripts/set_claims.py --orphan-claims --apply --email <email>
  ... FIRESTORE_DATABASE=staging ... --orphan-claims --env staging     # the staging database with --env staging
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import firebase_admin
from firebase_admin import auth

ROLES = ("admin", "operator", "viewer")
ENVS = ("prod", "staging")


def env_claims_after(current: dict | None, env: str, tenant_id: str, role: str) -> dict:
    """The custom claims with this environment's tenant and role, the other environment kept. The flat claims of before
    P-67 are KEPT (the production BFF of before P-67 reads only those: no one loses access whatever the order of the
    commands) and copied as production's when there is none."""
    claims = dict(current or {})
    if claims.get("tenant_id") and "prod" not in claims:
        claims["prod"] = {"tenant_id": claims["tenant_id"], "role": claims.get("role")}
    claims[env] = {"tenant_id": tenant_id, "role": role}
    if env == "prod" and claims.get("tenant_id"):        # the old BFF keeps reading the same production role
        claims["tenant_id"], claims["role"] = tenant_id, role
    return claims


def migrated(current: dict | None) -> dict | None:
    """The claims with production's copy of the flat ones next to them (the flat ones stay, for the BFF of before
    P-67), or None when there is nothing to add."""
    claims = dict(current or {})
    if not claims.get("tenant_id") or isinstance(claims.get("prod"), dict):
        return None
    claims["prod"] = {"tenant_id": claims["tenant_id"], "role": claims.get("role")}
    return claims


def own_claims(claims: dict | None, env: str) -> dict:
    """This environment's {tenant_id, role}, as the BFF reads them (bff.auth.env_claims): its own key, and outside
    staging the flat ones of before P-67."""
    claims = claims or {}
    if isinstance(claims.get(env), dict):
        return claims[env]
    if env != "staging" and claims.get("tenant_id"):
        return {"tenant_id": claims.get("tenant_id"), "role": claims.get("role")}
    return {}


async def orphans(repo, accounts_list, env: str) -> list[tuple]:
    """(account, tenant_id, role, record or None) for every account whose claims of env name an organisation where it
    has no record and no invitation waiting."""
    found = []
    for u in accounts_list:
        own = own_claims(u.custom_claims, env)
        tenant_id = own.get("tenant_id")
        if not tenant_id:
            continue
        record = await repo.get_user(u.uid)
        if record is not None and record.tenant_id == tenant_id:
            continue
        invited = await repo.get_user_by_email(u.email) if u.email else None
        if invited is not None and invited.uid.startswith("inv-") and invited.tenant_id == tenant_id:
            continue                                        # an invitation waiting there: the claims will be used
        found.append((u, tenant_id, own.get("role"), record))
    return found


def orphan_command(env: str, apply: bool, email: str | None) -> int:
    repo = _firestore_repository("--orphan-claims")
    from bff.config import get_settings
    database = get_settings().firestore_database
    if (env == "staging") != (database == "staging"):
        raise SystemExit(f"--env {env} con il database «{database}»: per lo staging FIRESTORE_DATABASE=staging e "
                         "--env staging, per la produzione nessuno dei due")
    if apply and not email:
        raise SystemExit("--apply vuole --email: una persona alla volta, fra quelle dell'elenco")
    init()
    accounts_list = list(auth.list_users().iterate_all())

    async def go():
        return await orphans(repo, accounts_list, env)
    found = asyncio.run(go())
    if not apply:
        for u, tenant_id, role, record in found:
            where = "nessun record" if record is None else f"record in un'altra organizzazione ({record.tenant_id})"
            print(f"{u.email or u.uid}: claim {env} -> {tenant_id} {role}; {where}")
        print(f"{len(found)} account con claim senza record in quella organizzazione (niente scritto)")
        return len(found)
    target = next((f for f in found if (f[0].email or "").lower() == email.strip().lower()), None)
    if target is None:
        raise SystemExit(f"{email} non è nell'elenco di --orphan-claims: non tocco niente")
    from bff.accounts import without_env_claims
    u, tenant_id = target[0], target[1]
    left = without_env_claims(u.custom_claims, env, tenant_id) or {}
    auth.set_custom_user_claims(u.uid, left)
    if env != "staging":
        auth.revoke_refresh_tokens(u.uid)
    print(f"{u.email}: claim {env} di {tenant_id} tolti" + ("" if env == "staging" else ", sessioni revocate"))
    return 1


def init() -> None:
    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": os.environ.get("FIREBASE_PROJECT_ID") or None})


def set_claims(email: str, tenant_id: str, role: str, create: bool, send_reset_link: bool, env: str = "prod") -> str:
    if role not in ROLES:
        raise SystemExit(f"role must be one of {ROLES}")
    if env not in ENVS:
        raise SystemExit(f"env must be one of {ENVS}")
    try:
        user = auth.get_user_by_email(email)
    except auth.UserNotFoundError:
        if not create:
            raise SystemExit(f"{email}: user not found in Firebase Auth (use --create)")
        user = auth.create_user(email=email, email_verified=False)
    auth.set_custom_user_claims(user.uid, env_claims_after(user.custom_claims, env, tenant_id, role))
    if env == "prod":
        auth.revoke_refresh_tokens(user.uid)
    print(f"{email}: uid={user.uid} env={env} tenant_id={tenant_id} role={role}")
    if send_reset_link:
        print(f"  password setup link: {auth.generate_password_reset_link(email)}")
    return user.uid


def migrate_claims(apply: bool) -> int:
    """Every account with the flat claims of before P-67 gets them as production's; prints each one."""
    changed = 0
    for user in auth.list_users().iterate_all():
        new = migrated(user.custom_claims)
        if new is None:
            continue
        changed += 1
        print(f"{user.email or user.uid}: {user.custom_claims} -> {new}" + ("" if apply else "  (prova, niente scritto)"))
        if apply:
            auth.set_custom_user_claims(user.uid, new)
    print(f"{changed} account {'riscritti' if apply else 'da riscrivere (aggiungi --apply)'}")
    return changed


async def from_repo(create: bool, send_reset_link: bool, env: str = "prod") -> None:
    from bff.repository import get_repository

    repo = get_repository()
    for tenant in await repo.list_tenants():
        for u in await repo.list_users(tenant.tenant_id):
            if u.uid.startswith("inv-"):
                set_claims(u.email, u.tenant_id, u.role, create, send_reset_link, env)


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
    p.add_argument("--env", choices=ENVS, default="prod", help="the environment of the claims (P-67), prod by default")
    p.add_argument("--migrate-claims", action="store_true", help="rewrite the flat claims per environment (P-67)")
    p.add_argument("--apply", action="store_true", help="with --migrate-claims or --orphan-claims: write (without: only show)")
    p.add_argument("--orphan-claims", action="store_true", help="R4-1: claims naming an organisation without the record")
    a = p.parse_args()
    if a.orphan_claims:
        if a.tenant or a.role or a.from_repo or a.migrate_claims or a.tenant_name is not None or a.platform_add:
            p.error("--orphan-claims va usato solo con --env, --apply e --email")
        orphan_command(a.env, a.apply, a.email)
        return
    if a.migrate_claims:
        init()
        migrate_claims(a.apply)
        return
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
        asyncio.run(from_repo(a.create, a.send_reset_link, a.env))
    elif a.email and a.tenant and a.role:
        set_claims(a.email, a.tenant, a.role, a.create, a.send_reset_link, a.env)
    else:
        p.error("--email, --tenant and --role are required (or --from-repo)")


if __name__ == "__main__":
    main()
