from .base import Apartment, ExternalIds, PlatformMember, Tenant, User
from .memory import InMemoryRepository

DEMO_TENANT = "t-flatsharing-demo"
OTHER_TENANT = "t-altra-demo"
MOCK_INSTANCE_URL = "mock://builtin"


def seed_demo(repo: InMemoryRepository) -> None:
    repo.tenants[DEMO_TENANT] = Tenant(tenant_id=DEMO_TENANT, name="Flatsharing demo", created_at="2026-10-01T08:00:00.000Z")
    users = [
        ("dev-admin", "admin@demo.it", "Amministratore demo", "admin"),
        ("dev-operator", "operatore@demo.it", "Operatore demo", "operator"),
        ("dev-viewer", "lettura@demo.it", "Utente in sola lettura", "viewer"),
        ("dev-owner", "m.cracchiolo@hqe.it", "Massimiliano Cracchiolo", "admin"),
    ]
    for uid, email, name, role in users:
        repo.users[uid] = User(uid=uid, email=email, display_name=name, tenant_id=DEMO_TENANT, role=role)
    # P-18: a viewer limited to one apartment, for local testing and the end-to-end suite
    repo.users["dev-proprietario"] = User(uid="dev-proprietario", email="proprietario@demo.it", display_name="Proprietario (solo Rimini)",
                                          tenant_id=DEMO_TENANT, role="viewer", apartment_ids=["apt-rimini-01"])
    # P-36: a second organisation, so isolation between tenants is tested on real data, not on missing ids
    repo.tenants[OTHER_TENANT] = Tenant(tenant_id=OTHER_TENANT, name="Altra organizzazione demo", created_at="2026-10-01T08:00:00.000Z")
    for uid, email, name, role in [("dev-altra-admin", "admin@altra.it", "Amministratore altra", "admin"),
                                   ("dev-altra-operator", "operatore@altra.it", "Operatore altra", "operator")]:
        repo.users[uid] = User(uid=uid, email=email, display_name=name, tenant_id=OTHER_TENANT, role=role)
    apartments = [
        ("apt-rimini-01", "Via Roma 12 – int. 3", "Via Roma 12, 47921 Rimini RN", "IW-DEMO-RIMINI-01", DEMO_TENANT),
        ("apt-bologna-01", "Corso Italia 5 – int. 7", "Corso Italia 5, 40121 Bologna BO", "IW-DEMO-BOLOGNA-01", DEMO_TENANT),
        ("apt-altra-01", "Via Altra 1", "Via Altra 1, 20121 Milano MI", "IW-DEMO-ALTRA-01", OTHER_TENANT),
    ]
    for apt_id, name, address, ext, tenant_id in apartments:
        repo.apartments[apt_id] = Apartment(
            apartment_id=apt_id,
            tenant_id=tenant_id,
            name=name,
            address=address,
            timezone="Europe/Rome",
            instance_url=MOCK_INSTANCE_URL,
            instance_secret_name=None,
            port=None,
            enabled=True,
            external_ids=ExternalIds(italianway=ext),
            created_at="2026-10-01T08:00:00.000Z",
        )
    # P-36: platform managers, one without an organisation and one who is also an admin of the demo tenant
    for email in ("piattaforma@demo.it", "m.cracchiolo@hqe.it"):
        repo.platform_members[email] = PlatformMember(email=email, added_by="seed", added_at="2026-10-01T08:00:00.000Z")
