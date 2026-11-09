"""Push notifications: FCM behind FCM_ENABLED; stream hooks decide *when* to notify.

The message is data-only (no notification block, no webpush link): the PWA's service worker shows it. Its format is
agreed with the PWA and described in bff/API.md («Notifiche push»). Sending never blocks the stream: hooks only start
tasks, and task errors are logged.
"""
import asyncio
import time

from . import instances, runtime
from .auth import sees, tenant_status
from .config import get_settings
from .logs import info, warn
from .repository import Apartment, get_repository
from .sse_hub import CURSOR_SAVE_S, SseEvent, envelope, hub_manager, link_of

BODY_MAX = 200
TTL_SECONDS = {"approval": 3600, "device_offline": 86400, "instance_down": 86400, "booking": 86400,
               "summary": 7 * 86400,   # P-60 step 11: the weekly summary stays a week
               "frost_inactive": 86400}  # D-164: a boiler without its sensor in «casa vuota»

_offline_timers: dict[tuple[str, str], asyncio.Task] = {}
_health_down: set[str] = set()
_down_timers: dict[str, asyncio.Task] = {}      # D-131: the "instance down" push waits for the offline_alert minutes
_tasks: set[asyncio.Task] = set()  # strong references: the loop keeps only weak ones to running tasks
_loops: list[asyncio.Task] = []    # the rounds that last as long as the process
HUB_ALIGN_S = 60


def build_push(kind: str, apt: Apartment, title: str, body: str, link: str, tag: str, ts: str | None = None,
               **ids: str | None) -> tuple[dict[str, str], dict[str, str]]:
    """(data, webpush headers) of one notification; every value is a string, the body is cut to BODY_MAX."""
    body = body.strip()
    if len(body) > BODY_MAX:
        body = body[:BODY_MAX - 1].rstrip() + "…"
    data = {"title": title, "body": body, "link": link, "tag": tag, "kind": kind, "apartment_id": apt.apartment_id}
    data.update({k: str(v) for k, v in ids.items() if v})
    if ts:
        data["ts"] = ts
    # the weekly summary is news, not an alarm: "normal" lets a phone in battery saving deliver it later
    return data, {"Urgency": "normal" if kind == "summary" else "high", "TTL": str(TTL_SECONDS[kind])}


def approval_push(apt: Apartment, approval_id: str, description: str | None, ts: str | None):
    # a blank description would give an empty body, and the PWA turns a push without body into a generic one opening "/"
    body = (description or "").strip() or "Il motore chiede il tuo consenso"
    return build_push("approval", apt, f"{apt.name}: approvazione richiesta", body,
                      f"/a/{apt.apartment_id}/approvazioni", f"approval:{approval_id}", ts, approval_id=approval_id)


def device_offline_push(apt: Apartment, device_id: str, label: str, minutes: float, ts: str | None):
    return build_push("device_offline", apt, f"{apt.name}: dispositivo offline", f"{label} non risponde da oltre {int(minutes)} minuti",
                      f"/a/{apt.apartment_id}", f"offline:{apt.apartment_id}:{device_id}", ts, device_id=device_id)


def instance_down_push(apt: Apartment, ts: str | None):
    return build_push("instance_down", apt, f"{apt.name}: sistema domotico non raggiungibile", "Il connettore domotico risulta fermo",
                      f"/a/{apt.apartment_id}", f"instance:{apt.apartment_id}", ts)


def booking_reset_push(apt: Apartment, decision_id: str, reasoning: str | None, ts: str | None):
    """D-121/D-123: a booking cancelled after its prearrival, the engine put the apartment back to empty."""
    body = (reasoning or "").strip() or "Prenotazione annullata dopo il pre-arrivo: appartamento rimesso a vuoto"
    return build_push("booking", apt, f"{apt.name}: prenotazione annullata, appartamento rimesso a vuoto", body,
                      f"/a/{apt.apartment_id}/decisioni", f"booking:{decision_id}", ts)


def frost_inactive_push(apt: Apartment, device_id: str, reasoning: str | None, ts: str | None):
    """D-164: the frost protection cannot act, the boiler's temperature sensor is missing or not answering."""
    body = (reasoning or "").strip() or "Sensore di temperatura mancante: antigelo non attivo"
    return build_push("frost_inactive", apt, f"{apt.name}: antigelo non attivo", body, f"/a/{apt.apartment_id}/decisioni",
                      f"frost:{apt.apartment_id}:{device_id}", ts, device_id=device_id)


