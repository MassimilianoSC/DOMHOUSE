"""P-36 points 3, 4, 5 with a fake Firebase Auth (no network): what the dev mode cannot exercise because the accounts
module is switched off there. Stale claims, session revocation, invitation migration bound to a verified email,
deletion by email that never touches an account of another organisation, role change that never stays half done."""
import asyncio
import dataclasses
import types

import pytest
from fastapi import HTTPException

from bff import accounts, auth
from bff.auth import CurrentUser, _from_claims
from bff.config import get_settings
from bff.repository import Tenant, User, get_repository
from bff.routes import admin


class UserNotFoundError(Exception):
    pass


class FakeAuth:
    """The subset of firebase_admin.auth used by bff/accounts.py."""
    UserNotFoundError = UserNotFoundError

    def __init__(self):
        self.users: dict[str, types.SimpleNamespace] = {}
        self.calls: list[tuple] = []
        self.fail_claims = False

    def add(self, uid, email, claims=None, valid_after_ms=0, email_verified=False):
        self.users[uid] = types.SimpleNamespace(uid=uid, email=email, custom_claims=claims,
                                                tokens_valid_after_timestamp=valid_after_ms, email_verified=email_verified)

    def get_user(self, uid, app=None):
        self.calls.append(("get_user", uid))
        if uid not in self.users:
            raise UserNotFoundError(uid)
        return self.users[uid]

    def get_user_by_email(self, email, app=None):
        for u in self.users.values():
            if u.email == email:
                return u
        raise UserNotFoundError(email)

    def set_custom_user_claims(self, uid, claims, app=None):
        if self.fail_claims:
            raise RuntimeError("Auth non raggiungibile")
        self.users[uid].custom_claims = claims

    def revoke_refresh_tokens(self, uid, app=None):
        self.calls.append(("revoke", uid))
        self.users[uid].tokens_valid_after_timestamp = 5_000_000          # seconds 5000, in ms

    def delete_user(self, uid, app=None):
        self.calls.append(("delete", uid))
        del self.users[uid]


@pytest.fixture
def fb(monkeypatch):
    fake = FakeAuth()
    firebase = dataclasses.replace(get_settings(), auth_mode="firebase")
    monkeypatch.setattr(accounts, "get_settings", lambda: firebase)
    monkeypatch.setattr(accounts, "_auth", lambda: (fake, None))
    accounts._valid_after.clear()
    auth._known_tenants.clear()
    run(get_repository().upsert_tenant(Tenant(tenant_id="t-fb", name="Firebase finto")))
    return fake


def run(coro):
    return asyncio.run(coro)


def own(user):
    """DELETE /app/me takes the person's own identity (P-48, Fable note 4), as resolve_own_identity would give it."""
    from bff.auth import Identity

    return Identity(uid=user.uid, email=user.email, display_name=user.display_name, user=user,
                    platform_manager=run(get_repository().get_platform_member(user.email)) is not None)


# -------- point 3: claims and revocation --------
def test_role_change_updates_claims_and_revokes_sessions(fb):
    repo = get_repository()
    fb.add("u-fb-op", "op@fb.it", {"tenant_id": "t-fb", "role": "admin"})
    run(repo.upsert_user(User(uid="u-fb-op", email="op@fb.it", tenant_id="t-fb", role="admin")))
    run(repo.upsert_user(User(uid="u-fb-boss", email="boss@fb.it", tenant_id="t-fb", role="admin")))
    boss = CurrentUser("u-fb-boss", "boss@fb.it", "t-fb", "admin")
    out = run(admin.patch_user("u-fb-op", admin.UserPatch(role="viewer"), boss))
    assert out["role"] == "viewer"
    assert fb.users["u-fb-op"].custom_claims == {"tenant_id": "t-fb", "role": "viewer"}   # tenant kept, role changed
    assert ("revoke", "u-fb-op") in fb.calls
    assert accounts.token_revoked("u-fb-op", 1000.0) is True     # a token issued before: refused at once
    assert accounts.token_revoked("u-fb-op", 6000.0) is False    # a token issued after the change: fine


def test_failed_claim_update_leaves_the_record_as_it_was(fb):
    repo = get_repository()
    fb.add("u-fb-x", "x@fb.it", {"tenant_id": "t-fb", "role": "operator"})
    run(repo.upsert_user(User(uid="u-fb-x", email="x@fb.it", tenant_id="t-fb", role="operator")))
    fb.fail_claims = True
    boss = CurrentUser("u-fb-boss2", "boss2@fb.it", "t-fb", "admin")
    r = run(admin.patch_user("u-fb-x", admin.UserPatch(role="viewer"), boss))
    assert r.status_code == 502
    assert run(repo.get_user("u-fb-x")).role == "operator"        # nothing half done


