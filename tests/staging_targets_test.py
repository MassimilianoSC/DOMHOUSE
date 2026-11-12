"""D04 (P-83 review, gravity 2): staging runs with production's identity and reaches the same VM. A platform manager of
staging (anyone added to the staging database) could link an apartment to a real engine's address and port: staging
would read langbrain-api-key-<id> and command that apartment. Now staging has INSTANCE_ALLOWED, the engines it may reach
(dev and the load test's, scripts/load), checked when an apartment is linked and before every key is read, for every
call, «Verifica connessione» and stream; it does not start without the list; production (no list) is unchanged.
The other half of D04 (a service account of its own for staging) is a change of permissions, in the procedure."""
import asyncio
import dataclasses
from pathlib import Path

import pytest

from bff import instances, main
from bff.auth import Identity
from bff.config import get_settings
from bff.repository import Apartment, Tenant, get_repository
from bff.routes import platform

ROOT = Path(__file__).resolve().parent.parent
PLAT = Identity(uid="u-plat-d04", email="piattaforma@demo.it", display_name="", user=None, platform_manager=True)
ALLOWED = "10.198.0.2:8100,10.198.0.2:8150-8169"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def staging(monkeypatch):
    s = dataclasses.replace(get_settings(), instance_mode="real", app_env="staging", instance_allowed=ALLOWED)
    monkeypatch.setattr(instances, "get_settings", lambda: s)
    read = []

    def never(name):                                  # a key read here would be the defect itself
        read.append(name)
        raise AssertionError(f"segreto letto: {name}")
    monkeypatch.setattr(instances, "_read_secret", never)
    instances._secret_cache.clear()
    run(get_repository().upsert_tenant(Tenant(tenant_id="t-d04", name="Staging D04")))
    return read


@pytest.mark.parametrize("url, port", [("http://10.198.0.2:8100", None), ("10.198.0.2:8150", None),
                                       ("http://10.198.0.2", 8169), ("mock://builtin", None)])
def test_dev_the_load_test_and_the_demonstrations_are_allowed(staging, url, port):
    assert instances.target_problem(url, port) is None


@pytest.mark.parametrize("url, port", [("http://10.198.0.2:8101", None), ("http://10.198.0.2", 8170),
                                       ("http://10.198.0.3:8100", None), ("https://10.198.0.2", None),
                                       ("http://10.198.0.2:porta", None)])
def test_any_other_engine_is_refused(staging, url, port):
    assert instances.target_problem(url, port) == instances.MSG_NOT_ALLOWED


def test_production_has_no_list_and_nothing_changes(monkeypatch):
    s = dataclasses.replace(get_settings(), instance_mode="real", app_env="prod", instance_allowed="")
    monkeypatch.setattr(instances, "get_settings", lambda: s)
    assert instances.target_problem("http://10.198.0.2:8101") is None


def test_linking_a_real_engine_in_staging_is_refused_without_reading_any_key(staging):
    r = run(platform.create_tenant_apartment("t-d04", platform.ApartmentCreate(
        apartment_id="casa-rossi", name="Casa Rossi", instance_url="http://10.198.0.2:8101"), identity=PLAT))
    assert r.status_code == 422 and b"invalid_instance_url" in r.body
    r = run(platform.create_tenant_apartment("t-d04", platform.ApartmentCreate(
        apartment_id="casa-rossi-2", name="Casa Rossi", instance_url="http://10.198.0.2", port=8101), identity=PLAT))
    assert r.status_code == 422                                     # the port in its own field counts the same
    assert run(get_repository().get_apartment("casa-rossi")) is None and staging == []
    ok = run(platform.create_tenant_apartment("t-d04", platform.ApartmentCreate(
        apartment_id="carico-d04", name="Carico", instance_url="http://10.198.0.2:8150"), identity=PLAT))
    assert getattr(ok, "status_code", 201) == 201
    r = run(platform.relink_tenant_apartment("t-d04", "carico-d04", platform.ApartmentLink(port=8101,
                                             instance_url="http://10.198.0.2"), identity=PLAT))
    assert r.status_code == 422
    assert run(get_repository().get_apartment("carico-d04")).instance_url == "http://10.198.0.2:8150"


def test_a_record_saved_before_is_never_called_nor_its_key_read(staging):
    apt = Apartment(apartment_id="casa-vecchia", tenant_id="t-d04", name="Vecchia", instance_url="http://10.198.0.2:8101")
    run(get_repository().upsert_apartment(apt))
    with pytest.raises(instances.TargetRefused):
        run(instances.call(apt, "GET", "/health"))
    with pytest.raises(instances.TargetRefused):
        run(instances.instance_headers(apt, instances.BFF_ACTOR))   # what the stream uses too
    out = run(instances.verify(apt, instances.BFF_ACTOR))
    assert out["error"] == instances.MSG_NOT_ALLOWED and not out["ok"]
    assert staging == []


@pytest.mark.parametrize("allowed, refused", [("", True), ("your-vm-internal-ip:8100", True), ("10.0.0.2:8100", False)])
def test_staging_does_not_start_without_its_list(allowed, refused):
    s = dataclasses.replace(get_settings(), app_env="staging", auth_mode="firebase", instance_mode="real",
                            instance_allowed=allowed)
    if refused:
        with pytest.raises(SystemExit, match="INSTANCE_ALLOWED"):
            main.check_access_settings(s, {})
    else:
        main.check_access_settings(s, {})
    main.check_access_settings(dataclasses.replace(s, app_env="prod", instance_allowed=""), {})   # production: no list


def test_the_staging_manifest_lists_dev_and_the_load_test_and_production_none():
    staging_yaml = (ROOT / "bff" / "cloudrun.staging.yaml").read_text(encoding="utf-8")
    prod_yaml = (ROOT / "bff" / "cloudrun.yaml").read_text(encoding="utf-8")
    assert "value: your-vm-internal-ip:8100,your-vm-internal-ip:8150-8169" in staging_yaml
    assert "INSTANCE_ALLOWED" not in prod_yaml
    deploy = (ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
    assert 's#your-vm-internal-ip#${VM_INTERNAL_IP:-}#g' in deploy and "set VM_INTERNAL_IP" in deploy
    conf = (ROOT / "scripts" / "publish-settings.conf").read_text(encoding="utf-8")
    assert "\nVM_INTERNAL_IP=" in conf
    # the load test's engines (scripts/load: PORT_BASE 8150, at most 20 apartments) stay inside the list
    load = (ROOT / "scripts" / "load" / "ambiente.py").read_text(encoding="utf-8")
    assert "PORT_BASE = 8150" in load
