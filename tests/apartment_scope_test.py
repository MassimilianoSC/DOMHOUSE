"""P-18 in-process: the one visibility rule, and an SSE stream already open that closes when its apartment is taken
away from the user (D-44). The end-to-end cases (404, list, stream refused, admin API) are in backend_phase3_test."""
import asyncio
import json

import pytest

from bff.auth import CurrentUser, sees, still_sees
from bff.repository import Apartment, Tenant, User, get_repository
from bff.routes import apartments
from bff.sse_hub import SseEvent

TENANT = "t-scope-test"
APT = "apt-scope-a"


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize("role, ids, expected", [
    ("viewer", None, True), ("viewer", [], False), ("viewer", [APT], True), ("viewer", ["apt-other"], False),
    ("operator", ["apt-other"], False), ("admin", [], True), ("admin", ["apt-other"], True),
])
def test_one_rule(role, ids, expected):
    assert sees(role, ids, APT) is expected
    assert CurrentUser("u", "e", TENANT, role, apartment_ids=ids).can_see(APT) is expected


class FakeHub:
    def __init__(self):
        self.subscribers: set[asyncio.Queue] = set()

    def start(self, _last_event_id):
        pass

    def replay_after(self, _last_event_id):
        return []

    def push(self, n: int):
        env = {"id": str(n), "event": "device.state", "ts": "2026-10-16T10:00:00.000Z", "apartment_id": APT, "data": {}}
        for q in self.subscribers:
            q.put_nowait(SseEvent(id=str(n), event="device.state", data=json.dumps(env), received=0.0))


class FakeRequest:
    headers: dict = {}

    async def is_disconnected(self):
        return False


@pytest.fixture
def scoped(monkeypatch):
    hub = FakeHub()
    monkeypatch.setattr(apartments, "hub_manager", type("HM", (), {"hub": staticmethod(lambda _apt: hub)})())
    monkeypatch.setattr(apartments, "ACCESS_RECHECK_SECONDS", 0.0)  # check at every event

    async def setup():
        repo = get_repository()
        await repo.upsert_tenant(Tenant(tenant_id=TENANT, name="Scope"))
        await repo.upsert_apartment(Apartment(apartment_id=APT, tenant_id=TENANT, name="A", instance_url="mock://builtin"))
        await repo.upsert_user(User(uid="u-scope", email="scope@test.it", tenant_id=TENANT, role="viewer", apartment_ids=[APT]))
    run(setup())
    return hub, CurrentUser("u-scope", "scope@test.it", TENANT, "viewer", apartment_ids=[APT])


async def _open(user):
    resp = await apartments.stream(APT, FakeRequest(), user)
    it = resp.body_iterator
    assert "connected" in await it.__anext__()
    return it


def test_open_stream_closes_when_apartment_is_removed(scoped):
    hub, user = scoped

    async def scenario():
        it = await _open(user)
        hub.push(1)
        assert '"id": "1"' in await asyncio.wait_for(it.__anext__(), 1)   # still visible: delivered
        stored = await get_repository().get_user("u-scope")
        stored.apartment_ids = []
        await get_repository().upsert_user(stored)
        hub.push(2)
        with pytest.raises(StopAsyncIteration):                          # closed, event 2 not delivered
            await asyncio.wait_for(it.__anext__(), 1)
        assert hub.subscribers == set()
    run(scenario())


def test_open_stream_closes_when_user_is_deleted(scoped):
    hub, user = scoped

    async def scenario():
        it = await _open(user)
        await get_repository().delete_user("u-scope")
        hub.push(3)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(it.__anext__(), 1)
    run(scenario())


def test_still_sees_uses_the_reread_role_not_the_request_one(scoped):
    # F3 (D-70): a request made as admin, but whose record now says viewer with no apartments, loses the stream
    hub, _ = scoped
    admin_req = CurrentUser("u-scope", "scope@test.it", TENANT, "admin", apartment_ids=None)
    assert run(still_sees(admin_req, APT)) is True                 # record viewer with [APT]: visible
    assert run(still_sees(admin_req, "apt-altro")) is False        # request role admin does NOT grant everything

    async def narrow():
        stored = await get_repository().get_user("u-scope")
        stored.apartment_ids = []
        await get_repository().upsert_user(stored)
    run(narrow())
    assert run(still_sees(admin_req, APT)) is False                # the record (viewer, apartments []) governs


def test_open_stream_closes_after_sessions_are_revoked(scoped, monkeypatch):
    """P-36 point 10: 'Esci da tutti i dispositivi' revokes the sessions; a stream opened before must end too."""
    from bff import accounts

    hub, _ = scoped
    revoked = {"now": False}
    monkeypatch.setattr(accounts, "token_revoked", lambda uid, iat: revoked["now"] and iat == 1000.0)
    user = CurrentUser("u-scope", "scope@test.it", TENANT, "viewer", apartment_ids=[APT], issued_at=1000.0)

    async def scenario():
        it = await _open(user)
        hub.push(4)
        assert '"id": "4"' in await asyncio.wait_for(it.__anext__(), 1)   # session valid: delivered
        revoked["now"] = True
        hub.push(5)
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(it.__anext__(), 1)
    run(scenario())


def test_dev_mode_streams_skip_the_revocation_check(scoped, monkeypatch):
    from bff import accounts

    hub, user = scoped                       # issued_at 0: no Firebase token, nothing to revoke
    monkeypatch.setattr(accounts, "token_revoked", lambda uid, iat: (_ for _ in ()).throw(AssertionError("chiamato")))

    async def scenario():
        it = await _open(user)
        hub.push(6)
        assert '"id": "6"' in await asyncio.wait_for(it.__anext__(), 1)
    run(scenario())


def test_deletion_stops_the_upstream_stream():
    """P-36 point 9: a deleted apartment's hub is stopped and forgotten (before, deletion left it running)."""
    from bff.routes.admin import remove_apartment
    from bff.sse_hub import hub_manager

    async def scenario():
        repo = get_repository()
        apt = Apartment(apartment_id="apt-drop", tenant_id=TENANT, name="Da cancellare", instance_url="mock://builtin")
        await repo.upsert_apartment(apt)
        hub = hub_manager.hub(apt)
        hub.task = asyncio.create_task(asyncio.sleep(3600))
        await remove_apartment(apt)
        await asyncio.sleep(0)
        assert "apt-drop" not in hub_manager.hubs and hub.task.cancelled()
        assert await repo.get_apartment("apt-drop") is None
        assert await repo.reserve_apartment_id("apt-drop") is False            # and the id stays used
    run(scenario())
