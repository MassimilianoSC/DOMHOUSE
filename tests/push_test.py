"""Push notifications (P-11): message format agreed with the PWA, token pruning, hooks that never block the stream.
FCM is replaced by a fake send_each_for_multicast; no network, memory repository."""
import asyncio
import itertools
import time
import threading
import dataclasses
import json
from types import SimpleNamespace

import httpx
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


_ids = itertools.count(1000)


def event(name: str, data: dict, event_id: str | None = None) -> SseEvent:
    """event_id: the engine's id of the event, the same for every instance that receives it."""
    event_id = event_id or str(next(_ids))
    env = {"id": event_id, "event": name, "ts": TS, "apartment_id": APT.apartment_id, "correlation_id": None, "data": data}
    return SseEvent(id=event_id, event=name, data=json.dumps(env), received=0.0)


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
    get_repository().work.clear()


@pytest.fixture
def fcm(monkeypatch):
    """FCM on, sends recorded; `fcm.fail` maps token -> exception, `fcm.gate` (an Event) holds the send if set."""
    monkeypatch.setattr(push, "get_settings", lambda: dataclasses.replace(get_settings(), fcm_enabled=True))
    state = SimpleNamespace(sent=[], fail={}, gate=None, threads=[], down=None)

    def fake_send(msg, dry_run=False, app=None):               # in a worker thread (D-198)
        state.threads.append(threading.current_thread())
        while state.gate is not None and not state.gate.is_set():
            time.sleep(0.005)
        state.sent.append(msg)
        failing = {t: state.down for t in msg.tokens} if state.down else state.fail
        responses = [SimpleNamespace(success=t not in failing, exception=failing.get(t)) for t in msg.tokens]
        ok = sum(r.success for r in responses)
        return SimpleNamespace(responses=responses, success_count=ok, failure_count=len(responses) - ok)

    monkeypatch.setattr(messaging, "send_each_for_multicast", fake_send)
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
    assert fcm.threads[0] is not threading.main_thread()         # D-198: Google's token is renewed off the event loop


def test_hook_failure_is_logged_not_raised(users, fcm, monkeypatch):
    logged = []
    monkeypatch.setattr(push, "warn", lambda msg, **kw: logged.append((msg, kw)))

    def boom(*_a, **_k):
        raise RuntimeError("fcm down")
    monkeypatch.setattr(messaging, "send_each_for_multicast", boom)

    async def scenario():
        await push.on_stream_event(APT, event("approval.pending", {"approval_id": "apv-6"}))
        await drain()
    run(scenario())
    assert logged and logged[0][0] == "push send failed" and "fcm down" in logged[0][1]["error"]


def alert_minutes(monkeypatch, minutes):
    """The offline_alert rule's minutes as the engine would answer them (None: the rule is off)."""
    async def fake(apt):
        return minutes
    monkeypatch.setattr(push, "_offline_alert_minutes", fake)


def test_instance_down_once_until_back_up(users, fcm, monkeypatch):
    alert_minutes(monkeypatch, 0)
    async def scenario():
        for status in ("down", "down", "ok", "down"):
            await push.on_stream_event(APT, event("instance.health", {"status": status}))
            await drain()
    run(scenario())
    assert [m.data["kind"] for m in fcm.sent] == ["instance_down", "instance_down"]


def test_instance_down_waits_for_the_offline_alert_minutes(users, fcm, monkeypatch):
    """D-131: a connector that drops and comes back before the rule's minutes sends nothing; with the rule off, never."""
    alert_minutes(monkeypatch, 1000)                     # still waiting when it comes back

    async def back_up_in_time():
        await push.on_stream_event(APT, event("instance.health", {"status": "down"}))
        await asyncio.sleep(0.05)
        await push.on_stream_event(APT, event("instance.health", {"status": "ok"}))
        await drain()
    run(back_up_in_time())
    assert fcm.sent == [] and APT.apartment_id not in push._down_timers
    alert_minutes(monkeypatch, None)

    async def rule_off():
        await push.on_stream_event(APT, event("instance.health", {"status": "down"}))
        await drain()
    run(rule_off())
    assert fcm.sent == []


def test_unsubscribe_removes_the_token_from_every_holder(users):
    """F4 (D-70): on a shared device the token may still be registered to a previous user; unsubscribe clears it from
    everyone, so no leftover push reaches the device after sign-out."""
    from bff.auth import CurrentUser, Identity
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
        member = CurrentUser("u-push-1", "p1@test.it", TENANT, "admin")
        caller = Identity(uid=member.uid, email=member.email, display_name="", user=member, platform_manager=False)
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


# -------- D-121 / D-123: booking cancelled after the prearrival («Prenotazioni») --------
def test_booking_reset_message():
    data, headers = push.booking_reset_push(APT, "dec-1", "Prenotazione bk-1 annullata dopo il pre-arrivo: appartamento rimesso a vuoto", TS)
    assert data == {"title": "Milano Centro: prenotazione annullata, appartamento rimesso a vuoto",
                    "body": "Prenotazione bk-1 annullata dopo il pre-arrivo: appartamento rimesso a vuoto",
                    "link": "/a/apt-push/decisioni", "tag": "booking:dec-1", "kind": "booking", "apartment_id": "apt-push",
                    "ts": TS}
    assert headers == {"Urgency": "high", "TTL": "86400"}


