"""Push notifications: FCM behind FCM_ENABLED; stream hooks decide *when* to notify.

The message is data-only (no notification block, no webpush link): the PWA's service worker shows it. Its format is
agreed with the PWA and described in bff/API.md («Notifiche push»). Sending never blocks the stream: hooks only start
tasks, and task errors are logged.
"""
import asyncio
import time
from datetime import UTC, datetime, timedelta

from . import instances, runtime
from .auth import sees, tenant_status
from .config import get_settings
from .logs import info, warn
from .repository import Apartment, get_repository
from .sse_hub import CURSOR_SAVE_S, SseEvent, envelope, hub_manager, link_of

BODY_MAX = 200
TTL_SECONDS = {"approval": 3600, "device_offline": 86400, "instance_down": 86400, "booking": 86400,
               "summary": 7 * 86400,   # P-60 step 11: the weekly summary stays a week
               "frost_inactive": 86400,  # D-164: a boiler without its sensor in «casa vuota»
               "schedule_failed": 86400}  # D-219: scheduled actions not done

_offline_timers: dict[tuple[str, str], asyncio.Task] = {}
_health_down: set[str] = set()
_down_timers: dict[str, asyncio.Task] = {}      # D-131: the "instance down" push waits for the offline_alert minutes
_tasks: set[asyncio.Task] = set()  # strong references: the loop keeps only weak ones to running tasks
_loops: list[asyncio.Task] = []    # the rounds that last as long as the process
HUB_ALIGN_S = 60
_resumed: set[str] = set()         # the apartments whose timers this process has picked up (resume_watches)
OFFLINE_RESUME_MAX_S = 6 * 86400   # the claims last 7 days: an outage older than this could be notified a second time
# D-217: the engine that does not answer this process's stream. Since when (time.time()), its timer, and the last minutes
# of the offline_alert rule read while it answered (None: the rule off), because when it does not answer it cannot say
_unreachable: dict[str, float] = {}
_unreachable_timers: dict[str, asyncio.Task] = {}
_alert_minutes: dict[str, float | None] = {}
ALERT_MINUTES_DEFAULT = 15.0
# D-219: scheduled actions not done, grouped per apartment and category for SCHEDULE_GROUP_S from the first one
SCHEDULE_GROUP_S = 60.0
SCHEDULE_FAILURES = ("schedule_failed", "schedule_missed")
BOOKING_KINDS = ("prearrival", "checkout", "empty")       # the actions born from the bookings: category «Prenotazioni»
_schedule_groups: dict[tuple[str, str], dict] = {}
SUSPENSION_MAX_DAYS = 30           # UNREACHABLE_ALERTS_OFF_UNTIL further than this is refused: alerts stay on


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


def instance_unreachable_push(apt: Apartment, minutes: float, ts: str | None):
    """D-217: the server does not reach the engine itself (machine or process stopped, network cut). Same kind, tag and
    claim as instance_down: one notification per outage whatever its cause."""
    return build_push("instance_down", apt, f"{apt.name}: sistema domotico non raggiungibile",
                      f"Il sistema domotico non risponde da {int(minutes)} minuti: i comandi dall'app non arrivano e "
                      f"le regole automatiche potrebbero essere ferme.", f"/a/{apt.apartment_id}",
                      f"instance:{apt.apartment_id}", ts)


def schedule_failed_push(apt: Apartment, first_decision_id: str, reasonings: list[str], ts: str | None):
    """D-219: one or more scheduled actions not done (refused at their time, or missed with the engine down). Several
    of the same apartment and category close together are one notification, with the first in full."""
    n = len(reasonings)
    if n == 1:
        title, body = f"{apt.name}: azione programmata non eseguita", reasonings[0]
    else:
        title, body = f"{apt.name}: azioni programmate non eseguite", f"{n} azioni programmate non eseguite. La prima: {reasonings[0]}"
    return build_push("schedule_failed", apt, title, body or "Azione programmata non eseguita",
                      f"/a/{apt.apartment_id}/programmazione", f"schedule:{apt.apartment_id}:{first_decision_id}", ts)


def maintenance_push(apt: Apartment, n: int):
    """D-219: at the end of a planned shutdown, the scheduled actions it made the engine miss, one notification."""
    body = ("Durante la manutenzione 1 azione programmata non è stata eseguita" if n == 1
            else f"Durante la manutenzione {n} azioni programmate non sono state eseguite")
    return build_push("schedule_failed", apt, f"{apt.name}: azioni programmate non eseguite", body,
                      f"/a/{apt.apartment_id}/programmazione", f"maintenance:{apt.apartment_id}")


