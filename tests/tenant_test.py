"""Organisation records (P-36, D-63 D4): organisations are created by the platform, never implicitly. A user whose tenant
has no record is refused at login ("Organizzazione non attiva"), PATCH /app/admin/tenant answers 404, and
scripts/set_claims.py --tenant-name creates or renames a record. In-process, memory repository."""
import asyncio

import pytest
from fastapi import HTTPException

from bff import auth
from bff.auth import CurrentUser, _from_claims, Identity
from bff.repository import Apartment, Tenant, User, get_repository
from bff.routes import admin, platform


# P-47: platform routes record who acted; called directly here, they get a platform manager as FastAPI would
PLAT = Identity(uid="u-plat-test", email="piattaforma@demo.it", display_name="", user=None, platform_manager=True)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def fresh():
    auth._known_tenants.clear()


def claims(uid: str, tenant: str, role: str = "admin") -> dict:
    return {"uid": uid, "email": f"{uid}@nuovo.it", "email_verified": True, "tenant_id": tenant, "role": role}


def test_login_with_a_tenant_without_record_is_refused_and_creates_nothing():
    repo = get_repository()
    with pytest.raises(HTTPException) as e:
        run(_from_claims(repo, claims("u-orphan", "t-no-record-login")))
    assert e.value.status_code == 403 and e.value.detail["error"] == "tenant_inactive"
    assert run(repo.get_tenant("t-no-record-login")) is None
    assert run(repo.get_user("u-orphan")) is None


def test_tenant_read_once_per_process(monkeypatch):
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-repeat", name="Ripetuto")))
    reads = []
    original = repo.get_tenant

    async def counting(tenant_id):
        reads.append(tenant_id)
        return await original(tenant_id)
    monkeypatch.setattr(repo, "get_tenant", counting)
    for _ in range(3):
        run(_from_claims(repo, claims("u-repeat", "t-repeat", "viewer")))
    assert reads == ["t-repeat"]


def test_patch_tenant_without_record_is_404():
    user = CurrentUser("u-adm", "u-adm@nuovo.it", "t-no-record", "admin")
    out = run(admin.patch_tenant(admin.TenantPatch(enabled_features=["devices"]), user))
    assert out.status_code == 404
    assert run(get_repository().get_tenant("t-no-record")) is None