def test_booking_reset_goes_to_who_wants_bookings(users, fcm):
    async def scenario():
        repo = get_repository()
        viewer = await repo.get_user("u-push-3")
        viewer.notification_prefs = NotificationPrefs(approvals=False, offline=False, bookings=False)
        await repo.upsert_user(viewer)
        await push.on_stream_event(APT, event("decision.logged", {"decision_id": "dec-2", "action": "set_mode",
                                                                  "reasoning": "x"}))        # any other decision: no push
        await push.on_stream_event(APT, event("decision.logged", {"decision_id": "dec-3", "action": "booking_cancel_reset",
                                                                  "reasoning": "Prenotazione bk-3 annullata"}))
        await drain()
    run(scenario())
    assert len(fcm.sent) == 1 and fcm.sent[0].data["kind"] == "booking" and fcm.sent[0].data["tag"] == "booking:dec-3"
    tokens = set(fcm.sent[0].tokens)        # other tests leave more users in the tenant: only who matters here
    assert {"tok-a", "tok-b", "tok-c", "tok-d"} <= tokens and "tok-z" not in tokens


def test_bookings_is_on_also_for_preferences_saved_before():
    """Users who saved their preferences before D-123 have no "bookings" key: they get it, on, without doing anything."""
    old = User.model_validate({"uid": "u-old", "email": "old@test.it", "tenant_id": TENANT, "role": "admin",
                               "notification_prefs": {"approvals": True, "offline": False, "decisions": False}})
    assert old.notification_prefs.bookings is True and old.notification_prefs.offline is False
    assert NotificationPrefs().bookings is True


def test_a_platform_manager_without_organisation_can_still_clear_a_device(users):
    """Lot 27: a member used this browser before and left the token; a platform manager without an organisation signs
    in on it: the removal (F4) is not refused for lack of a tenant, and the member's pushes stop reaching the device."""
    from bff.auth import Identity
    from bff.routes import push as push_routes

    async def scenario():
        repo = get_repository()
        me = await repo.get_user("u-push-2")
        me.push_tokens = ["tok-shared-pc", "tok-c"]
        await repo.upsert_user(me)
        manager = Identity(uid="u-plat-alone", email="solo@piattaforma.it", display_name="", user=None,
                           platform_manager=True)
        out = await push_routes.unsubscribe(push_routes.TokenBody(token="tok-shared-pc"), manager)
        assert out == {"subscribed": False, "tokens": 0}
        assert (await repo.get_user("u-push-2")).push_tokens == ["tok-c"]
        assert await repo.get_user("u-plat-alone") is None                 # no record made for someone without a tenant
    run(scenario())



# -------- D-164: a boiler without its sensor in «casa vuota» («Dispositivi e istanza offline») --------
def test_frost_inactive_goes_to_who_wants_offline(users, fcm):
    reason = "Caldaia: sensore di temperatura mancante, antigelo non attivo (nessun sensore di temperatura collegato)"

    async def scenario():
        await push.on_stream_event(APT, event("decision.logged", {
            "decision_id": "dec-9", "action": "frost_inactive", "target": {"type": "device", "device_id": "dev-caldaia"},
            "reasoning": reason}))
        await drain()
    run(scenario())
    assert len(fcm.sent) == 1
    data = fcm.sent[0].data
    assert (data["kind"], data["title"], data["body"], data["tag"], data["link"], data["device_id"]) == (
        "frost_inactive", "Milano Centro: antigelo non attivo", reason, "frost:apt-push:dev-caldaia",
        "/a/apt-push/decisioni", "dev-caldaia")
    assert "tok-z" not in fcm.sent[0].tokens                   # u-push-3 turned «offline» off
    assert fcm.sent[0].webpush.headers == {"Urgency": "high", "TTL": "86400"}


# -------- D-170: «Decisioni del motore» is gone, without breaking saved preferences --------
def test_decisions_preference_is_accepted_and_ignored():
    import httpx as _httpx
    from bff.main import app as _app

    old = User.model_validate({"uid": "u-d170", "email": "d170@test.it", "tenant_id": TENANT, "role": "admin",
                               "notification_prefs": {"approvals": True, "offline": True, "decisions": True}})
    assert set(old.notification_prefs.model_dump()) == {"approvals", "offline", "bookings", "summary"}

    async def scenario():
        async with _httpx.AsyncClient(transport=_httpx.ASGITransport(app=_app), base_url="http://t") as c:
            with_key = await c.put("/app/me/notification-prefs", headers={"X-Dev-User": "admin@demo.it"},
                                   json={"approvals": True, "offline": False, "decisions": True, "bookings": True,
                                         "summary": True})
            without = await c.put("/app/me/notification-prefs", headers={"X-Dev-User": "admin@demo.it"},
                                  json={"approvals": True, "offline": True, "bookings": True, "summary": True})
            status = await c.get("/app/push/status", headers={"X-Dev-User": "admin@demo.it"})
        return with_key, without, status
    with_key, without, status = run(scenario())
    assert with_key.status_code == 200 and "decisions" not in with_key.json()
    assert without.status_code == 200 and "decisions" not in status.json()["prefs"]


def test_firebase_is_initialized_through_its_lock(monkeypatch):
    """D-198: the token checks initialize it from their threads; a second initialize_app would be refused."""
    from firebase_admin import messaging

    from bff import auth
    calls = []
    monkeypatch.setattr(auth, "firebase_app", lambda: calls.append(1))
    monkeypatch.setattr(messaging, "send_each_for_multicast", lambda msg: SimpleNamespace(responses=[]))
    run(push._send_multicast(["t"], {"a": "b"}, {}))
    assert calls == [1]


# -------- D-201: several instances --------
def test_two_instances_that_receive_the_same_event_send_one_notification(users, fcm):
    async def scenario():
        same = event("approval.pending", {"approval_id": "apv-due"}, event_id="7001")
        await asyncio.gather(push.on_stream_event(APT, same), push.on_stream_event(APT, same))   # one per instance
        await drain()
    run(scenario())
    assert len(fcm.sent) == 1