def maintenance_key(apt: Apartment) -> str:
    """D-219: the summary of one planned shutdown, one per apartment: kept claimed until the suspension ends, then due."""
    return f"push:maintenance:{apt.apartment_id}"


MAINTENANCE_LEASE_MAX_S = 6 * 86400              # the claims last 7 days in Firestore (retention.work_claim)


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
    _resumed.discard(apartment_id)
    if (task := _down_timers.pop(apartment_id, None)) and not task.done():
        task.cancel()
    _unreachable.pop(apartment_id, None)
    _alert_minutes.pop(apartment_id, None)
    for key in [k for k in _schedule_groups if k[0] == apartment_id]:
        _schedule_groups.pop(key, None)            # its flush finds nothing
    if (task := _unreachable_timers.pop(apartment_id, None)) and not task.done():
        task.cancel()


async def _offline_alert_minutes(apt: Apartment) -> float | None:
    try:
        resp = await instances.call(apt, "GET", "/rules", timeout=5.0)
        for r in resp.json().get("rules", []):
            if r["rule_id"] == "offline_alert":
                minutes = float(r["params"]["minutes"]) if r["enabled"] else None
                _alert_minutes[apt.apartment_id] = minutes        # D-217: what to use when the engine does not answer
                return minutes
    except Exception as exc:
        warn("offline_alert rule lookup failed", error=str(exc), apartment_id=apt.apartment_id)
    return ALERT_MINUTES_DEFAULT


def alerts_suspended_until(now: datetime | None = None) -> datetime | None:
    """D-217: the end of the suspension of the «sistema domotico non raggiungibile» notifications, or None (on). A value
    that cannot be read, without its offset, past, or further than SUSPENSION_MAX_DAYS leaves them on (the prudent
    side); start_background_hubs writes which."""
    raw = get_settings().unreachable_alerts_off_until
    if not raw:
        return None
    try:
        until = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = now or datetime.now(UTC)
    if until.tzinfo is None or until <= now or until - now > timedelta(days=SUSPENSION_MAX_DAYS):
        return None
    return until


def _suspension_note() -> None:
    raw = get_settings().unreachable_alerts_off_until
    if not raw:
        return
    until = alerts_suspended_until()
    if until:
        info("unreachable alerts suspended", until=until.isoformat())
    else:
        warn("UNREACHABLE_ALERTS_OFF_UNTIL ignored: alerts on", value=raw[:40],
             reason=f"not an ISO 8601 instant with its offset, past, or more than {SUSPENSION_MAX_DAYS} days ahead")


async def _after_suspension(apt: Apartment) -> None:
    """While suspended the notification waits for the end of the suspension, then whoever called looks again: an engine
    still down after a planned shutdown is told."""
    until = alerts_suspended_until()
    if until:
        info("instance alert waits for the end of the suspension", apartment_id=apt.apartment_id, until=until.isoformat())
        await asyncio.sleep((until - datetime.now(UTC)).total_seconds())


def _minute_s() -> float:
    from engine.core import seconds_per_minute

    return seconds_per_minute() if get_settings().instance_mode == "mock" else 60.0


async def _engine_answers(apt: Apartment) -> bool:
    try:
        return (await instances.call(apt, "GET", "/health", timeout=5.0)).status_code == 200
    except Exception:
        return False


