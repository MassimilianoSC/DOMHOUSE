"""F-1 (attack-from-outside review, 22 November 2026, serious): a person removed from the organisation (or an account
deleted by its owner) was made again by _from_claims from the claims of the token, with apartment_ids None, that is
every apartment: in staging always (staging never revokes), in production within the revocation cache of another
instance. And the conveniences of /app/me (push, preferences, name) wrote the record back if it went in the meantime.
Now a record is made from claims alone only when Firebase holds them now (403 when not, 503 when it does not answer), and
the conveniences change only a record that exists. Fake Firebase Auth, memory repository, no network."""
import asyncio
import dataclasses
import time
import types

import pytest
from fastapi import HTTPException

from bff import accounts, auth
from bff.auth import CurrentUser, Identity
from bff.config import get_settings
from bff.repository import NotificationPrefs, Tenant, User, get_repository
from bff.routes import account, admin, push

TENANT = "t-f1"


class UserNotFoundError(Exception):
    pass


class FakeAuth:
    """The subset of firebase_admin.auth used by bff/accounts.py (as in tests/firebase_flows_test.py)."""
    UserNotFoundError = UserNotFoundError

    def __init__(self):
        self.users: dict[str, types.SimpleNamespace] = {}
        self.down = False

    def add(self, uid, email, claims, email_verified=True):
        self.users[uid] = types.SimpleNamespace(uid=uid, email=email, custom_claims=claims, email_verified=email_verified,
                                                tokens_valid_after_timestamp=0)

    def get_user(self, uid, app=None):
        if self.down:
            raise RuntimeError("Auth non raggiungibile")
        if uid not in self.users:
            raise UserNotFoundError(uid)
        return self.users[uid]

    def get_user_by_email(self, email, app=None):
        for u in self.users.values():
            if u.email == email:
                return u
        raise UserNotFoundError(email)

    def set_custom_user_claims(self, uid, claims, app=None):
        self.users[uid].custom_claims = claims

    def revoke_refresh_tokens(self, uid, app=None):
        self.users[uid].tokens_valid_after_timestamp = 5_000_000          # seconds 5000, in ms

    def delete_user(self, uid, app=None):
        del self.users[uid]


def run(coro):
    return asyncio.run(coro)


def _env(monkeypatch, env):
    from bff import config
    fake = FakeAuth()
    settings = dataclasses.replace(get_settings(), app_env=env, auth_mode="firebase")
    for module in (config, auth, accounts):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(accounts, "_auth", lambda: (fake, None))
    accounts._valid_after.clear()
    auth._known_tenants.clear()
    run(get_repository().upsert_tenant(Tenant(tenant_id=TENANT, name="F-1")))
    return fake


@pytest.fixture
def staging(monkeypatch):
    return _env(monkeypatch, "staging")


@pytest.fixture
def prod(monkeypatch):
    return _env(monkeypatch, "prod")


def _request(monkeypatch, claims):
    """A request carrying a token with these claims (the token's signature is not what is tested here)."""
    monkeypatch.setattr(auth, "_verify_firebase_token", lambda token: dict(claims))
    return types.SimpleNamespace(headers={"Authorization": "Bearer token-vecchio"})


def _refused(request) -> tuple[int, str]:
    with pytest.raises(HTTPException) as e:
        run(auth._member(request))
    return e.value.status_code, e.value.detail["error"]


def _limited_operator(fb, env, uid):
    repo = get_repository()
    fb.add(uid, f"{uid}@f1.it", {env: {"tenant_id": TENANT, "role": "operator"}})
    run(repo.upsert_user(User(uid=uid, email=f"{uid}@f1.it", tenant_id=TENANT, role="operator", apartment_ids=["apt-1"])))
    run(repo.upsert_user(User(uid=f"{uid}-boss", email=f"boss-{uid}@f1.it", tenant_id=TENANT, role="admin")))
    old_token = {"uid": uid, "email": f"{uid}@f1.it", "email_verified": True, "iat": 1000,
                 env: {"tenant_id": TENANT, "role": "operator"}}
    return old_token, CurrentUser(f"{uid}-boss", f"boss-{uid}@f1.it", TENANT, "admin")


# -------- (a) staging: removed, the old token with the claims never makes the record again --------
def test_a_staging_a_removed_operator_never_comes_back(staging, monkeypatch):
    repo = get_repository()
    old_token, boss = _limited_operator(staging, "staging", "u-f1-a")
    assert run(admin.delete_user("u-f1-a", boss)) is None                          # 204
    assert "staging" not in (staging.users["u-f1-a"].custom_claims or {})          # staging forgot its claims
    assert _refused(_request(monkeypatch, old_token)) == (403, "forbidden")        # the old token still carries them
    assert run(repo.get_user("u-f1-a")) is None
    without = {k: v for k, v in old_token.items() if k != "staging"}
    assert _refused(_request(monkeypatch, without)) == (403, "forbidden")          # then a token without them
    assert run(repo.get_user("u-f1-a")) is None