def test_a_notification_claimed_by_a_process_that_died_is_sent(users, fcm):
    data, headers = push.approval_push(APT, "apv-orfana", "Spegnere il clima", TS)
    payload = {"tenant_id": TENANT, "pref": "approvals", "data": data, "headers": headers}
    key = "push:prova:orfana"

    async def scenario():
        repo = get_repository()
        await repo.claim_work(key, "processo-morto", 0.2, payload)
        assert await push.recover_once() == 0                       # its lease is still running: nobody touches it
        await asyncio.sleep(0.25)
        assert await push.recover_once() == 1
        assert await repo.claim_work(key, "altro", 60, payload) == "done"
    run(scenario())
    assert len(fcm.sent) == 1 and fcm.sent[0].data["tag"] == "approval:apv-orfana"


def test_a_failed_send_is_retried_then_given_up(users, fcm, monkeypatch):
    logged = []
    monkeypatch.setattr(push, "warn", lambda msg, **kw: logged.append(msg))
    monkeypatch.setattr(messaging, "send_each_for_multicast", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fcm giu")))
    monkeypatch.setattr(push, "get_settings", lambda: dataclasses.replace(
        get_settings(), fcm_enabled=True, notification_lease_s=0.0))
    data, headers = push.approval_push(APT, "apv-giu", "x", TS)

    async def scenario():
        await push.notify_once("push:prova:giu", TENANT, "approvals", data, headers)
        for _ in range(6):
            await push.recover_once(now=time.time() + 1)
        assert await get_repository().claim_work("push:prova:giu", "altro", 60) == "done"
    run(scenario())
    assert logged.count("push send failed") == push.MAX_SEND_ATTEMPTS and logged.count("push given up") == 1


def offline_engine(monkeypatch, last_seen=None, health="ok"):
    """The engine still says the device is offline when the timer runs out."""
    async def fake(apt, method, path, **kw):
        body = {"status": health} if path == "/health" else {
            "devices": [{"device_id": "dev-due", "label": "Presa", "online": False, "last_seen": last_seen}]}
        return httpx.Response(200, json=body, request=httpx.Request("GET", "http://x"))
    monkeypatch.setattr(push.instances, "call", fake)


def test_two_instances_whose_offline_timers_run_out_send_one_notification(users, fcm, monkeypatch):
    """Each instance has its own timers, hence the clear(): in one process the second event would cancel the first timer."""
    alert_minutes(monkeypatch, 0)
    offline_engine(monkeypatch)

    async def scenario():
        same = event("device.online", {"device_id": "dev-due", "online": False}, event_id="7101")
        await push.on_stream_event(APT, same)
        push._offline_timers.clear()
        await push.on_stream_event(APT, same)
        await drain()
        assert len(fcm.sent) == 1
        push._offline_timers.clear()                            # an instance started later, given the same event again
        await push.on_stream_event(APT, same)
        await drain()
    run(scenario())
    assert len(fcm.sent) == 1 and fcm.sent[0].data["tag"] == "offline:apt-push:dev-due"


def test_two_instances_whose_instance_down_timers_run_out_send_one_notification(users, fcm, monkeypatch):
    alert_minutes(monkeypatch, 0)

    async def scenario():
        same = event("instance.health", {"status": "down"}, event_id="7102")
        await push.on_stream_event(APT, same)
        push._health_down.clear()                               # the other instance has its own state
        await push.on_stream_event(APT, same)
        await drain()
    run(scenario())
    assert [m.data["kind"] for m in fcm.sent] == ["instance_down"]


def test_a_device_that_goes_offline_twice_notifies_twice(users, fcm, monkeypatch):
    """The claim is per event: a new outage of the same device is a new notification."""
    alert_minutes(monkeypatch, 0)
    offline_engine(monkeypatch)

    async def scenario():
        for event_id in ("7103", "7104"):
            await push.on_stream_event(APT, event("device.online", {"device_id": "dev-due", "online": False}, event_id=event_id))
            await drain()
    run(scenario())
    assert len(fcm.sent) == 2


def lease_zero(monkeypatch):
    monkeypatch.setattr(push, "get_settings", lambda: dataclasses.replace(get_settings(), fcm_enabled=True, notification_lease_s=0.0))


def test_an_fcm_outage_is_not_a_sent_notification(users, fcm, monkeypatch):
    """firebase-admin does not raise: every token comes back failed."""
    lease_zero(monkeypatch)
    data, headers = push.approval_push(APT, "apv-fcm-giu", "x", TS)
    key = "push:prova:fcm-giu"

    async def scenario():
        fcm.down = exceptions.UnavailableError("FCM giu")
        await push.notify_once(key, TENANT, "approvals", data, headers)
        fcm.down = None
        fcm.sent.clear()
        assert await push.recover_once(now=time.time() + 1) == 1
        assert await get_repository().claim_work(key, "altro", 60) == "done"
    run(scenario())
    assert [m.data["tag"] for m in fcm.sent] == ["approval:apv-fcm-giu"]


def test_when_every_token_is_dead_there_is_nothing_to_retry(users, fcm, monkeypatch):
    lease_zero(monkeypatch)
    data, headers = push.approval_push(APT, "apv-morti", "x", TS)

    async def scenario():
        fcm.down = messaging.UnregisteredError("gone")
        await push.notify_once("push:prova:morti", TENANT, "approvals", data, headers)
        assert await get_repository().claim_work("push:prova:morti", "altro", 60) == "done"
    run(scenario())


def test_an_error_while_pruning_does_not_send_it_again(users, fcm, monkeypatch):
    logged = []
    monkeypatch.setattr(push, "warn", lambda msg, **kw: logged.append(msg))

    async def broken(_dead):
        raise RuntimeError("Firestore non raggiungibile")
    monkeypatch.setattr(push, "_prune_tokens", broken)
    fcm.fail = {"tok-a": messaging.UnregisteredError("gone")}
    data, headers = push.approval_push(APT, "apv-pota", "x", TS)

    async def scenario():
        await push.notify_once("push:prova:pota", TENANT, "approvals", data, headers)
        assert await get_repository().claim_work("push:prova:pota", "altro", 60) == "done"
    run(scenario())
    assert logged == ["push tokens not pruned"]


# -------- review of lot 36: an outage is one notification on every instance, and a restart does not lose it --------
SEEN = "2026-10-16T09:00:00.000Z"


def went_offline(event_id):
    return event("device.online", {"device_id": "dev-due", "online": False}, event_id=event_id)


def ago(seconds):
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def fresh_process():
    push._offline_timers.clear()
    push._health_down.clear()
    push._resumed.clear()


def test_an_instance_that_joined_during_the_outage_does_not_notify_it_again(users, fcm, monkeypatch):
    """Its timer started from a later event of the engine: not the same id, the same outage."""
    alert_minutes(monkeypatch, 0)
    offline_engine(monkeypatch, last_seen=SEEN)

    async def scenario():
        await push.on_stream_event(APT, went_offline("7201"))
        await drain()
        push._offline_timers.clear()
        await push.on_stream_event(APT, went_offline("7202"))
        await drain()
    run(scenario())
    assert len(fcm.sent) == 1


def test_when_the_device_has_answered_a_new_outage_is_a_new_notification(users, fcm, monkeypatch):
    alert_minutes(monkeypatch, 0)

    async def scenario():
        for event_id, seen in (("7203", SEEN), ("7204", "2026-10-16T09:30:00.000Z")):
            offline_engine(monkeypatch, last_seen=seen)
            await push.on_stream_event(APT, went_offline(event_id))
            await drain()
    run(scenario())
    assert len(fcm.sent) == 2


def test_instance_down_is_one_notification_for_the_whole_outage(users, fcm, monkeypatch):
    """The engine repeats instance.health at every change of a device; an instance can join with any of those events."""
    alert_minutes(monkeypatch, 0)

    async def scenario():
        await push.on_stream_event(APT, event("instance.health", {"status": "down"}, event_id="7205"))
        await drain()
        push._health_down.clear()
        await push.on_stream_event(APT, event("instance.health", {"status": "down"}, event_id="7206"))
        await drain()
    run(scenario())
    assert [m.data["kind"] for m in fcm.sent] == ["instance_down"]


def test_a_restart_goes_on_waiting_for_a_device_already_offline(users, fcm, monkeypatch):
    """The timer died with the process and the event is behind the saved id."""
    from engine.core import seconds_per_minute

    alert_minutes(monkeypatch, 10)
    unit = seconds_per_minute()

    async def scenario():
        fresh_process()
        offline_engine(monkeypatch, last_seen=ago(9 * unit))    # 9 minutes of 10: it still has to wait
        await push.resume_watches(APT)
        await asyncio.sleep(0.01)
        pending = push._offline_timers[(APT.apartment_id, "dev-due")]
        assert not pending.done() and fcm.sent == []
        pending.cancel()
        fresh_process()
        offline_engine(monkeypatch, last_seen=ago(11 * unit))   # the wait is over: at once
        await push.resume_watches(APT)
        await drain()
    run(scenario())
    assert [m.data["kind"] for m in fcm.sent] == ["device_offline"]


def test_a_restart_does_not_notify_again_what_was_already_sent(users, fcm, monkeypatch):
    alert_minutes(monkeypatch, 0)
    offline_engine(monkeypatch, last_seen=ago(600))

    async def scenario():
        for _ in range(2):
            fresh_process()
            await push.resume_watches(APT)
            await drain()
    run(scenario())
    assert len(fcm.sent) == 1


def test_an_outage_older_than_the_claims_is_not_picked_up(users, fcm, monkeypatch):
    alert_minutes(monkeypatch, 0)
    offline_engine(monkeypatch, last_seen=ago(push.OFFLINE_RESUME_MAX_S + 60))

    async def scenario():
        fresh_process()
        await push.resume_watches(APT)
        await drain()
    run(scenario())
    assert fcm.sent == []


def test_a_restart_picks_up_an_instance_down_and_says_only_that(users, fcm, monkeypatch):
    alert_minutes(monkeypatch, 0)
    offline_engine(monkeypatch, last_seen=ago(600), health="down")

    async def scenario():
        fresh_process()
        await push.resume_watches(APT)
        await drain()
    run(scenario())
    assert [m.data["kind"] for m in fcm.sent] == ["instance_down"]


def test_an_outage_that_ended_while_nobody_listened_does_not_silence_the_next(users, fcm, monkeypatch):
    alert_minutes(monkeypatch, 0)
    offline_engine(monkeypatch, health="ok")

    async def scenario():
        repo = get_repository()
        await repo.claim_work(push.instance_down_key(APT), "morto", 60)
        await repo.finish_work(push.instance_down_key(APT))
        fresh_process()
        await push.resume_watches(APT)
        assert await repo.claim_work(push.instance_down_key(APT), "altro", 60) == "mine"
    run(scenario())


def test_an_engine_that_does_not_answer_is_asked_again(users, fcm, monkeypatch):
    async def fake(apt, method, path, **kw):
        raise httpx.ConnectError("giu")
    monkeypatch.setattr(push.instances, "call", fake)

    async def scenario():
        fresh_process()
        push._resumed.add(APT.apartment_id)
        await push.resume_watches(APT)
    run(scenario())
    assert APT.apartment_id not in push._resumed



# -------- D-217: the engine itself unreachable ------------------------------------------------------------------------
MINUTE_S = 0.01                                    # MOCK_TIME_SCALE here: the rule's 15 minutes are 0.15 s


@pytest.fixture
def unreachable(users, fcm, monkeypatch):
    """The engine does not answer (calls raise ConnectError unless `state.answers`); the rule's last minutes are 15."""
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE_S))
    base = push.get_settings()
    state = SimpleNamespace(answers=False, health="ok", settings=dataclasses.replace(base, instance_mode="mock"),
                            notes=[], note_status=201)
    monkeypatch.setattr(push, "get_settings", lambda: state.settings)

    async def call(apt, method, path, **kw):
        if not state.answers:
            raise httpx.ConnectError("motore spento")
        if path == "/_internal/reachability":                # D-217: the engine's note in its Decisions
            state.notes.append((method, kw["json"]))
            return httpx.Response(state.note_status, json={}, request=httpx.Request(method, "http://x"))
        body = {"status": state.health} if path == "/health" else {"devices": [], "rules": [
            {"rule_id": "offline_alert", "enabled": True, "params": {"minutes": 15}}]}
        return httpx.Response(200, json=body, request=httpx.Request("GET", "http://x"))
    monkeypatch.setattr(push.instances, "call", call)
    for d in (push._unreachable, push._unreachable_timers, push._alert_minutes, push._down_timers):
        d.clear()
    push._resumed.clear()
    push._alert_minutes[APT.apartment_id] = 15.0
    return state