async def _unreachable_watch(apt: Apartment, since: float) -> None:
    """D-217: the engine has not answered this process since `since`. After the offline_alert rule's minutes (the last
    ones read; 15 if never; nothing with the rule off), and after a suspension if there is one, it is asked once more;
    still silent, one notification for the outage (the instance_down claim: one for every instance and every cause)."""
    apartment_id = apt.apartment_id
    minutes = _alert_minutes.get(apartment_id, ALERT_MINUTES_DEFAULT)
    if minutes is None:
        return
    await asyncio.sleep(max(0.0, minutes * _minute_s() - (time.time() - since)))
    await _after_suspension(apt)
    if apartment_id not in _unreachable or await _engine_answers(apt):
        return                                     # back meanwhile, maybe before this process saw it
    ts = datetime.fromtimestamp(since, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    await notify_once(instance_down_key(apt), apt.tenant_id, "offline", *instance_unreachable_push(apt, minutes, ts))


def reachable_note_key(apt: Apartment) -> str:
    """D-217: one decision «di nuovo raggiungibile» per outage, whatever the number of instances: taken and finished at
    the return, released when the next outage starts. Without a payload, push recovery never picks it up."""
    return f"note:reachable:{apt.apartment_id}"


def _iso_utc(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def _note_reachable(apt: Apartment, since: float, until: float) -> None:
    """D-217: the engine writes in its Decisions «Sistema domotico di nuovo raggiungibile dopo …» (POST
    /_internal/reachability, a route of the engine outside the contract). One instance; an engine without the route
    (404) is skipped with a line; a failure is written and not retried: it is a note, the outage is over."""
    key, repo = reachable_note_key(apt), get_repository()
    if await repo.claim_work(key, runtime.BOOT_ID, get_settings().notification_lease_s) != "mine":
        return
    try:
        resp = await instances.call(apt, "POST", "/_internal/reachability",
                                    json={"from": _iso_utc(since), "to": _iso_utc(until)}, timeout=5.0)
        if resp.status_code == 404:
            warn("reachability note skipped: the engine has no route", apartment_id=apt.apartment_id)
        elif not 200 <= resp.status_code < 300:
            warn("reachability note refused", apartment_id=apt.apartment_id, status=resp.status_code)
        else:
            info("reachability note written", apartment_id=apt.apartment_id, after_s=int(until - since))
    except Exception as exc:
        warn("reachability note not written", apartment_id=apt.apartment_id, error=type(exc).__name__)
    finally:
        await repo.finish_work(key)


async def on_link_change(apt: Apartment, up: bool) -> None:
    """Hook of every instance hub (D-217): the engine stopped answering this process's stream, or answers again."""
    apartment_id = apt.apartment_id
    if not up:
        if apartment_id not in _unreachable:
            _unreachable[apartment_id] = time.time()
            info("engine unreachable, waiting", apartment_id=apartment_id)
            _unreachable_timers[apartment_id] = _spawn(_unreachable_watch(apt, _unreachable[apartment_id]),
                                                       "instance_unreachable", apartment_id)
            _spawn(get_repository().release_work(reachable_note_key(apt)), "reachability note", apartment_id)
        return
    threshold = (_alert_minutes.get(apartment_id) or ALERT_MINUTES_DEFAULT) * _minute_s()   # the rule off: 15
    _spawn(_offline_alert_minutes(apt), "alert minutes", apartment_id)      # kept for the next outage
    since = _unreachable.pop(apartment_id, None)
    if (task := _unreachable_timers.pop(apartment_id, None)) and not task.done():
        task.cancel()
    if since is not None:
        now = time.time()
        info("engine reachable again", apartment_id=apartment_id, after_s=int(now - since))
        if now - since >= threshold:               # the short drops do not fill the Decisions; also when suspended
            _spawn(_note_reachable(apt, since, now), "reachability note", apartment_id)
        # what the engine says now: the outage's claim released if it is fine, its connector watched if not, the devices
        # still offline waited for (the events of the outage may be gone)
        _resumed.add(apartment_id)
        _spawn(resume_watches(apt), "resume", apartment_id)


def offline_key(apt: Apartment, device_id: str, last_seen: str | None) -> str | None:
    """One outage of one device: the engine moves last_seen only when the device answers, so every instance gets the same
    key whichever event started its timer, also one that started later."""
    return f"push:offline:{apt.apartment_id}:{device_id}:{last_seen}" if last_seen else None


def instance_down_key(apt: Apartment) -> str:
    """The engine repeats instance.health at every change of a device, and has no date for the start of an outage: one
    claim for the whole outage, released when the connector is back."""
    return f"push:instance_down:{apt.apartment_id}"


async def _offline_watch(apt: Apartment, device_id: str, ts: str | None, key: str, already_s: float = 0.0) -> None:
    """D-201: every instance has this timer; when it runs out only one sends. `already_s`: how long the device has been
    offline when a process that has just started picks up the wait (resume_watches)."""
    minutes = await _offline_alert_minutes(apt)
    if minutes is None:
        return
    from engine.core import seconds_per_minute

    await asyncio.sleep(max(0.0, minutes * (seconds_per_minute() if get_settings().instance_mode == "mock" else 60.0) - already_s))
    try:
        resp = await instances.call(apt, "GET", "/devices", timeout=5.0)
        dev = next((d for d in resp.json().get("devices", []) if d["device_id"] == device_id), None)
    except Exception:
        return
    if dev and not dev["online"]:
        await notify_once(offline_key(apt, device_id, dev.get("last_seen")) or key, apt.tenant_id, "offline",
                          *device_offline_push(apt, device_id, dev.get("label") or device_id, minutes, ts))


async def _instance_down_watch(apt: Apartment, ts: str | None) -> None:
    """D-131: the "instance down" push only when it stays down as long as the offline_alert rule's minutes (the same
    wait as a device's); never with the rule off. A connector that drops and reconnects at once sends nothing."""
    minutes = await _offline_alert_minutes(apt)
    if minutes is None:
        return
    from engine.core import seconds_per_minute

    await asyncio.sleep(minutes * (seconds_per_minute() if get_settings().instance_mode == "mock" else 60.0))
    await _after_suspension(apt)                   # D-217: a planned shutdown is not told
    if apt.apartment_id in _health_down:
        await notify_once(instance_down_key(apt), apt.tenant_id, "offline", *instance_down_push(apt, ts))


async def resume_watches(apt: Apartment) -> None:
    """D-201: the timers live in memory, so a publication or a crash loses them, and the events that started them are
    already behind the saved id. A process that opens a connection asks the engine who is offline now and goes on waiting;
    what was already notified is stopped by the claim."""
    apartment_id = apt.apartment_id
    try:
        health = (await instances.call(apt, "GET", "/health", timeout=5.0)).json()
        devices = (await instances.call(apt, "GET", "/devices", timeout=5.0)).json().get("devices") or []
        if health.get("status") != "down":
            await get_repository().release_work(instance_down_key(apt))    # the outage ended while nobody was listening
        elif apartment_id not in _health_down:
            _health_down.add(apartment_id)
            _down_timers[apartment_id] = _spawn(_instance_down_watch(apt, health.get("checked_at")), "instance_down", apartment_id)
        if health.get("status") == "down":                                  # the notification of the outage says it all
            return
        for device in devices:
            seen, timer = device.get("last_seen"), (apartment_id, device["device_id"])
            if device.get("online") or not seen or (timer in _offline_timers and not _offline_timers[timer].done()):
                continue
            offline_for = time.time() - datetime.fromisoformat(seen.replace("Z", "+00:00")).timestamp()
            if offline_for <= OFFLINE_RESUME_MAX_S:
                _offline_timers[timer] = _spawn(_offline_watch(apt, device["device_id"], seen, offline_key(apt, device["device_id"], seen),
                                                               offline_for), "device_offline", apartment_id)
    except Exception as exc:                       # the engine does not answer now: the next round asks again
        _resumed.discard(apartment_id)
        info("offline timers not resumed yet", apartment_id=apartment_id, error=type(exc).__name__)


def schedule_pref(kind: str | None) -> str:
    """D-219: pre-arrivo, check-out and casa vuota go to «Prenotazioni»; the manual ones and the assistant's (and an
    engine that does not say the kind) to «Dispositivi e sistema domotico offline», their usual cause."""
    return "bookings" if kind in BOOKING_KINDS else "offline"


def _schedule_not_done(apt: Apartment, ev: SseEvent, data: dict, ts: str | None) -> None:
    """D-219: the engine's decision schedule_failed or schedule_missed joins the open group of its apartment and
    category, or opens one. The key of the group is its first event's, the same on every instance that receives it."""
    if data.get("action") == "schedule_missed" and alerts_suspended_until():
        # after a planned shutdown no burst: the engine writes them all at its start, they make one summary (D-219)
        key = (apt.apartment_id, "maintenance")
        group = _schedule_groups.get(key)
        if group is None:
            group = _schedule_groups[key] = {"kinds": []}
            _spawn(_keep_maintenance_summary(apt, key), "maintenance summary", apt.apartment_id)
        group["kinds"].append(data.get("new_value"))
        return
    pref = schedule_pref(data.get("new_value"))
    key = (apt.apartment_id, pref)
    group = _schedule_groups.get(key)
    if group is None:
        group = _schedule_groups[key] = {"first": str(data.get("decision_id", "")), "claim": event_key(apt, ev, ts),
                                         "ts": ts, "reasonings": []}
        _spawn(_flush_schedule_group(apt, key), "schedule_failed", apt.apartment_id)
    group["reasonings"].append(str(data.get("reasoning") or "").strip())


async def _flush_schedule_group(apt: Apartment, key: tuple[str, str]) -> None:
    await asyncio.sleep(SCHEDULE_GROUP_S)
    group = _schedule_groups.pop(key, None)
    if not group:
        return
    await notify_once(f"{group['claim']}:schedule:{key[1]}", apt.tenant_id, key[1],
                      *schedule_failed_push(apt, group["first"], group["reasonings"], group["ts"]))


async def _keep_maintenance_summary(apt: Apartment, key: tuple[str, str]) -> None:
    """D-219: the missed actions of a planned shutdown wait as one notification, claimed until the end of the suspension:
    then the push recovery (recover_once, any instance) sends it. When the suspension is removed early the new revision
    makes it due at its start (expire_maintenance_summaries). One per apartment: the first instance keeps it."""
    await asyncio.sleep(SCHEDULE_GROUP_S)
    group = _schedule_groups.pop(key, None)
    until = alerts_suspended_until()
    if not group or not get_settings().fcm_enabled:
        return
    kinds = group["kinds"]
    pref = "bookings" if any(k in BOOKING_KINDS for k in kinds) else "offline"
    data, headers = maintenance_push(apt, len(kinds))
    payload = {"tenant_id": apt.tenant_id, "pref": pref, "data": data, "headers": headers}
    left = (until - datetime.now(UTC)).total_seconds() if until else 0.0
    lease = min(max(left, 0.0), MAINTENANCE_LEASE_MAX_S)
    repo = get_repository()
    claimed = await repo.claim_work(maintenance_key(apt), runtime.BOOT_ID, lease, payload)
    if claimed == "done":                          # the summary of an earlier shutdown, already sent
        await repo.release_work(maintenance_key(apt))
        claimed = await repo.claim_work(maintenance_key(apt), runtime.BOOT_ID, lease, payload)
    info("maintenance summary kept", apartment_id=apt.apartment_id, missed=len(kinds), outcome=claimed, lease_s=int(lease))


async def expire_maintenance_summaries() -> int:
    """D-219: a process that starts without a suspension (the variable removed: a new revision) makes the kept summaries
    due at once; recover_once sends them within its round."""
    if alerts_suspended_until():
        return 0
    repo = get_repository()
    expired = 0
    for apt in await repo.list_apartments():
        if await repo.expire_work(maintenance_key(apt)):
            expired += 1
            info("maintenance summary due", apartment_id=apt.apartment_id)
    return expired


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
    elif ev.event == "decision.logged" and data.get("action") in SCHEDULE_FAILURES:     # D-219
        _schedule_not_done(apt, ev, data, ts)
    elif ev.event == "decision.logged" and data.get("action") == "frost_inactive":     # D-164
        device_id = str((data.get("target") or {}).get("device_id", ""))
        _spawn(notify_once(event_key(apt, ev, ts), apt.tenant_id, "offline", *frost_inactive_push(apt, device_id, data.get("reasoning"), ts)),
               "frost_inactive", apt.apartment_id)
    elif ev.event == "instance.health":
        down = data.get("status") == "down"
        if down and apt.apartment_id not in _health_down:
            _health_down.add(apt.apartment_id)
            _down_timers[apt.apartment_id] = _spawn(_instance_down_watch(apt, ts), "instance_down", apt.apartment_id)
        elif not down:
            if apt.apartment_id in _health_down:
                _spawn(get_repository().release_work(instance_down_key(apt)), "instance_up", apt.apartment_id)
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
                if apt.apartment_id not in _resumed:
                    _resumed.add(apt.apartment_id)
                    _spawn(resume_watches(apt), "resume", apt.apartment_id)


def _start_round(seconds: float, work, what: str) -> None:
    _loops.append(_spawn(_every(seconds, work, what), what, "-"))


async def start_background_hubs() -> None:
    _suspension_note()
    if get_settings().fcm_enabled:
        try:
            await expire_maintenance_summaries()       # D-219: the suspension removed, the summaries go now
        except Exception as exc:
            warn("maintenance summaries not made due", error=type(exc).__name__)
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
    if on_link_change not in hub_manager.link_hooks:
        hub_manager.link_hooks.append(on_link_change)