# -------- (b) production: another instance still holds «not revoked» in its 60 s --------
def test_b_production_a_removed_operator_never_comes_back_through_another_instance(prod, monkeypatch):
    repo = get_repository()
    old_token, boss = _limited_operator(prod, "prod", "u-f1-b")
    run(admin.delete_user("u-f1-b", boss))
    accounts._valid_after["u-f1-b"] = (time.monotonic(), 0.0)                      # the other instance's memory
    assert _refused(_request(monkeypatch, old_token)) == (403, "forbidden")
    assert run(repo.get_user("u-f1-b")) is None


def test_b_production_an_account_deleted_by_its_owner_is_not_made_again(prod, monkeypatch):
    repo = get_repository()
    old_token, _boss = _limited_operator(prod, "prod", "u-f1-own")
    me = CurrentUser("u-f1-own", "u-f1-own@f1.it", TENANT, "operator", apartment_ids=["apt-1"])
    run(account.delete_account(Identity(uid=me.uid, email=me.email, display_name="", user=me, platform_manager=False)))
    assert "u-f1-own" not in prod.users                                            # really deleted (N3)
    accounts._valid_after["u-f1-own"] = (time.monotonic(), 0.0)
    assert _refused(_request(monkeypatch, old_token)) == (403, "forbidden")
    assert run(repo.get_user("u-f1-own")) is None


def test_firebase_silent_when_a_record_would_be_made_is_try_again(prod, monkeypatch):
    old_token, _boss = _limited_operator(prod, "prod", "u-f1-down")
    run(get_repository().delete_user("u-f1-down"))
    accounts._valid_after["u-f1-down"] = (time.monotonic(), 0.0)
    prod.down = True
    assert _refused(_request(monkeypatch, old_token)) == (503, "auth_unavailable")
    assert run(get_repository().get_user("u-f1-down")) is None


@pytest.mark.parametrize("env", ["staging", "prod"])
def test_the_first_admin_of_set_claims_still_gets_a_record(monkeypatch, env):
    """scripts/set_claims.py: claims in Firebase, no record yet; Firebase confirms them, so the record is made."""
    fb = _env(monkeypatch, env)
    fb.add("u-f1-first", "first@f1.it", {env: {"tenant_id": TENANT, "role": "admin"}})
    token = {"uid": "u-f1-first", "email": "first@f1.it", "email_verified": True, "iat": 1000,
             env: {"tenant_id": TENANT, "role": "admin"}}
    user = run(auth._member(_request(monkeypatch, token)))
    assert (user.tenant_id, user.role) == (TENANT, "admin")
    assert run(get_repository().get_user("u-f1-first")).role == "admin"


# -------- (c) the record goes while a convenience of /app/me is under way: never written back --------
def _gone(uid):
    """A person resolved a moment ago, whose record was removed since."""
    return CurrentUser(uid, f"{uid}@f1.it", TENANT, "operator", apartment_ids=["apt-1"])


def test_c_notification_preferences_never_make_the_record_again():
    run(push.set_prefs(NotificationPrefs(), _gone("u-f1-prefs")))
    assert run(get_repository().get_user("u-f1-prefs")) is None


def test_c_the_name_never_makes_the_record_again():
    me = _gone("u-f1-name")
    run(account.patch_profile(account.ProfilePatch(display_name="Torno"),
                              Identity(uid=me.uid, email=me.email, display_name="", user=me, platform_manager=False)))
    assert run(get_repository().get_user("u-f1-name")) is None


def test_c_push_routes_never_make_the_record_again():
    repo = get_repository()
    me = _gone("u-f1-push")
    run(push.subscribe(push.TokenBody(token="token-push-f1-1"), me))
    run(push.unsubscribe(push.TokenBody(token="token-push-f1-1"),
                         Identity(uid=me.uid, email=me.email, display_name="", user=me, platform_manager=False)))
    run(push.status(me))
    assert run(repo.get_user("u-f1-push")) is None