def suspend(state, value: str) -> None:
    state.settings = dataclasses.replace(state.settings, unreachable_alerts_off_until=value)


def soon(seconds: float) -> str:
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


UNREACHABLE_BODY = ("Il sistema domotico non risponde da 15 minuti: i comandi dall'app non arrivano e le regole "
                    "automatiche potrebbero essere ferme.")


def test_unreachable_message():
    data, headers = push.instance_unreachable_push(APT, 15, TS)
    assert data == {"title": "Milano Centro: sistema domotico non raggiungibile", "body": UNREACHABLE_BODY,
                    "link": "/a/apt-push", "tag": "instance:apt-push", "kind": "instance_down", "apartment_id": "apt-push",
                    "ts": TS}
    assert headers == {"Urgency": "high", "TTL": "86400"}


def test_an_engine_silent_for_the_rules_minutes_is_told_once(unreachable, fcm):
    async def scenario():
        await push.on_link_change(APT, False)
        await push.on_link_change(APT, False)                 # the hub tells only changes; twice changes nothing
        await drain()
    run(scenario())
    assert [m.data["body"] for m in fcm.sent] == [UNREACHABLE_BODY]


def test_back_before_the_minutes_nothing_and_the_next_outage_is_told(unreachable, fcm):
    async def scenario():
        await push.on_link_change(APT, False)
        await asyncio.sleep(0.03)
        unreachable.answers = True
        await push.on_link_change(APT, True)
        await drain()
        assert fcm.sent == [] and APT.apartment_id not in push._unreachable_timers
        unreachable.answers = False
        await push.on_link_change(APT, False)
        await drain()
    run(scenario())
    assert len(fcm.sent) == 1


