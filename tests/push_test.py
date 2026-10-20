"""Push notifications (P-11): message format agreed with the PWA, token pruning, hooks that never block the stream.
FCM is replaced by a fake send_each_for_multicast_async; no network, memory repository."""
import asyncio
import dataclasses
import json
from types import SimpleNamespace

import pytest
from firebase_admin import exceptions, messaging

from bff import push
from bff.config import get_settings
from bff.repository import Apartment, NotificationPrefs, Tenant, User, get_repository
from bff.sse_hub import SseEvent

TENANT = "t-push-test"
APT = Apartment(apartment_id="apt-push", tenant_id=TENANT, name="Milano Centro", instance_url="mock://builtin")
TS = "2026-10-16T10:00:00.000Z"


def run(coro):
    return asyncio.run(coro)


def event(name: str, data: dict) -> SseEvent:
    env = {"id": "1", "event": name, "ts": TS, "apartment_id": APT.apartment_id, "correlation_id": None, "data": data}
    return SseEvent(id="1", event=name, data=json.dumps(env), received=0.0)


async def drain():
    while push._tasks:
        await asyncio.gather(*list(push._tasks), return_exceptions=True)


@pytest.fixture
def users():
    """Tenant with two opted-in users (tokens a, b, c, d) and one who turned approvals off (token z)."""
    async def setup():
        repo = get_repository()
        await repo.upsert_tenant(Tenant(tenant_id=TENANT, name="Push"))
        await repo.upsert_user(User(uid="u-push-1", email="p1@test.it", tenant_id=TENANT, role="admin", push_tokens=["tok-a", "tok-b"]))
        await repo.upsert_user(User(uid="u-push-2", email="p2@test.it", tenant_id=TENANT, role="operator", push_tokens=["tok-c", "tok-d"]))
        await repo.upsert_user(User(uid="u-push-3", email="p3@test.it", tenant_id=TENANT, role="viewer", push_tokens=["tok-z"],
                                    notification_prefs=NotificationPrefs(approvals=False, offline=False)))
    run(setup())
    push._health_down.clear()


@pytest.fixture
def fcm(monkeypatch):
    """FCM on, sends recorded; `fcm.fail` maps token -> exception, `fcm.gate` (an Event) holds the send if set."""
    monkeypatch.setattr(push, "get_settings", lambda: dataclasses.replace(get_settings(), fcm_enabled=True))
    state = SimpleNamespace(sent=[], fail={}, gate=None)

    async def fake_send(msg, dry_run=False, app=None):
        if state.gate is not None:
            await state.gate.wait()
        state.sent.append(msg)
        responses = [SimpleNamespace(success=t not in state.fail, exception=state.fail.get(t)) for t in msg.tokens]
        ok = sum(r.success for r in responses)
        return SimpleNamespace(responses=responses, success_count=ok, failure_count=len(responses) - ok)

    monkeypatch.setattr(messaging, "send_each_for_multicast_async", fake_send)
    return state


# -------- message format (bff/API.md, «Notifiche push») --------
def test_approval_message():
    data, headers = push.approval_push(APT, "apv-1", "Accendere il riscaldamento?", TS)
    assert data == {"title": "Milano Centro: approvazione richiesta", "body": "Accendere il riscaldamento?",
                    "link": "/a/apt-push/approvazioni", "tag": "approval:apv-1", "kind": "approval",
                    "apartment_id": "apt-push", "approval_id": "apv-1", "ts": TS}
    assert headers == {"Urgency": "high", "TTL": "3600"}


def test_approval_blank_description_keeps_a_body():
    # the PWA (lib/pushPayload.ts, toNotice) shows a generic notice opening "/" when body is missing or blank
    for description in ("", "   ", None):
        data, _ = push.approval_push(APT, "apv-1", description, TS)
        assert data["body"] == "Il motore chiede il tuo consenso" and data["link"] == "/a/apt-push/approvazioni"


def test_device_offline_message():
    data, headers = push.device_offline_push(APT, "dev-7", "Termostato sala", 15, TS)
    assert data["kind"] == "device_offline" and data["tag"] == "offline:apt-push:dev-7"
    assert data["link"] == "/a/apt-push" and data["device_id"] == "dev-7" and "approval_id" not in data
    assert data["body"] == "Termostato sala non risponde da oltre 15 minuti"
    assert headers == {"Urgency": "high", "TTL": "86400"}


def test_instance_down_message():
    data, headers = push.instance_down_push(APT, None)
    assert data["kind"] == "instance_down" and data["tag"] == "instance:apt-push" and data["link"] == "/a/apt-push"
    assert "ts" not in data and "device_id" not in data and "approval_id" not in data
    assert headers["TTL"] == "86400"