async def send_to_tenant(tenant_id: str, pref: str, data: dict[str, str], headers: dict[str, str]) -> int:
    """Sends to every user of the tenant who opted in for `pref` and may see the message's apartment (P-18);
    returns number of tokens targeted."""
    repo = get_repository()
    if await tenant_status(repo, tenant_id) != "active":   # P-50: a suspended organisation receives nothing
        info("push skipped (organisation not active)", kind=data.get("kind"), tag=data.get("tag"))
        return 0
    apartment_id = data["apartment_id"]
    tokens = [tok for u in await repo.list_users(tenant_id)
              if getattr(u.notification_prefs, pref, False) and sees(u.role, u.apartment_ids, apartment_id)
              for tok in u.push_tokens]
    if not tokens:
        return 0
    if not get_settings().fcm_enabled:
        info("push skipped (FCM disabled)", kind=data.get("kind"), tag=data.get("tag"), tokens=len(tokens))
        return len(tokens)
    resp = await _send_multicast(tokens, data, headers)
    info("push sent", kind=data.get("kind"), tag=data.get("tag"), success=resp.success_count, failure=resp.failure_count)
    if resp.failure_count:
        try:
            # Same event loop as the repository (the async Firestore client is bound to it): no thread, no asyncio.run.
            await _prune_tokens([t for t, r in zip(tokens, resp.responses) if not r.success and _dead_token(r.exception)])
        except Exception as exc:                   # the message has gone: this must not make it go again
            warn("push tokens not pruned", error=type(exc).__name__)
    # firebase-admin reports a network error or an FCM outage per token, it does not raise: nobody reached and a token that
    # may still work means not sent, so that the claim stays pending and recover_once tries again
    if not resp.success_count and any(not r.success and not _dead_token(r.exception) for r in resp.responses):
        raise RuntimeError(f"no token reached: {type(resp.responses[0].exception).__name__}")
    return len(tokens)


async def _send_multicast(tokens: list[str], data: dict[str, str], headers: dict[str, str]):
    from firebase_admin import messaging

    from .auth import firebase_app

    firebase_app()                                 # under its lock: the token checks call it from their threads
    msg = messaging.MulticastMessage(tokens=tokens, data=data, webpush=messaging.WebpushConfig(headers=headers))
    # D-198: the sync call in a thread. The async one renews Google's access token on the event loop (firebase-admin's
    # httpx.Auth has only a sync flow), with a blocking request
    return await asyncio.to_thread(messaging.send_each_for_multicast, msg)


MAX_SEND_ATTEMPTS = 5


def event_key(apt: Apartment, ev: SseEvent, ts: str | None) -> str:
    """The same for every instance that receives this event of the engine; with its time, because a demonstration's or a
    restored engine's numbering can start again."""
    return f"push:{apt.apartment_id}:{ev.id}:{ts}"


async def claim_notification(key: str, tenant_id: str, pref: str, data: dict[str, str], headers: dict[str, str],
                             lease_s: float | None = None) -> dict | None:
    """The claim holding the message, or None when it is not ours to send. From here on a process that dies loses nothing:
    when the lease runs out recover_once sends it (see «Notifiche push» in bff/API.md)."""
    if not get_settings().fcm_enabled:
        return None
    payload = {"tenant_id": tenant_id, "pref": pref, "data": data, "headers": headers}
    lease = get_settings().notification_lease_s if lease_s is None else lease_s
    return payload if await get_repository().claim_work(key, runtime.BOOT_ID, lease, payload) == "mine" else None


async def notify_once(key: str, tenant_id: str, pref: str, data: dict[str, str], headers: dict[str, str]) -> int:
    """D-201: one notification however many instances saw the event: whoever claims it first sends it."""
    payload = await claim_notification(key, tenant_id, pref, data, headers)
    return await deliver(key, payload) if payload else 0


async def deliver(key: str, payload: dict) -> int:
    try:
        sent = await send_to_tenant(payload["tenant_id"], payload["pref"], payload["data"], payload["headers"])
    except Exception as exc:                       # still claimed: when its lease runs out recover_once tries again
        warn("push send failed", key=key, error=repr(exc))
        return 0
    await get_repository().finish_work(key)
    return sent