def test_with_the_rule_off_never(unreachable, fcm):
    push._alert_minutes[APT.apartment_id] = None             # the last time the engine answered, the rule was off

    async def scenario():
        await push.on_link_change(APT, False)
        await drain()
    run(scenario())
    assert fcm.sent == []


def test_an_engine_that_answers_at_the_last_check_is_not_told(unreachable, fcm):
    """Another instance may have seen it come back, or this hub is still in its backoff."""
    async def scenario():
        await push.on_link_change(APT, False)
        await asyncio.sleep(0.05)
        unreachable.answers = True
        await drain()
    run(scenario())
    assert fcm.sent == []


def test_two_instances_one_notification_and_the_return_frees_the_next(unreachable, fcm):
    async def scenario():
        await push.on_link_change(APT, False)
        await drain()
        push._unreachable.clear()                            # a second instance, the same outage
        await push.on_link_change(APT, False)
        await drain()
        assert len(fcm.sent) == 1
        unreachable.answers = True
        await push.on_link_change(APT, True)                 # back, and its connector fine: the claim goes
        await drain()
        unreachable.answers = False
        await push.on_link_change(APT, False)
        await drain()
    run(scenario())
    assert len(fcm.sent) == 2


def test_one_notification_for_the_outage_whatever_its_cause(unreachable, fcm, monkeypatch):
    alert_minutes(monkeypatch, 0)

    async def scenario():
        await push.on_stream_event(APT, event("instance.health", {"status": "down"}))   # first the connector
        await drain()
        await push.on_link_change(APT, False)                                          # then the engine itself
        await drain()
    run(scenario())
    assert [m.data["body"] for m in fcm.sent] == ["Il connettore domotico risulta fermo"]


def test_a_suspension_holds_it_until_its_end_then_an_engine_still_down_is_told(unreachable, fcm):
    suspend(unreachable, soon(0.4))

    async def scenario():
        await push.on_link_change(APT, False)
        await asyncio.sleep(0.25)                            # past the minutes, inside the suspension
        assert fcm.sent == []
        await drain()
    run(scenario())
    assert [m.data["body"] for m in fcm.sent] == [UNREACHABLE_BODY]


def test_a_suspension_holds_the_connector_down_too(unreachable, fcm, monkeypatch):
    alert_minutes(monkeypatch, 0)
    suspend(unreachable, soon(0.3))

    async def scenario():
        await push.on_stream_event(APT, event("instance.health", {"status": "down"}))
        await asyncio.sleep(0.1)
        assert fcm.sent == []
        await push.on_stream_event(APT, event("instance.health", {"status": "ok"}))    # back during the suspension
        await drain()
    run(scenario())
    assert fcm.sent == []


def test_a_suspension_that_cannot_be_read_or_is_too_long_leaves_alerts_on(unreachable):
    from datetime import UTC, datetime
    now = datetime(2026, 11, 20, 8, 0, tzinfo=UTC)
    for value, on in (("", True), ("domani", True), ("2026-11-22T08:00:00", True),           # no offset
                      ("2026-11-19T08:00:00Z", True), ("2026-12-21T08:00:00Z", True),          # past, 31 days
                      ("2026-11-22T08:00:00Z", False), ("2026-11-22T09:00:00+01:00", False)):
        suspend(unreachable, value)
        assert (push.alerts_suspended_until(now) is None) is on, value
    assert push.alerts_suspended_until(now).isoformat() == "2026-11-22T09:00:00+01:00"


