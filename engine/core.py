"""The engine of one apartment (contract 1.0.4): rules, modes, bookings, schedule, approvals, decisions, assistant,
the commands' life and the event stream. In memory until step 3 of the plan (SQLite).

Moved here from the BFF's simulated engine (bff/mock_instance/state.py) at P-60 step 2: one program for the engine
and the demonstration apartments, which the BFF still mounts at /mock. The devices are behind the connector
interface (engine/connector/): the catalog comes from the connector, commands go through its execute() and the state
it reports through changes()."""
import asyncio
import calendar
import copy
import random
import re
import time
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from . import log as logs
from .connector.interface import CommandResult, ConnectorCommand, DeviceInfo, StateChange
from .confirmation import delivered_outcome
from .connector.simulated import SimulatedConnector
from .store import MemoryStore

CONTRACT_VERSION = "1.0.4"
COMMAND_DEADLINE_S = 9           # the connector's deadline, inside the contract's 10 s (connector.md §2.2)
# what a command asks the device: only the device's fields of the capability (connector.md §2.4, D-108)
TARGET_FIELDS = {"switch": ("on",), "climate": ("on", "mode", "setpoint", "fan"), "heating": ("on",)}
# the fields of each capability in the contract (components.schemas.Cap*): nothing else reaches the app
CONTRACT_FIELDS = {
    "switch": ("on",), "power_meter": ("watts", "kwh_today"),
    "climate": ("on", "mode", "setpoint", "fan", "setpoint_min", "setpoint_max", "confirmation"),
    "heating": ("on", "setpoint", "setpoint_min", "setpoint_max"), "temperature": ("celsius",),
    "humidity": ("percent",), "contact": ("open", "since"), "motion": ("detected", "last_seen"),
}
ALL_FEATURES = ["apartment", "devices", "commands", "energy", "schedule", "rules", "approvals", "decisions", "ask", "bookings", "stream"]
MODES = ["comfort", "eco", "empty"]
CLIMATE_MODES = ["cool", "heat", "dry", "fan"]
FANS = ["auto", "low", "mid", "high"]
ACTIONS = {"switch": ["turn_on", "turn_off"], "climate": ["set_climate", "turn_off"], "heating": ["set_heating", "turn_off"]}
PARAMS = {"set_climate": ["on", "mode", "setpoint", "fan"], "set_heating": ["on", "setpoint"]}
FINAL = {"acked", "failed", "timeout"}
BUFFER_SECONDS = 3600
# retention (D-94): the activity log 24 months, bookings 12 months after the check-out (their schedule 12 months after
# it runs), commands and assistant requests 90 days (the contract asks at least 7), the hourly consumption 24 months
DECISION_MONTHS, BOOKING_MONTHS, COMMAND_DAYS, TELEMETRY_MONTHS = 24, 12, 90, 24
RETENTION_EVERY_S = 3600
ARREARS_MINUTES = 30      # at a restart, a scheduled action older than this is not run any more: failed, "missed"
# the engine's own fields of a capability, kept across restarts (the device reports the others again)
ENGINE_FIELDS = {"heating": ("setpoint",), "contact": ("since",), "motion": ("last_seen",), "power_meter": ("kwh_today",)}

NAMES = {"apt-rimini-01": "Via Roma 12 – int. 3", "apt-bologna-01": "Corso Italia 5 – int. 7"}

DEFAULT_RULES = [
    {"rule_id": "window_open_off", "label": "Finestra aperta spegne il clima", "enabled": True, "editable": True,
     "params": {"minutes": 5}, "limits": {"minutes": {"min": 1, "max": 30}}},
    {"rule_id": "setpoint_limits", "label": "Limiti del setpoint", "enabled": True, "editable": True,
     "params": {"min": 16, "max": 24}, "limits": {"min": {"min": 7, "max": 20}, "max": {"min": 20, "max": 28}}},
    {"rule_id": "frost_protection", "label": "Antigelo a casa vuota", "enabled": True, "editable": True,
     "params": {"celsius": 8}, "limits": {"celsius": {"min": 5, "max": 12}}},
    {"rule_id": "mold_protection", "label": "Antimuffa a casa vuota", "enabled": True, "editable": True,
     "params": {"humidity_percent": 65}, "limits": {"humidity_percent": {"min": 50, "max": 80}}},
    {"rule_id": "prearrival", "label": "Pre-arrivo", "enabled": True, "editable": True,
     "params": {"hours_before": 2}, "limits": {"hours_before": {"min": 0, "max": 6}}},
    {"rule_id": "checkout_eco", "label": "Risparmio al check-out", "enabled": True, "editable": True,
     "params": {"minutes_after": 30}, "limits": {"minutes_after": {"min": 0, "max": 180}}},
    {"rule_id": "compressor_min_off", "label": "Pausa minima del compressore", "enabled": True, "editable": False,
     "params": {"minutes": 3}, "limits": {"minutes": {"min": 3, "max": 3}}},
    {"rule_id": "offline_alert", "label": "Avviso dispositivo offline", "enabled": True, "editable": True,
     "params": {"minutes": 15}, "limits": {"minutes": {"min": 5, "max": 120}}},
]


def seconds_per_minute() -> float:
    """MOCK_TIME_SCALE = real seconds per simulated minute (1 in dev, 60 = real time)."""
    import os

    return float(os.environ.get("MOCK_TIME_SCALE", "1"))


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_dt(value) -> datetime:
    if not isinstance(value, str):
        raise ValueError("not a string")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timezone required")
    return dt


def fmt_num(n) -> str:
    return f"{n:g}".replace(".", ",")


class MockError(Exception):
    def __init__(self, status: int, error: str, message: str, details: dict | None = None):
        self.status, self.error, self.message, self.details = status, error, message, details

    def body(self) -> dict:
        b = {"error": self.error, "message": self.message}
        if self.details:
            b["details"] = self.details
        return b


def bad_request(message: str) -> MockError:
    return MockError(400, "bad_request", message)


def describe(cap: str, state: dict) -> str:
    if not state.get("on"):
        return "off"
    if cap == "climate":
        return f"{state['mode']} {fmt_num(state['setpoint'])}"
    if cap == "heating":
        return f"on {fmt_num(state['setpoint'])}"
    return "on"


class EnergyCounter:
    """kwh_today of one power meter, from the connector's raw cumulative counter (energy_total_wh, connector.md §2.3)
    since the apartment's local midnight. A counter that drops (the device restarted) counts again from zero. Its
    state is saved with the engine's, so neither kwh_today nor the hourly telemetry start again after a restart."""

    def __init__(self, timezone: str, state: dict | None = None):
        self.tz = ZoneInfo(timezone)
        state = state or {}
        self.day = state.get("day")                    # ISO date, local
        self.last_wh: float | None = state.get("last_wh")
        self.today_wh = float(state.get("today_wh", 0.0))

    def state(self) -> dict:
        return {"day": self.day, "last_wh": self.last_wh, "today_wh": self.today_wh}

    def update(self, total_wh: float, ts: datetime) -> tuple[float, float]:
        """(kwh_today, Wh used since the previous reading)."""
        day = ts.astimezone(self.tz).date().isoformat()
        if day != self.day:
            self.day, self.today_wh = day, 0.0
        used = 0.0
        if self.last_wh is not None:
            used = total_wh - self.last_wh if total_wh >= self.last_wh else total_wh
        self.today_wh += used
        self.last_wh = total_wh
        return round(self.today_wh / 1000, 3), used