async def recover_once(now: float | None = None) -> int:
    """The notifications whose lease ran out without being sent: the process died, or FCM failed. Returns how many."""
    repo = get_repository()
    recovered = 0
    for item in await repo.due_work(now if now is not None else time.time()):
        key = item["key"]
        if item["attempts"] >= MAX_SEND_ATTEMPTS:
            await repo.finish_work(key)
            warn("push given up", key=key, attempts=item["attempts"])
            continue
        if await repo.claim_work(key, runtime.BOOT_ID, get_settings().notification_lease_s) != "mine":
            continue                                   # another instance got there first
        info("push recovered", key=key, attempts=item["attempts"])
        await deliver(key, item["payload"])
        recovered += 1
    return recovered


async def _every(seconds: float, work, what: str) -> None:
    while True:
        await asyncio.sleep(seconds)
        try:
            await work()
        except Exception as exc:
            warn("background round failed", what=what, error=type(exc).__name__)


def _dead_token(exc) -> bool:
    """Only tokens that can never work again: unregistered, or issued for another Firebase project. INVALID_ARGUMENT
    is not one of them: a malformed message fails every token with it, and they would all be wiped."""
    from firebase_admin import messaging

    return isinstance(exc, (messaging.UnregisteredError, messaging.SenderIdMismatchError))


async def _prune_tokens(dead: list[str]) -> None:
    if not dead:
        return
    repo = get_repository()
    for t in await repo.list_tenants():
        for u in await repo.list_users(t.tenant_id):
            if any(tok in u.push_tokens for tok in dead):
                u.push_tokens = [tok for tok in u.push_tokens if tok not in dead]
                await repo.upsert_user(u)
    info("push tokens pruned", count=len(dead))


def _spawn(coro, what: str, apartment_id: str) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _tasks.add(task)

    def done(t: asyncio.Task) -> None:
        _tasks.discard(t)
        if not t.cancelled() and t.exception() is not None:
            warn("push task failed", what=what, apartment_id=apartment_id, error=repr(t.exception()))

    task.add_done_callback(done)
    return task


def forget_apartment(apartment_id: str) -> None:
    """D-97: after a reset the pending "offline" timers and the "instance down" state of that apartment are gone."""
    for key, task in list(_offline_timers.items()):
        if key[0] == apartment_id:
            task.cancel()
            _offline_timers.pop(key, None)
    _health_down.discard(apartment_id)
    if (task := _down_timers.pop(apartment_id, None)) and not task.done():
        task.cancel()


async def _offline_alert_minutes(apt: Apartment) -> float | None:
    try:
        resp = await instances.call(apt, "GET", "/rules", timeout=5.0)
        for r in resp.json().get("rules", []):
            if r["rule_id"] == "offline_alert":
                return float(r["params"]["minutes"]) if r["enabled"] else None
    except Exception as exc:
        warn("offline_alert rule lookup failed", error=str(exc), apartment_id=apt.apartment_id)
    return 15.0


async def _offline_watch(apt: Apartment, device_id: str, ts: str | None, key: str) -> None:
    """D-201: every instance has this timer; `key` is the originating event's, so when it runs out only one sends."""
    minutes = await _offline_alert_minutes(apt)
    if minutes is None:
        return
    from engine.core import seconds_per_minute

    await asyncio.sleep(minutes * (seconds_per_minute() if get_settings().instance_mode == "mock" else 60.0))
    try:
        resp = await instances.call(apt, "GET", "/devices", timeout=5.0)
        dev = next((d for d in resp.json().get("devices", []) if d["device_id"] == device_id), None)
    except Exception:
        return
    if dev and not dev["online"]:
        await notify_once(key, apt.tenant_id, "offline", *device_offline_push(apt, device_id, dev.get("label") or device_id, minutes, ts))


async def _instance_down_watch(apt: Apartment, ts: str | None, key: str) -> None:
    """D-131: the "instance down" push only when it stays down as long as the offline_alert rule's minutes (the same
    wait as a device's); never with the rule off. A connector that drops and reconnects at once sends nothing."""
    minutes = await _offline_alert_minutes(apt)
    if minutes is None:
        return
    from engine.core import seconds_per_minute

    await asyncio.sleep(minutes * (seconds_per_minute() if get_settings().instance_mode == "mock" else 60.0))
    if apt.apartment_id in _health_down:
        await notify_once(key, apt.tenant_id, "offline", *instance_down_push(apt, ts))


