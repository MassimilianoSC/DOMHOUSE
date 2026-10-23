"""D-178 (D-183 point 128): a platform manager without an organisation saves the name and signs out everywhere, with no
403; a manager who is also a member updates both records. In-process, dev auth, memory repository."""
import asyncio

import httpx

from bff import accounts
from bff.main import app
from bff.repository import get_repository

ALONE, BOTH = "piattaforma@demo.it", "m.cracchiolo@hqe.it"          # seed: a manager only; a manager and an admin


def run(coro):
    return asyncio.run(coro)


async def call(method, path, who, **kw):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, path, headers={"X-Dev-User": who}, **kw)


def test_a_manager_without_organisation_saves_the_name_and_signs_out(monkeypatch):
    revoked = []
    monkeypatch.setattr(accounts, "revoke_sessions", lambda uid: revoked.append(uid))
    r = run(call("PATCH", "/app/me", ALONE, json={"display_name": "  Gestore Uno  "}))
    assert r.status_code == 200 and r.json() == {"display_name": "Gestore Uno"}
    assert run(get_repository().get_platform_member(ALONE)).display_name == "Gestore Uno"
    me = run(call("GET", "/app/me", ALONE)).json()
    assert me["tenant"] is None and me["user"]["display_name"] == "Gestore Uno"
    r = run(call("POST", "/app/me/revoke-sessions", ALONE))
    assert r.status_code == 204 and revoked == [f"dev-{ALONE}"]


def test_a_manager_who_is_also_a_member_updates_both():
    repo = get_repository()
    before = run(repo.get_user_by_email(BOTH)).display_name
    try:
        assert run(call("PATCH", "/app/me", BOTH, json={"display_name": "Massimiliano C."})).status_code == 200
        assert run(repo.get_user_by_email(BOTH)).display_name == "Massimiliano C."
        assert run(repo.get_platform_member(BOTH)).display_name == "Massimiliano C."
    finally:
        run(call("PATCH", "/app/me", BOTH, json={"display_name": before}))