def test_stale_claims_after_a_change_are_refused(fb):
    """A token minted before the change still carries the old role in its claims: the revocation check refuses it,
    so the old role can never come back through _from_claims."""
    fb.add("u-fb-old", "old@fb.it", {"tenant_id": "t-fb", "role": "viewer"}, valid_after_ms=5_000_000)
    assert accounts.token_revoked("u-fb-old", 4999.0) is True
    assert accounts.token_revoked("u-fb-gone", 4999.0) is True    # deleted account: refused too


def test_revocation_cache_is_bounded(fb, monkeypatch):
    fb.add("u-fb-cache", "c@fb.it", {}, valid_after_ms=0)
    accounts.token_revoked("u-fb-cache", 10.0)
    accounts.token_revoked("u-fb-cache", 10.0)
    assert fb.calls.count(("get_user", "u-fb-cache")) == 1          # cached
    now = accounts.time.monotonic()
    monkeypatch.setattr(accounts.time, "monotonic", lambda: now + accounts.REVOCATION_CACHE_S + 1)
    accounts.token_revoked("u-fb-cache", 10.0)
    assert fb.calls.count(("get_user", "u-fb-cache")) == 2          # re-read after REVOCATION_CACHE_S


# -------- point 4: the invitation belongs to a VERIFIED mailbox --------
def test_invitation_migrates_only_with_a_verified_email(fb):
    repo = get_repository()
    run(repo.upsert_user(User(uid="inv-fb-1", email="nuovo@fb.it", tenant_id="t-fb", role="operator")))
    with pytest.raises(HTTPException) as e:
        run(_from_claims(repo, {"uid": "fb-real-1", "email": "nuovo@fb.it", "email_verified": False}))
    assert e.value.detail["error"] == "email_not_verified"
    assert run(repo.get_user("inv-fb-1")) is not None and run(repo.get_user("fb-real-1")) is None   # untouched
    user = run(_from_claims(repo, {"uid": "fb-real-1", "email": "nuovo@fb.it", "email_verified": True}))
    assert (user.tenant_id, user.role) == ("t-fb", "operator")
    assert run(repo.get_user("inv-fb-1")) is None and run(repo.get_user("fb-real-1")).email == "nuovo@fb.it"


# -------- point 5: an org-level deletion never destroys a real or protected Firebase identity --------
def test_delete_account_protects_real_and_protected_identities(fb):
    # only a never-used account (unverified, no claims, not protected) is hard-deleted; the others are kept + revoked
    fb.add("fb-claims", "condivisa@fb.it", {"tenant_id": "t-altra", "role": "admin"})
    assert accounts.delete_account(None, "condivisa@fb.it") is False and "fb-claims" in fb.users

    fb.add("fb-verified", "vera@fb.it", None, email_verified=True)
    assert accounts.delete_account(None, "vera@fb.it") is False     # real person: kept
    assert "fb-verified" in fb.users and ("revoke", "fb-verified") in fb.calls

    fb.add("fb-manager", "gestore@fb.it", None)                     # a manager by email: protected by the caller
    assert accounts.delete_account(None, "gestore@fb.it", protect=True) is False
    assert "fb-manager" in fb.users

    fb.add("fb-never", "mai@fb.it", None)                           # unverified, no claims, invite never accepted
    assert accounts.delete_account(None, "mai@fb.it") is True
    assert "fb-never" not in fb.users and accounts.token_revoked("fb-never", 1.0) is True


def test_demotion_of_a_user_without_claims_revokes_sessions(fb):
    # F3 (D-70): the user signed in (real uid) but has no claims; set_role_claim does nothing, so patch_user must
    # revoke the sessions itself, or a valid token would keep the old role until it expires
    repo = get_repository()
    fb.add("u-noclaims", "nc@fb.it", None)                       # account exists, NO custom claims
    run(repo.upsert_user(User(uid="u-noclaims", email="nc@fb.it", tenant_id="t-fb", role="admin")))
    run(repo.upsert_user(User(uid="u-boss3", email="boss3@fb.it", tenant_id="t-fb", role="admin")))
    boss = CurrentUser("u-boss3", "boss3@fb.it", "t-fb", "admin")
    out = run(admin.patch_user("u-noclaims", admin.UserPatch(role="viewer"), boss))
    assert out["role"] == "viewer"
    assert ("revoke", "u-noclaims") in fb.calls                  # sessions revoked despite no claims
    assert accounts.token_revoked("u-noclaims", 1000.0) is True


