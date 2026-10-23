"""D-64/D-65 in INSTANCE_MODE=real, in-process (the end-to-end run uses the mock): the admin can no longer create,
delete or re-link an apartment (403 platform_only); editing name and the rest still works even when the PWA form sends
the unchanged URL and port; 'Verifica connessione' stays with the admin and stores last_check."""
import asyncio
import dataclasses

import pytest

from bff import instances
from bff.auth import CurrentUser, Identity
from bff.config import get_settings
from bff.repository import Apartment, Tenant, get_repository
from bff.routes import admin


# P-47: platform routes record who acted; called directly here, they get a platform manager as FastAPI would
PLAT = Identity(uid="u-plat-test", email="piattaforma@demo.it", display_name="", user=None, platform_manager=True)

TENANT = "t-real-mode"
ADMIN = CurrentUser("u-real-admin", "admin@real.it", TENANT, "admin")
URL = "http://10.198.0.2:8101"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def real(monkeypatch):
    real_settings = dataclasses.replace(get_settings(), instance_mode="real")
    monkeypatch.setattr(instances, "get_settings", lambda: real_settings)
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id=TENANT, name="Real")))
    run(repo.upsert_apartment(Apartment(apartment_id="apt-real-1", tenant_id=TENANT, name="Uno", instance_url=URL, port=None)))


def status(resp) -> int:
    return getattr(resp, "status_code", 200)  # a dict means FastAPI would answer 200


def test_admin_cannot_create():
    r = run(admin.create_apartment(ADMIN))
    assert status(r) == 403 and b"platform_only" in r.body


def test_admin_cannot_delete():
    r = run(admin.delete_apartment("apt-real-1", ADMIN))
    assert status(r) == 403 and b"platform_only" in r.body
    assert run(get_repository().get_apartment("apt-real-1")) is not None


def test_admin_cannot_relink_but_can_edit_with_the_same_link():
    r = run(admin.patch_apartment("apt-real-1", admin.ApartmentPatch(instance_url="http://10.198.0.2:8199"), ADMIN))
    assert status(r) == 403 and b"platform_only" in r.body
    r = run(admin.patch_apartment("apt-real-1", admin.ApartmentPatch(port=8199), ADMIN))
    assert status(r) == 403
    # what the PWA sends today: the whole form, link unchanged (even written with upper case and spaces)
    out = run(admin.patch_apartment("apt-real-1", admin.ApartmentPatch(name="Rinominato", instance_url=f"  HTTP://10.198.0.2:8101",
                                                                       port=None, address="Via Nuova 1"), ADMIN))
    assert status(out) == 200 and out["name"] == "Rinominato" and out["instance_url"] == URL
    assert run(get_repository().get_apartment("apt-real-1")).instance_url == URL


def test_admin_verify_stores_last_check(monkeypatch):
    async def unreachable(*_a, **_k):
        raise OSError("rete")
    monkeypatch.setattr(instances, "call", unreachable)
    monkeypatch.setattr(instances, "_read_secret", lambda name: "chiave-finta")  # never the real Secret Manager
    instances._secret_cache.clear()
    out = run(admin.verify_apartment("apt-real-1", ADMIN))
    assert out["ok"] is False and out["error"] == "Sistema domotico non raggiungibile"
    lc = run(get_repository().get_apartment("apt-real-1")).last_check
    assert lc is not None and lc.ok is False and lc.error == "Sistema domotico non raggiungibile" and lc.checked_at


@pytest.mark.parametrize("exc_name, expected", [
    ("NotFound", "Chiave del sistema domotico non trovata in Secret Manager: crea il segreto langbrain-api-key-apt-real-1"),
    ("PermissionDenied", "Chiave del sistema domotico non leggibile dal server: manca il permesso su langbrain-api-key-apt-real-1"),
])
def test_verify_explains_a_missing_or_unreadable_key(monkeypatch, exc_name, expected):
    # D-67 (N3): otherwise it would look like a network problem ("Sistema domotico non raggiungibile")
    from google.api_core import exceptions

    def refuse(name):
        raise getattr(exceptions, exc_name)(name)
    monkeypatch.setattr(instances, "_read_secret", refuse)
    instances._secret_cache.clear()
    called = []
    monkeypatch.setattr(instances, "call", lambda *a, **k: called.append(a))
    out = run(admin.verify_apartment("apt-real-1", ADMIN))
    # D-90: the admin reads a generic message; the detail (with the secret's name) stays for the platform
    assert out["ok"] is False and out["error"] == instances.ADMIN_SECRET_MESSAGE and called == []
    assert "secret_problem" not in out
    stored = run(get_repository().get_apartment("apt-real-1")).last_check
    assert stored.error == expected and stored.secret_problem is True


def test_same_engine_link_refused_for_two_apartments():
    """P-36 point 8: an apartment of another organisation linked to an instance already in use would show its devices.
    The link is compared as host + effective port, whatever form it is written in."""
    from bff.routes import platform

    run(get_repository().upsert_tenant(Tenant(tenant_id="t-real-other", name="Altra real")))
    same_forms = ["http://10.198.0.2:8101", "  HTTP://10.198.0.2:8101/api/v1", "10.198.0.2:8101"]
    for i, url in enumerate(same_forms):
        r = run(platform.create_tenant_apartment("t-real-other", platform.ApartmentCreate(
            apartment_id=f"apt-link-{i}", name="Doppio", instance_url=url), identity=PLAT))
        assert status(r) == 409 and b"link_in_use" in r.body, url
    r = run(platform.create_tenant_apartment("t-real-other", platform.ApartmentCreate(
        apartment_id="apt-link-port", name="Porta a parte", instance_url="http://10.198.0.2", port=8101), identity=PLAT))
    assert status(r) == 409                                                     # port in the field, same instance
    r = run(platform.create_tenant_apartment("t-real-other", platform.ApartmentCreate(
        apartment_id="apt-link-ok", name="Altra istanza", instance_url="http://10.198.0.2:8102"), identity=PLAT))
    assert status(r) == 201 or isinstance(r, dict)
    assert run(get_repository().reserve_apartment_id("apt-link-0")) is True    # a refused create burns no id
    r = run(platform.relink_tenant_apartment("t-real-other", "apt-link-ok", platform.ApartmentLink(instance_url="http://10.198.0.2:8101"), identity=PLAT))
    assert status(r) == 409
    r = run(platform.relink_tenant_apartment("t-real-other", "apt-link-ok", platform.ApartmentLink(port=8103), identity=PLAT))
    assert status(r) == 200                                                     # URL port wins: still 8102, not in use


def test_two_apartments_claim_the_same_link_at_once():
    """L8 (D-70): two platform creates with the same engine link at the same moment: one wins, atomically."""
    from bff.routes import platform

    run(get_repository().upsert_tenant(Tenant(tenant_id="t-link-conc", name="Link conc")))

    async def both():
        mk = lambda aid: platform.ApartmentCreate(apartment_id=aid, name=aid, instance_url="http://10.198.0.2:8190")
        return await asyncio.gather(platform.create_tenant_apartment("t-link-conc", mk("apt-lk-1"), identity=PLAT),
                                    platform.create_tenant_apartment("t-link-conc", mk("apt-lk-2"), identity=PLAT))
    results = run(both())
    codes = sorted(getattr(r, "status_code", 201) for r in results)
    assert codes == [201, 409]
    on_link = [a.apartment_id for a in run(get_repository().list_apartments("t-link-conc"))
               if a.instance_url == "http://10.198.0.2:8190"]
    assert len(on_link) == 1