def test_body_cut_and_size_under_4kb():
    long_apt = APT.model_copy(update={"name": "N" * 120})  # longest name the admin form accepts
    data, headers = push.approval_push(long_apt, "a" * 64, "x" * 5000, TS)
    assert len(data["body"]) == push.BODY_MAX and data["body"].endswith("…")
    assert all(isinstance(v, str) for v in data.values())
    encoded = messaging._MessagingService.encode_message(
        messaging.Message(token="t" * 200, data=data, webpush=messaging.WebpushConfig(headers=headers)))
    assert len(json.dumps(encoded, ensure_ascii=False).encode()) < 4096
    assert "notification" not in encoded and "fcm_options" not in encoded["webpush"]


# -------- sending --------
def test_send_only_to_opted_in_users_data_only(users, fcm):
    n = run(push.send_to_tenant(TENANT, "approvals", *push.approval_push(APT, "apv-2", "ok?", TS)))
    assert n == 4
    msg = fcm.sent[0]
    assert sorted(msg.tokens) == ["tok-a", "tok-b", "tok-c", "tok-d"]
    assert msg.notification is None and msg.webpush.fcm_options is None and msg.webpush.notification is None
    assert msg.data["link"] == "/a/apt-push/approvazioni" and msg.webpush.headers == {"Urgency": "high", "TTL": "3600"}


def test_fcm_disabled_sends_nothing(users, monkeypatch, fcm):
    monkeypatch.setattr(push, "get_settings", lambda: dataclasses.replace(get_settings(), fcm_enabled=False))
    assert run(push.send_to_tenant(TENANT, "approvals", *push.approval_push(APT, "apv-3", "ok?", TS))) == 4
    assert fcm.sent == []


def test_prune_only_dead_tokens(users, fcm):
    fcm.fail = {"tok-a": messaging.UnregisteredError("gone"), "tok-b": messaging.SenderIdMismatchError("other project"),
                "tok-c": exceptions.InvalidArgumentError("bad message")}
    run(push.send_to_tenant(TENANT, "approvals", *push.approval_push(APT, "apv-4", "ok?", TS)))
    tokens = {u.uid: u.push_tokens for u in run(get_repository().list_users(TENANT))}
    assert tokens["u-push-1"] == []                      # unregistered + sender mismatch: removed
    assert tokens["u-push-2"] == ["tok-c", "tok-d"]       # INVALID_ARGUMENT is about the message: kept
    assert tokens["u-push-3"] == ["tok-z"]                # not targeted, untouched


def test_push_only_to_users_who_see_the_apartment(users, fcm):
    """P-18: a user limited to other apartments gets nothing; an admin's leftover list is ignored."""
    async def setup():
        repo = get_repository()
        await repo.upsert_user(User(uid="u-push-4", email="p4@test.it", tenant_id=TENANT, role="viewer",
                                    push_tokens=["tok-other"], apartment_ids=["apt-altro"]))
        await repo.upsert_user(User(uid="u-push-5", email="p5@test.it", tenant_id=TENANT, role="viewer",
                                    push_tokens=["tok-none"], apartment_ids=[]))
        await repo.upsert_user(User(uid="u-push-6", email="p6@test.it", tenant_id=TENANT, role="operator",
                                    push_tokens=["tok-mine"], apartment_ids=["apt-push"]))
        await repo.upsert_user(User(uid="u-push-7", email="p7@test.it", tenant_id=TENANT, role="admin",
                                    push_tokens=["tok-admin"], apartment_ids=["apt-altro"]))
    run(setup())
    run(push.send_to_tenant(TENANT, "approvals", *push.approval_push(APT, "apv-9", "ok?", TS)))
    sent = set(fcm.sent[0].tokens)
    assert {"tok-mine", "tok-admin", "tok-a", "tok-b", "tok-c", "tok-d"} <= sent
    assert not {"tok-other", "tok-none", "tok-z"} & sent


def test_push_never_crosses_tenants(users, fcm):
    """P-36: an event of another organisation's apartment reaches only that organisation's users."""
    async def setup():
        repo = get_repository()
        await repo.upsert_tenant(Tenant(tenant_id="t-push-other", name="Altra"))
        await repo.upsert_user(User(uid="u-push-other", email="po@test.it", tenant_id="t-push-other", role="admin",
                                    push_tokens=["tok-other-tenant"]))
    run(setup())
    other_apt = APT.model_copy(update={"apartment_id": "apt-push-other", "tenant_id": "t-push-other"})
    run(push.send_to_tenant(other_apt.tenant_id, "approvals", *push.approval_push(other_apt, "apv-x", "ok?", TS)))
    assert set(fcm.sent[0].tokens) == {"tok-other-tenant"}
    fcm.sent.clear()
    run(push.send_to_tenant(TENANT, "approvals", *push.approval_push(APT, "apv-y", "ok?", TS)))
    assert "tok-other-tenant" not in set(fcm.sent[0].tokens)