def test_the_hub_tells_the_link_changes(monkeypatch):
    """The stream to the engine fails, then answers: the hooks hear False, then True."""
    from bff import sse_hub

    heard, attempts = [], iter(["fail", "ok"])

    class Resp:
        status_code = 200

        async def aiter_lines(self):
            await asyncio.Event().wait()
            yield ""                                         # pragma: no cover

    class Stream:
        async def __aenter__(self):
            if next(attempts) == "fail":
                raise httpx.ConnectError("motore spento")
            return Resp()

        async def __aexit__(self, *exc):
            return False

    class Http:
        def stream(self, *a, **kw):
            return Stream()

    async def headers(apt, actor):
        return {}
    monkeypatch.setattr(sse_hub.instances, "http", lambda: Http())
    monkeypatch.setattr(sse_hub.instances, "instance_headers", headers)

    async def hook(apt, up):
        heard.append(up)

    async def scenario():
        hub = sse_hub.InstanceHub(APT, [], [hook])
        hub.start(None)
        for _ in range(300):
            if heard == [False, True]:
                break
            await asyncio.sleep(0.01)
        hub.task.cancel()
    run(scenario())
    assert heard == [False, True]


def test_register_adds_the_link_hook():
    from bff.sse_hub import hub_manager
    push.register()
    assert push.on_link_change in hub_manager.link_hooks


# -------- D-217: the decision «di nuovo raggiungibile» at the return ----------------------------------------------------
async def outage(state, seconds: float) -> None:
    """The engine silent for `seconds`, then back."""
    state.answers = False
    await push.on_link_change(APT, False)
    await asyncio.sleep(seconds)
    state.answers = True
    await push.on_link_change(APT, True)
    await drain()


def test_a_long_outage_asks_the_engine_for_its_note_once(unreachable):
    run(outage(unreachable, 0.2))                            # longer than the 15 minutes (0.15 s)
    assert [m for m, _ in unreachable.notes] == ["POST"]
    body = unreachable.notes[0][1]
    assert set(body) == {"from", "to"} and body["from"] < body["to"]
    assert all(v.endswith("Z") and len(v) == 24 for v in body.values())   # UTC, milliseconds


def test_a_short_drop_writes_nothing(unreachable):
    run(outage(unreachable, 0.03))
    assert unreachable.notes == []


def test_one_note_for_every_instance_and_the_next_outage_has_its_own(unreachable):
    async def scenario():
        await outage(unreachable, 0.2)
        push._unreachable[APT.apartment_id] = time.time() - 1   # a second instance, back from the same outage
        await push.on_link_change(APT, True)
        await drain()
        assert len(unreachable.notes) == 1
        await outage(unreachable, 0.2)                          # the next outage releases the claim
    run(scenario())
    assert len(unreachable.notes) == 2


def test_also_during_a_suspension(unreachable, fcm):
    suspend(unreachable, soon(5))
    run(outage(unreachable, 0.2))
    assert len(unreachable.notes) == 1 and fcm.sent == []


def test_the_rule_off_still_uses_fifteen_minutes(unreachable):
    push._alert_minutes[APT.apartment_id] = None
    run(outage(unreachable, 0.05))
    assert unreachable.notes == []
    run(outage(unreachable, 0.2))
    assert len(unreachable.notes) == 1


def test_an_engine_without_the_route_is_skipped_and_not_asked_again(unreachable):
    unreachable.note_status = 404

    async def scenario():
        await outage(unreachable, 0.2)
        push._unreachable[APT.apartment_id] = time.time() - 1   # another instance
        await push.on_link_change(APT, True)
        await drain()
    run(scenario())
    assert len(unreachable.notes) == 1
    assert get_repository().work[push.reachable_note_key(APT)]["status"] == "done"


# -------- D-219: scheduled actions not done -----------------------------------------------------------------------------
@pytest.fixture
def grouped(users, fcm, monkeypatch):
    """The grouping window short; bookings and offline on for the opted-in users."""
    monkeypatch.setattr(push, "SCHEDULE_GROUP_S", 0.05)
    push._schedule_groups.clear()
    return fcm


def not_done(kind: str | None, reasoning: str, action: str = "schedule_failed", decision_id: str | None = None):
    decision_id = decision_id or f"dec-{next(_ids)}"
    return event("decision.logged", {"decision_id": decision_id, "action": action, "outcome": "failed",
                                     "target": {"type": "schedule"}, "new_value": kind, "reasoning": reasoning})


PREARRIVAL = "Azione programmata (pre-arrivo) non eseguita: Il dispositivo non è raggiungibile; riprova quando torna online"


def test_one_action_not_done_one_notification_in_its_category(grouped):
    async def scenario():
        await push.on_stream_event(APT, not_done("prearrival", PREARRIVAL, decision_id="dec-7"))
        await drain()
    run(scenario())
    [msg] = grouped.sent
    assert msg.data["kind"] == "schedule_failed" and msg.data["title"] == "Milano Centro: azione programmata non eseguita"
    assert msg.data["body"] == PREARRIVAL and msg.data["link"] == "/a/apt-push/programmazione"
    assert msg.data["tag"] == "schedule:apt-push:dec-7" and msg.webpush.headers == {"Urgency": "high", "TTL": "86400"}


def test_the_categories():
    assert [push.schedule_pref(k) for k in ("prearrival", "checkout", "empty", "manual", None, "altro")] == [
        "bookings", "bookings", "bookings", "offline", "offline", "offline"]