def _set_claims():
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("set_claims", Path(__file__).resolve().parent.parent / "scripts" / "set_claims.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_set_claims_tenant_name_creates_or_renames():
    sc, repo = _set_claims(), get_repository()
    assert run(sc.set_tenant_name(repo, "t-name-new", "  Flatsharing ")) is None        # created
    assert run(repo.get_tenant("t-name-new")).name == "Flatsharing"
    run(repo.upsert_tenant(Tenant(tenant_id="t-name-old", name="", enabled_features=["devices"])))
    assert run(sc.set_tenant_name(repo, "t-name-old", "Flatsharing")) == ""             # renamed
    t = run(repo.get_tenant("t-name-old"))
    assert t.name == "Flatsharing" and t.enabled_features == ["devices"]                  # nothing else touched
    with pytest.raises(SystemExit):
        run(sc.set_tenant_name(repo, "t-name-old", "   "))


def test_set_claims_refuses_memory_repository():
    sc = _set_claims()
    for call in (lambda: sc.tenant_name_command("t-x", "Flatsharing"), lambda: sc.platform_command("x@y.it")):
        with pytest.raises(SystemExit) as e:
            call()
        assert "REPOSITORY=firestore" in str(e.value)


def test_set_claims_platform_add():
    sc, repo = _set_claims(), get_repository()
    assert run(sc.platform_add(repo, "  Nuovo.Gestore@Esempio.it ")) is True
    assert run(repo.get_platform_member("nuovo.gestore@esempio.it")) is not None
    assert run(sc.platform_add(repo, "nuovo.gestore@esempio.it")) is False      # already there
    with pytest.raises(SystemExit):
        run(sc.platform_add(repo, "senza-chiocciola"))


class LoopBoundRepo:
    """Like the Firestore AsyncClient: bound to the event loop of its first call, unusable from another one."""

    def __init__(self):
        self.loop, self.members = None, {}

    def _same_loop(self):
        loop = asyncio.get_running_loop()
        if self.loop is None:
            self.loop = loop
        elif self.loop is not loop:
            raise RuntimeError("Event loop is closed")

    async def get_platform_member(self, email):
        self._same_loop()
        return self.members.get(email)

    async def add_platform_member(self, m):
        self._same_loop()
        self.members[m.email] = m
        return m

    async def list_platform_members(self):
        self._same_loop()
        return list(self.members.values())


def test_set_claims_platform_command_uses_one_event_loop(monkeypatch, capsys):
    """D-76: --platform-add assigned the role, then listing the managers in a second asyncio.run failed with
    "Event loop is closed" on the real Firestore client. The whole command must run in one event loop."""
    sc = _set_claims()
    repo = LoopBoundRepo()
    monkeypatch.setattr(sc, "_firestore_repository", lambda option: repo)
    sc.platform_command("Gestore@Esempio.it")
    out = capsys.readouterr().out
    assert "gestore@esempio.it: ruolo di gestore della piattaforma assegnato" in out
    assert "gestore: gestore@esempio.it (aggiunto da scripts/set_claims.py" in out


def test_two_admins_demoting_each_other_at_once_leave_one():
    """P-36 point 14b at route level: before, only self-demotion was checked."""
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-dueadmin", name="Due admin")))
    for uid in ("da-1", "da-2"):
        run(repo.upsert_user(User(uid=uid, email=f"{uid}@due.it", tenant_id="t-dueadmin", role="admin")))
    a, b = (CurrentUser(u, f"{u}@due.it", "t-dueadmin", "admin") for u in ("da-1", "da-2"))

    async def crossed():
        return await asyncio.gather(admin.patch_user("da-2", admin.UserPatch(role="viewer"), a),
                                    admin.patch_user("da-1", admin.UserPatch(role="viewer"), b))
    results = run(crossed())
    assert sorted(getattr(r, "status_code", 200) for r in results) == [200, 409]
    assert [u.role for u in run(repo.list_users("t-dueadmin"))].count("admin") == 1


def test_two_admins_removing_each_other_at_once_leave_one():
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-duerim", name="Due rimozioni")))
    for uid in ("dr-1", "dr-2"):
        run(repo.upsert_user(User(uid=uid, email=f"{uid}@due.it", tenant_id="t-duerim", role="admin")))
    a, b = (CurrentUser(u, f"{u}@due.it", "t-duerim", "admin") for u in ("dr-1", "dr-2"))

    async def crossed():
        return await asyncio.gather(admin.delete_user("dr-2", a), admin.delete_user("dr-1", b))
    run(crossed())
    assert [u.role for u in run(repo.list_users("t-duerim"))] == ["admin"]


def test_same_italianway_code_at_once_in_two_organisations():
    """P-36 point 7: the same code saved at the same moment for apartments of two organisations: one wins.
    D-72: only the platform sets codes."""
    repo = get_repository()
    for t in ("t-iw-1", "t-iw-2"):
        run(repo.upsert_tenant(Tenant(tenant_id=t, name=t)))

    async def crossed():
        return await asyncio.gather(
            platform.create_tenant_apartment("t-iw-1", platform.ApartmentCreate(apartment_id="apt-iw-1", name="A", instance_url="mock://builtin", italianway_id="IW-CONC"), identity=PLAT),
            platform.create_tenant_apartment("t-iw-2", platform.ApartmentCreate(apartment_id="apt-iw-2", name="B", instance_url="mock://builtin", italianway_id="IW-CONC"), identity=PLAT))
    results = run(crossed())
    assert sorted(getattr(r, "status_code", 200) for r in results) == [200, 409]
    assert len(run(repo.find_apartments_by_external_id("italianway", "IW-CONC"))) == 1


def test_italianway_code_is_freed_by_a_change_a_removal_or_a_deletion():
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-iw-3", name="t-iw-3")))

    def create(apt_id, code):
        return run(platform.create_tenant_apartment("t-iw-3", platform.ApartmentCreate(apartment_id=apt_id, name=apt_id, instance_url="mock://builtin", italianway_id=code), identity=PLAT))

    assert create("apt-iw-3", " IW-OLD ")["italianway_id"] == "IW-OLD"           # trimmed
    assert getattr(create("apt-iw-6", "IW-OLD"), "status_code", 200) == 409       # taken
    run(platform.relink_tenant_apartment("t-iw-3", "apt-iw-3", platform.ApartmentLink(italianway_id="IW-NEW"), identity=PLAT))
    assert getattr(create("apt-iw-4", "IW-OLD"), "status_code", 200) == 200       # the old code was released
    row = run(platform.relink_tenant_apartment("t-iw-3", "apt-iw-4", platform.ApartmentLink(italianway_id=""), identity=PLAT))
    assert row["italianway_id"] is None                                            # "" removes it
    assert getattr(create("apt-iw-7", "IW-OLD"), "status_code", 200) == 200       # released by the removal
    run(platform.delete_tenant_apartment("t-iw-3", "apt-iw-3", identity=PLAT))
    assert getattr(create("apt-iw-5", "IW-NEW"), "status_code", 200) == 200       # released by the deletion


def test_admin_cannot_set_or_change_an_italianway_code():
    """D-72 (F6): an admin may only resend the saved value; any new, different or removed code is refused.
    (Creating an apartment is refused to the admin altogether, D-77.)"""
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-iw-4", name="t-iw-4")))
    a = CurrentUser("u-iw-4", "d@iw.it", "t-iw-4", "admin")
    run(platform.create_tenant_apartment("t-iw-4", platform.ApartmentCreate(apartment_id="apt-iw-9", name="G", instance_url="mock://builtin", italianway_id="IW-PIAT"), identity=PLAT))
    for value in ("IW-ALTRO", None, ""):
        r = run(admin.patch_apartment("apt-iw-9", admin.ApartmentPatch(italianway_id=value), a))
        assert r.status_code == 403 and b"platform_only" in r.body
    row = run(admin.patch_apartment("apt-iw-9", admin.ApartmentPatch(name="G2", italianway_id="IW-PIAT"), a))
    assert row["name"] == "G2" and row["italianway_id"] == "IW-PIAT"
    assert run(repo.get_apartment("apt-iw-9")).external_ids.italianway == "IW-PIAT"


# -------- P-50 (D-85): suspension --------
def test_suspension_stops_sign_in_streams_and_comes_back(monkeypatch):
    from bff.auth import still_sees

    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-susp", name="Sospesa")))
    run(_from_claims(repo, claims("u-susp", "t-susp", "viewer")))               # cached as active
    viewer = CurrentUser("u-susp", "u-susp@nuovo.it", "t-susp", "viewer")
    run(repo.upsert_apartment(Apartment(apartment_id="apt-susp", tenant_id="t-susp", name="S", instance_url="mock://builtin")))
    assert run(still_sees(viewer, "apt-susp")) is True
    out = run(platform.suspend_tenant("t-susp", platform.Suspension(reason="  Contratto scaduto "), identity=PLAT))
    assert out["suspended"] is True and out["suspended_reason"] == "Contratto scaduto" and out["suspended_at"]
    with pytest.raises(HTTPException) as e:                                      # at once, despite the cache (L9)
        run(_from_claims(repo, claims("u-susp", "t-susp", "viewer")))
    assert e.value.status_code == 403 and e.value.detail["error"] == "tenant_suspended"
    assert run(still_sees(viewer, "apt-susp")) is False                          # an open stream closes
    r = run(platform.suspend_tenant("t-susp", platform.Suspension(reason="ancora"), identity=PLAT))
    assert r.status_code == 409 and b"already_suspended" in r.body
    r = run(platform.suspend_tenant("t-susp", platform.Suspension(reason="   "), identity=PLAT))
    assert r.status_code == 422 and b"invalid_reason" in r.body
    out = run(platform.reactivate_tenant("t-susp", identity=PLAT))
    assert out["suspended"] is False and out["suspended_reason"] is None
    assert run(_from_claims(repo, claims("u-susp", "t-susp", "viewer"))).tenant_id == "t-susp"
    r = run(platform.reactivate_tenant("t-susp", identity=PLAT))
    assert r.status_code == 409 and b"not_suspended" in r.body
    actions = [e.action for e in run(repo.list_audit("t-susp", 10))]
    assert actions[:2] == ["tenant_reactivated", "tenant_suspended"]
    assert run(repo.list_audit("t-susp", 10))[1].details == {"reason": "Contratto scaduto"}


def test_suspension_seen_by_other_processes_within_the_recheck_time(monkeypatch):
    """With more than one instance only the process that suspended forgets its cache: the others re-read the record
    after TENANT_RECHECK_SECONDS."""
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-susp-2", name="Altra sospesa")))
    clock = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: clock[0])
    run(_from_claims(repo, claims("u-susp-2", "t-susp-2", "viewer")))
    run(repo.update_tenant("t-susp-2", {"status": "suspended"}))                # written by "another instance"
    run(_from_claims(repo, claims("u-susp-2", "t-susp-2", "viewer")))           # still cached: allowed for now
    clock[0] += auth.TENANT_RECHECK_SECONDS
    with pytest.raises(HTTPException) as e:
        run(_from_claims(repo, claims("u-susp-2", "t-susp-2", "viewer")))
    assert e.value.detail["error"] == "tenant_suspended"
