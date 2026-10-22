"""P-67 (D-136): production and staging in the same project with one Firebase Auth. Each BFF reads only its own
environment's claims (a staging-only account is refused in production and vice versa, the committente's condition),
staging never deletes a Firebase account nor revokes its sessions, the demonstration apartments only in staging, and
scripts/set_claims.py writes and migrates the claims per environment. Firebase is replaced by a fake."""
import asyncio
import dataclasses
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from bff import accounts, auth, config, instances
from bff.repository import get_repository

ROOT = Path(__file__).resolve().parent.parent
TENANT = "t-flatsharing-demo"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def env(monkeypatch):
    """env("prod" | "staging"): the BFF's APP_ENV for this test."""
    def set_env(name):
        s = dataclasses.replace(config.get_settings(), app_env=name, auth_mode="firebase")
        monkeypatch.setattr(config, "get_settings", lambda: s)
        monkeypatch.setattr(accounts, "get_settings", lambda: s)
        monkeypatch.setattr(instances, "get_settings", lambda: s)
    return set_env


def claims(uid, **per_env):
    return {"uid": uid, "email": f"{uid}@esempio.it", "email_verified": True, **per_env}


def test_each_environment_reads_only_its_own_claims(env):
    staging_only = claims("solo-staging", staging={"tenant_id": TENANT, "role": "admin"})
    prod_only = claims("solo-prod", prod={"tenant_id": TENANT, "role": "admin"})
    flat = claims("piatto", tenant_id=TENANT, role="viewer")                 # before P-67
    repo = get_repository()
    env("prod")
    with pytest.raises(Exception) as refused:
        run(auth._from_claims(repo, staging_only))
    assert getattr(refused.value, "status_code", None) == 403
    assert run(auth._from_claims(repo, prod_only)).role == "admin"
    assert run(auth._from_claims(repo, flat)).role == "viewer"                # still valid in production
    env("staging")
    with pytest.raises(Exception) as refused:
        run(auth._from_claims(repo, claims("solo-prod-2", prod={"tenant_id": TENANT, "role": "admin"})))
    assert getattr(refused.value, "status_code", None) == 403
    with pytest.raises(Exception):
        run(auth._from_claims(repo, claims("piatto-2", tenant_id=TENANT, role="viewer")))   # flat: not in staging
    assert run(auth._from_claims(repo, claims("solo-staging-2", staging={"tenant_id": TENANT, "role": "operator"}))).role == "operator"


class FakeAuth:
    """firebase_admin.auth with one account; records what the BFF asks."""

    class UserNotFoundError(Exception):
        pass

    def __init__(self, custom_claims, email_verified=True):
        self.record = SimpleNamespace(uid="u-1", custom_claims=custom_claims, email_verified=email_verified)
        self.calls = []

    def get_user(self, uid, app=None):
        return self.record

    get_user_by_email = get_user

    def set_custom_user_claims(self, uid, value, app=None):
        self.calls.append(("claims", value))
        self.record.custom_claims = value

    def revoke_refresh_tokens(self, uid, app=None):
        self.calls.append(("revoke", uid))

    def delete_user(self, uid, app=None):
        self.calls.append(("delete", uid))


@pytest.fixture
def firebase(monkeypatch):
    def make(custom_claims, **kw):
        fake = FakeAuth(custom_claims, **kw)
        monkeypatch.setattr(accounts, "_auth", lambda: (fake, None))
        return fake
    return make


def test_staging_never_deletes_the_account_nor_revokes_its_sessions(env, firebase):
    env("staging")
    fake = firebase({"prod": {"tenant_id": TENANT, "role": "admin"}, "staging": {"tenant_id": TENANT, "role": "admin"}})
    assert accounts.delete_account(uid="u-1", owner=True) is False              # even the person's own deletion
    assert fake.calls == [("claims", {"prod": {"tenant_id": TENANT, "role": "admin"}})]   # only staging's claims go
    fake = firebase({"staging": {"tenant_id": TENANT, "role": "viewer"}})
    accounts.set_role_claim("u-1", "operator")
    assert fake.calls == [("claims", {"staging": {"tenant_id": TENANT, "role": "operator"}})]   # no revocation