class ApartmentEngine:
    def __init__(self, apartment_id: str, connector=None, *, simulated: bool = True, seed: bool | None = None,
                 implementation: dict | None = None, store: MemoryStore | None = None):
        """Without a connector: the demonstration apartment, a SimulatedConnector chosen by the apartment's id. seed
        (by default: without a connector) adds the demonstration's bookings and decisions; otherwise the history
        starts empty and the apartment in mode "empty". store: where the state lives (engine/store.py), in memory by
        default; a store that already holds an apartment is loaded instead of seeded."""
        self.apartment_id = apartment_id
        self.name = NAMES.get(apartment_id, apartment_id)
        self.timezone = "Europe/Rome"
        variant = 1 if "bologna" in apartment_id else 0
        seeded = connector is None if seed is None else seed
        self.connector = SimulatedConnector(variant) if connector is None else connector
        self.store = store if store is not None else MemoryStore()
        self.simulated = simulated
        self.implementation = implementation or {"name": "bff-mock-instance", "version": "0.1.0"}
        self.meters: dict[str, EnergyCounter] = {}
        self.rooms = [{"room_id": r.room_id, "name": r.name} for r in self.connector.rooms()]
        self.rules = copy.deepcopy(DEFAULT_RULES)
        # (device_id, capability, correlation_id, state requested) of the commands running: at most one per device
        self.inflight: list[tuple[str, str, str, dict]] = []
        self.device_locks: dict[str, asyncio.Lock] = {}
        self.rules_updated_at = "2026-10-10T09:00:00.000Z"
        self.mode = "comfort" if seeded and variant == 0 else "empty"
        self.hold: dict | None = None
        self.bookings: dict[str, dict] = {}
        self.processed_events: dict[str, dict] = {}
        self.schedule: dict[str, dict] = {}
        self.commands: dict[str, dict] = {}
        self.approvals: list[dict] = []
        self.approval_queue: list[dict] = []
        self.decisions: list[dict] = []
        self.asks: dict[str, dict] = {}
        self.events: deque[dict] = deque()
        self.subscribers: set[asyncio.Queue] = set()
        self.idem: dict[str, tuple[float, int, object]] = {}
        self.counter = 1000
        self.started_at = time.monotonic()
        self.loop_task: asyncio.Task | None = None
        self.consumer_task: asyncio.Task | None = None
        self.tasks: set[asyncio.Task] = set()
        self.last_housekeeping = self.last_retention = time.monotonic()
        self.restored = bool(self.store.get_meta("initialized"))
        if self.restored:
            self._load()
        else:
            self.devices = {d.device_id: self._device_from(d) for d in self.connector.devices()}
            for device in self.devices.values():
                self._save_device(device)
            self._save_apartment()
            if seeded:
                self._seed_history(variant)
            self.store.put_meta("initialized", {"at": iso(utcnow()), "seeded": seeded})

    # ---- infrastructure -------------------------------------------------
    def next_id(self, prefix: str) -> str:
        self.counter += 1
        self.store.put_meta("counter", self.counter)      # an id is never given twice, also across restarts
        return f"{prefix}-{self.counter:04x}"

    # ---- persistence (engine/store.py) -----------------------------------
    def _save_apartment(self) -> None:
        self.store.put_meta("apartment", {"mode": self.mode, "hold": self.hold, "rules": self.rules,
                                          "rules_updated_at": self.rules_updated_at})

    def _save_device(self, device: dict) -> None:
        self.store.put("devices", device["device_id"], device)

    def _save_meter(self, device_id: str) -> None:
        self.store.put("meters", device_id, self.meters[device_id].state())

    def _save_command(self, cmd: dict) -> None:
        self.store.put("commands", cmd["command_id"], cmd, expire_at=expire(cmd["created_at"], days=COMMAND_DAYS))

    def _save_decision(self, d: dict) -> None:
        self.store.put("decisions", d["decision_id"], d, expire_at=expire(d["ts"], months=DECISION_MONTHS))

    def _save_schedule(self, item: dict) -> None:
        self.store.put("schedule", item["schedule_id"], item, expire_at=expire(item["run_at"], months=BOOKING_MONTHS))

    def _save_booking(self, b: dict) -> None:
        doc = {**b, "checkin": iso(b["checkin"]), "checkout": iso(b["checkout"])}
        self.store.put("bookings", b["booking_id"], doc, expire_at=expire(doc["checkout"], months=BOOKING_MONTHS))

    def _save_processed(self, event_id: str, result: dict, checkout: datetime) -> None:
        self.store.put("processed_events", event_id, result, expire_at=expire(iso(checkout), months=BOOKING_MONTHS))

    def _save_approval(self, a: dict) -> None:
        self.store.put("approvals", a["approval_id"], a, expire_at=expire(a["created_at"], months=DECISION_MONTHS))

    def _save_queue(self) -> None:
        self.store.put_meta("approval_queue", self.approval_queue)

    def _save_ask(self, a: dict) -> None:
        self.store.put("asks", a["ask_id"], a, expire_at=expire(a["created_at"], days=COMMAND_DAYS))

    def _load(self) -> None:
        """The apartment as the store keeps it. Devices: what the connector reports now, with the engine's own
        fields (name, room, a boiler's setpoint, since, last_seen, kwh_today) as they were."""
        st = self.store
        apt = st.get_meta("apartment") or {}
        self.mode = apt.get("mode", self.mode)
        self.hold = apt.get("hold")
        self.rules = apt.get("rules", self.rules)
        self.rules_updated_at = apt.get("rules_updated_at", self.rules_updated_at)
        self.counter = st.get_meta("counter", self.counter)
        self.meters = {k: EnergyCounter(self.timezone, v) for k, v in st.all("meters")}
        stored = dict(st.all("devices"))
        self.devices = {}
        for info in self.connector.devices():
            device = self._device_from(info)
            old = stored.get(info.device_id)
            if old:
                device["label"], device["room_id"] = old["label"], old["room_id"]
                for cap, fields in ENGINE_FIELDS.items():
                    if cap in device["capabilities"] and cap in old["capabilities"]:
                        if cap == "power_meter" and info.device_id in self.meters:
                            continue                    # kwh_today comes from the restored counter
                        for f in fields:
                            if f in old["capabilities"][cap]:
                                device["capabilities"][cap][f] = old["capabilities"][cap][f]
                contact, was = device["capabilities"].get("contact"), old["capabilities"].get("contact")
                if contact and was and contact.get("open") != was.get("open"):
                    contact["since"] = iso(utcnow())    # it changed while the engine was down
            self.devices[info.device_id] = device
            self._save_device(device)
        sl = self.rule("setpoint_limits")["params"]
        for device in self.devices.values():               # the limits are the rules', not the catalog's
            c = device["capabilities"].get("climate")
            if c:
                c["setpoint_min"], c["setpoint_max"] = sl["min"], sl["max"]
                c["setpoint"] = min(max(c["setpoint"], sl["min"]), sl["max"])
        self.commands = dict(st.all("commands"))
        self.decisions = [d for _, d in st.all("decisions")]
        self.schedule = dict(st.all("schedule"))
        self.bookings = {k: {**b, "checkin": parse_dt(b["checkin"]), "checkout": parse_dt(b["checkout"])}
                         for k, b in st.all("bookings")}
        self.processed_events = dict(st.all("processed_events"))
        self.approvals = [a for _, a in st.all("approvals")]
        self.approval_queue = st.get_meta("approval_queue", [])
        self.asks = dict(st.all("asks"))
        now = time.time()
        self.idem = {k: (v["until"], v["status"], v["body"]) for k, v in st.all("idem") if v["until"] > now}
        for i, t, env in st.events_since(now - BUFFER_SECONDS):
            self.events.append({"id": str(i), **env, "_t": t})
        self._after_restart()
        self._purge_retention()

    def _after_restart(self) -> None:
        """What the restart interrupted (P-60 step 3): a command half way is failed with its decision (the contract has
        no reason "restart": internal_error, and the decision says why); a pending assistant request is failed; an
        action scheduled more than ARREARS_MINUTES ago, that could not run while the engine was down, is failed as
        missed with its decision. The younger ones run at the first tick, as usual."""
        for cmd in self.commands.values():
            if cmd["status"] in FINAL:
                continue
            self._set_status(cmd, "failed", "internal_error")
            self.log("system", {"type": "device", "device_id": cmd["device_id"]}, cmd["action"], None, None,
                     "Motore riavviato durante il comando: esito sconosciuto, comando non completato", "failed",
                     cmd["correlation_id"], command_id=cmd["command_id"])
        for ask in self.asks.values():
            if ask["status"] == "pending":
                ask.update(status="failed", reason="internal_error", updated_at=iso(utcnow()),
                           answer="Il motore è stato riavviato prima di rispondere: riprova.")
                self._save_ask(ask)
        now = utcnow()
        for item in sorted(self.schedule.values(), key=lambda s: s["run_at"]):
            late = now - parse_dt(item["run_at"])
            if item["status"] != "planned" or late <= timedelta(minutes=ARREARS_MINUTES):
                continue
            item["status"], item["executed_at"] = "failed", iso(now)
            self._save_schedule(item)
            self.log("system", {"type": "schedule"}, "schedule_missed", item["run_at"], None,
                     f"Azione programmata non eseguita: il motore era fermo all'orario previsto ({item['run_at']}), "
                     f"oltre {ARREARS_MINUTES} minuti fa", "failed", str(uuid.uuid4()))

    def spawn(self, coro) -> None:
        task = asyncio.get_running_loop().create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def ensure_started(self) -> None:
        if self.loop_task is None or self.loop_task.done():
            self.loop_task = asyncio.get_running_loop().create_task(self._tick_loop())
            self.device_locks = {}          # a new event loop (the tests run one per case): locks belong to a loop
        if self.consumer_task is None or self.consumer_task.done():
            self.consumer_task = asyncio.get_running_loop().create_task(self._consume_changes())

    async def _consume_changes(self) -> None:
        async for change in self.connector.changes():
            try:
                self._apply_change(change)
            except Exception as exc:
                logs.error("state change not applied", apartment_id=self.apartment_id, device_id=change.device_id,
                           error=str(exc)[:200])

    # ---- from the connector's view to the contract's ---------------------
    def _device_from(self, d: DeviceInfo) -> dict:
        """A device as GET /devices shows it: the contract's fields of each capability (never links, never the raw
        energy_total_wh); the engine's own fields the connector does not report get their starting value."""
        caps = {}
        for cap, raw in d.capabilities.items():
            if cap not in CONTRACT_FIELDS:
                logs.warn("unknown capability ignored", apartment_id=self.apartment_id, device_id=d.device_id,
                          capability=cap)
                continue
            state = self._contract_part(d.device_id, cap, raw, d.last_seen or utcnow(), {})
            for key, value in self._starting_values(cap, state).items():
                state.setdefault(key, value)
            caps[cap] = state
        return {"device_id": d.device_id, "label": d.label, "room_id": d.room_id, "online": d.online,
                "last_seen": iso(d.last_seen) if d.last_seen else None, "capabilities": caps}

    def _starting_values(self, cap: str, state: dict) -> dict:
        """The engine's fields before anything is known (a catalog lists `switch: {}`); sensors' readings have none."""
        def clamp(value, lo, hi):
            return min(max(value, lo), hi)
        sl = self.rule("setpoint_limits")["params"]
        if cap == "climate":
            lo, hi = state.get("setpoint_min", sl["min"]), state.get("setpoint_max", sl["max"])
            return {"on": False, "mode": "heat", "setpoint": clamp(21, lo, hi), "fan": "auto", "setpoint_min": lo,
                    "setpoint_max": hi, "confirmation": "none"}
        if cap == "heating":
            lo, hi = state.get("setpoint_min", 7), state.get("setpoint_max", 23)
            frost = self.rule("frost_protection")["params"]["celsius"]
            return {"on": False, "setpoint": clamp(frost, lo, hi), "setpoint_min": lo, "setpoint_max": hi}
        return {"switch": {"on": False}, "power_meter": {"watts": 0, "kwh_today": 0},
                "contact": {"open": False, "since": None}, "motion": {"detected": False, "last_seen": None}}.get(cap, {})

    def _contract_part(self, device_id: str, cap: str, raw: dict, ts: datetime, current: dict) -> dict:
        """The contract's fields out of what the connector reports, plus what the engine computes (connector.md §2.3):
        kwh_today from energy_total_wh, contact's since, motion's last_seen."""
        out = {k: copy.deepcopy(v) for k, v in raw.items() if k in CONTRACT_FIELDS[cap]}
        if cap == "power_meter" and isinstance(raw.get("energy_total_wh"), (int, float)):
            meter = self.meters.setdefault(device_id, EnergyCounter(self.timezone))
            out["kwh_today"], used = meter.update(float(raw["energy_total_wh"]), ts)
            self._save_meter(device_id)
            if used > 0:
                self.store.add_telemetry(device_id, hour_of(ts), used)
        if cap == "contact" and "since" not in raw and "open" in raw and raw["open"] != current.get("open"):
            out["since"] = iso(ts)
        if cap == "motion" and "last_seen" not in raw and raw.get("detected"):
            out["last_seen"] = iso(ts)
        return out

    def device_target(self, cap: str, state: dict) -> dict:
        """What the connector is asked to reach: only the device's fields (D-108)."""
        return {k: copy.deepcopy(state[k]) for k in TARGET_FIELDS[cap] if k in state}

    def _apply_change(self, change: StateChange) -> None:
        """What the connector reports becomes the engine's state; during a command its changes carry its correlation
        and the engine's own fields of the command (a boiler's setpoint) are applied with the device's."""
        device = self.devices.get(change.device_id)
        if device is None:
            logs.warn("change from an unknown device ignored", apartment_id=self.apartment_id, device_id=change.device_id)
            return
        running = next((r for r in self.inflight if r[0] == change.device_id
                        and (r[1] == change.capability or change.capability not in ACTIONS)), None)
        corr = running[2] if running else None
        if change.kind == "online":
            device["online"] = change.online
            if change.online:
                device["last_seen"] = iso(change.ts)
            self._save_device(device)
            self.emit("device.online", {"device_id": device["device_id"], "online": device["online"],
                                        "last_seen": device["last_seen"]}, corr)
            self.emit("instance.health", self.health()[1], corr)
            self.apartment_changed(corr)
            return
        cap = change.capability
        state = device["capabilities"].get(cap)
        if state is None:
            logs.warn("change for a capability not in the catalog ignored", apartment_id=self.apartment_id,
                      device_id=change.device_id, capability=cap)
            return
        part = self._contract_part(change.device_id, cap, change.state or {}, change.ts, state)
        if running and running[1] == cap:
            state.update({k: copy.deepcopy(v) for k, v in running[3].items() if k in CONTRACT_FIELDS[cap]})
        state.update(part)
        device["last_seen"] = iso(change.ts)
        self._save_device(device)
        self.emit("device.state", {"device_id": device["device_id"], "capability": cap, "state": state}, corr)

    def _device_lock(self, device_id: str) -> asyncio.Lock:
        lock = self.device_locks.get(device_id)
        if lock is None:
            lock = self.device_locks[device_id] = asyncio.Lock()
        return lock

    def emit(self, event: str, data: dict, correlation_id: str | None = None) -> dict:
        env = {"event": event, "ts": iso(utcnow()), "apartment_id": self.apartment_id,
               "correlation_id": correlation_id, "data": copy.deepcopy(data)}
        t = time.time()
        # the id comes from the store: it keeps growing across restarts, so Last-Event-ID stays meaningful
        env = {"id": str(self.store.append_event(t, env)), **env, "_t": t}
        self.events.append(env)
        cutoff = t - BUFFER_SECONDS
        while self.events and self.events[0]["_t"] < cutoff:
            self.events.popleft()
        for q in list(self.subscribers):
            q.put_nowait(env)
        return env

    def events_after(self, last_id: str | None) -> list[dict]:
        if not last_id:
            return []
        try:
            n = int(last_id)
        except ValueError:
            return []
        return [e for e in self.events if int(e["id"]) > n]

    def idempotent(self, key: str):
        hit = self.idem.get(key)
        if hit and hit[0] > time.time():
            return hit[1], hit[2]
        return None

    def remember(self, key: str, status: int, body) -> None:
        until = time.time() + 60
        self.idem[key] = (until, status, body)
        self.store.put("idem", key, {"until": until, "status": status, "body": body}, expire_at=until)

    def rule(self, rule_id: str) -> dict:
        return next(r for r in self.rules if r["rule_id"] == rule_id)

    def log(self, actor: str, target: dict, action: str, old, new, reasoning: str, outcome: str,
            correlation_id: str, command_id=None, approval_id=None, ts: datetime | None = None, emit=True) -> dict:
        d = {"decision_id": self.next_id("dec"), "ts": iso(ts or utcnow()), "actor": actor, "target": target,
             "action": action, "old_value": old, "new_value": new, "reasoning": reasoning, "outcome": outcome,
             "command_id": command_id, "approval_id": approval_id, "correlation_id": correlation_id}
        self.decisions.append(d)
        self._save_decision(d)
        if emit:
            self.emit("decision.logged", d, correlation_id)
        return d

    # ---- apartment -------------------------------------------------------
    def active_booking(self) -> dict | None:
        now = utcnow()
        for b in self.bookings.values():
            if not b["cancelled"] and not b["checked_out"] and b["checkin"] <= now < b["checkout"]:
                return b
        return None

    def apartment(self) -> dict:
        now = utcnow()
        active = self.active_booking()
        future = sorted((b for b in self.bookings.values() if not b["cancelled"] and b["checkin"] > now),
                        key=lambda b: b["checkin"])
        if active:
            occupancy = "occupied" if active["checked_in"] else "reserved"
            next_checkout = active["checkout"]
        else:
            occupancy = "vacant"
            next_checkout = future[0]["checkout"] if future else None
        online_count = sum(1 for d in self.devices.values() if d["online"])
        return {
            "apartment_id": self.apartment_id, "name": self.name, "timezone": self.timezone,
            "occupancy": occupancy, "mode": self.mode, "hold": copy.deepcopy(self.hold),
            "next_checkin": iso(future[0]["checkin"]) if future else None,
            "next_checkout": iso(next_checkout) if next_checkout else None,
            "current_booking_id": active["booking_id"] if active else None,
            "online": self.connector_up() and online_count > 0,
            "devices_online": online_count, "devices_total": len(self.devices), "updated_at": iso(now),
        }

    def connector_up(self) -> bool:
        return self.connector.status().up

    def health(self) -> tuple[int, dict]:
        up = self.connector_up()
        devs = [{"device_id": d["device_id"], "online": d["online"], "last_seen": d["last_seen"]} for d in self.devices.values()]
        online = sum(1 for d in devs if d["online"])
        status = "down" if not up else ("ok" if online == len(devs) else "degraded")
        last = self.events[-1]["ts"] if self.events else None
        body = {
            "status": status, "apartment_id": self.apartment_id,
            "implementation": dict(self.implementation),
            "uptime_s": int(time.monotonic() - self.started_at), "database": {"status": "ok"},
            "connector": {"status": "up" if up else "down", "connected_devices": online if up else 0, "last_event_at": last},
            # /ask answers from keywords in simulated mode only; with a real connector it is off (501) until step 9
            "model_provider": ({"status": "ok", "provider": "mock-keywords"} if self.simulated
                               else {"status": "unknown", "provider": "none"}),
            "devices": devs if up else [], "checked_at": iso(utcnow()),
        }
        return (503 if not up else 200), body

    def apartment_changed(self, correlation_id: str | None) -> None:
        self.emit("apartment.changed", self.apartment(), correlation_id)

    def mode_commands(self, mode: str) -> list[tuple[str, dict]]:
        out = []
        frost = self.rule("frost_protection")["params"]["celsius"]
        for d in self.devices.values():
            caps = d["capabilities"]
            if not d["online"]:
                continue
            if "climate" in caps:
                c = caps["climate"]
                if mode == "comfort":
                    sp = min(max(21, c["setpoint_min"]), c["setpoint_max"])
                    out.append((d["device_id"], {"capability": "climate", "action": "set_climate",
                                                 "params": {"on": True, "mode": "heat", "setpoint": sp}}))
                else:
                    out.append((d["device_id"], {"capability": "climate", "action": "turn_off"}))
            if "heating" in caps:
                h = caps["heating"]
                target = {"comfort": 21, "eco": 18, "empty": frost}[mode]
                sp = min(max(target, h["setpoint_min"]), h["setpoint_max"])
                out.append((d["device_id"], {"capability": "heating", "action": "set_heating",
                                             "params": {"on": True, "setpoint": sp}}))
        return out

    def set_mode(self, mode: str, actor: str, correlation_id: str, reasoning: str, decision_actor: str | None = None) -> list[str]:
        if mode not in MODES:
            raise bad_request("Modalità non valida")
        command_ids = []
        for device_id, body in self.mode_commands(mode):
            try:
                cmd = self.create_command(device_id, body, actor, correlation_id, decision_actor=decision_actor,
                                          reasoning=f"Modalità {mode}")
                command_ids.append(cmd["command_id"])
            except MockError:
                continue
        old = self.mode
        self.mode = mode
        self._save_apartment()
        self.log(decision_actor or actor_of(actor), {"type": "apartment"}, "set_mode", old, mode, reasoning,
                 "applied", correlation_id)
        self.apartment_changed(correlation_id)
        return command_ids

    def set_hold(self, minutes, mode, actor: str, correlation_id: str):
        if not isinstance(minutes, int) or isinstance(minutes, bool) or not 0 <= minutes <= 720:
            raise bad_request("minutes deve essere un intero tra 0 e 720")
        if mode is not None and mode not in MODES:
            raise bad_request("Modalità non valida")
        if minutes == 0:
            old = self.hold
            self.hold = None
            self._save_apartment()
            self.log(actor_of(actor), {"type": "apartment"}, "hold_cancel", old["mode"] if old else None, None,
                     "Forzatura annullata dall'app", "applied", correlation_id)
            self.apartment_changed(correlation_id)
            return None
        if mode and mode != self.mode:
            self.set_mode(mode, actor, correlation_id, "Modalità impostata con la forzatura")
        self.hold = {"mode": mode or self.mode, "until": iso(utcnow() + timedelta(minutes=minutes)),
                     "set_by": actor.split(":", 1)[1] if actor.startswith("system:") else actor}
        self._save_apartment()
        self.log(actor_of(actor), {"type": "apartment"}, "hold", None, f"{self.hold['mode']} {minutes} min",
                 f"Forzatura per {minutes} minuti: regole di comfort sospese", "applied", correlation_id)
        self.apartment_changed(correlation_id)
        return copy.deepcopy(self.hold)

    # ---- devices & commands ---------------------------------------------
    def get_device(self, device_id: str) -> dict:
        d = self.devices.get(device_id)
        if not d:
            raise MockError(404, "not_found", "Dispositivo inesistente")
        return d

    def update_device(self, device_id: str, body: dict, actor: str, correlation_id: str) -> dict:
        d = self.get_device(device_id)
        if not isinstance(body, dict) or not body or set(body) - {"label", "room_id"}:
            raise bad_request("Indicare label e/o room_id")
        if "label" in body:
            label = body["label"]
            if not isinstance(label, str) or not label.strip() or len(label) > 60:
                raise MockError(422, "invalid_label", "Il nome deve avere da 1 a 60 caratteri")
        if "room_id" in body and body["room_id"] not in {r["room_id"] for r in self.rooms}:
            raise MockError(422, "unknown_room", "Stanza inesistente")
        old = f"{d['label']} · {d['room_id']}"
        d.update({k: (v.strip() if k == "label" else v) for k, v in body.items()})
        self._save_device(d)
        self.log(actor_of(actor), {"type": "device", "device_id": device_id}, "update_device", old,
                 f"{d['label']} · {d['room_id']}", "Anagrafica aggiornata dall'app", "informational", correlation_id)
        return copy.deepcopy(d)

    def validate_command(self, device: dict, body: dict) -> tuple[str, str, dict]:
        if not isinstance(body, dict):
            raise bad_request("Corpo del comando non valido")
        cap, action, params = body.get("capability"), body.get("action"), body.get("params") or {}
        if cap not in ACTIONS or action not in ["turn_on", "turn_off", "set_climate", "set_heating"]:
            raise bad_request("capability o action non validi")
        if not isinstance(params, dict):
            raise bad_request("params non valido")
        if cap not in device["capabilities"]:
            raise MockError(422, "capability_not_supported", "Il dispositivo non ha questa capacità")
        if action not in ACTIONS[cap]:
            raise MockError(422, "invalid_action", "Azione non ammessa per questa capacità")
        allowed = PARAMS.get(action, [])
        if set(params) - set(allowed):
            raise bad_request("Parametri non ammessi per questa azione")
        if allowed and not params:
            raise MockError(422, "missing_params", "Indicare almeno un parametro")
        if "on" in params and not isinstance(params["on"], bool):
            raise bad_request("on deve essere booleano")
        if "mode" in params and params["mode"] not in CLIMATE_MODES:
            raise bad_request("mode non valido")
        if "fan" in params and params["fan"] not in FANS:
            raise bad_request("fan non valido")
        if "setpoint" in params:
            sp = params["setpoint"]
            if not isinstance(sp, (int, float)) or isinstance(sp, bool):
                raise bad_request("setpoint deve essere numerico")
            state = device["capabilities"][cap]
            lo, hi = state["setpoint_min"], state["setpoint_max"]
            if not lo <= sp <= hi:
                raise MockError(422, "setpoint_out_of_range", f"Il setpoint deve essere tra {fmt_num(lo)} e {fmt_num(hi)}",
                                {"min": lo, "max": hi})
        return cap, action, params

    def target_state(self, device: dict, cap: str, action: str, params: dict) -> dict:
        state = copy.deepcopy(device["capabilities"][cap])
        if action == "turn_on":
            state["on"] = True
        elif action == "turn_off":
            state["on"] = False
        else:
            state.update(params)
        return state

    def window_open(self) -> dict | None:
        for d in self.devices.values():
            c = d["capabilities"].get("contact")
            if c and c["open"]:
                return d
        return None

    def window_rule_active(self) -> bool:
        return self.rule("window_open_off")["enabled"] and self.hold is None

    def create_command(self, device_id: str, body: dict, actor: str, correlation_id: str,
                       decision_actor: str | None = None, reasoning: str | None = None) -> dict:
        device = self.get_device(device_id)
        if not device["online"]:
            raise MockError(409, "device_offline", "Il dispositivo non è raggiungibile; riprova quando torna online")
        cap, action, params = self.validate_command(device, body)
        now = iso(utcnow())
        cmd = {"command_id": self.next_id("cmd"), "device_id": device_id, "status": "pending", "capability": cap,
               "action": action, "params": params, "correlation_id": correlation_id, "created_at": now,
               "updated_at": now, "reason": None}
        self.commands[cmd["command_id"]] = cmd
        self._save_command(cmd)
        self.emit("command.updated", self._cmd_event(cmd), correlation_id)
        self.spawn(self._run_command(cmd, decision_actor or actor_of(actor), reasoning or "Comando manuale dall'app"))
        return copy.deepcopy(cmd)

    @staticmethod
    def _cmd_event(cmd: dict) -> dict:
        return {k: cmd[k] for k in ("command_id", "device_id", "status", "reason")}

    def _set_status(self, cmd: dict, status: str, reason: str | None = None) -> None:
        cmd["status"], cmd["reason"], cmd["updated_at"] = status, reason, iso(utcnow())
        self._save_command(cmd)
        self.emit("command.updated", self._cmd_event(cmd), cmd["correlation_id"])

    def _settle(self, device: dict, cap: str, requested: dict, reported: dict, correlation_id: str) -> None:
        """After a successful command: the engine's fields of the request and the device's reported ones; an event
        only if something changed (nothing, when changes() already brought it)."""
        state = device["capabilities"][cap]
        merged = dict(state)
        merged.update({k: copy.deepcopy(v) for k, v in requested.items() if k in CONTRACT_FIELDS[cap]})
        merged.update(self._contract_part(device["device_id"], cap, reported, utcnow(), state))
        if merged == state:
            return
        state.update(merged)
        device["last_seen"] = iso(utcnow())
        self._save_device(device)
        self.emit("device.state", {"device_id": device["device_id"], "capability": cap, "state": state}, correlation_id)

    async def _run_command(self, cmd: dict, decision_actor: str, reasoning: str) -> None:
        device = self.devices[cmd["device_id"]]
        cap = cmd["capability"]
        target = {"type": "device", "device_id": device["device_id"]}
        old = describe(cap, device["capabilities"][cap])
        new_state = self.target_state(device, cap, cmd["action"], cmd["params"])
        window = self.window_open()
        if cap in ("climate", "heating") and new_state["on"] and window and self.window_rule_active():
            # the engine's rule: the device is never asked; the app sees the same steps as before P-60 (sent, failed)
            await asyncio.sleep(0.3)
            self._set_status(cmd, "sent")
            await asyncio.sleep(0.2)
            self._set_status(cmd, "failed", "blocked_by_rule")
            self.log(decision_actor, target, cmd["action"], old, describe(cap, new_state),
                     f"Comando bloccato dalla regola «Finestra aperta spegne il clima»: {window['label'].lower()} aperta",
                     "rejected", cmd["correlation_id"], command_id=cmd["command_id"])
            return
        ids = {"correlation_id": cmd["correlation_id"], "command_id": cmd["command_id"], "device_id": device["device_id"]}
        deadline = parse_dt(cmd["created_at"]) + timedelta(seconds=COMMAND_DEADLINE_S)
        async with self._device_lock(device["device_id"]):       # at most one command per device (connector.md §2.5)
            running = (device["device_id"], cap, cmd["correlation_id"], new_state)
            self.inflight.append(running)
            try:
                result = await asyncio.wait_for(self.connector.execute(
                    ConnectorCommand(command_id=cmd["command_id"], correlation_id=cmd["correlation_id"],
                                     device_id=device["device_id"], capability=cap,
                                     target=self.device_target(cap, new_state), deadline=deadline),
                    lambda step: self._set_status(cmd, step) if step in ("sent", "verifying") else None),
                    timeout=max((deadline - utcnow()).total_seconds(), 0))
            except TimeoutError:
                result = None
            except Exception as exc:
                logs.error("connector execute raised", apartment_id=self.apartment_id, error=str(exc)[:200], **ids)
                result = CommandResult("failed", "internal_error", detail="connector raised")
            finally:
                self.inflight.remove(running)
        if result is None:
            logs.warn("command timeout", apartment_id=self.apartment_id, **ids)
            self._set_status(cmd, "timeout", "no_confirmation")
            self.log(decision_actor, target, cmd["action"], old, describe(cap, new_state),
                     "Nessuna conferma dal dispositivo entro il tempo massimo", "failed", cmd["correlation_id"],
                     command_id=cmd["command_id"])
            return
        if result.outcome == "failed":
            logs.warn("command failed", apartment_id=self.apartment_id, reason=result.reason, detail=result.detail, **ids)
            reason = result.reason or "internal_error"
            self._set_status(cmd, "failed", reason)
            why = {"device_offline": "Il dispositivo è andato offline durante la verifica",
                   "device_rejected": "Il dispositivo ha rifiutato il comando"}.get(reason, "Errore interno del collegamento")
            self.log(decision_actor, target, cmd["action"], old, describe(cap, new_state), why, "failed",
                     cmd["correlation_id"], command_id=cmd["command_id"])
            return
        # the simulated connector reports the new state through changes() before the outcome, so it is already here;
        # a connector may also confirm only in its result; "delivered" (no confirmation possible) is decided by
        # engine/confirmation.py, today a placeholder that shows the state requested (confirmation "none")
        reported = result.state if result.outcome == "confirmed" and result.state else self.device_target(cap, new_state)
        status = "acked" if result.outcome == "confirmed" else delivered_outcome(new_state)
        self._settle(device, cap, new_state, reported, cmd["correlation_id"])
        self._set_status(cmd, status)
        self.log(decision_actor, target, cmd["action"], old, describe(cap, new_state), reasoning, "applied",
                 cmd["correlation_id"], command_id=cmd["command_id"])

    async def _window_reflex(self, device_id: str) -> None:
        minutes = self.rule("window_open_off")["params"]["minutes"]
        await asyncio.sleep(minutes * seconds_per_minute())
        contact = self.devices[device_id]["capabilities"]["contact"]
        if not contact["open"] or not self.window_rule_active():
            return
        corr = str(uuid.uuid4())
        for d in list(self.devices.values()):
            for cap in ("climate", "heating"):
                st = d["capabilities"].get(cap)
                if st and st["on"] and d["online"]:
                    self.create_command(d["device_id"], {"capability": cap, "action": "turn_off"}, "system:engine", corr,
                                        decision_actor="rule:window_open_off",
                                        reasoning=f"{self.devices[device_id]['label']} aperta da oltre {minutes} minuti con {d['label'].lower()} acceso")

    def test_state(self, body: dict, actor: str, correlation_id: str) -> None:
        if not isinstance(body, dict) or not body:
            raise bad_request("Corpo non valido")
        if body.get("trigger") is not None:
            if body["trigger"] != "approval":
                raise MockError(422, "unknown_trigger", "Trigger non supportato")
            self.trigger_approval(correlation_id)
        device_id = body.get("device_id")
        if device_id is None:
            return
        device = self.get_device(device_id)
        if "online" in body:
            if not isinstance(body["online"], bool):
                raise bad_request("online deve essere booleano")
            self.connector.set_online(device_id, body["online"], notify=False)
            device["online"] = body["online"]
            device["last_seen"] = iso(utcnow()) if body["online"] else device["last_seen"]
            self._save_device(device)
            self.emit("device.online", {"device_id": device_id, "online": device["online"], "last_seen": device["last_seen"]},
                      correlation_id)
            self.emit("instance.health", self.health()[1], correlation_id)
            self.apartment_changed(correlation_id)
        cap = body.get("capability")
        if cap is not None:
            if cap not in device["capabilities"] or not isinstance(body.get("state"), dict):
                raise MockError(422, "invalid_state", "Capacità inesistente o stato non valido")
            self.connector.set_state(device_id, cap, body["state"], notify=False)
            state = device["capabilities"][cap]
            was_open = state.get("open")
            state.update(body["state"])
            if cap == "contact" and state.get("open") != was_open:
                state["since"] = iso(utcnow())
            device["last_seen"] = iso(utcnow())
            self._save_device(device)
            self.emit("device.state", {"device_id": device_id, "capability": cap, "state": state}, correlation_id)
            if cap == "contact" and state.get("open") and not was_open:
                self.spawn(self._window_reflex(device_id))

    # ---- rules -------------------------------------------------------------
    def ruleset(self) -> dict:
        return {"updated_at": self.rules_updated_at, "rules": copy.deepcopy(self.rules)}

    def update_rules(self, body: dict, actor: str, correlation_id: str) -> dict:
        patches = body.get("rules") if isinstance(body, dict) else None
        if not isinstance(patches, list) or not patches:
            raise bad_request("rules deve essere un elenco non vuoto")
        staged = copy.deepcopy(self.rules)
        by_id = {r["rule_id"]: r for r in staged}
        for p in patches:
            if not isinstance(p, dict) or "rule_id" not in p or len(p) < 2:
                raise bad_request("Ogni regola deve indicare rule_id e almeno un campo")
            rule = by_id.get(p["rule_id"])
            if not rule:
                raise MockError(422, "unknown_rule", f"Regola inesistente: {p['rule_id']}")
            if not rule["editable"]:
                raise MockError(422, "rule_not_editable", f"La regola «{rule['label']}» non è modificabile")
            if "enabled" in p:
                if not isinstance(p["enabled"], bool):
                    raise bad_request("enabled deve essere booleano")
                rule["enabled"] = p["enabled"]
            for key, value in (p.get("params") or {}).items():
                lim = rule["limits"].get(key)
                if lim is None:
                    raise MockError(422, "unknown_param", f"Parametro inesistente: {key}")
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not lim["min"] <= value <= lim["max"]:
                    raise MockError(422, "param_out_of_range",
                                    f"«{rule['label']}»: {key} deve essere tra {fmt_num(lim['min'])} e {fmt_num(lim['max'])}",
                                    {"rule_id": rule["rule_id"], "param": key, "min": lim["min"], "max": lim["max"]})
                rule["params"][key] = value
        sl = by_id["setpoint_limits"]["params"]
        if sl["min"] > sl["max"]:
            raise MockError(422, "invalid_range", "Il minimo del setpoint non può superare il massimo")
        self.rules = staged
        self.rules_updated_at = iso(utcnow())
        self._save_apartment()
        changed = ", ".join(p["rule_id"] for p in patches)
        self.log(actor_of(actor), {"type": "rules"}, "update_rules", None, changed, "Regole modificate dall'app",
                 "applied", correlation_id)
        for d in self.devices.values():
            c = d["capabilities"].get("climate")
            if c and (c["setpoint_min"], c["setpoint_max"]) != (sl["min"], sl["max"]):
                c["setpoint_min"], c["setpoint_max"] = sl["min"], sl["max"]
                c["setpoint"] = min(max(c["setpoint"], sl["min"]), sl["max"])
                self._save_device(d)
                self.emit("device.state", {"device_id": d["device_id"], "capability": "climate", "state": c}, correlation_id)
        return self.ruleset()

    # ---- schedule & bookings -----------------------------------------------
    def list_schedule(self, frm=None, to=None) -> dict:
        cutoff = utcnow() - timedelta(days=7)
        items = []
        for s in self.schedule.values():
            run_at = parse_dt(s["run_at"])
            if s["status"] != "planned" and run_at < cutoff:
                continue
            if (frm and run_at < frm) or (to and run_at > to):
                continue
            items.append(copy.deepcopy(s))
        return {"items": sorted(items, key=lambda s: s["run_at"])}

    def validate_action(self, action) -> dict:
        if not isinstance(action, dict) or action.get("type") not in ("apartment_mode", "device_command"):
            raise bad_request("action.type deve essere apartment_mode o device_command")
        if action["type"] == "apartment_mode":
            if action.get("mode") not in MODES:
                raise bad_request("action.mode non valido")
            return {"type": "apartment_mode", "mode": action["mode"]}
        device = self.get_device(action.get("device_id", ""))
        cap, act, params = self.validate_command(device, action)
        out = {"type": "device_command", "device_id": device["device_id"], "capability": cap, "action": act}
        if params:
            out["params"] = params
        return out

    def add_schedule(self, run_at: datetime, action: dict, kind: str, source: str, booking_id=None) -> dict:
        item = {"schedule_id": self.next_id("sch"), "kind": kind, "source": source, "booking_id": booking_id,
                "run_at": iso(run_at), "action": action, "status": "planned", "executed_at": None, "command_ids": []}
        self.schedule[item["schedule_id"]] = item
        self._save_schedule(item)
        return item

    def create_schedule(self, body: dict, actor: str, correlation_id: str, source: str = "manual") -> dict:
        if not isinstance(body, dict) or "run_at" not in body or "action" not in body:
            raise bad_request("run_at e action sono obbligatori")
        try:
            run_at = parse_dt(body["run_at"])
        except ValueError:
            raise bad_request("run_at non valido")
        if run_at <= utcnow():
            raise MockError(422, "run_at_in_past", "L'orario deve essere nel futuro")
        item = self.add_schedule(run_at, self.validate_action(body["action"]), "manual", source)
        self.log(actor_of(actor) if source == "manual" else "assistant", {"type": "schedule"}, "schedule_create", None,
                 item["run_at"], "Azione programmata aggiunta", "applied", correlation_id)
        self.apartment_changed(correlation_id)
        return copy.deepcopy(item)

    def _open_item(self, schedule_id: str) -> dict:
        item = self.schedule.get(schedule_id)
        if not item:
            raise MockError(404, "not_found", "Azione programmata inesistente")
        if item["status"] != "planned":
            raise MockError(409, "already_closed", "L'azione è già stata eseguita o annullata")
        return item

    def move_schedule(self, schedule_id: str, body: dict, actor: str, correlation_id: str) -> dict:
        item = self._open_item(schedule_id)
        try:
            run_at = parse_dt((body or {}).get("run_at"))
        except (ValueError, AttributeError):
            raise bad_request("run_at non valido")
        if run_at <= utcnow():
            raise MockError(422, "run_at_in_past", "L'orario deve essere nel futuro")
        old = item["run_at"]
        item["run_at"] = iso(run_at)
        self._save_schedule(item)
        note = " (sarà ricalcolata a una modifica della prenotazione)" if item["source"] == "booking" else ""
        self.log(actor_of(actor), {"type": "schedule"}, "schedule_move", old, item["run_at"],
                 f"Orario modificato dall'app{note}", "applied", correlation_id)
        self.apartment_changed(correlation_id)
        return copy.deepcopy(item)

    def cancel_schedule(self, schedule_id: str, actor: str, correlation_id: str) -> None:
        item = self._open_item(schedule_id)
        item["status"] = "cancelled"
        self._save_schedule(item)
        self.log(actor_of(actor), {"type": "schedule"}, "schedule_cancel", item["run_at"], None,
                 "Azione programmata annullata dall'app", "applied", correlation_id)
        self.apartment_changed(correlation_id)

    def ingest_booking(self, ev: dict, correlation_id: str, emit: bool = True) -> tuple[int, dict]:
        required = ["event_id", "type", "booking_id", "checkin_at", "checkout_at", "source", "ts"]
        if not isinstance(ev, dict) or any(k not in ev for k in required):
            raise bad_request("Evento di prenotazione incompleto")
        if ev["event_id"] in self.processed_events:
            return 200, {**self.processed_events[ev["event_id"]], "duplicate": True}
        if ev["type"] not in ("booking_created", "booking_changed", "booking_cancelled", "checkin", "checkout"):
            raise bad_request("type non valido")
        if ev["source"] not in ("italianway", "ical", "simulator", "manual"):
            raise bad_request("source non valido")
        try:
            checkin, checkout = parse_dt(ev["checkin_at"]), parse_dt(ev["checkout_at"])
            parse_dt(ev["ts"])
        except ValueError:
            raise bad_request("Date non valide")
        if checkout <= checkin:
            raise MockError(422, "invalid_dates", "Il check-out deve essere successivo al check-in")
        bid = ev["booking_id"]
        booking = self.bookings.setdefault(bid, {"booking_id": bid, "checkin": checkin, "checkout": checkout,
                                                 "cancelled": False, "checked_in": False, "checked_out": False})
        items = [s for s in self.schedule.values() if s["booking_id"] == bid]
        ids: list[str] = []
        if ev["type"] == "booking_cancelled":
            booking["cancelled"] = True
            for s in items:
                if s["status"] == "planned":
                    s["status"] = "cancelled"
                ids.append(s["schedule_id"])
            reasoning = f"Prenotazione {bid} cancellata: azioni annullate"
        elif ev["type"] in ("checkin", "checkout"):
            booking["checked_in"] = ev["type"] == "checkin"
            booking["checked_out"] = ev["type"] == "checkout"
            ids = [s["schedule_id"] for s in items]
            reasoning = f"{'Check-in' if ev['type'] == 'checkin' else 'Check-out'} effettivo della prenotazione {bid}"
        else:
            booking.update({"checkin": checkin, "checkout": checkout, "cancelled": False})
            plan = []
            pre = self.rule("prearrival")
            if pre["enabled"]:
                plan.append(("prearrival", checkin - timedelta(hours=pre["params"]["hours_before"]), "comfort"))
            co = self.rule("checkout_eco")
            if co["enabled"]:
                plan.append(("checkout", checkout + timedelta(minutes=co["params"]["minutes_after"]), "empty"))
            for kind, run_at, mode in plan:
                existing = next((s for s in items if s["kind"] == kind and s["status"] == "planned"), None)
                if existing:
                    existing["run_at"] = iso(run_at)
                    ids.append(existing["schedule_id"])
                else:
                    ids.append(self.add_schedule(run_at, {"type": "apartment_mode", "mode": mode}, kind, "booking", bid)["schedule_id"])
            reasoning = f"Prenotazione {bid} {'ricevuta' if ev['type'] == 'booking_created' else 'modificata'}: pre-arrivo e check-out programmati"
        result = {"event_id": ev["event_id"], "accepted": True, "duplicate": False, "schedule_ids": ids}
        self.processed_events[ev["event_id"]] = result
        self._save_booking(booking)
        for item in self.schedule.values():
            if item["booking_id"] == bid:
                self._save_schedule(item)
        self._save_processed(ev["event_id"], result, booking["checkout"])
        self.log("system", {"type": "schedule"}, ev["type"], None, bid, reasoning, "informational", correlation_id, emit=emit)
        if emit:
            self.apartment_changed(correlation_id)
        return 202, result

    # ---- approvals ---------------------------------------------------------
    def pending_approval(self) -> dict | None:
        return next((a for a in self.approvals if a["status"] == "pending"), None)

    def trigger_approval(self, correlation_id: str, source: str = "brain", reason: str | None = None) -> dict | None:
        heating = next((d for d in self.devices.values() if "heating" in d["capabilities"]), None)
        if heating is None:
            raise MockError(422, "no_heating", "Nessuna caldaia nell'appartamento")
        sp = heating["capabilities"]["heating"]["setpoint"]
        window = self.window_open()
        default_reason = (f"{window['label']} aperta e la caldaia è accesa a {fmt_num(sp)} °C" if window
                          else f"La caldaia è accesa a {fmt_num(sp)} °C con consumi superiori alla media del periodo")
        now = utcnow()
        approval = {
            "approval_id": self.next_id("apr"), "status": "pending", "created_at": iso(now),
            "expires_at": iso(now + timedelta(minutes=30)), "expires_action": "reject", "source": source,
            "description": "Spegnere la caldaia mentre l'appartamento risulta occupato",
            "reason": reason or default_reason,
            "proposed_action": {"type": "device_command", "device_id": heating["device_id"], "capability": "heating",
                                "action": "turn_off"},
            "decided_by": None, "decided_at": None, "note": None, "correlation_id": correlation_id,
        }
        if self.pending_approval():
            self.approval_queue.append(approval)
            self._save_queue()
            return None
        self._open_approval(approval)
        return approval

    def _open_approval(self, approval: dict) -> None:
        now = utcnow()
        approval["created_at"], approval["expires_at"] = iso(now), iso(now + timedelta(minutes=30))
        self.approvals.append(approval)
        self._save_approval(approval)
        self.emit("approval.pending", approval, approval["correlation_id"])
        actor = "assistant" if approval["source"] == "assistant" else "brain"
        self.log(actor, {"type": "device", "device_id": approval["proposed_action"]["device_id"]}, "turn_off", "on", "off",
                 approval["reason"], "pending_approval", approval["correlation_id"], approval_id=approval["approval_id"])

    def list_approvals(self, status: str) -> dict:
        if status not in ("pending", "all"):
            raise bad_request("status deve essere pending o all")
        cutoff = utcnow() - timedelta(days=7)
        items = [a for a in self.approvals if a["status"] == "pending" or (status == "all" and parse_dt(a["created_at"]) >= cutoff)]
        return {"items": copy.deepcopy(sorted(items, key=lambda a: a["created_at"], reverse=True))}

    def _execute_proposed(self, approval: dict, actor: str, correlation_id: str, decision_actor: str) -> None:
        pa = approval["proposed_action"]
        try:
            if pa["type"] == "apartment_mode":
                self.set_mode(pa["mode"], actor, correlation_id, "Azione approvata", decision_actor)
            else:
                self.create_command(pa["device_id"], pa, actor, correlation_id, decision_actor=decision_actor,
                                    reasoning=f"Azione approvata: {approval['description']}")
        except MockError:
            pass

    def decide(self, approval_id: str, body: dict, actor: str, correlation_id: str) -> dict:
        approval = next((a for a in self.approvals if a["approval_id"] == approval_id), None)
        if not approval:
            raise MockError(404, "not_found", "Approvazione inesistente")
        if not isinstance(body, dict) or body.get("decision") not in ("approve", "reject"):
            raise bad_request("decision deve essere approve o reject")
        note = body.get("note")
        if note is not None and (not isinstance(note, str) or len(note) > 500):
            raise bad_request("note troppo lunga")
        if approval["status"] != "pending":
            raise MockError(409, "already_closed", "L'approvazione è già stata decisa")
        approve = body["decision"] == "approve"
        approval.update({"status": "approved" if approve else "rejected", "decided_by": actor, "decided_at": iso(utcnow()),
                         "note": note})
        self._save_approval(approval)
        who = actor_of(actor)
        reasoning = ("Approvata dal gestore" if approve else "Respinta dal gestore") + (f": {note}" if note else "")
        self.log(who, {"type": "device", "device_id": approval["proposed_action"].get("device_id")}, body["decision"],
                 None, approval["status"], reasoning, "applied" if approve else "rejected", correlation_id,
                 approval_id=approval_id)
        if approve:
            self._execute_proposed(approval, actor, correlation_id, who)
        self._dequeue_approval()
        return copy.deepcopy(approval)

    def _dequeue_approval(self) -> None:
        if self.approval_queue and not self.pending_approval():
            approval = self.approval_queue.pop(0)
            self._save_queue()
            self._open_approval(approval)

    # ---- decisions -----------------------------------------------------------
    def list_decisions(self, q) -> dict:
        try:
            limit = int(q.get("limit", 50))
            offset = int(q.get("cursor") or 0)
            frm = parse_dt(q["from"]) if q.get("from") else None
            to = parse_dt(q["to"]) if q.get("to") else None
        except ValueError:
            raise bad_request("Parametri di ricerca non validi")
        if not 1 <= limit <= 200 or offset < 0:
            raise bad_request("limit deve essere tra 1 e 200")
        items = []
        for d in sorted(self.decisions, key=lambda d: d["ts"], reverse=True):
            ts = parse_dt(d["ts"])
            if (frm and ts < frm) or (to and ts > to):
                continue
            if q.get("device_id") and d["target"].get("device_id") != q["device_id"]:
                continue
            if q.get("actor") and not (d["actor"] == q["actor"] or d["actor"].startswith(q["actor"])):
                continue
            if q.get("correlation_id") and d["correlation_id"] != q["correlation_id"]:
                continue
            items.append(d)
        page = items[offset:offset + limit]
        nxt = str(offset + limit) if offset + limit < len(items) else None
        return {"items": copy.deepcopy(page), "next_cursor": nxt}

    # ---- energy ----------------------------------------------------------------
    def energy(self, q) -> dict:
        try:
            frm, to = parse_dt(q["from"]), parse_dt(q["to"])
        except (KeyError, ValueError):
            raise bad_request("from e to sono obbligatori in formato ISO 8601")
        bucket = q.get("bucket", "day")
        if bucket not in ("hour", "day"):
            raise bad_request("bucket deve essere hour o day")
        if to <= frm or to - frm > timedelta(days=31):
            raise bad_request("Periodo non valido: massimo 31 giorni per richiesta")
        tz = ZoneInfo(self.timezone)
        series, avoided = [], 0.0

        def local_midnight(day) -> datetime:
            return datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(UTC)

        def next_start(cur: datetime) -> datetime:
            # a day is from local midnight to local midnight: 23 or 25 hours on the days the clock changes (P-60 step 4)
            if bucket == "hour":
                return cur + timedelta(hours=1)
            return local_midnight(cur.astimezone(tz).date() + timedelta(days=1))

        if bucket == "hour":
            start = frm.replace(minute=0, second=0, microsecond=0)
        else:
            start = local_midnight(frm.astimezone(tz).date())
        cur = start
        now = utcnow()
        while cur < to and cur < now:
            step = next_start(cur) - cur
            rnd = random.Random(f"{self.apartment_id}|{bucket}|{iso(cur)}")
            if bucket == "hour":
                hour = cur.astimezone(tz).hour
                profile = 1.4 if 6 <= hour <= 9 or 17 <= hour <= 23 else 0.5
                kwh = (0.15 + rnd.random() * 0.45) * profile
            else:
                kwh = 3.5 + rnd.random() * 4.5
                avoided += round(rnd.random() * 3, 1)
            frac = min(1.0, (min(to, now) - cur) / step)
            series.append({"ts": iso(cur), "kwh": round(kwh * frac, 2)})
            cur = next_start(cur)
        total = round(sum(s["kwh"] for s in series), 2)
        meters = [d for d in self.devices.values() if "power_meter" in d["capabilities"]]
        weights = [0.62, 0.28, 0.10][: len(meters)]
        wsum = sum(weights) or 1
        by_device = [{"device_id": d["device_id"], "label": d["label"], "kwh": round(total * w / wsum, 2)}
                     for d, w in zip(meters, weights)]
        return {"from": iso(frm), "to": iso(to), "bucket": bucket, "total_kwh": total,
                "avoided_hvac_hours": round(avoided, 1) if bucket == "day" else None,
                "series": series, "by_device": by_device}

    # ---- assistant ---------------------------------------------------------------
    def create_ask(self, body: dict, actor: str, correlation_id: str) -> dict:
        text = body.get("text") if isinstance(body, dict) else None
        if not isinstance(text, str) or len(text) > 500:
            raise bad_request("text obbligatorio, massimo 500 caratteri")
        if not text.strip():
            raise MockError(422, "empty_text", "Scrivi una richiesta")
        now = iso(utcnow())
        ask = {"ask_id": self.next_id("ask"), "status": "pending", "text": text, "answer": None, "actions": [],
               "approval_id": None, "reason": None, "correlation_id": correlation_id, "created_at": now, "updated_at": now}
        self.asks[ask["ask_id"]] = ask
        self._save_ask(ask)
        self.spawn(self._resolve_ask(ask, actor))
        return copy.deepcopy(ask)

    def _match_device(self, text: str, cap: str | None = None) -> dict | None:
        candidates = [d for d in self.devices.values()
                      if any(c in d["capabilities"] for c in ([cap] if cap else ACTIONS.keys()))]
        room_names = {r["room_id"]: r["name"].lower() for r in self.rooms}
        for d in candidates:
            words = [w for w in re.split(r"\W+", d["label"].lower()) if len(w) >= 4]
            if any(w in text for w in words) or room_names.get(d["room_id"], "\0") in text:
                return d
        if cap is None:
            on = [d for d in candidates if any(d["capabilities"].get(c, {}).get("on") for c in ACTIONS)]
            climate = [d for d in candidates if "climate" in d["capabilities"]]
            return (on or climate or candidates or [None])[0]
        return candidates[0] if candidates else None

    async def _resolve_ask(self, ask: dict, actor: str) -> None:
        await asyncio.sleep(1.0)
        text = ask["text"].lower()
        corr = ask["correlation_id"]
        num = re.search(r"(\d{1,2}(?:[.,]\d)?)\s*(?:gradi|°)", text)
        setpoint = float(num.group(1).replace(",", ".")) if num else None
        at = re.search(r"\balle\s+(\d{1,2})(?:[:.](\d{2}))?\b", text)
        try:
            if "caldaia" in text and self.apartment()["occupancy"] == "occupied":
                pending = self.pending_approval()
                if pending:
                    ask.update(status="answered", approval_id=pending["approval_id"],
                               answer="C'è già un'approvazione in attesa: decidi prima quella.")
                else:
                    approval = self.trigger_approval(corr, source="assistant",
                                                     reason=f"Richiesta all'assistente: «{ask['text']}». Ospiti presenti nell'appartamento.")
                    ask.update(status="needs_approval", approval_id=approval["approval_id"],
                               answer="Spegnere la caldaia con ospiti presenti richiede la tua approvazione.")
            elif at and int(at.group(1)) < 24:
                hh, mm = int(at.group(1)), int(at.group(2) or 0)
                tz = ZoneInfo(self.timezone)
                local_now = utcnow().astimezone(tz)
                run = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
                if run <= local_now:
                    run += timedelta(days=1)
                climate = self._match_device(text, "climate")
                if setpoint is not None and climate:
                    action = {"type": "device_command", "device_id": climate["device_id"], "capability": "climate",
                              "action": "set_climate", "params": {"on": True, "setpoint": setpoint}}
                    what = f"{climate['label']} a {fmt_num(setpoint)} °C"
                elif "spegni" in text and climate:
                    action = {"type": "device_command", "device_id": climate["device_id"], "capability": "climate",
                              "action": "turn_off"}
                    what = f"lo spegnimento di {climate['label'].lower()}"
                else:
                    mode = "eco" if "eco" in text else ("empty" if "vuot" in text else "comfort")
                    action = {"type": "apartment_mode", "mode": mode}
                    what = f"la modalità {mode}"
                item = self.create_schedule({"run_at": iso(run), "action": action}, actor, corr, source="assistant")
                ask.update(status="answered", actions=[{"type": "schedule", "schedule_id": item["schedule_id"]}],
                           answer=f"Ho programmato {what} alle {hh:02d}:{mm:02d}.")
            elif "spegni" in text:
                d = self._match_device(text)
                cap = next(c for c in ACTIONS if c in d["capabilities"])
                cmd = self.create_command(d["device_id"], {"capability": cap, "action": "turn_off"}, actor, corr,
                                          decision_actor="assistant", reasoning=f"Richiesta all'assistente: «{ask['text']}»")
                ask.update(status="answered", actions=[{"type": "command", "command_id": cmd["command_id"]}],
                           answer=f"Ho spento {d['label'].lower()}.")
            elif "gradi" in text or "temperatura" in text:
                d = self._match_device(text, "climate")
                if setpoint is None:
                    ask.update(status="answered", answer="Indica la temperatura, ad esempio «porta il soggiorno a 21 gradi».")
                else:
                    cmd = self.create_command(d["device_id"], {"capability": "climate", "action": "set_climate",
                                                               "params": {"on": True, "setpoint": setpoint}}, actor, corr,
                                              decision_actor="assistant", reasoning=f"Richiesta all'assistente: «{ask['text']}»")
                    ask.update(status="answered", actions=[{"type": "command", "command_id": cmd["command_id"]}],
                               answer=f"Ho impostato {d['label'].lower()} a {fmt_num(setpoint)} °C.")
            else:
                ask.update(status="answered",
                           answer="Non ho capito. Posso spegnere, impostare una temperatura o programmare un'azione.")
        except MockError as exc:
            ask.update(status="failed", reason=exc.error, answer=exc.message)
        ask["updated_at"] = iso(utcnow())
        self._save_ask(ask)

    # ---- background loop ---------------------------------------------------------
    async def _tick_loop(self) -> None:
        while True:
            await asyncio.sleep(1.0)
            try:
                self.tick()
            except Exception:
                pass

    def _purge_retention(self) -> None:
        """Retention (D-94): what is past its expire_at goes from engine.db and from memory; the hourly telemetry after
        TELEMETRY_MONTHS. Live data (devices, rules, the apartment, planned actions, open approvals) never expires."""
        t = time.time()
        self.store.purge_expired(t)

        def alive(expire_at: float) -> bool:
            return expire_at > t

        self.decisions = [d for d in self.decisions
                          if alive(expire(d["ts"], months=DECISION_MONTHS))]
        self.approvals = [a for a in self.approvals if a["status"] == "pending"
                          or alive(expire(a["created_at"], months=DECISION_MONTHS))]
        self.commands = {k: c for k, c in self.commands.items()
                         if alive(expire(c["created_at"], days=COMMAND_DAYS))}
        self.asks = {k: a for k, a in self.asks.items() if alive(expire(a["created_at"], days=COMMAND_DAYS))}
        self.schedule = {k: i for k, i in self.schedule.items() if i["status"] == "planned"
                         or alive(expire(i["run_at"], months=BOOKING_MONTHS))}
        gone = {k for k, b in self.bookings.items() if not alive(expire(iso(b["checkout"]), months=BOOKING_MONTHS))}
        self.bookings = {k: b for k, b in self.bookings.items() if k not in gone}
        kept = {k for k, _ in self.store.all("processed_events")}
        self.processed_events = {k: r for k, r in self.processed_events.items() if k in kept}
        self.store.purge_telemetry(hour_of(add_months(utcnow(), -TELEMETRY_MONTHS)))
        self.last_retention = time.monotonic()

    def housekeeping(self) -> None:
        """Once a minute: the stream's buffer beyond one hour and the expired idempotency keys go; once an hour, the
        retention clean-up."""
        if time.monotonic() - self.last_retention >= RETENTION_EVERY_S:
            self._purge_retention()
        t = time.time()
        self.store.prune_events(t - BUFFER_SECONDS)
        self.idem = {k: v for k, v in self.idem.items() if v[0] > t}
        for key in [k for k, _ in self.store.all("idem")]:
            if key not in self.idem:
                self.store.delete("idem", key)

    def tick(self) -> None:
        now = utcnow()
        if time.monotonic() - self.last_housekeeping >= 60:
            self.last_housekeeping = time.monotonic()
            self.housekeeping()
        if self.hold and parse_dt(self.hold["until"]) <= now:
            self.hold = None
            self._save_apartment()
            corr = str(uuid.uuid4())
            self.log("system", {"type": "apartment"}, "hold_expired", None, None,
                     "Forzatura scaduta: le regole tornano attive", "informational", corr)
            self.apartment_changed(corr)
        for a in self.approvals:
            if a["status"] == "pending" and a["expires_at"] and parse_dt(a["expires_at"]) <= now:
                a["status"] = "expired"
                self._save_approval(a)
                corr = str(uuid.uuid4())
                outcome = {"reject": "respinta", "approve": "approvata", "wait": "in attesa"}[a["expires_action"]]
                self.log("system", {"type": "device", "device_id": a["proposed_action"].get("device_id")}, "expire",
                         "pending", "expired", f"Approvazione scaduta senza risposta: {outcome}", "informational", corr,
                         approval_id=a["approval_id"])
                if a["expires_action"] == "approve":
                    self._execute_proposed(a, "system:engine", corr, "system")
                self._dequeue_approval()
        # by time, and by creation for the same time (a stable sort on the creation order, which engine.db keeps too).
        # An action is closed (done/failed) and saved in this same pass, so a later pass never runs it again. After a
        # crash between its commands and that save it runs again at the restart (within ARREARS_MINUTES): harmless,
        # commands are states to reach (P-60 step 4).
        for item in sorted(self.schedule.values(), key=lambda s: s["run_at"]):
            if item["status"] != "planned" or parse_dt(item["run_at"]) > now:
                continue
            corr = str(uuid.uuid4())
            labels = {"prearrival": "pre-arrivo", "checkout": "check-out", "empty": "casa vuota", "manual": "manuale"}
            reasoning = f"Azione programmata ({labels[item['kind']]})" + (f", prenotazione {item['booking_id']}" if item["booking_id"] else "")
            act = item["action"]
            try:
                if act["type"] == "apartment_mode":
                    item["command_ids"] = self.set_mode(act["mode"], "system:engine", corr, reasoning, "system")
                else:
                    cmd = self.create_command(act["device_id"], act, "system:engine", corr, decision_actor="system",
                                              reasoning=reasoning)
                    item["command_ids"] = [cmd["command_id"]]
                item["status"] = "done"
            except MockError:
                item["status"] = "failed"
            item["executed_at"] = iso(now)
            self._save_schedule(item)
            self.apartment_changed(corr)

    # ---- seed ------------------------------------------------------------------------
    def _seed_history(self, variant: int) -> None:
        now = utcnow()
        corr = str(uuid.uuid4())
        if variant == 0:
            ci, co = now - timedelta(hours=26), now + timedelta(hours=43)
            self.ingest_booking({"event_id": "seed-evt-001", "type": "booking_created", "booking_id": "bk-77812",
                                 "checkin_at": iso(ci), "checkout_at": iso(co), "guests": 2, "source": "simulator",
                                 "ts": iso(ci - timedelta(days=5))}, corr, emit=False)
            self.ingest_booking({"event_id": "seed-evt-002", "type": "checkin", "booking_id": "bk-77812",
                                 "checkin_at": iso(ci), "checkout_at": iso(co), "guests": 2, "source": "simulator",
                                 "ts": iso(ci)}, corr, emit=False)
            nci = co + timedelta(hours=31)
            self.ingest_booking({"event_id": "seed-evt-003", "type": "booking_created", "booking_id": "bk-77813",
                                 "checkin_at": iso(nci), "checkout_at": iso(nci + timedelta(days=3, hours=17)), "guests": 3,
                                 "source": "simulator", "ts": iso(now - timedelta(days=1))}, corr, emit=False)
            for s in self.schedule.values():
                if s["booking_id"] == "bk-77812" and s["kind"] == "prearrival":
                    s.update(status="done", executed_at=s["run_at"])
                    self._save_schedule(s)
            self.log("rule:window_open_off", {"type": "device", "device_id": "dev-clima-soggiorno"}, "turn_off", "on", "off",
                     "Finestra della camera aperta da 5 minuti con il clima acceso", "applied", str(uuid.uuid4()),
                     command_id="cmd-seed-01", ts=now - timedelta(hours=5), emit=False)
            self.log("system", {"type": "apartment"}, "set_mode", "eco", "comfort",
                     "Azione programmata (pre-arrivo), prenotazione bk-77812", "applied", str(uuid.uuid4()),
                     ts=ci - timedelta(hours=2), emit=False)
        else:
            nci = now + timedelta(days=3, hours=2)
            self.ingest_booking({"event_id": "seed-evt-101", "type": "booking_created", "booking_id": "bk-90210",
                                 "checkin_at": iso(nci), "checkout_at": iso(nci + timedelta(days=2, hours=17)), "guests": 2,
                                 "source": "simulator", "ts": iso(now - timedelta(days=2))}, corr, emit=False)
            self.log("system", {"type": "apartment"}, "set_mode", "eco", "empty",
                     "Azione programmata (check-out), prenotazione bk-90001", "applied", str(uuid.uuid4()),
                     ts=now - timedelta(hours=20), emit=False)


