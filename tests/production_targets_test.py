"""F-3 (attack-from-outside review, 22 November 2026, medium): production had no list of the engines it may reach
(INSTANCE_ALLOWED empty = any host). Whoever stole a platform manager's account could move a real apartment, of any
organisation, onto an address of theirs: the BFF sent it the engine's key at once (X-API-Key), then the users'
commands. Now production does not start in real mode without its list (the VM's dev engine, 8100, which serves
production until the second VM, and production's band 8101-8149), the same checks as staging's D04 apply (link saved,
every call and stream, «Verifica»), with production's own message; loopback and link-local addresses are refused outside
development even when listed; a relink leaves a warn line with the manager's uid. In-process, memory repository."""
import asyncio
import dataclasses
import json
import logging
from pathlib import Path

import pytest

from bff import instances, main
from bff.auth import Identity
from bff.config import get_settings
from bff.logs import JsonFormatter
from bff.repository import Apartment, Tenant, get_repository
from bff.routes import platform

ROOT = Path(__file__).resolve().parent.parent
PLAT = Identity(uid="u-plat-f3", email="piattaforma@demo.it", display_name="", user=None, platform_manager=True)
ALLOWED = "10.198.0.2:8100,10.198.0.2:8101-8149"
MSG_PROD = "Indirizzo del motore non ammesso: in questo ambiente si collegano solo i motori della produzione"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def prod(monkeypatch):
    s = dataclasses.replace(get_settings(), instance_mode="real", app_env="prod", instance_allowed=ALLOWED)
    monkeypatch.setattr(instances, "get_settings", lambda: s)
    read = []

    def never(name):                                  # a key read here would be the defect itself
        read.append(name)
        raise AssertionError(f"segreto letto: {name}")
    monkeypatch.setattr(instances, "_read_secret", never)
    instances._secret_cache.clear()
    run(get_repository().upsert_tenant(Tenant(tenant_id="t-f3", name="Produzione F-3")))
    return read


# -------- (a) no list, no start --------
@pytest.mark.parametrize("allowed, refused", [("", True), ("your-vm-internal-ip:8100", True), (ALLOWED, False)])
def test_a_production_does_not_start_without_its_list(allowed, refused):
    s = dataclasses.replace(get_settings(), app_env="prod", auth_mode="firebase", instance_mode="real",
                            instance_allowed=allowed)
    if refused:
        with pytest.raises(SystemExit, match="INSTANCE_ALLOWED"):
            main.check_access_settings(s, {})
    else:
        main.check_access_settings(s, {})


# -------- (b) a relink outside the list: 422, no key read --------
@pytest.mark.parametrize("url, port", [("http://10.198.0.2:8100", None), ("http://10.198.0.2:8101", None),
                                       ("http://10.198.0.2", 8149), ("mock://builtin", None)])
def test_dev_and_production_engines_are_allowed(prod, url, port):
    assert instances.target_problem(url, port) is None


@pytest.mark.parametrize("url, port", [("https://evil.example", None), ("http://10.198.0.2:8150", None),
                                       ("http://10.198.0.2", 8169), ("http://10.198.0.3:8101", None)])
def test_b_any_other_engine_is_refused_with_productions_message(prod, url, port):
    assert instances.target_problem(url, port) == MSG_PROD


def test_b_moving_a_real_apartment_to_another_address_is_refused_without_reading_its_key(prod):
    ok = run(platform.create_tenant_apartment("t-f3", platform.ApartmentCreate(
        apartment_id="casa-f3", name="Casa", instance_url="http://10.198.0.2:8101"), identity=PLAT))
    assert getattr(ok, "status_code", 201) == 201
    r = run(platform.relink_tenant_apartment("t-f3", "casa-f3", platform.ApartmentLink(
        instance_url="https://evil.example"), identity=PLAT))
    assert r.status_code == 422 and json.loads(r.body) == {"error": "invalid_instance_url", "message": MSG_PROD}
    assert run(get_repository().get_apartment("casa-f3")).instance_url == "http://10.198.0.2:8101"
    assert prod == []


@pytest.mark.parametrize("url", ["http://127.0.0.1:8100", "http://localhost:8100", "http://[::1]:8100",
                                 "http://169.254.169.254:80", "http://0.0.0.0:8100", "http://[fe80::1]:8100"])
