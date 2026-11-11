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
from fastapi import HTTPException

from bff import accounts, auth, config, instances
from bff.repository import Apartment, get_repository

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


def test_d202_demonstrations_are_refused_in_production_only(env):
    """D-202 (revises D-188): the built-in engine is in each instance's memory. Real addresses are not concerned."""
    env("prod")
    for url in ("mock://builtin", "mock://builtin?variante=occupato", "MOCK://builtin"):
        assert instances.instance_url_problem(url) == instances.MSG_NO_DEMO, url
    assert instances.instance_url_problem("https://motore.esempio.it") != instances.MSG_NO_DEMO
    for name in ("staging", "dev"):
        env(name)
        assert instances.instance_url_problem("mock://builtin") is None, name
        assert instances.instance_url_problem("mock://builtin?variante=occupato") is None, name
        assert instances.instance_url_problem("mock://builtin?variante=pieno") == instances.MSG_BAD_VARIANT, name


LEFT = Apartment(apartment_id="apt-rimasto", tenant_id=TENANT, name="Rimasto", instance_url="mock://builtin")


def test_d202_a_demonstration_left_in_production_gets_a_clear_answer(env):
    run(get_repository().upsert_apartment(LEFT))
    user = auth.CurrentUser("u-1", "a@esempio.it", TENANT, "admin", "Prova")
    env("prod")
    with pytest.raises(HTTPException) as refused:
        run(auth.get_tenant_apartment(user, LEFT.apartment_id))
    assert refused.value.status_code == 409 and instances.MSG_NO_DEMO in str(refused.value.detail)
    env("staging")
    assert run(auth.get_tenant_apartment(user, LEFT.apartment_id)).apartment_id == LEFT.apartment_id


def test_d202_no_call_reaches_the_built_in_engine_in_production(env, monkeypatch):
    async def answer(*_a, **_k):
        return "risposta"
    monkeypatch.setattr(instances, "http", lambda: SimpleNamespace(request=answer))
    env("prod")
    with pytest.raises(instances.DemoRefused):
        run(instances.call(LEFT, "GET", "/health"))
    env("staging")
    assert run(instances.call(LEFT, "GET", "/health")) == "risposta"


def test_d202_the_connection_check_says_why(env):
    run(get_repository().upsert_apartment(LEFT))
    env("prod")
    out = run(instances.verify(LEFT, "system:bff"))
    assert out["error"] == instances.MSG_NO_DEMO and out["ok"] is False


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


def test_orphan_claims_lists_removed_people_and_not_members_nor_waiting_invitations():
    """R4-1: the people removed before the fix kept their claims; the list names them, never a member nor a person
    with an invitation waiting in that organisation, and reads each environment's own claims only."""
    from bff.repository import User
    from bff.repository.memory import InMemoryRepository
    sc = _set_claims()
    repo = InMemoryRepository()
    repo.users["u-member"] = User(uid="u-member", email="m@x.it", tenant_id="t-a", role="admin")
    repo.users["u-moved"] = User(uid="u-moved", email="mv@x.it", tenant_id="t-b", role="viewer")
    repo.users["inv-w"] = User(uid="inv-w", email="w@x.it", tenant_id="t-a", role="operator")
    acc = lambda uid, email, claims: SimpleNamespace(uid=uid, email=email, custom_claims=claims)
    accounts_list = [
        acc("u-member", "m@x.it", {"prod": {"tenant_id": "t-a", "role": "admin"}}),          # member: fine
        acc("u-gone", "g@x.it", {"prod": {"tenant_id": "t-a", "role": "operator"}}),         # removed: listed
        acc("u-flat", "f@x.it", {"tenant_id": "t-a", "role": "admin"}),                      # removed, flat: listed
        acc("u-moved", "mv@x.it", {"prod": {"tenant_id": "t-a", "role": "admin"}}),          # record elsewhere: listed
        acc("u-wait", "w@x.it", {"prod": {"tenant_id": "t-a", "role": "operator"}}),         # invitation waiting: fine
        acc("u-stg", "s@x.it", {"staging": {"tenant_id": "t-s", "role": "viewer"}}),         # staging only
        acc("u-none", "n@x.it", None),
    ]
    found = run(sc.orphans(repo, accounts_list, "prod"))
    assert [(u.uid, t, r) for u, t, r, _ in found] == [("u-gone", "t-a", "operator"), ("u-flat", "t-a", "admin"),
                                                         ("u-moved", "t-a", "admin")]
    assert found[2][3].tenant_id == "t-b"
    staging = run(sc.orphans(repo, accounts_list, "staging"))
    assert [u.uid for u, *_ in staging] == ["u-stg"]                   # the flat ones never count in staging


def test_orphan_claims_apply_removes_one_persons_claims_and_revokes_in_production(monkeypatch):
    from bff.repository import User
    from bff.repository.memory import InMemoryRepository
    sc = _set_claims()
    repo = InMemoryRepository()
    repo.users["u-ok"] = User(uid="u-ok", email="ok@x.it", tenant_id="t-a", role="admin")
    people = {"u-gone": SimpleNamespace(uid="u-gone", email="g@x.it", custom_claims={
                  "prod": {"tenant_id": "t-a", "role": "admin"}, "tenant_id": "t-a", "role": "admin",
                  "staging": {"tenant_id": "t-s", "role": "viewer"}}),
              "u-ok": SimpleNamespace(uid="u-ok", email="ok@x.it", custom_claims={"prod": {"tenant_id": "t-a", "role": "admin"}})}
    calls = []
    fake = SimpleNamespace(
        list_users=lambda: SimpleNamespace(iterate_all=lambda: iter(people.values())),
        set_custom_user_claims=lambda uid, c: (calls.append(("claims", uid)), setattr(people[uid], "custom_claims", c)),
        revoke_refresh_tokens=lambda uid: calls.append(("revoke", uid)))
    monkeypatch.setattr(sc, "auth", fake)
    monkeypatch.setattr(sc, "init", lambda: None)
    monkeypatch.setattr(sc, "_firestore_repository", lambda option: repo)
    assert sc.orphan_command("prod", False, None) == 1 and calls == []           # the list writes nothing
    with pytest.raises(SystemExit):
        sc.orphan_command("prod", True, "ok@x.it")                                # a member: refused
    with pytest.raises(SystemExit):
        sc.orphan_command("prod", True, None)                                     # never everybody at once
    assert sc.orphan_command("prod", True, "G@x.it") == 1
    assert people["u-gone"].custom_claims == {"staging": {"tenant_id": "t-s", "role": "viewer"}}
    assert calls == [("claims", "u-gone"), ("revoke", "u-gone")]
    assert people["u-ok"].custom_claims == {"prod": {"tenant_id": "t-a", "role": "admin"}}


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