def test_email_change_not_adopted_when_already_used(fb):
    # L6 (D-70): an email belongs to one uid only
    repo = get_repository()
    run(repo.upsert_user(User(uid="u-l6-a", email="a@l6.it", tenant_id="t-fb", role="viewer")))
    run(repo.upsert_user(User(uid="u-l6-b", email="b@l6.it", tenant_id="t-fb", role="viewer")))
    # u-l6-b signs in with a token whose email is now a@l6.it (changed in Firebase) — already used by u-l6-a
    c = lambda e: {"uid": "u-l6-b", "email": e, "email_verified": True, "tenant_id": "t-fb", "role": "viewer"}
    user = run(_from_claims(repo, c("a@l6.it")))
    assert user.email == "b@l6.it"                                   # not adopted
    assert run(repo.get_user("u-l6-b")).email == "b@l6.it"
    assert run(repo.get_user("u-l6-a")).email == "a@l6.it"           # untouched
    # the same person signing in again with their own uid and a genuinely new free email: adopted
    user = run(_from_claims(repo, c("nuova@l6.it")))
    assert user.email == "nuova@l6.it"


def test_owner_deleting_own_account_really_deletes_it(fb):
    # N3 (D-71): "Elimina il mio account" asked by the owner is a real deletion, also for a verified account;
    # the protection of F5 is for actions of an administrator on someone else
    from bff.routes import account

    repo = get_repository()
    fb.add("u-owner", "titolare@fb.it", {"tenant_id": "t-fb", "role": "viewer"}, email_verified=True)
    run(repo.upsert_user(User(uid="u-owner", email="titolare@fb.it", tenant_id="t-fb", role="viewer")))
    out = run(account.delete_account(own(CurrentUser("u-owner", "titolare@fb.it", "t-fb", "viewer"))))
    assert getattr(out, "status_code", 204) == 204
    assert "u-owner" not in fb.users and ("delete", "u-owner") in fb.calls
    assert run(repo.get_user("u-owner")) is None


def test_admin_removing_a_verified_user_still_only_revokes(fb):
    # the other side of N3: an administrator never destroys a real identity (F5 stays)
    repo = get_repository()
    fb.add("u-kept", "tenuto@fb.it", None, email_verified=True)
    run(repo.upsert_user(User(uid="u-kept", email="tenuto@fb.it", tenant_id="t-fb", role="viewer")))
    run(repo.upsert_user(User(uid="u-boss4", email="boss4@fb.it", tenant_id="t-fb", role="admin")))
    run(admin.delete_user("u-kept", CurrentUser("u-boss4", "boss4@fb.it", "t-fb", "admin")))
    assert "u-kept" in fb.users and ("revoke", "u-kept") in fb.calls
    assert run(repo.get_user("u-kept")) is None


def test_failed_session_revocation_does_not_end_in_500(fb, monkeypatch):
    # N5 (D-71): the role change is saved and effective (record, stream re-check); a revocation that fails is logged
    repo = get_repository()
    fb.add("u-n5", "n5@fb.it", None)
    run(repo.upsert_user(User(uid="u-n5", email="n5@fb.it", tenant_id="t-fb", role="operator")))
    run(repo.upsert_user(User(uid="u-boss5", email="boss5@fb.it", tenant_id="t-fb", role="admin")))

    def broken(uid, app=None):
        raise RuntimeError("Auth non raggiungibile")
    monkeypatch.setattr(fb, "revoke_refresh_tokens", broken)
    out = run(admin.patch_user("u-n5", admin.UserPatch(role="viewer"), CurrentUser("u-boss5", "boss5@fb.it", "t-fb", "admin")))
    assert getattr(out, "status_code", 200) == 200 and out["role"] == "viewer"
    assert run(repo.get_user("u-n5")).role == "viewer"


# -------- D-73: a platform manager deleting their own account --------
@pytest.fixture
def managers():
    """Replaces the platform managers for one test and puts the seed ones back afterwards."""
    from bff.repository import PlatformMember

    repo = get_repository()
    saved = run(repo.list_platform_members())
    for m in saved:
        run(repo.remove_platform_member(m.email))

    def use(*emails):
        for e in emails:
            run(repo.add_platform_member(PlatformMember(email=e)))
    yield use
    for m in run(repo.list_platform_members()):
        run(repo.remove_platform_member(m.email))
    for m in saved:
        run(repo.add_platform_member(m))


def _owner(fb, uid, email):
    fb.add(uid, email, {"tenant_id": "t-fb", "role": "viewer"}, email_verified=True)
    run(get_repository().upsert_user(User(uid=uid, email=email, tenant_id="t-fb", role="viewer")))
    return CurrentUser(uid, email, "t-fb", "viewer")