def hour_of(ts: datetime) -> str:
    """The UTC hour a reading belongs to, as the hourly telemetry keys it (e.g. 2026-10-20T09:00Z)."""
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:00Z")


def add_months(dt: datetime, months: int) -> datetime:
    """Same day and time `months` later; the month's last day when that day does not exist (as bff/retention.py)."""
    y, m = divmod(dt.month - 1 + months, 12)
    year, month = dt.year + y, m + 1
    return dt.replace(year=year, month=month, day=min(dt.day, calendar.monthrange(year, month)[1]))


def expire(ts: str, months: int = 0, days: int = 0) -> float:
    """When a record dated ts may be deleted, as epoch seconds (the store's expire_at)."""
    return (add_months(parse_dt(ts), months) + timedelta(days=days)).timestamp()


def actor_of(x_actor: str) -> str:
    return "system" if x_actor.startswith("system:") else f"user:{x_actor}"


class Registry:
    def __init__(self) -> None:
        self.sims: dict[str, ApartmentEngine] = {}

    def reset(self, apartment_id: str) -> bool:
        """D-97: forget the apartment's simulated engine and stop its tasks; the next call builds it from the seed."""
        sim = self.sims.pop(apartment_id, None)
        if sim is None:
            return False
        for task in [sim.loop_task, sim.consumer_task, *sim.tasks]:
            if task is not None and not task.done():
                task.cancel()
        return True

    def get(self, apartment_id: str) -> ApartmentEngine:
        sim = self.sims.get(apartment_id)
        if sim is None:
            sim = self.sims[apartment_id] = ApartmentEngine(apartment_id)
        sim.ensure_started()
        return sim