def test_several_close_together_are_one_notification_with_the_first_in_full(grouped):
    async def scenario():
        for kind in ("prearrival", "checkout", "empty"):
            await push.on_stream_event(APT, not_done(kind, PREARRIVAL if kind == "prearrival" else f"Azione ({kind})"))
        await push.on_stream_event(APT, not_done("manual", "Azione programmata (manuale) non eseguita: x"))
        await drain()
    run(scenario())
    bodies = sorted(m.data["body"] for m in grouped.sent)
    assert bodies == sorted([f"3 azioni programmate non eseguite. La prima: {PREARRIVAL}",
                             "Azione programmata (manuale) non eseguita: x"])   # bookings and offline apart
    assert {m.data["title"] for m in grouped.sent} == {"Milano Centro: azioni programmate non eseguite",
                                                       "Milano Centro: azione programmata non eseguita"}


def test_a_user_without_the_category_receives_nothing(grouped):
    """Token z belongs to a user with offline off: a manual action does not reach it."""
    async def scenario():
        await push.on_stream_event(APT, not_done("manual", "Azione programmata (manuale) non eseguita: x"))
        await drain()
    run(scenario())
    assert "tok-z" not in grouped.sent[0].tokens


def test_two_instances_one_notification(grouped):
    async def scenario():
        ev = not_done("checkout", "Azione programmata (check-out) non eseguita: y", decision_id="dec-77")
        await push.on_stream_event(APT, ev)
        push._schedule_groups.clear()                         # a second instance receives the same event
        await push.on_stream_event(APT, ev)
        await drain()
    run(scenario())
    assert len(grouped.sent) == 1


def test_missed_actions_during_a_suspension_are_not_notified_one_by_one(grouped, monkeypatch):
    s = dataclasses.replace(push.get_settings(), unreachable_alerts_off_until=soon(60))
    monkeypatch.setattr(push, "get_settings", lambda: s)

    async def scenario():
        await push.on_stream_event(APT, not_done("prearrival", "saltata", action="schedule_missed"))
        await push.on_stream_event(APT, not_done("prearrival", PREARRIVAL))               # refused: always told
        await drain()
    run(scenario())
    assert [m.data["body"] for m in grouped.sent] == [PREARRIVAL]


# -------- D-219 (2): an action that ran with some commands not successful ------------------------------------------------
PARTIAL = "Pre-arrivo eseguito in parte: 1 comando non riuscito (Caldaia: Il dispositivo ha rifiutato il comando)"


def partly(kind, reasoning=PARTIAL, decision_id=None):
    return not_done(kind, reasoning, action="schedule_partial", decision_id=decision_id)


def test_a_prearrival_done_in_part_is_told_in_bookings(grouped):
    async def scenario():
        await push.on_stream_event(APT, partly("prearrival", decision_id="dec-9"))
        await drain()
    run(scenario())
    [msg] = grouped.sent
    assert msg.data["title"] == "Milano Centro: pre-arrivo con comandi non riusciti" and msg.data["body"] == PARTIAL
    assert msg.data["kind"] == "schedule_failed" and msg.data["link"] == "/a/apt-push/programmazione"
    assert msg.data["tag"] == "schedule:apt-push:dec-9" and "tok-z" in msg.tokens       # «Prenotazioni»


def test_only_the_prearrival_and_the_checkout_are_told(grouped):
    async def scenario():
        for kind in ("empty", "manual", "assistant", None):
            await push.on_stream_event(APT, partly(kind, "Azione programmata (…) eseguita in parte: …"))
        await push.on_stream_event(APT, partly("checkout", "Check-out non riuscito: 2 comandi non riusciti (…)"))
        await drain()
    run(scenario())
    assert [(m.data["title"], m.data["body"]) for m in grouped.sent] == [
        ("Milano Centro: check-out con comandi non riusciti", "Check-out non riuscito: 2 comandi non riusciti (…)")]


def test_with_an_action_not_done_close_together_one_notification(grouped):
    async def scenario():
        await push.on_stream_event(APT, partly("prearrival"))
        await push.on_stream_event(APT, not_done("checkout", "Azione programmata (check-out) non eseguita: y"))
        await drain()
    run(scenario())
    [msg] = grouped.sent
    assert msg.data["title"] == "Milano Centro: azioni programmate non eseguite o eseguite in parte"
    assert msg.data["body"].startswith(f"2 azioni programmate non eseguite o eseguite in parte. La prima: {PARTIAL[:40]}")


def test_done_in_part_is_told_also_during_a_suspension(grouped, monkeypatch):
    s = dataclasses.replace(push.get_settings(), unreachable_alerts_off_until=soon(60))
    monkeypatch.setattr(push, "get_settings", lambda: s)

    async def scenario():
        await push.on_stream_event(APT, partly("prearrival"))
        await drain()
    run(scenario())
    assert [m.data["body"] for m in grouped.sent] == [PARTIAL]


# -------- D-219: the summary at the end of a planned shutdown ------------------------------------------------------------
@pytest.fixture
def maintenance(grouped, monkeypatch):
    """A suspension that can be set and removed; the apartment in the registry (the start reads it)."""
    state = SimpleNamespace(settings=push.get_settings())
    monkeypatch.setattr(push, "get_settings", lambda: state.settings)
    run(get_repository().upsert_apartment(APT))
    run(get_repository().release_work(push.maintenance_key(APT)))
    state.suspend = lambda value: setattr(state, "settings", dataclasses.replace(state.settings, unreachable_alerts_off_until=value))
    return state


def missed(kind):
    return not_done(kind, "Azione programmata non eseguita: il motore era fermo", action="schedule_missed")


def kept():
    return get_repository().work.get(push.maintenance_key(APT))