def test_last_platform_manager_cannot_delete_own_account(fb, managers):
    from bff.routes import account

    managers("solo@gestori.it")
    r = run(account.delete_account(own(_owner(fb, "u-solo-mgr", "solo@gestori.it"))))
    assert r.status_code == 409 and b"last_manager" in r.body
    repo = get_repository()
    assert run(repo.get_platform_member("solo@gestori.it")) is not None   # nothing changed
    assert run(repo.get_user("u-solo-mgr")) is not None and "u-solo-mgr" in fb.users


def test_platform_manager_deleting_own_account_leaves_the_platform(fb, managers):
    from bff.routes import account

    managers("uno@gestori.it", "altro@gestori.it")
    out = run(account.delete_account(own(_owner(fb, "u-mgr-2", "uno@gestori.it"))))
    assert getattr(out, "status_code", 204) == 204
    repo = get_repository()
    assert run(repo.get_platform_member("uno@gestori.it")) is None        # the role went with the account
    assert run(repo.get_platform_member("altro@gestori.it")) is not None
    assert "u-mgr-2" not in fb.users and run(repo.get_user("u-mgr-2")) is None


# -------- D-76: the app is called DOMHOUSE wherever it is seen --------
def test_invitation_email_carries_the_app_name():
    from bff import invites

    msg = invites._compose("nuovo@esempio.it", "Nuovo", "viewer", "Flatsharing", "admin@demo.it", None)
    assert msg["Subject"] == "Invito a DOMHOUSE" and msg["From"].startswith("DOMHOUSE")
    assert "a usare DOMHOUSE per Flatsharing" in msg.get_body(("plain",)).get_content()


# -------- P-47 / P-48: after "Elimina il mio account" the log keeps the actions, not the person --------
def test_own_account_deletion_leaves_removed_user_in_the_log(fb, managers):
    from bff import audit
    from bff.routes import account

    managers("via@gestori.it", "resta@gestori.it")
    me = _owner(fb, "u-via", "via@gestori.it")
    colleague = User(uid="u-x", email="x@fb.it", tenant_id="t-fb", role="viewer")
    run(get_repository().upsert_user(colleague))                               # still a member: stays readable (D-91)
    run(audit.record("invite_resent", audit.by_user(me), "t-fb", audit.user_target(colleague)))
    assert getattr(run(account.delete_account(own(me))), "status_code", 204) == 204
    items = run(audit.page("t-fb", 100, None, viewer="admin"))["items"]
    gone = next(i for i in items if i["action"] == "account_deleted")
    assert gone["actor"] == {"kind": "user", "email": None, "display_name": None, "removed": True, "role": "viewer"}
    assert gone["target"]["removed"] is True and gone["target"]["label"] is None
    earlier = next(i for i in items if i["action"] == "invite_resent")
    assert earlier["actor"]["removed"] is True and earlier["target"]["label"] == "x@fb.it"   # others stay readable
    platform = run(audit.page(None, 100, None, viewer="platform"))["items"]
    left = next(i for i in platform if i["action"] == "account_deleted")
    assert left["target"]["type"] == "manager" and left["target"]["removed"] is True


# -------- Fable note 4 (P-48): a platform manager without an organisation deletes their own account --------
def test_manager_without_organisation_deletes_own_account(fb, managers):
    from bff.auth import Identity
    from bff.routes import account

    managers("solo-piattaforma@gestori.it", "altro2@gestori.it")
    fb.add("u-only-platform", "solo-piattaforma@gestori.it", {}, email_verified=True)
    me = Identity(uid="u-only-platform", email="solo-piattaforma@gestori.it", display_name="", user=None, platform_manager=True)
    assert getattr(run(account.delete_account(me)), "status_code", 204) == 204
    repo = get_repository()
    assert run(repo.get_platform_member("solo-piattaforma@gestori.it")) is None
    assert "u-only-platform" not in fb.users                                   # the Firebase account is gone
    left = next(i for i in run(audit_page(None)) if i["action"] == "account_deleted")
    assert left["target"]["removed"] is True


def test_last_manager_without_organisation_is_refused(fb, managers):
    from bff.auth import Identity
    from bff.routes import account

    managers("ultimo@gestori.it")
    fb.add("u-last-platform", "ultimo@gestori.it", {}, email_verified=True)
    me = Identity(uid="u-last-platform", email="ultimo@gestori.it", display_name="", user=None, platform_manager=True)
    r = run(account.delete_account(me))
    assert r.status_code == 409 and b"last_manager" in r.body and "u-last-platform" in fb.users


async def audit_page(tenant_id):
    from bff import audit

    return (await audit.page(tenant_id, 100, None, viewer="platform"))["items"]
