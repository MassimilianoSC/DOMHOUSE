"""P-50 (D-86), what the end-to-end suite cannot do quickly: the expiry of a support access (logged once, refused at once,
the stream closed at the exact deadline) and the isolation of pushes. In-process, dev auth, memory repository."""
import asyncio
import time
from datetime import UTC, datetime, timedelta

import httpx

from bff import push
from bff.auth import Identity
from bff.main import app
from bff.repository import get_repository
from bff.routes import platform

TID, APT = "t-altra-demo", "apt-altra-01"
MANAGER = "m.cracchiolo@hqe.it"   # seed: admin of t-flatsharing-demo and platform manager
ME = Identity(uid="dev-owner", email=MANAGER, display_name="Massimiliano Cracchiolo", user=None, platform_manager=True)


def run(coro):
    return asyncio.run(coro)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def call(method, path, support=True, **kw):
    headers = {"X-Dev-User": MANAGER, **({"X-Support-Tenant": TID} if support else {})}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t", timeout=30) as c:
        return await c.request(method, path, headers=headers, **kw)


def open_access(reason="Prova"):
    row = run(platform.open_support_access(TID, platform.SupportOpen(hours=1, reason=reason), identity=ME))
    return row["access_id"]


def close(aid):
    run(platform.close_tenant_support_access(TID, aid, identity=ME))


def test_expiry_refuses_at_once_and_is_logged_once():
    aid = open_access()
    assert run(call("GET", "/app/me")).json()["support"]["access_id"] == aid
    past = iso(datetime.now(UTC) - timedelta(seconds=1))
    run(get_repository().update_support_access(aid, {"expires_at": past}))
    for _ in range(2):
        r = run(call("GET", "/app/apartments"))
        assert r.status_code == 403 and r.json()["error"] == "support_expired"
    entries = [e for e in run(get_repository().list_audit(TID, 100)) if e.target.id == aid]
    assert [e.action for e in entries] == ["support_access_expired", "support_access_opened"]   # expired: once
    assert entries[0].actor.kind == "system"
    assert run(call("GET", "/app/me", support=False)).json()["tenant"]["tenant_id"] == "t-flatsharing-demo"  # back home


def test_stream_closes_at_the_exact_expiry():
    aid = open_access("Stream")
    soon = iso(datetime.now(UTC) + timedelta(seconds=1.5))
    run(get_repository().update_support_access(aid, {"expires_at": soon}))
    start = time.monotonic()
    r = run(call("GET", f"/app/apartments/{APT}/stream"))   # the ASGI transport returns when the stream ends
    elapsed = time.monotonic() - start
    assert r.status_code == 200 and ": connected" in r.text
    assert elapsed < 10, elapsed                                  # the deadline, not the 25 s ping or the 30 s recheck
    close(aid)


def test_a_manager_removed_from_the_platform_loses_the_access():
    aid = open_access("Rimosso")
    repo = get_repository()
    member = run(repo.get_platform_member(MANAGER))
    run(repo.remove_platform_member(MANAGER))
    try:
        r = run(call("GET", "/app/me"))
        assert r.status_code == 403 and r.json()["error"] == "support_expired"
    finally:
        run(repo.add_platform_member(member))
    close(aid)


def test_push_is_never_tied_to_the_assisted_organisation(monkeypatch):
    aid = open_access("Push")
    repo = get_repository()
    r = run(call("POST", "/app/push/subscribe", json={"token": "tok-support-test"}))
    assert r.status_code == 200
    holders = run(repo.users_with_push_token("tok-support-test"))
    assert [(u.uid, u.tenant_id) for u in holders] == [("dev-owner", "t-flatsharing-demo")]   # their own organisation
    assert all(u.uid != "dev-owner" for u in run(repo.list_users(TID)))                     # never a member here
    sent = []
    monkeypatch.setattr(push, "_send_multicast", lambda tokens, data, headers: sent.append(tokens))
    apt = run(repo.get_apartment(APT))
    run(push.send_to_tenant(TID, "approvals", *push.approval_push(apt, "apv-sa", "ok?", None)))
    assert all("tok-support-test" not in t for t in sent)
    run(call("DELETE", "/app/push/subscribe", json={"token": "tok-support-test"}))
    close(aid)


# -------- D-88 (Fable) --------
def test_opening_and_closing_show_the_person_to_the_admin():
    aid = open_access("Persona visibile")
    close(aid)
    items = run(_admin_audit())
    mine = [i for i in items if i["target"]["id"] == aid]
    assert [i["action"] for i in mine] == ["support_access_closed", "support_access_opened"]
    for i in mine:
        assert i["actor"]["kind"] == "support" and i["actor"]["email"] == MANAGER, i["actor"]


async def _admin_audit():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/app/admin/audit", params={"limit": 100}, headers={"X-Dev-User": "admin@altra.it"})
        return r.json()["items"]


def test_two_closings_at_once_write_one_entry():
    from bff import audit, support

    aid = open_access("Doppio")
    a = run(get_repository().get_support_access(aid))

    async def both():
        return await asyncio.gather(support.close(a, audit.SYSTEM, "admin"), support.close(a, audit.SYSTEM, "platform"))
    assert sorted(run(both())) == [False, True]
    entries = [e for e in run(get_repository().list_audit(TID, 100)) if e.target.id == aid]
    assert [e.action for e in entries].count("support_access_closed") == 1


def test_expiry_entry_is_retried_when_the_first_write_fails(monkeypatch):
    from bff import audit, support

    aid = open_access("Scadenza")
    run(get_repository().update_support_access(aid, {"expires_at": iso(datetime.now(UTC) - timedelta(seconds=1))}))
    real = audit.record

    async def failing(action, *a, **kw):
        if action == "support_access_expired":
            raise RuntimeError("Firestore non raggiungibile")
        return await real(action, *a, **kw)
    monkeypatch.setattr(audit, "record", failing)
    run(support.note_expiry(run(get_repository().get_support_access(aid))))
    monkeypatch.setattr(audit, "record", real)
    run(support.note_expiry(run(get_repository().get_support_access(aid))))
    actions = [e.action for e in run(get_repository().list_audit(TID, 100)) if e.target.id == aid]
    assert actions.count("support_access_expired") == 1


def test_the_role_inside_is_always_operator():
    aid = open_access("Ruolo")
    run(get_repository().update_support_access(aid, {"role": "admin"}))       # a tampered or future record
    r = run(call("GET", "/app/admin/users"))
    assert r.status_code == 403, r.text
    assert run(call("GET", "/app/me")).json()["role"] == "operator"
    close(aid)


def test_removing_the_manager_closes_their_accesses():
    from bff.repository import PlatformMember

    repo = get_repository()
    run(repo.add_platform_member(PlatformMember(email="temporaneo@hqe.it")))
    temp = Identity(uid="dev-temporaneo@hqe.it", email="temporaneo@hqe.it", display_name="", user=None, platform_manager=True)
    aid = run(platform.open_support_access(TID, platform.SupportOpen(hours=2, reason="Temporaneo"), identity=temp))["access_id"]
    assert run(platform.remove_manager({"email": "temporaneo@hqe.it"}, identity=ME)).status_code == 204
    a = run(repo.get_support_access(aid))
    assert a.closed_at is not None
    assert "support_access_closed" in [e.action for e in run(repo.list_audit(TID, 100)) if e.target.id == aid]