def test_production_updates_its_own_or_the_flat_claims_and_revokes(env, firebase):
    env("prod")
    fake = firebase({"prod": {"tenant_id": TENANT, "role": "viewer"}, "staging": {"tenant_id": TENANT, "role": "admin"}})
    accounts.set_role_claim("u-1", "operator")
    assert fake.calls == [("claims", {"prod": {"tenant_id": TENANT, "role": "operator"},
                                      "staging": {"tenant_id": TENANT, "role": "admin"}}), ("revoke", "u-1")]
    fake = firebase({"tenant_id": TENANT, "role": "viewer"})
    accounts.set_role_claim("u-1", "admin")
    assert fake.calls[0] == ("claims", {"tenant_id": TENANT, "role": "admin"}) and fake.calls[1][0] == "revoke"


def test_demonstrations_only_in_staging(env):
    env("prod")
    assert "ambiente di prova" in instances.instance_url_problem("mock://builtin")
    env("staging")
    assert instances.instance_url_problem("mock://builtin") is None


def _set_claims():
    spec = importlib.util.spec_from_file_location("set_claims", ROOT / "scripts" / "set_claims.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_set_claims_writes_one_environment_and_keeps_the_flat_ones_for_the_old_bff():
    """The flat claims stay (the production BFF of before P-67 reads only those): the commands run in any order."""
    sc = _set_claims()
    flat = {"tenant_id": TENANT, "role": "admin"}
    after = sc.env_claims_after(flat, "staging", "t-prova", "viewer")
    assert after == {**flat, "prod": {"tenant_id": TENANT, "role": "admin"}, "staging": {"tenant_id": "t-prova", "role": "viewer"}}
    again = sc.env_claims_after(after, "prod", TENANT, "operator")
    assert again["prod"] == {"tenant_id": TENANT, "role": "operator"} and (again["tenant_id"], again["role"]) == (TENANT, "operator")
    assert again["staging"] == {"tenant_id": "t-prova", "role": "viewer"}
    assert sc.migrated({**flat, "altro": 1}) == {**flat, "altro": 1, "prod": {"tenant_id": TENANT, "role": "admin"}}
    assert sc.migrated({**flat, "prod": {"tenant_id": TENANT, "role": "admin"}}) is None   # already done
    assert sc.migrated(None) is None
    # what each BFF reads after the migration: the old one the flat claims, the new one its own environment's
    migrated = sc.migrated(flat)
    assert (migrated["tenant_id"], migrated["role"]) == (TENANT, "admin") and migrated["prod"]["role"] == "admin"


# -------- D-180: the model in the European Union, for every model and environment --------
def test_the_model_location_must_be_european():
    import dataclasses

    import pytest

    from bff import main
    from bff.config import european_location, get_settings
    assert european_location("eu") and european_location("europe-west1") and european_location(" Europe-west8 ")
    for bad in ("global", "us", "us-central1", "asia-east1", ""):
        assert not european_location(bad)
        with pytest.raises(SystemExit, match="is not European"):
            main.check_ai_location(dataclasses.replace(get_settings(), ai_location=bad))
    main.check_ai_location(dataclasses.replace(get_settings(), ai_location="eu"))          # starts


def test_both_manifests_say_eu():
    from pathlib import Path
    import re
    root = Path(__file__).resolve().parent.parent
    for name in ("cloudrun.yaml", "cloudrun.staging.yaml"):
        text = (root / "bff" / name).read_text(encoding="utf-8")
        assert re.search(r"name: AI_LOCATION[^\n]*\n\s*value: \"eu\"", text), name