def test_token_belongs_to_one_person_across_tenants(users):
    """P-36 point 11: A of another organisation left without unsubscribing; B signs in on the same browser and
    registers the same device token: A's pushes must no longer reach that device."""
    from bff.auth import CurrentUser
    from bff.routes import push as push_routes

    async def scenario():
        repo = get_repository()
        await repo.upsert_tenant(Tenant(tenant_id="t-push-a", name="A"))
        await repo.upsert_user(User(uid="u-dev-a", email="a@dev.it", tenant_id="t-push-a", role="viewer",
                                    push_tokens=["tok-same-device", "tok-a-phone"]))
        b = CurrentUser("u-push-1", "p1@test.it", TENANT, "admin")
        out = await push_routes.subscribe(push_routes.TokenBody(token="tok-same-device"), b)
        assert out["subscribed"] is True
        assert (await repo.get_user("u-dev-a")).push_tokens == ["tok-a-phone"]          # removed from A only
        assert "tok-same-device" in (await repo.get_user("u-push-1")).push_tokens
        assert [u.uid for u in await repo.users_with_push_token("tok-same-device")] == ["u-push-1"]
    run(scenario())


# -------- stream hooks --------
def test_hook_does_not_block_the_stream(users, fcm):
    async def scenario():
        fcm.gate = asyncio.Event()
        await asyncio.wait_for(push.on_stream_event(APT, event("approval.pending", {"approval_id": "apv-5", "description": "d"})), 0.5)
        assert fcm.sent == []                            # still waiting on FCM, yet the hook has returned
        fcm.gate.set()
        await drain()
    run(scenario())
    assert len(fcm.sent) == 1 and fcm.sent[0].data["tag"] == "approval:apv-5" and fcm.sent[0].data["ts"] == TS


def test_hook_failure_is_logged_not_raised(users, fcm, monkeypatch):
    logged = []
    monkeypatch.setattr(push, "warn", lambda msg, **kw: logged.append((msg, kw)))

    async def boom(*_a, **_k):
        raise RuntimeError("fcm down")
    monkeypatch.setattr(messaging, "send_each_for_multicast_async", boom)

    async def scenario():
        await push.on_stream_event(APT, event("approval.pending", {"approval_id": "apv-6"}))
        await drain()
    run(scenario())
    assert logged and logged[0][0] == "push task failed" and "fcm down" in logged[0][1]["error"]


def test_instance_down_once_until_back_up(users, fcm):
    async def scenario():
        for status in ("down", "down", "ok", "down"):
            await push.on_stream_event(APT, event("instance.health", {"status": status}))
            await drain()
    run(scenario())
    assert [m.data["kind"] for m in fcm.sent] == ["instance_down", "instance_down"]


def test_unsubscribe_removes_the_token_from_every_holder(users):
    """F4 (D-70): on a shared device the token may still be registered to a previous user; unsubscribe clears it from
    everyone, so no leftover push reaches the device after sign-out."""
    from bff.auth import CurrentUser
    from bff.routes import push as push_routes

    async def scenario():
        repo = get_repository()
        await repo.upsert_tenant(Tenant(tenant_id="t-f4-other", name="Altra"))
        await repo.upsert_user(User(uid="u-f4-prev", email="prev@f4.it", tenant_id="t-f4-other", role="viewer",
                                    push_tokens=["tok-device", "tok-prev-phone"]))
        # u-push-1 (seed of this suite) also still lists it, e.g. a stale copy
        me = await repo.get_user("u-push-1")
        me.push_tokens = ["tok-device"]
        await repo.upsert_user(me)
        caller = CurrentUser("u-push-1", "p1@test.it", TENANT, "admin")
        out = await push_routes.unsubscribe(push_routes.TokenBody(token="tok-device"), caller)
        assert out == {"subscribed": False, "tokens": 0}
        assert await repo.users_with_push_token("tok-device") == []
        assert (await repo.get_user("u-f4-prev")).push_tokens == ["tok-prev-phone"]   # the previous user's other device kept
    run(scenario())


def test_suspended_organisation_gets_no_push(users, fcm):
    """P-50 (D-85): a suspension stops the app, notifications included; reactivation brings them back."""
    from bff import auth

    repo = get_repository()
    before = run(push.send_to_tenant(TENANT, "approvals", *push.approval_push(APT, "apv-a", "ok?", TS)))
    assert before > 0
    fcm.sent.clear()
    run(repo.update_tenant(TENANT, {"status": "suspended"}))
    auth.forget_tenant(TENANT)
    assert run(push.send_to_tenant(TENANT, "approvals", *push.approval_push(APT, "apv-s", "ok?", TS))) == 0
    assert fcm.sent == []
    run(repo.update_tenant(TENANT, {"status": "active"}))
    auth.forget_tenant(TENANT)
    assert run(push.send_to_tenant(TENANT, "approvals", *push.approval_push(APT, "apv-r", "ok?", TS))) == before