async def on_stream_event(apt: Apartment, ev: SseEvent) -> None:
    """Hook of every instance hub: decides whether an event deserves a push and starts the sending in a task."""
    env = envelope(ev)
    data = env.get("data") or {}
    ts = env.get("ts")
    if ev.event == "approval.pending":
        approval_id = str(data.get("approval_id", ""))
        _spawn(notify_once(event_key(apt, ev, ts), apt.tenant_id, "approvals", *approval_push(apt, approval_id, data.get("description", ""), ts)),
               "approval", apt.apartment_id)
    elif ev.event == "device.online":
        key = (apt.apartment_id, str(data.get("device_id", "")))
        if (task := _offline_timers.pop(key, None)) and not task.done():
            task.cancel()
        if data.get("online") is False:
            _offline_timers[key] = _spawn(_offline_watch(apt, key[1], ts, event_key(apt, ev, ts)), "device_offline", apt.apartment_id)
    elif ev.event == "decision.logged" and data.get("action") == "booking_cancel_reset":
        decision_id = str(data.get("decision_id", ""))
        _spawn(notify_once(event_key(apt, ev, ts), apt.tenant_id, "bookings", *booking_reset_push(apt, decision_id, data.get("reasoning"), ts)),
               "booking", apt.apartment_id)
    elif ev.event == "decision.logged" and data.get("action") == "frost_inactive":     # D-164
        device_id = str((data.get("target") or {}).get("device_id", ""))
        _spawn(notify_once(event_key(apt, ev, ts), apt.tenant_id, "offline", *frost_inactive_push(apt, device_id, data.get("reasoning"), ts)),
               "frost_inactive", apt.apartment_id)
    elif ev.event == "instance.health":
        down = data.get("status") == "down"
        if down and apt.apartment_id not in _health_down:
            _health_down.add(apt.apartment_id)
            _down_timers[apt.apartment_id] = _spawn(_instance_down_watch(apt, ts, event_key(apt, ev, ts)), "instance_down", apt.apartment_id)
        elif not down:
            _health_down.discard(apt.apartment_id)
            if (task := _down_timers.pop(apt.apartment_id, None)) and not task.done():
                task.cancel()


async def align_hubs_once() -> None:
    """D-201: a change to the registry is made on one instance and the others learn it here, within HUB_ALIGN_S: closes the
    connections of apartments removed or disabled, makes again those whose link changed (the browsers on them reload, as
    after a reset) and, with FCM on, opens the missing ones, so that pushes do not depend on an open browser."""
    apartments = {a.apartment_id: a for a in await get_repository().list_apartments()}
    for apartment_id, hub in list(hub_manager.hubs.items()):
        apt = apartments.get(apartment_id)
        running = hub.task is not None and not hub.task.done()
        reason = ("removed" if apt is None else "disabled" if not apt.enabled and running
                  else "link changed" if running and hub.link not in (None, link_of(apt)) else None)
        if reason:
            forget_apartment(apartment_id)
            hub_manager.drop(apartment_id)
            info("upstream stream closed", apartment_id=apartment_id, reason=reason)
    if get_settings().fcm_enabled:
        for apt in apartments.values():
            if apt.enabled and not instances.demo_refused(apt.instance_url):
                hub_manager.hub(apt).start(None)


def _start_round(seconds: float, work, what: str) -> None:
    _loops.append(_spawn(_every(seconds, work, what), what, "-"))


async def start_background_hubs() -> None:
    if get_settings().fcm_enabled:
        await align_hubs_once()
        _start_round(get_settings().notification_lease_s, recover_once, "push recovery")
        _start_round(CURSOR_SAVE_S, hub_manager.save_cursors, "stream cursors")
    _start_round(HUB_ALIGN_S, align_hubs_once, "hub alignment")


def stop_background() -> None:
    while _loops:
        _loops.pop().cancel()


def register() -> None:
    if on_stream_event not in hub_manager.hooks:
        hub_manager.hooks.append(on_stream_event)
