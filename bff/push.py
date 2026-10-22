"""Push notifications: FCM behind FCM_ENABLED; stream hooks decide *when* to notify.

The message is data-only (no notification block, no webpush link): the PWA's service worker shows it. Its format is
agreed with the PWA and described in bff/API.md («Notifiche push»). Sending never blocks the stream: hooks only start
tasks, and task errors are logged.
"""
import asyncio

from . import instances
from .auth import sees, tenant_status
from .config import get_settings
from .logs import info, warn
from .repository import Apartment, get_repository
from .sse_hub import SseEvent, envelope, hub_manager

BODY_MAX = 200
TTL_SECONDS = {"approval": 3600, "device_offline": 86400, "instance_down": 86400, "booking": 86400,
               "summary": 7 * 86400,   # P-60 step 11: the weekly summary stays a week
               "frost_inactive": 86400}  # D-164: a boiler without its sensor in «casa vuota»

_offline_timers: dict[tuple[str, str], asyncio.Task] = {}
_health_down: set[str] = set()
_down_timers: dict[str, asyncio.Task] = {}      # D-131: the "instance down" push waits for the offline_alert minutes
_tasks: set[asyncio.Task] = set()  # strong references: the loop keeps only weak ones to running tasks


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
    return build_push("instance_down", apt, f"{apt.name}: istanza non raggiungibile", "Il connettore domotico risulta fermo",
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
        # Same event loop as the repository (the async Firestore client is bound to it): no thread, no asyncio.run.
        await _prune_tokens([t for t, r in zip(tokens, resp.responses) if not r.success and _dead_token(r.exception)])
    return len(tokens)


async def _send_multicast(tokens: list[str], data: dict[str, str], headers: dict[str, str]):
    import firebase_admin
    from firebase_admin import messaging

    if not firebase_admin._apps:
        firebase_admin.initialize_app(options={"projectId": get_settings().firebase_project_id})
    msg = messaging.MulticastMessage(tokens=tokens, data=data, webpush=messaging.WebpushConfig(headers=headers))
    return await messaging.send_each_for_multicast_async(msg)


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


async def _offline_watch(apt: Apartment, device_id: str, ts: str | None) -> None:
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
        await send_to_tenant(apt.tenant_id, "offline", *device_offline_push(apt, device_id, dev.get("label") or device_id, minutes, ts))


async def _instance_down_watch(apt: Apartment, ts: str | None) -> None:
    """D-131: the "instance down" push only when it stays down as long as the offline_alert rule's minutes (the same
    wait as a device's); never with the rule off. A connector that drops and reconnects at once sends nothing."""
    minutes = await _offline_alert_minutes(apt)
    if minutes is None:
        return
    from engine.core import seconds_per_minute

    await asyncio.sleep(minutes * (seconds_per_minute() if get_settings().instance_mode == "mock" else 60.0))
    if apt.apartment_id in _health_down:
        await send_to_tenant(apt.tenant_id, "offline", *instance_down_push(apt, ts))


async def on_stream_event(apt: Apartment, ev: SseEvent) -> None:
    """Hook of every instance hub: decides whether an event deserves a push and starts the sending in a task."""
    env = envelope(ev)
    data = env.get("data") or {}
    ts = env.get("ts")
    if ev.event == "approval.pending":
        approval_id = str(data.get("approval_id", ""))
        _spawn(send_to_tenant(apt.tenant_id, "approvals", *approval_push(apt, approval_id, data.get("description", ""), ts)),
               "approval", apt.apartment_id)
    elif ev.event == "device.online":
        key = (apt.apartment_id, str(data.get("device_id", "")))
        if (task := _offline_timers.pop(key, None)) and not task.done():
            task.cancel()
        if data.get("online") is False:
            _offline_timers[key] = _spawn(_offline_watch(apt, key[1], ts), "device_offline", apt.apartment_id)
    elif ev.event == "decision.logged" and data.get("action") == "booking_cancel_reset":
        decision_id = str(data.get("decision_id", ""))
        _spawn(send_to_tenant(apt.tenant_id, "bookings", *booking_reset_push(apt, decision_id, data.get("reasoning"), ts)),
               "booking", apt.apartment_id)
    elif ev.event == "decision.logged" and data.get("action") == "frost_inactive":     # D-164
        device_id = str((data.get("target") or {}).get("device_id", ""))
        _spawn(send_to_tenant(apt.tenant_id, "offline", *frost_inactive_push(apt, device_id, data.get("reasoning"), ts)),
               "frost_inactive", apt.apartment_id)
    elif ev.event == "instance.health":
        down = data.get("status") == "down"
        if down and apt.apartment_id not in _health_down:
            _health_down.add(apt.apartment_id)
            _down_timers[apt.apartment_id] = _spawn(_instance_down_watch(apt, ts), "instance_down", apt.apartment_id)
        elif not down:
            _health_down.discard(apt.apartment_id)
            if (task := _down_timers.pop(apt.apartment_id, None)) and not task.done():
                task.cancel()


async def start_background_hubs() -> None:
    """With FCM on, keep one upstream stream per enabled apartment so pushes do not depend on an open browser."""
    if not get_settings().fcm_enabled:
        return
    for apt in await get_repository().list_apartments():
        if apt.enabled:
            hub_manager.hub(apt).start(None)


def register() -> None:
    if on_stream_event not in hub_manager.hooks:
        hub_manager.hooks.append(on_stream_event)
