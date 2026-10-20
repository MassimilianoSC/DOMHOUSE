"""P-36 (D-62): the platform manager role, in Firebase mode with fake tokens. The role is a record matched against the
token's VERIFIED email; it opens /app/me and /app/platform/* only, never the organisation routes (resolve_user)."""
import asyncio
import dataclasses

import pytest
from fastapi import HTTPException

from bff import accounts, auth
from bff.config import get_settings
from bff.repository import PlatformMember, Tenant, User, get_repository


class FakeRequest:
    headers = {"Authorization": "Bearer token-finto"}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def firebase(monkeypatch):
    """Firebase auth mode; `firebase.claims` is what the fake token verifies to."""
    monkeypatch.setattr(auth, "get_settings", lambda: dataclasses.replace(get_settings(), auth_mode="firebase"))
    monkeypatch.setattr(accounts, "token_revoked", lambda uid, iat: False)
    state = type("S", (), {"claims": {}})()
    monkeypatch.setattr(auth, "_verify_firebase_token", lambda token: dict(state.claims))
    repo = get_repository()
    run(repo.add_platform_member(PlatformMember(email="Gestore.Solo@Piattaforma.it")))
    run(repo.add_platform_member(PlatformMember(email="gestore.con.org@piattaforma.it")))
    run(repo.upsert_tenant(Tenant(tenant_id="t-plat-org", name="Org del gestore")))
    auth._known_tenants.clear()
    return state


def claims(uid, email, verified=True, tenant=None, role=None):
    c = {"uid": uid, "email": email, "email_verified": verified, "iat": 0}
    if tenant:
        c.update(tenant_id=tenant, role=role)
    return c


def test_manager_without_organisation(firebase):
    firebase.claims = claims("u-plat-solo", "gestore.solo@piattaforma.it")
    ident = run(auth.resolve_identity(FakeRequest()))
    assert ident.platform_manager is True and ident.user is None
    assert run(auth.require_platform(FakeRequest())).email == "gestore.solo@piattaforma.it"
    with pytest.raises(HTTPException) as e:                       # organisation routes stay closed
        run(auth.resolve_user(FakeRequest()))
    assert e.value.status_code == 403


def test_unverified_email_gets_no_role(firebase):
    firebase.claims = claims("u-plat-unv", "gestore.solo@piattaforma.it", verified=False)
    with pytest.raises(HTTPException) as e:
        run(auth.resolve_identity(FakeRequest()))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        run(auth.require_platform(FakeRequest()))


def test_manager_with_organisation_keeps_both_apart(firebase):
    firebase.claims = claims("u-plat-org", "gestore.con.org@piattaforma.it", tenant="t-plat-org", role="viewer")
    ident = run(auth.resolve_identity(FakeRequest()))
    assert ident.platform_manager is True and ident.user.tenant_id == "t-plat-org" and ident.user.role == "viewer"
    user = run(auth.resolve_user(FakeRequest()))
    assert user.role == "viewer" and not user.is_admin            # the platform role does not raise the tenant role


def test_member_of_an_organisation_without_role(firebase):
    run(get_repository().upsert_user(User(uid="u-plat-no", email="normale@org.it", tenant_id="t-plat-org", role="admin")))
    firebase.claims = claims("u-plat-no", "normale@org.it", tenant="t-plat-org", role="admin")
    assert run(auth.resolve_identity(FakeRequest())).platform_manager is False
    with pytest.raises(HTTPException) as e:
        run(auth.require_platform(FakeRequest()))
    assert e.value.status_code == 403 and "piattaforma" in e.value.detail["message"]


def test_nobody_without_organisation_nor_role(firebase):
    firebase.claims = claims("u-plat-none", "sconosciuto@altrove.it")
    with pytest.raises(HTTPException) as e:
        run(auth.resolve_identity(FakeRequest()))
    assert e.value.status_code == 403