def test_loopback_and_link_local_are_refused_outside_development_even_when_listed(monkeypatch, url):
    listed = ALLOWED + ",127.0.0.1:8100,localhost:8100,::1:8100,169.254.169.254:80,0.0.0.0:8100,fe80::1:8100"
    for env in ("prod", "staging"):
        s = dataclasses.replace(get_settings(), instance_mode="real", app_env=env, instance_allowed=listed)
        monkeypatch.setattr(instances, "get_settings", lambda: s)
        assert instances.target_problem(url) is not None, (env, url)
    s = dataclasses.replace(get_settings(), app_env="dev", instance_allowed="")    # development: a local engine
    monkeypatch.setattr(instances, "get_settings", lambda: s)
    assert instances.target_problem(url) is None


# -------- (c) a record saved before outside the list: «Verifica» calls nothing --------
def test_c_a_record_saved_before_is_never_called_nor_its_key_read(prod):
    apt = Apartment(apartment_id="casa-f3-vecchia", tenant_id="t-f3", name="Vecchia", instance_url="https://evil.example")
    run(get_repository().upsert_apartment(apt))
    with pytest.raises(instances.TargetRefused):
        run(instances.call(apt, "GET", "/health"))
    out = run(instances.verify(apt, instances.BFF_ACTOR))
    assert out["error"] == MSG_PROD and not out["ok"]
    assert prod == []


# -------- the manifest and the trace --------
def test_the_production_manifest_lists_dev_and_productions_band():
    prod_yaml = (ROOT / "bff" / "cloudrun.yaml").read_text(encoding="utf-8")
    assert "value: your-vm-internal-ip:8100,your-vm-internal-ip:8101-8149" in prod_yaml


def test_a_relink_leaves_a_warn_line_with_the_managers_uid(prod):
    logger, got = logging.getLogger("bff"), []

    class Keep(logging.Handler):
        def emit(self, record):
            got.append(json.loads(JsonFormatter().format(record)))
    handler, level = Keep(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        run(platform.create_tenant_apartment("t-f3", platform.ApartmentCreate(
            apartment_id="casa-f3-log", name="Casa", instance_url="http://10.198.0.2:8102"), identity=PLAT))
        run(platform.relink_tenant_apartment("t-f3", "casa-f3-log", platform.ApartmentLink(
            instance_url="http://10.198.0.2:8103"), identity=PLAT))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)
    lines = [g for g in got if g.get("msg") == "apartment relinked"]
    assert len(lines) == 1 and lines[0]["level"] == "warning"
    assert lines[0].get("by") == "u-plat-f3" and lines[0].get("apartment_id") == "casa-f3-log"
    assert "piattaforma@demo.it" not in json.dumps(lines[0])                    # the uid, never the email


def test_staging_still_reaches_dev_lab_01_and_the_load_test(monkeypatch):
    """Checked with F-3: staging's own list and message are unchanged (tests/staging_targets_test.py holds the rest)."""
    s = dataclasses.replace(get_settings(), instance_mode="real", app_env="staging",
                            instance_allowed="10.198.0.2:8100,10.198.0.2:8150-8169")
    monkeypatch.setattr(instances, "get_settings", lambda: s)
    for url, port in (("http://10.198.0.2:8100", None), ("http://10.198.0.2:8150", None), ("http://10.198.0.2", 8169)):
        assert instances.target_problem(url, port) is None, (url, port)
    assert instances.target_problem("http://10.198.0.2:8101") == instances.MSG_NOT_ALLOWED
    main.check_access_settings(dataclasses.replace(s, auth_mode="firebase"), {})


# -------- rereading of the medium fixes, P-6: the port checked was not the port called --------
@pytest.mark.parametrize("env", ["prod", "staging", "dev"])
def test_p6_an_address_with_user_and_password_is_refused(monkeypatch, env):
    """http://u:p@10.198.0.2 with the port field 8101: the check saw 8101 (allowed), base_url saw «:» in the netloc
    (the userinfo's), added no port, and the key went to 10.198.0.2:80."""
    s = dataclasses.replace(get_settings(), instance_mode="real", app_env=env,
                            instance_allowed=ALLOWED if env != "dev" else "")
    monkeypatch.setattr(instances, "get_settings", lambda: s)
    for url in ("http://u:p@10.198.0.2", "http://u@10.198.0.2:8101", "http://:p@10.198.0.2:8101"):
        assert instances.target_problem(url, 8101) is not None, (env, url)


def test_p6_the_port_called_is_the_port_checked():
    apt = Apartment(apartment_id="a-p6", tenant_id="t", name="P6", instance_url="http://10.198.0.2", port=8101)
    assert instances.base_url(apt) == "http://10.198.0.2:8101/api/v1"
    apt = Apartment(apartment_id="a-p6", tenant_id="t", name="P6", instance_url="http://[fd00::2]", port=8101)
    assert instances.base_url(apt) == "http://[fd00::2]:8101/api/v1"            # «:» of IPv6 is not a port