def test_c_another_holder_removed_meanwhile_is_not_written_back(monkeypatch):
    """subscribe takes the token from its other holders: one of them removed between the read and the write."""
    repo = get_repository()
    run(repo.upsert_user(User(uid="u-f1-me", email="me@f1.it", tenant_id=TENANT, role="operator")))
    stale = User(uid="u-f1-left", email="left@f1.it", tenant_id=TENANT, role="operator", push_tokens=["token-push-f1-2"])

    async def holders(token):
        return [stale.model_copy(deep=True)]
    monkeypatch.setattr(repo, "users_with_push_token", holders)
    run(push.subscribe(push.TokenBody(token="token-push-f1-2"), CurrentUser("u-f1-me", "me@f1.it", TENANT, "operator")))
    assert run(repo.get_user("u-f1-left")) is None
    assert "token-push-f1-2" in run(repo.get_user("u-f1-me")).push_tokens


# -------- the race between a request and the removal --------
def test_claims_taken_away_between_the_check_and_the_write_leave_no_record(prod, monkeypatch):
    """The request checked Firebase (claims there), the removal took them away, then the request wrote the record:
    Firebase is asked again after the write, and the record goes."""
    old_token, _boss = _limited_operator(prod, "prod", "u-f1-race")
    run(get_repository().delete_user("u-f1-race"))
    answers = [{"tenant_id": TENANT, "role": "operator"}, {}]
    monkeypatch.setattr(accounts, "current_env_claims", lambda uid: answers.pop(0))
    assert _refused(_request(monkeypatch, old_token)) == (403, "forbidden")
    assert run(get_repository().get_user("u-f1-race")) is None and answers == []


def _made_again_meanwhile(monkeypatch, uid):
    """While Firebase is being changed, a request of the person writes the record back (it checked before)."""
    real = accounts.delete_account

    def racing(*args, **kwargs):
        get_repository().users[uid] = User(uid=uid, email=f"{uid}@f1.it", tenant_id=TENANT, role="operator")
        return real(*args, **kwargs)
    monkeypatch.setattr(accounts, "delete_account", racing)


def test_the_admin_removal_deletes_the_record_again_after_firebase(prod, monkeypatch):
    _old_token, boss = _limited_operator(prod, "prod", "u-f1-again")
    _made_again_meanwhile(monkeypatch, "u-f1-again")
    run(admin.delete_user("u-f1-again", boss))
    assert run(get_repository().get_user("u-f1-again")) is None


def test_the_owner_deletion_deletes_the_record_again_after_firebase(prod, monkeypatch):
    _limited_operator(prod, "prod", "u-f1-own2")
    _made_again_meanwhile(monkeypatch, "u-f1-own2")
    me = CurrentUser("u-f1-own2", "u-f1-own2@f1.it", TENANT, "operator", apartment_ids=["apt-1"])
    run(account.delete_account(Identity(uid=me.uid, email=me.email, display_name="", user=me, platform_manager=False)))
    assert run(get_repository().get_user("u-f1-own2")) is None


def test_an_email_change_never_writes_back_a_record_removed_meanwhile(prod, monkeypatch):
    """_from_claims read the record, then adopted the new email of Firebase with a write of that copy."""
    repo = get_repository()
    prod.add("u-f1-mail", "nuova@f1.it", {"prod": {"tenant_id": TENANT, "role": "operator"}})
    run(repo.upsert_user(User(uid="u-f1-mail", email="vecchia@f1.it", tenant_id=TENANT, role="operator",
                              apartment_ids=["apt-1"])))
    token = {"uid": "u-f1-mail", "email": "nuova@f1.it", "email_verified": True, "iat": 1000,
             "prod": {"tenant_id": TENANT, "role": "operator"}}
    real = repo.get_user_by_email

    async def removed_now(email):                     # the removal lands while the request looks for a clash
        repo.users.pop("u-f1-mail", None)
        return await real(email)
    monkeypatch.setattr(repo, "get_user_by_email", removed_now)
    assert _refused(_request(monkeypatch, token)) == (403, "forbidden")
    assert run(repo.get_user("u-f1-mail")) is None


def test_an_apartment_deleted_never_writes_back_a_person_removed_meanwhile(monkeypatch):
    """remove_apartment (A6 deletion) takes the apartment out of every list, from a copy of the users read before."""
    from bff.repository import Apartment
    repo = get_repository()
    apt = Apartment(apartment_id="apt-f1-del", tenant_id=TENANT, name="F-1", instance_url="mock://builtin")
    run(repo.upsert_apartment(apt))
    stale = User(uid="u-f1-list", email="list@f1.it", tenant_id=TENANT, role="operator", apartment_ids=["apt-f1-del"])

    async def users(tenant_id=None):
        return [stale.model_copy(deep=True)]
    monkeypatch.setattr(repo, "list_users", users)
    run(admin.remove_apartment(apt))
    assert run(repo.get_user("u-f1-list")) is None