def test_the_missed_actions_wait_as_one_summary_until_the_end_of_the_suspension(maintenance, grouped):
    maintenance.suspend(soon(3600))

    async def scenario():
        for kind in ("prearrival", "checkout", "manual"):
            await push.on_stream_event(APT, missed(kind))
        await drain()
    run(scenario())
    assert grouped.sent == []
    summary = kept()
    assert summary["status"] == "pending" and summary["payload"]["pref"] == "bookings"
    assert summary["payload"]["data"]["body"] == "Durante la manutenzione 3 azioni programmate non sono state eseguite"
    assert summary["payload"]["data"]["link"] == "/a/apt-push/programmazione"
    assert 3590 < summary["lease_until"] - time.time() <= 3600                 # until the end of the suspension


def test_the_natural_end_sends_it_once(maintenance, grouped):
    maintenance.suspend(soon(0.2))

    async def scenario():
        await push.on_stream_event(APT, missed("manual"))
        await drain()
        assert await push.recover_once() == 0                                  # not yet
        await asyncio.sleep(0.3)                                               # the suspension is over
        first = await push.recover_once()
        await drain()
        return first, await push.recover_once()
    first, second = run(scenario())
    assert (first, second) == (1, 0)
    [msg] = grouped.sent
    assert msg.data["body"] == "Durante la manutenzione 1 azione programmata non è stata eseguita"
    assert "tok-z" not in msg.tokens                                           # only manual: «Dispositivi…» category


def test_removed_early_the_new_revision_sends_it_at_its_start(maintenance, grouped):
    maintenance.suspend(soon(86400))

    async def scenario():
        await push.on_stream_event(APT, missed("checkout"))
        await drain()
        assert await push.expire_maintenance_summaries() == 0                  # still suspended: it waits
        maintenance.suspend("")                                                # the variable removed
        assert await push.expire_maintenance_summaries() == 1
        return await push.recover_once()
    assert run(scenario()) == 1 and len(grouped.sent) == 1


def test_two_instances_keep_one_summary(maintenance, grouped):
    maintenance.suspend(soon(0.2))

    async def scenario():
        ev = missed("prearrival")
        await push.on_stream_event(APT, ev)
        push._schedule_groups.clear()                                         # a second instance, the same event
        await push.on_stream_event(APT, ev)
        await drain()
        await asyncio.sleep(0.3)
        return await push.recover_once()
    assert run(scenario()) == 1 and len(grouped.sent) == 1


def test_the_next_shutdown_has_its_own_summary(maintenance, grouped):
    async def one_shutdown():
        maintenance.suspend(soon(0.2))
        await push.on_stream_event(APT, missed("prearrival"))
        await drain()
        await asyncio.sleep(0.3)
        await push.recover_once()
    run(one_shutdown())
    run(one_shutdown())
    assert len(grouped.sent) == 2


# -------- D42 (P-83): a process that dies within the grouping window ----------------------------------------------------
async def dies():
    """The process stops: its tasks cancelled, its open groups gone (they lived only in its memory)."""
    for task in list(push._tasks):
        task.cancel()
    await asyncio.gather(*list(push._tasks), return_exceptions=True)
    push._schedule_groups.clear()


def leases_run_out():
    for d in get_repository().work.values():
        d["lease_until"] = min(d["lease_until"], time.time())


def test_a_group_survives_a_process_that_dies_in_the_window(grouped, monkeypatch):
    """Before D42 the group was only in memory for 60 s (and the stream's cursor already beyond its event): lost."""
    monkeypatch.setattr(push, "SCHEDULE_GROUP_S", 30.0)

    async def scenario():
        await push.on_stream_event(APT, not_done("checkout", "Azione programmata (check-out) non eseguita: z",
                                                 decision_id="dec-42"))
        await asyncio.sleep(0.05)
        await dies()
        assert await push.recover_once() == 0              # its lease covers the window and a margin
        leases_run_out()
        recovered = await push.recover_once()
        await drain()
        return recovered
    assert run(scenario()) == 1
    [msg] = grouped.sent
    assert msg.data["body"] == "Azione programmata (check-out) non eseguita: z"
    assert msg.data["tag"] == "schedule:apt-push:dec-42"


def test_the_group_claimed_at_once_is_sent_whole_at_the_end_of_the_window(grouped):
    async def scenario():
        for n in range(3):
            await push.on_stream_event(APT, not_done("checkout", f"Azione {n}", decision_id=f"dec-42{n}"))
        await drain()
        leases_run_out()
        return await push.recover_once()
    assert run(scenario()) == 0                            # sent and done: nothing left to recover
    [msg] = grouped.sent
    assert msg.data["body"] == "3 azioni programmate non eseguite. La prima: Azione 0"


def test_a_reset_within_the_window_leaves_nothing_to_recover(grouped, monkeypatch):
    monkeypatch.setattr(push, "SCHEDULE_GROUP_S", 0.2)

    async def scenario():
        await push.on_stream_event(APT, not_done("manual", "Azione programmata (manuale) non eseguita: r"))
        await asyncio.sleep(0.05)
        push.forget_apartment(APT.apartment_id)
        await drain()
        leases_run_out()
        return await push.recover_once()
    assert run(scenario()) == 0 and grouped.sent == []


def test_the_maintenance_summary_survives_a_process_that_dies_in_the_window(maintenance, grouped, monkeypatch):
    monkeypatch.setattr(push, "SCHEDULE_GROUP_S", 30.0)
    maintenance.suspend(soon(0.2))

    async def scenario():
        await push.on_stream_event(APT, missed("checkout"))
        await asyncio.sleep(0.05)
        await dies()
        await asyncio.sleep(0.3)                           # the suspension is over
        recovered = await push.recover_once()
        await drain()
        return recovered
    assert run(scenario()) == 1
    [msg] = grouped.sent
    assert msg.data["body"] == "Durante la manutenzione 1 azione programmata non è stata eseguita"