# -------- D-218: no development setting that opens the access outside development ------------------------------------
def startup(app_env: str, auth_mode: str, service: str | None = None):
    """check_access_settings with these values; the error lines it writes."""
    from bff import main, logs
    lines = []
    original = logs.error
    logs.error = lambda msg, **fields: lines.append((msg, fields))
    try:
        main.check_access_settings(dataclasses.replace(config.get_settings(), app_env=app_env, auth_mode=auth_mode),
                                   {"K_SERVICE": service} if service else {})
    finally:
        logs.error = original
    return lines


def test_dev_login_refused_in_staging_and_production():
    for app_env in ("staging", "prod"):
        for auth_mode in ("dev", "", "firebse"):
            with pytest.raises(SystemExit, match=rf"AUTH_MODE «{auth_mode}» with APP_ENV «{app_env}».*does not start"):
                startup(app_env, auth_mode, "domotica-bff")
        assert startup(app_env, "firebase", "domotica-bff") == []                    # starts


def test_on_cloud_run_app_env_must_say_staging_or_prod():
    """APP_ENV and AUTH_MODE are both «dev» when the variables are missing: on Cloud Run that is refused."""
    with pytest.raises(SystemExit, match=r"APP_ENV is «dev» \(or missing\) on Cloud Run \(service domotica-bff\)"):
        startup("dev", "dev", "domotica-bff")
    assert startup("dev", "dev") == []                                               # the PC and the test runs


def test_an_unknown_app_env_is_refused_everywhere():
    with pytest.raises(SystemExit, match=r"APP_ENV «production» is not one of dev, staging, prod"):
        startup("production", "firebase")


def test_the_refusal_is_one_clear_line_in_the_log():
    from bff import main, logs
    lines = []
    original = logs.error
    logs.error = lambda msg, **fields: lines.append((msg, fields))
    try:
        with pytest.raises(SystemExit):
            main.check_access_settings(dataclasses.replace(config.get_settings(), app_env="prod", auth_mode="dev"),
                                       {"K_SERVICE": "domotica-bff"})
    finally:
        logs.error = original
    assert [m for m, _ in lines] == ["development setting refused"]
    assert {k: lines[0][1][k] for k in ("app_env", "auth_mode", "service")} == {
        "app_env": "prod", "auth_mode": "dev", "service": "domotica-bff"}


def test_both_manifests_start(monkeypatch):
    """What the two manifests declare passes the check on Cloud Run."""
    from bff import main
    from tests.cloudrun_manifests_test import PROD, STAGING, env as manifest_env
    for manifest in (STAGING, PROD):
        e = manifest_env(manifest)
        settings = dataclasses.replace(config.get_settings(), app_env=e["APP_ENV"], auth_mode=e["AUTH_MODE"])
        main.check_access_settings(settings, {"K_SERVICE": "domotica-bff"})


@pytest.mark.parametrize("argv, database", [(["--from-repo"], "staging"),                      # no --env: refused
                                            (["--from-repo", "--env", "prod"], "staging"),     # the wrong database
                                            (["--from-repo", "--env", "staging"], "(default)")])
def test_from_repo_needs_its_environment_and_the_matching_database(monkeypatch, argv, database):
    """D26 (P-83): --from-repo wrote production claims (the default --env) for the invitations of whatever database was
    open, and revoked sessions: with the staging database, a staging invitation became a production admin, or locked a
    production account out. Now --env is required and must match the database; nothing is written otherwise."""
    import sys

    from bff import config as bff_config
    sc = _set_claims()
    s = dataclasses.replace(bff_config.get_settings(), repository="firestore", firestore_database=database)
    monkeypatch.setattr(bff_config, "get_settings", lambda: s)
    written = []
    monkeypatch.setattr(sc, "set_claims", lambda *a, **k: written.append(a))
    monkeypatch.setattr(sc, "init", lambda: None)
    monkeypatch.setattr(sys, "argv", ["set_claims.py", *argv])
    with pytest.raises(SystemExit):
        sc.main()
    assert written == []


def test_from_repo_with_its_environment_goes_on(monkeypatch):
    import sys

    from bff import config as bff_config
    sc = _set_claims()
    s = dataclasses.replace(bff_config.get_settings(), repository="firestore", firestore_database="staging")
    monkeypatch.setattr(bff_config, "get_settings", lambda: s)
    seen = []

    async def fake_from_repo(create, send_reset_link, env="prod"):
        seen.append(env)
    monkeypatch.setattr(sc, "from_repo", fake_from_repo)
    monkeypatch.setattr(sc, "init", lambda: None)
    monkeypatch.setattr(sys, "argv", ["set_claims.py", "--from-repo", "--env", "staging"])
    sc.main()
    assert seen == ["staging"]
