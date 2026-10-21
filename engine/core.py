"""The engine of one apartment (contract 1.0.5): rules, modes, bookings, schedule, approvals, decisions, assistant,
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
from .connector.interface import LINKS, CommandResult, ConnectorCommand, DeviceInfo, StateChange
from . import confirmation as confirm
from .config import DEFAULT_SETTINGS
from .mold import mold_action
from .connector.simulated import SimulatedConnector
from .store import MemoryStore

CONTRACT_VERSION = "1.0.5"
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
# P-60 step 10 (D-104): a log line "engine alive" every HEARTBEAT_S of real time, the beat whose absence for 10 minutes
# raises the alert (scripts/monitoring/engine-alerts.sh); the inner loop is "stuck" without a tick for LOOP_STALE_S
HEARTBEAT_S = 300
LOOP_STALE_S = 30
# D-130, decision 3: a demonstration apartment (seeded) shows an invented, repeatable consumption, per meter, from the
# start of 2026 to the hour its engine started; after that only what its (simulated) meters measure. The BFF finds
# ENERGY_PROFILE_START as the apartment's energy_since, so nothing odd shows. Shares of the meters, in catalog order.
ENERGY_PROFILE_START = datetime(2026, 1, 1, tzinfo=ZoneInfo("Europe/Rome"))
ENERGY_PROFILE_SHARES = (0.62, 0.28, 0.10)
RETENTION_EVERY_S = 3600
# the engine's own fields of a capability, kept across restarts (the device reports the others again)
ENGINE_FIELDS = {"heating": ("on", "setpoint"), "contact": ("since",), "motion": ("last_seen",),
                 "power_meter": ("kwh_today",)}
# the boiler's thermostat (R1, R2, D-126, D-128): heating.on is the intention the app sees; the relay is the engine's
# D-133: the rules' thresholds that the app does not change are settings of the engine per apartment, with defaults
# and limits in engine/config.py (SETTINGS); the engine reads them with self.setting(name)

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


def spread(wh: float, start: datetime, end: datetime) -> list[tuple[str, float]]:
    """wh used between two readings, split over the UTC hours in proportion to the time in each (D-130: a meter away
    for a few hours brings back the whole gap at once; it goes to the hours it belongs to, also across midnight or the
    end of a month). Readings out of order or at the same instant: all in the reading's hour."""
    if end <= start:
        return [(hour_of(end), wh)]
    total = (end - start).total_seconds()
    out, cur, given = [], start, 0.0
    while cur < end:
        nxt = min(cur.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1), end)
        # the last hour takes what is left: the pieces add up to exactly wh (wh * s / total is not exact in floating
        # point, e.g. 499.99999999999994 for 500 with timestamps to the microsecond, as on Linux)
        piece = wh - given if nxt == end else wh * ((nxt - cur).total_seconds() / total)
        out.append((hour_of(cur), piece))
        given += piece
        cur = nxt
    return out


class EnergyCounter:
    """kwh_today of one power meter, from the connector's raw cumulative counter (energy_total_wh, connector.md §2.3)
    since the apartment's local midnight, and the Wh of each reading spread over the hours since the previous one
    (D-130). A counter that drops (the device restarted) counts again from zero: what was used between the last reading
    and the restart is not measurable. Its state is saved with the engine's, so neither kwh_today nor the hourly
    telemetry start again after a restart."""

    def __init__(self, timezone: str, state: dict | None = None):
        self.tz = ZoneInfo(timezone)
        state = state or {}
        self.day = state.get("day")                    # ISO date, local, of the last reading
        self.last_wh: float | None = state.get("last_wh")
        self.last_ts: str | None = state.get("last_ts")  # ISO instant of the last reading
        self.today_wh = float(state.get("today_wh", 0.0))

    def state(self) -> dict:
        return {"day": self.day, "last_wh": self.last_wh, "last_ts": self.last_ts, "today_wh": self.today_wh}

    def update(self, total_wh: float, ts: datetime) -> tuple[float, list[tuple[str, float]]]:
        """(kwh_today, [(UTC hour, Wh)] used since the previous reading, spread over the hours in between)."""
        used = 0.0
        if self.last_wh is not None:
            used = total_wh - self.last_wh if total_wh >= self.last_wh else total_wh
        prev = parse_dt(self.last_ts) if self.last_ts else ts
        pieces = spread(used, prev, ts) if used > 0 else []
        local = ts.astimezone(self.tz)
        day = local.date().isoformat()
        if day != self.day:                            # only the part of the gap after local midnight is today's
            midnight = hour_of(datetime(local.year, local.month, local.day, tzinfo=self.tz))
            self.day, self.today_wh = day, sum(wh for hour, wh in pieces if hour >= midnight)
        else:
            self.today_wh += used
        self.last_wh = total_wh
        if ts >= prev:
            self.last_ts = iso(ts)
        return round(self.today_wh / 1000, 3), pieces


class ApartmentEngine:
    def __init__(self, apartment_id: str, connector=None, *, simulated: bool = True, seed: bool | None = None,
                 implementation: dict | None = None, store: MemoryStore | None = None,
                 confirm_watts: tuple[float, float] | None = None, settings: dict[str, float] | None = None,
                 model=None):
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
        # D-131, D-133: the apartment's settings (engine/config.py), the defaults when not given
        self.settings = {**DEFAULT_SETTINGS, **(settings or {})}
        if confirm_watts:
            self.settings["CONFIRM_ON_WATTS"], self.settings["CONFIRM_OFF_WATTS"] = confirm_watts
        self.power_waiters: dict[str, list[tuple[str, float, asyncio.Future]]] = {}   # meter -> commands watching it
        self.rooms = [{"room_id": r.room_id, "name": r.name} for r in self.connector.rooms()]
        self.rules = copy.deepcopy(DEFAULT_RULES)
        self._compressor_from_settings()
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
        self.deferred: dict[str, str] = {}      # schedule_id -> the hold's end, for mode actions waiting for it (D-122)
        self.compressor_off: dict[str, float] = {}   # climate device -> when it went off (monotonic), R4
        self.offline_watch: dict[str, object] = {}   # device -> the offline episode being watched, R5
        self.links: dict[str, dict[str, str]] = {}   # device -> its links (connector.md §2.2), never shown to the app
        self.relay: dict[str, bool] = {}             # boiler -> its relay as the device reports it (R2, D-128)
        self.relay_switched: dict[str, float] = {}   # boiler -> when the thermostat last switched it (monotonic)
        self.relay_busy: set[str] = set()            # boilers with a thermostat switch running
        self.thermostat_issue: dict[str, str] = {}   # boiler -> the sensor problem already reported
        self.last_regulation = 0.0
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
        self.last_tick = time.monotonic()            # P-60 step 10: the inner loop is alive when this moves
        self.last_heartbeat = 0.0
        self.profile_until: datetime | None = None   # D-130: end of the demonstration's invented consumption
        self.connector_was_up = self.connector_up()  # D-131: a change is an event and a decision (tick)
        self.empty_power: dict[str, dict] = {}       # D-137 F2: meter -> {"since": monotonic, "asked": bool}, one episode
        self.model = model                           # P-60 step 9: engine/assistant.ModelClient, None = keywords
        self.restored = bool(self.store.get_meta("initialized"))
        if self.restored:
            self._load()
        else:
            self.devices = {d.device_id: self._device_from(d) for d in self.connector.devices()}
            for device in self.devices.values():
                self._save_device(device)
            self._read_links_and_relays()
            self._save_apartment()
            if seeded:
                self._seed_history(variant)
                self._seed_energy_profile()
            self.store.put_meta("initialized", {"at": iso(utcnow()), "seeded": seeded})

    # ---- infrastructure -------------------------------------------------
    def setting(self, name: str):
        return self.settings[name]

    @property
    def confirm_on_watts(self) -> float:
        return self.settings["CONFIRM_ON_WATTS"]

    @property
    def confirm_off_watts(self) -> float:
        return self.settings["CONFIRM_OFF_WATTS"]

    def _compressor_from_settings(self) -> None:
        """D-133: compressor_min_off is not editable from the app; its value and limits are the apartment's setting."""
        minutes = self.setting("COMPRESSOR_MIN_OFF_MINUTES")
        minutes = int(minutes) if minutes == int(minutes) else minutes     # 3, not 3.0, as /rules always said
        for rule in self.rules:
            if rule["rule_id"] == "compressor_min_off":
                rule["params"]["minutes"] = minutes
                rule["limits"]["minutes"] = {"min": minutes, "max": minutes}

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
        self._compressor_from_settings()
        self.rules_updated_at = apt.get("rules_updated_at", self.rules_updated_at)
        self.counter = st.get_meta("counter", self.counter)
        self.meters = {k: EnergyCounter(self.timezone, v) for k, v in st.all("meters")}
        profile = st.get_meta("energy_profile")
        self.profile_until = parse_dt(profile["until"]) if profile else None
        stored = dict(st.all("devices"))
        self.devices = {}
        self._read_links_and_relays()
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
        self.deferred = st.get_meta("deferred", {})
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
        action scheduled more than MISSED_AFTER_MINUTES (a setting) ago, that could not run while the engine was down, is failed as
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
            if item["status"] != "planned" or late <= timedelta(minutes=self.setting("MISSED_AFTER_MINUTES")) or item["schedule_id"] in self.deferred:
                continue
            item["status"], item["executed_at"] = "failed", iso(now)
            self._save_schedule(item)
            self.log("system", {"type": "schedule"}, "schedule_missed", item["run_at"], None,
                     f"Azione programmata non eseguita: il motore era fermo all'orario previsto ({item['run_at']}), "
                     f"oltre {fmt_num(self.setting('MISSED_AFTER_MINUTES'))} minuti fa", "failed", str(uuid.uuid4()))

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
            out["kwh_today"], pieces = meter.update(float(raw["energy_total_wh"]), ts)
            self._save_meter(device_id)
            for hour, wh in pieces:
                if wh > 0:
                    self.store.add_telemetry(device_id, hour, wh)
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
            self._watch_offline(device["device_id"], change.online)
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
        raw = self._take_relay(change.device_id, cap, change.state or {})
        if cap == "heating" and not raw and not (running and running[1] == cap):
            device["last_seen"] = iso(change.ts)              # only the relay moved: nothing changes for the app
            self._save_device(device)
            return
        part = self._contract_part(change.device_id, cap, raw, change.ts, state)
        was_on = state.get("on")
        if running and running[1] == cap:
            state.update({k: copy.deepcopy(v) for k, v in running[3].items() if k in CONTRACT_FIELDS[cap]})
        was_open = state.get("open")
        state.update(part)
        if cap == "power_meter":
            self._power_seen(change.device_id, state)
        self._note_climate(change.device_id, cap, was_on, state.get("on"))
        if cap == "contact" and state.get("open") and not was_open:
            self._window_opened(change.device_id)
        device["last_seen"] = iso(change.ts)
        self._save_device(device)
        self.emit("device.state", {"device_id": device["device_id"], "capability": cap, "state": state}, corr)

    # ---- rules of P-60 step 5 (D-126) ----------------------------------------------------------------------------
    def _note_climate(self, device_id: str, cap: str, was_on, is_on) -> None:
        """R4: when a split's compressor stops, its minimum pause starts."""
        if cap == "climate" and was_on and not is_on:
            self.compressor_off[device_id] = time.monotonic()

    def compressor_wait(self, device_id: str) -> float:
        """R4: seconds left of the compressor's minimum pause (rule compressor_min_off), 0 when it may start."""
        rule = self.rule("compressor_min_off")
        off = self.compressor_off.get(device_id)
        if not rule["enabled"] or off is None:
            return 0.0
        return max(0.0, rule["params"]["minutes"] * seconds_per_minute() - (time.monotonic() - off))

    def _within_limits(self, device: dict, body: dict) -> tuple[dict, str | None]:
        """R6: a setpoint asked by an automatic path (mode, schedule, assistant, rule) is brought inside the device's
        limits, with a note for the decision; a manual command out of limits stays a 422."""
        params = body.get("params") if isinstance(body, dict) else None
        cap = body.get("capability") if isinstance(body, dict) else None
        state = device["capabilities"].get(cap) if isinstance(cap, str) else None
        if not isinstance(params, dict) or not state or "setpoint" not in params or "setpoint_min" not in state:
            return body, None
        sp, lo, hi = params["setpoint"], state["setpoint_min"], state["setpoint_max"]
        if not isinstance(sp, (int, float)) or isinstance(sp, bool) or lo <= sp <= hi:
            return body, None
        fixed = min(max(sp, lo), hi)
        note = f"setpoint {fmt_num(sp)} °C riportato a {fmt_num(fixed)} °C (limiti {fmt_num(lo)}–{fmt_num(hi)})"
        return {**body, "params": {**params, "setpoint": fixed}}, note

    def _watch_offline(self, device_id: str, online: bool) -> None:
        """R5: a device still offline after the minutes of offline_alert gets one decision for the episode (the push
        is the BFF's)."""
        if online:
            self.offline_watch.pop(device_id, None)
            return
        rule = self.rule("offline_alert")
        if not rule["enabled"] or device_id in self.offline_watch:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        episode = self.offline_watch[device_id] = object()
        minutes = rule["params"]["minutes"]

        async def later():
            await asyncio.sleep(minutes * seconds_per_minute())
            device = self.devices.get(device_id)
            if self.offline_watch.get(device_id) is episode and device and not device["online"]:
                self.log("rule:offline_alert", {"type": "device", "device_id": device_id}, "offline_alert", "online",
                         "offline", f"{device['label']} offline da oltre {fmt_num(minutes)} minuti", "informational",
                         str(uuid.uuid4()))
        self.spawn(later())

    def _mold_check(self) -> None:
        """R3: in an empty apartment (and not during a hold, R7) humidity above the threshold gives one warning a day;
        the action against it is engine/mold.py's, today none."""
        rule = self.rule("mold_protection")
        if not rule["enabled"] or self.mode != "empty":
            return
        threshold = rule["params"]["humidity_percent"]
        high = [(d, d["capabilities"]["humidity"]["percent"]) for d in self.devices.values()
                if "humidity" in d["capabilities"] and isinstance(d["capabilities"]["humidity"].get("percent"), (int, float))
                and d["capabilities"]["humidity"]["percent"] > threshold]
        if not high:
            return
        today = utcnow().astimezone(ZoneInfo(self.timezone)).date().isoformat()
        if self.store.get_meta("mold_notice_day") == today:
            return
        device, percent = max(high, key=lambda x: x[1])
        if self.hold:                                            # R7/R8: a hold suspends it, and the decision says so
            reason = "antimuffa sospesa dalla forzatura in corso"
        else:
            mold_action(self.mode, percent, threshold)          # placeholder: no action yet (D-126)
            reason = "solo avviso, nessuna azione automatica"
        self.log("rule:mold_protection", {"type": "device", "device_id": device["device_id"]}, "mold_warning", None,
                 f"{fmt_num(percent)} %", f"Umidità {fmt_num(percent)} % in {device['label'].lower()}, sopra la soglia "
                 f"dell'antimuffa ({fmt_num(threshold)} %) a casa vuota: {reason}", "informational", str(uuid.uuid4()))
        self.store.put_meta("mold_notice_day", today)

    # ---- the boiler's thermostat (R1, R2) ---------------------------------------------------------------------------
    def _read_links_and_relays(self) -> None:
        """The catalog's links, checked at start (connector.md §2.2, P-60 step 7b): a link with an unknown key, to a
        device that is not in the catalog or to one without the capability it needs, from a device without the
        capability it is for, is left out with a log line. Then a split with `confirmation: power` and no meter is
        treated as `confirmation: none`, a boiler without a sensor is not regulated (it follows the switch it is asked,
        with its decision, step 5b): each with a log line."""
        infos = self.connector.devices()
        caps = {i.device_id: i.capabilities for i in infos}
        self.links = {}
        for info in infos:
            kept = {}
            for key, target in dict(info.links).items():
                problem = None
                if key not in LINKS:
                    problem = "unknown link key"
                elif LINKS[key][0] not in info.capabilities:
                    problem = f"link only for a device with {LINKS[key][0]}"
                elif target not in caps:
                    problem = "target not in the catalog"
                elif LINKS[key][1] not in caps[target]:
                    problem = f"target without {LINKS[key][1]}"
                if problem:
                    logs.warn("link ignored", apartment_id=self.apartment_id, device_id=info.device_id, link=key,
                              target=str(target), reason=problem)
                else:
                    kept[key] = target
            self.links[info.device_id] = kept
            climate = info.capabilities.get("climate")
            if climate and climate.get("confirmation") == "power" and "confirmation_device_id" not in kept:
                logs.warn("split without confirmation meter", apartment_id=self.apartment_id, device_id=info.device_id,
                          treated_as="confirmation none")
            if "heating" in info.capabilities:
                self.relay[info.device_id] = bool(info.capabilities["heating"].get("on"))
                if "sensor_device_id" not in kept:
                    logs.warn("boiler without sensor", apartment_id=self.apartment_id, device_id=info.device_id,
                              treated_as="not regulated")

    def _take_relay(self, device_id: str, cap: str, raw: dict) -> dict:
        """For a boiler, "on" from the device is its relay: kept by the engine, not shown as heating.on (D-128)."""
        if cap != "heating" or "on" not in raw:
            return raw
        self.relay[device_id] = bool(raw["on"])
        return {k: v for k, v in raw.items() if k != "on"}

    def connector_target(self, device: dict, cap: str, state: dict) -> dict:
        """What the connector is asked: the device's fields (D-108); for a boiler the relay the thermostat wants."""
        if cap == "heating":
            return {"on": self.thermostat(device, state)[0]}
        return self.device_target(cap, state)

    def _sensor(self, device: dict) -> tuple[float | None, dict | None, str | None]:
        """(temperature, sensor, problem) of the sensor linked to a boiler (links.sensor_device_id)."""
        sensor_id = self.links.get(device["device_id"], {}).get("sensor_device_id")
        sensor = self.devices.get(sensor_id) if sensor_id else None
        if sensor is None or "temperature" not in sensor["capabilities"]:
            return None, None, "nessun sensore di temperatura collegato"
        celsius = sensor["capabilities"]["temperature"].get("celsius")
        if not sensor["online"] or not isinstance(celsius, (int, float)):
            return None, sensor, f"sensore «{sensor['label']}» non disponibile"
        return float(celsius), sensor, None

    def thermostat(self, device: dict, intention: dict | None = None) -> tuple[bool, float | None, float | None, bool]:
        """(relay wanted, temperature, setpoint used, frost) for a boiler. Enabled (heating.on) it keeps the setpoint;
        in an empty apartment the frost protection keeps at least its threshold even when disabled (a safety rule,
        never suspended). Without a usable sensor the relay follows the intention, as a plain switch."""
        intention = intention if intention is not None else device["capabilities"]["heating"]
        enabled = bool(intention.get("on"))
        frost_rule = self.rule("frost_protection")
        frost = self.mode == "empty" and frost_rule["enabled"]
        candidates = ([float(intention["setpoint"])] if enabled and isinstance(intention.get("setpoint"), (int, float))
                      else [])
        if frost:
            candidates.append(float(frost_rule["params"]["celsius"]))
        if not candidates:
            return False, None, None, False
        setpoint = max(candidates)
        frost_only = frost and (not enabled or setpoint == float(frost_rule["params"]["celsius"]))
        temperature, _, problem = self._sensor(device)
        if problem:
            return enabled, None, setpoint, frost_only
        current = self.relay.get(device["device_id"], False)
        if temperature < setpoint:
            return True, temperature, setpoint, frost_only
        if temperature > setpoint + self.setting("THERMOSTAT_HYSTERESIS_C"):
            return False, temperature, setpoint, frost_only
        return current, temperature, setpoint, frost_only

    def regulate(self) -> None:
        """Once a "minute": every boiler's relay where its thermostat wants it, at most one switch every
        THERMOSTAT_MIN_SWITCH_MINUTES. Decisions: the frost protection's every switch, the sensor's problems. With the
        connector down nothing can be switched: it waits for it (D-131)."""
        if not self.connector_was_up:
            return
        for device in self.devices.values():
            if "heating" not in device["capabilities"] or not device["online"]:
                continue
            device_id = device["device_id"]
            _, _, problem = self._sensor(device)
            if problem != self.thermostat_issue.get(device_id):
                self._sensor_issue(device, problem)
            if device_id in self.relay_busy or any(r[0] == device_id for r in self.inflight):
                continue
            want, temperature, setpoint, frost = self.thermostat(device)
            if want == self.relay.get(device_id, False):
                continue
            since = time.monotonic() - self.relay_switched.get(device_id, -1e18)
            if since < self.setting("THERMOSTAT_MIN_SWITCH_MINUTES") * seconds_per_minute():
                continue
            self.relay_busy.add(device_id)
            self.spawn(self._switch_relay(device, want, temperature, setpoint, frost))

    def _sensor_issue(self, device: dict, problem: str | None) -> None:
        device_id = device["device_id"]
        if problem:
            self.thermostat_issue[device_id] = problem
            reasoning = (f"Termostato di {device['label'].lower()}: {problem}; la caldaia segue l'accensione richiesta "
                         f"senza regolazione")
        else:
            self.thermostat_issue.pop(device_id, None)
            reasoning = f"Termostato di {device['label'].lower()}: sensore di nuovo disponibile, regolazione ripresa"
        self.log("system", {"type": "device", "device_id": device_id}, "thermostat_sensor", None,
                 "problema" if problem else "ok", reasoning, "informational", str(uuid.uuid4()))

    async def _switch_relay(self, device: dict, on: bool, temperature, setpoint, frost: bool) -> None:
        device_id = device["device_id"]
        corr = str(uuid.uuid4())
        try:
            async with self._device_lock(device_id):
                deadline = utcnow() + timedelta(seconds=COMMAND_DEADLINE_S)
                result = await asyncio.wait_for(self.connector.execute(
                    ConnectorCommand(command_id=f"thermostat-{uuid.uuid4().hex[:8]}", correlation_id=corr,
                                     device_id=device_id, capability="heating", target={"on": on}, deadline=deadline),
                    lambda step: None), timeout=COMMAND_DEADLINE_S)
        except Exception as exc:                          # timeout or connector error: the next minute tries again
            logs.warn("thermostat switch failed", apartment_id=self.apartment_id, device_id=device_id,
                      error=type(exc).__name__)
            return
        finally:
            self.relay_busy.discard(device_id)
        if result.outcome == "failed":
            logs.warn("thermostat switch failed", apartment_id=self.apartment_id, device_id=device_id,
                      reason=result.reason)
            return
        self.relay[device_id] = on
        self.relay_switched[device_id] = time.monotonic()
        if frost:                                          # R1: every switch of the frost protection is a decision
            what = (f"caldaia accesa: {fmt_num(temperature)} °C, sotto la soglia di {fmt_num(setpoint)} °C" if on else
                    f"caldaia spenta: {fmt_num(temperature)} °C, sopra la soglia di {fmt_num(setpoint)} °C "
                    f"+ {fmt_num(self.setting('THERMOSTAT_HYSTERESIS_C'))}")
            self.log("rule:frost_protection", {"type": "device", "device_id": device_id},
                     "frost_heating_on" if on else "frost_heating_off", "off" if on else "on", "on" if on else "off",
                     f"Antigelo a casa vuota: {what}", "applied", corr)

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

    def loop_alive(self) -> bool:
        """The inner loop (scheduler, rules, approvals) ticked within LOOP_STALE_S; True before it is started."""
        if self.loop_task is None:
            return True
        return not self.loop_task.done() and time.monotonic() - self.last_tick < LOOP_STALE_S

    def health(self) -> tuple[int, dict]:
        """P-60 step 10: the real state. down (503): the connector down or engine.db not answering; degraded: a device
        offline or the inner loop stuck; ok otherwise."""
        up = self.connector_up()
        db_ok = self.store.ping()
        devs = [{"device_id": d["device_id"], "online": d["online"], "last_seen": d["last_seen"]} for d in self.devices.values()]
        online = sum(1 for d in devs if d["online"])
        if not up or not db_ok:
            status = "down"
        else:
            status = "ok" if online == len(devs) and self.loop_alive() else "degraded"
        last = self.events[-1]["ts"] if self.events else None
        body = {
            "status": status, "apartment_id": self.apartment_id,
            "implementation": dict(self.implementation),
            "uptime_s": int(time.monotonic() - self.started_at), "database": {"status": "ok" if db_ok else "error"},
            "connector": {"status": "up" if up else "down", "connected_devices": online if up else 0, "last_event_at": last},
            # /ask: the real model through the BFF (step 9), keywords in simulated mode, otherwise off (501)
            "model_provider": ({"status": "ok", "provider": "bff-gateway"} if self.model is not None
                               else {"status": "ok", "provider": "mock-keywords"} if self.simulated
                               else {"status": "unknown", "provider": "none"}),
            "devices": devs if up else [], "checked_at": iso(utcnow()),
        }
        return (503 if status == "down" else 200), body

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
                if cmd:
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
            self._window_after_hold()
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
                       decision_actor: str | None = None, reasoning: str | None = None) -> dict | None:
        """A command, or None when an automatic one waits for the compressor's pause (R4) and starts after it."""
        device = self.get_device(device_id)
        if not self.connector_up():                          # D-131: nothing can reach the devices
            raise MockError(409, "device_offline", "Collegamento ai dispositivi non disponibile; riprova quando torna")
        if not device["online"]:
            raise MockError(409, "device_offline", "Il dispositivo non è raggiungibile; riprova quando torna online")
        who = decision_actor or actor_of(actor)
        manual = who.startswith("user:")
        if not manual:                                       # R6: automatic paths stay within the limits
            body, note = self._within_limits(device, body)
            if note:
                reasoning = f"{reasoning or 'Comando automatico'}; {note}"
        cap, action, params = self.validate_command(device, body)
        if cap == "climate" and not manual and who != "assistant" \
                and self.target_state(device, cap, action, params)["on"] and not device["capabilities"][cap]["on"]:
            wait = self.compressor_wait(device_id)
            if wait > 0:                                     # R4: an automatic start waits for the pause
                self.log("rule:compressor_min_off", {"type": "device", "device_id": device_id}, action, "off", "on",
                         f"{reasoning or 'Accensione automatica'}: rimandata di {int(wait) + 1} s per la pausa minima "
                         f"del compressore", "informational", correlation_id)

                async def later():
                    await asyncio.sleep(wait)
                    try:
                        self.create_command(device_id, body, actor, correlation_id, decision_actor, reasoning)
                    except MockError as exc:
                        logs.warn("deferred command not created", apartment_id=self.apartment_id, device_id=device_id,
                                  error=exc.error)
                self.spawn(later())
                return None
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

    def _settle(self, device: dict, cap: str, requested: dict, reported: dict, correlation_id: str,
                heard: bool = True) -> None:
        """After a successful command: the engine's fields of the request and the device's reported ones; an event
        only if something changed (nothing, when changes() already brought it). heard=False ("delivered": an infrared
        split says nothing) leaves last_seen alone: it is when the device was last heard, by the connector's clock."""
        state = device["capabilities"][cap]
        merged = dict(state)
        merged.update({k: copy.deepcopy(v) for k, v in requested.items() if k in CONTRACT_FIELDS[cap]})
        merged.update(self._contract_part(device["device_id"], cap, self._take_relay(device["device_id"], cap, reported),
                                          utcnow(), state))
        if merged == state:
            return
        was_on = state.get("on")
        state.update(merged)
        self._note_climate(device["device_id"], cap, was_on, state.get("on"))
        if heard:
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
        pause = self.compressor_wait(device["device_id"]) if cap == "climate" else 0.0
        if 0 < pause <= self.setting("COMPRESSOR_WAIT_SECONDS") and new_state["on"] and not device["capabilities"][cap]["on"]:
            await asyncio.sleep(pause)          # R4: the pause ends within the command's time: wait for it, then go
            pause = 0.0
        if pause > 0 and new_state["on"] and not device["capabilities"][cap]["on"]:
            # R4: a manual start during the compressor's pause is refused, saying when to try again
            await asyncio.sleep(0.3)
            self._set_status(cmd, "sent")
            await asyncio.sleep(0.2)
            self._set_status(cmd, "failed", "blocked_by_rule")
            self.log(decision_actor, target, cmd["action"], old, describe(cap, new_state),
                     f"Comando bloccato dalla regola «Pausa minima del compressore»: riprova tra {int(pause) + 1} secondi",
                     "rejected", cmd["correlation_id"], command_id=cmd["command_id"])
            return
        ids = {"correlation_id": cmd["correlation_id"], "command_id": cmd["command_id"], "device_id": device["device_id"]}
        deadline = parse_dt(cmd["created_at"]) + timedelta(seconds=COMMAND_DEADLINE_S)
        check = self._power_check(device, cap, new_state)        # D-131: (meter, direction, watts before) or None
        waiter = self._watch_power(check) if check and check[0]["online"] else None
        no_confirmation = "Nessuna conferma dal dispositivo entro il tempo massimo"
        async with self._device_lock(device["device_id"]):       # at most one command per device (connector.md §2.5)
            running = (device["device_id"], cap, cmd["correlation_id"], new_state)
            self.inflight.append(running)
            try:
                result = await asyncio.wait_for(self.connector.execute(
                    ConnectorCommand(command_id=cmd["command_id"], correlation_id=cmd["correlation_id"],
                                     device_id=device["device_id"], capability=cap,
                                     target=self.connector_target(device, cap, new_state), deadline=deadline),
                    lambda step: self._set_status(cmd, step) if step in ("sent", "verifying") else None),
                    timeout=max((deadline - utcnow()).total_seconds(), 0))
                if result.outcome == "delivered" and waiter is not None and not await self._power_confirmed(waiter, cmd):
                    result = None                                 # the meter did not move: not confirmed (D-131)
                    no_confirmation = (f"Nessuna conferma dal misuratore «{check[0]['label']}» entro 10 secondi: "
                                       f"{device['label'].lower()} potrebbe non aver ricevuto il comando")
            except TimeoutError:
                result = None
            except Exception as exc:
                logs.error("connector execute raised", apartment_id=self.apartment_id, error=str(exc)[:200], **ids)
                result = CommandResult("failed", "internal_error", detail="connector raised")
            finally:
                self.inflight.remove(running)
                if waiter is not None:
                    self._unwatch_power(check[0]["device_id"], waiter)
        if result is None:
            logs.warn("command timeout", apartment_id=self.apartment_id, **ids)
            self._set_status(cmd, "timeout", "no_confirmation")
            self.log(decision_actor, target, cmd["action"], old, describe(cap, new_state), no_confirmation, "failed",
                     cmd["correlation_id"], command_id=cmd["command_id"])
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
        # a connector may also confirm only in its result. "delivered" got here confirmed by the meter, or not to be
        # verified (engine/confirmation.py): the state requested
        reported = (result.state if result.outcome == "confirmed" and result.state
                    else self.connector_target(device, cap, new_state))
        if result.outcome == "delivered" and check and waiter is None:
            meter = check[0]
            self.log("system", target, "command_unverified", None, None,
                     f"Comando a {device['label'].lower()} non verificato: il misuratore «{meter['label']}» è offline",
                     "informational", cmd["correlation_id"], command_id=cmd["command_id"])
        self._settle(device, cap, new_state, reported, cmd["correlation_id"], heard=result.outcome == "confirmed")
        self._set_status(cmd, "acked")
        self.log(decision_actor, target, cmd["action"], old, describe(cap, new_state), reasoning, "applied",
                 cmd["correlation_id"], command_id=cmd["command_id"])

    # ---- power confirmation of an infrared split (P-60 step 7, D-131; engine/confirmation.py) ---------------------
    def confirmation_meter(self, device_id: str) -> dict | None:
        """The meter linked to a split (links.confirmation_device_id), when it exists and has a power_meter."""
        meter_id = self.links.get(device_id, {}).get("confirmation_device_id")
        meter = self.devices.get(meter_id) if meter_id else None
        return meter if meter is not None and "power_meter" in meter["capabilities"] else None

    def _power_check(self, device: dict, cap: str, new_state: dict) -> tuple[dict, str, float] | None:
        """(meter, "on"|"off", watts before) for a command to verify; None when it is not to be verified."""
        if cap != "climate" or device["capabilities"]["climate"].get("confirmation") != "power":
            return None
        direction = confirm.switch_direction(device["capabilities"]["climate"], new_state)
        meter = self.confirmation_meter(device["device_id"]) if direction else None
        if meter is None:
            return None
        return meter, direction, float(meter["capabilities"]["power_meter"].get("watts") or 0)

    def _watch_power(self, check: tuple[dict, str, float]) -> asyncio.Future:
        meter, direction, baseline = check
        waiter = asyncio.get_running_loop().create_future()
        self.power_waiters.setdefault(meter["device_id"], []).append((direction, baseline, waiter))
        return waiter

    def _unwatch_power(self, meter_id: str, waiter: asyncio.Future) -> None:
        left = [w for w in self.power_waiters.get(meter_id, []) if w[2] is not waiter]
        if left:
            self.power_waiters[meter_id] = left
        else:
            self.power_waiters.pop(meter_id, None)

    def _power_seen(self, meter_id: str, state: dict) -> None:
        """A meter's new watts: the commands watching it that they confirm are confirmed."""
        watts = float(state.get("watts") or 0)
        for direction, baseline, waiter in self.power_waiters.get(meter_id, []):
            if not waiter.done() and confirm.power_confirms(direction, baseline, watts, self.confirm_on_watts,
                                                            self.confirm_off_watts):
                waiter.set_result(True)

    async def _power_confirmed(self, waiter: asyncio.Future, cmd: dict) -> bool:
        """Wait for the meter until CONFIRM_UNTIL_S after the command's creation."""
        if waiter.done():
            return True
        left = (parse_dt(cmd["created_at"]) + timedelta(seconds=confirm.CONFIRM_UNTIL_S) - utcnow()).total_seconds()
        try:
            await asyncio.wait_for(waiter, timeout=max(left, 0))
            return True
        except TimeoutError:
            return False

    def _heartbeat(self) -> None:
        """P-60 step 10 (D-104): one line every HEARTBEAT_S; its absence for 10 minutes is the "silent engine" alert."""
        online = sum(1 for d in self.devices.values() if d["online"])
        running = sum(1 for c in self.commands.values() if c["status"] not in FINAL)
        logs.info("engine alive", apartment_id=self.apartment_id, connector="up" if self.connector_up() else "down",
                  devices_online=online, devices_total=len(self.devices), commands_running=running,
                  database="ok" if self.store.ping() else "error")

    def _connector_changed(self, up: bool) -> None:
        """D-131: the connector went down or came back: a decision, instance.health (the BFF's push, after the minutes
        of the offline_alert rule) and apartment.changed (its "online" follows the connector)."""
        corr = str(uuid.uuid4())
        if up:
            logs.info("connector up", apartment_id=self.apartment_id)
            self.log("system", {"type": "apartment"}, "connector_up", "down", "up",
                     "Collegamento ai dispositivi ripristinato", "informational", corr)
        else:
            logs.warn("connector down", apartment_id=self.apartment_id)
            self.log("system", {"type": "apartment"}, "connector_down", "up", "down",
                     "Collegamento ai dispositivi perso: i comandi non partono finché non torna", "informational", corr)
        self.emit("instance.health", self.health()[1], corr)
        self.apartment_changed(corr)

    def _window_opened(self, device_id: str) -> None:
        """A window opened: the rule's reflex starts; during a hold the rule is suspended until its end (R7, D-127),
        and a decision says so."""
        if self.hold and self.rule("window_open_off")["enabled"]:
            until = parse_dt(self.hold["until"]).astimezone(ZoneInfo(self.timezone)).strftime("%H:%M")
            self.log("rule:window_open_off", {"type": "device", "device_id": device_id}, "window_rule_suspended",
                     None, self.hold["until"], f"{self.devices[device_id]['label']} aperta durante la forzatura: la regola "
                     f"«Finestra aperta spegne il clima» riparte alla sua fine (alle {until})", "informational",
                     str(uuid.uuid4()))
        self.spawn(self._window_reflex(device_id))

    async def _window_reflex(self, device_id: str, delay: float | None = None) -> None:
        minutes = self.rule("window_open_off")["params"]["minutes"]
        await asyncio.sleep(minutes * seconds_per_minute() if delay is None else delay)
        contact = self.devices[device_id]["capabilities"]["contact"]
        if not contact["open"] or not self.window_rule_active():
            return                       # closed meanwhile, or a hold: the end of the hold looks again (R7)
        self._window_turn_off(device_id, f"{self.devices[device_id]['label']} aperta da oltre {fmt_num(minutes)} minuti")

    def _window_turn_off(self, window_id: str, why: str) -> None:
        corr = str(uuid.uuid4())
        frost = self.mode == "empty" and self.rule("frost_protection")["enabled"]
        for d in list(self.devices.values()):
            for cap in ("climate", "heating"):
                st = d["capabilities"].get(cap)
                if st and st["on"] and d["online"]:
                    # R8: safety stays stronger than the window: in an empty apartment the frost protection goes on
                    extra = "; l'antigelo resta attivo" if cap == "heating" and frost else ""
                    self.create_command(d["device_id"], {"capability": cap, "action": "turn_off"}, "system:engine", corr,
                                        decision_actor="rule:window_open_off",
                                        reasoning=f"{why} con {d['label'].lower()} acceso{extra}")

    def _window_after_hold(self) -> None:
        """R7 (D-127): at the end of a hold the window rule is active again. A window open for at least the rule's
        minutes turns climate and heating off now, with both reasons; one opened later waits for its remaining time."""
        rule = self.rule("window_open_off")
        if not rule["enabled"]:
            return
        minutes = rule["params"]["minutes"]
        for d in self.devices.values():
            contact = d["capabilities"].get("contact")
            if not contact or not contact.get("open"):
                continue
            open_s = (utcnow() - parse_dt(contact["since"])).total_seconds() if contact.get("since") else 0.0
            left = minutes * seconds_per_minute() - open_s
            if left <= 0:
                self._window_turn_off(d["device_id"], f"Forzatura finita e {d['label'].lower()} aperta da oltre "
                                                      f"{fmt_num(minutes)} minuti (regola «Finestra aperta spegne il "
                                                      f"clima» di nuovo attiva)")
            else:
                self.spawn(self._window_reflex(d["device_id"], delay=left))

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
            seen = self.connector.set_online(device_id, body["online"], notify=False)[0].ts   # the device's instant
            device["online"] = body["online"]
            device["last_seen"] = iso(seen) if body["online"] else device["last_seen"]
            self._save_device(device)
            self._watch_offline(device_id, body["online"])
            self.emit("device.online", {"device_id": device_id, "online": device["online"], "last_seen": device["last_seen"]},
                      correlation_id)
            self.emit("instance.health", self.health()[1], correlation_id)
            self.apartment_changed(correlation_id)
        cap = body.get("capability")
        if cap is not None:
            if cap not in device["capabilities"] or not isinstance(body.get("state"), dict):
                raise MockError(422, "invalid_state", "Capacità inesistente o stato non valido")
            seen = self.connector.set_state(device_id, cap, body["state"], notify=False).ts  # the device's instant
            state = device["capabilities"][cap]
            was_open = state.get("open")
            state.update(body["state"])
            if cap == "contact" and state.get("open") != was_open:
                state["since"] = iso(seen)
            if cap == "motion" and state.get("detected") and "last_seen" not in body["state"]:
                state["last_seen"] = iso(seen)          # D-140: a simulated movement is recorded as a real sensor's
            device["last_seen"] = iso(seen)
            self._save_device(device)
            self.emit("device.state", {"device_id": device_id, "capability": cap, "state": state}, correlation_id)
            if cap == "contact" and state.get("open") and not was_open:
                self._window_opened(device_id)

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
        reset = False
        if ev["type"] == "booking_cancelled":
            booking["cancelled"] = True
            for s in items:
                if s["status"] == "planned":
                    s["status"] = "cancelled"
                ids.append(s["schedule_id"])
            reasoning = f"Prenotazione {bid} cancellata: azioni annullate"
            # D-121: the prearrival already warmed the apartment up for nobody. Back to "empty" now, through the
            # scheduler (so a hold defers it, D-122), unless another booking needs the warmth (in course, or its own
            # prearrival already done); another booking's planned actions are never touched and warm it up later.
            prearrival_done = any(s["kind"] == "prearrival" and s["status"] == "done" for s in items)
            if prearrival_done and not booking["checked_out"] and not self._booking_needs_comfort(bid):
                ids.append(self.add_schedule(utcnow(), {"type": "apartment_mode", "mode": "empty"}, "empty", "booking",
                                             bid)["schedule_id"])
                reset = True
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
        if reset:   # its own decision, which the BFF turns into a push to the managers (D-121)
            self.log("system", {"type": "apartment"}, "booking_cancel_reset", self.mode, "empty",
                     f"Prenotazione {bid} annullata dopo il pre-arrivo: appartamento rimesso a vuoto", "informational",
                     correlation_id, emit=emit)
        if emit:
            self.apartment_changed(correlation_id)
        return 202, result

    def _booking_needs_comfort(self, cancelled_id: str) -> bool:
        """Another booking, not cancelled nor checked out, that is in course now or whose prearrival already ran."""
        now = utcnow()
        for b in self.bookings.values():
            if b["booking_id"] == cancelled_id or b["cancelled"] or b["checked_out"]:
                continue
            if b["checkin"] <= now < b["checkout"] or any(
                    s["booking_id"] == b["booking_id"] and s["kind"] == "prearrival" and s["status"] == "done"
                    for s in self.schedule.values()):
                return True
        return False

    # ---- approvals ---------------------------------------------------------
    def pending_approval(self) -> dict | None:
        return next((a for a in self.approvals if a["status"] == "pending"), None)

    def trigger_approval(self, correlation_id: str, source: str = "rule", reason: str | None = None) -> dict | None:
        """The assistant's proposal (source "assistant": the boiler off with guests in, D-119: rejected at expiry), or
        the simulator's test trigger (POST /_test/state, conformance C12): an example of F2 on the first device a
        meter could ask to switch off (D-137). Never source "brain": reserved by the contract."""
        if source == "assistant":
            heating = next((d for d in self.devices.values() if "heating" in d["capabilities"]), None)
            if heating is None:
                raise MockError(422, "no_heating", "Nessuna caldaia nell'appartamento")
            sp = heating["capabilities"]["heating"]["setpoint"]
            return self._new_approval("assistant", "Spegnere la caldaia mentre l'appartamento risulta occupato",
                                      reason or f"La caldaia è accesa a {fmt_num(sp)} °C",
                                      {"type": "device_command", "device_id": heating["device_id"], "capability": "heating",
                                       "action": "turn_off"}, "reject", correlation_id)
        found = next(((m, t) for m in self.devices.values() if (t := self._power_target(m))), None)
        if found is None:
            raise MockError(422, "no_device", "Nessun apparecchio con misuratore da proporre nell'appartamento")
        meter, target = found
        return self._propose_switch_off(target, meter, None, correlation_id)

    def _new_approval(self, source: str, description: str, reason: str, proposed: dict, expires_action: str,
                      correlation_id: str) -> dict | None:
        """An approval: opened at once, or queued behind the open one (None)."""
        now = utcnow()
        approval = {
            "approval_id": self.next_id("apr"), "status": "pending", "created_at": iso(now),
            "expires_at": iso(now + timedelta(minutes=self.setting("APPROVAL_EXPIRES_MINUTES"))),
            "expires_action": expires_action, "source": source, "description": description, "reason": reason,
            "proposed_action": proposed, "decided_by": None, "decided_at": None, "note": None,
            "correlation_id": correlation_id,
        }
        if self.pending_approval():
            self.approval_queue.append(approval)
            self._save_queue()
            return None
        self._open_approval(approval)
        return approval

    def _open_approval(self, approval: dict) -> None:
        now = utcnow()
        approval["created_at"] = iso(now)
        approval["expires_at"] = iso(now + timedelta(minutes=self.setting("APPROVAL_EXPIRES_MINUTES")))
        self.approvals.append(approval)
        self._save_approval(approval)
        self.emit("approval.pending", approval, approval["correlation_id"])
        pa = approval["proposed_action"]
        if pa["type"] == "apartment_mode":
            action, old, new = "set_mode", self.mode, pa["mode"]
        else:
            state = self.devices.get(pa["device_id"], {}).get("capabilities", {}).get(pa["capability"], {})
            action, old, new = pa["action"], ("on" if state.get("on") else "off"), "off"
        self.log(self._approval_actor(approval), self._approval_target(approval), action, old, new, approval["reason"],
                 "pending_approval", approval["correlation_id"], approval_id=approval["approval_id"])

    @staticmethod
    def _approval_target(approval: dict) -> dict:
        pa = approval["proposed_action"]
        return {"type": "apartment"} if pa["type"] == "apartment_mode" else {"type": "device", "device_id": pa["device_id"]}

    @staticmethod
    def _approval_actor(approval: dict) -> str:
        """Who asks, in the Decisions: the assistant, the check-out rule (F1), the engine (F2, no rule of its own)."""
        if approval["source"] == "assistant":
            return "assistant"
        return "rule:checkout_eco" if approval["proposed_action"]["type"] == "apartment_mode" else "system"

    # ---- approvals from real sources (P-60 step 8, D-137) ------------------------------------------------------
    def _power_target(self, meter: dict) -> dict | None:
        """The device a meter's consumption belongs to and that can be switched off: the meter's own (switch or
        climate), or the split it confirms (links.confirmation_device_id). Never a boiler: the frost protection
        governs it."""
        caps = meter["capabilities"]
        if "power_meter" not in caps or "heating" in caps:
            return None
        if "switch" in caps or "climate" in caps:
            return meter
        return next((d for d in self.devices.values() if "climate" in d["capabilities"] and "heating" not in d["capabilities"]
                     and self.links.get(d["device_id"], {}).get("confirmation_device_id") == meter["device_id"]), None)

    def _propose_switch_off(self, target: dict, meter: dict, watts: float | None, correlation_id: str) -> dict | None:
        """F2: switch off a device that draws power in an empty apartment; watts None = the simulator's example."""
        label = target["label"]
        if watts is None:
            reason = f"Prova dal simulatore: esempio di richiesta per {label.lower()}, come quando consuma a casa vuota"
        else:
            reason = (f"{label} consuma {fmt_num(round(watts))} W da oltre "
                      f"{fmt_num(self.setting('EMPTY_POWER_MINUTES'))} minuti con l'appartamento vuoto")
        cap = "climate" if "climate" in target["capabilities"] else "switch"
        return self._new_approval("rule", f"Spegnere {label.lower()}", reason,
                                  {"type": "device_command", "device_id": target["device_id"], "capability": cap,
                                   "action": "turn_off"}, self.setting("EMPTY_POWER_EXPIRED_ACTION"), correlation_id)

    def _watch_empty_power(self) -> None:
        """F2, at every tick: in an empty apartment and outside a hold, a meter above EMPTY_POWER_WATTS for
        EMPTY_POWER_MINUTES asks once for its episode (until the watts drop back under the threshold)."""
        if self.mode != "empty" or self.hold:
            self.empty_power.clear()
            return
        limit, wait = self.setting("EMPTY_POWER_WATTS"), self.setting("EMPTY_POWER_MINUTES") * seconds_per_minute()
        for meter in self.devices.values():
            pm = meter["capabilities"].get("power_meter")
            if pm is None:
                continue
            watts = float(pm.get("watts") or 0)
            if not meter["online"] or watts <= limit:
                self.empty_power.pop(meter["device_id"], None)
                continue
            seen = self.empty_power.setdefault(meter["device_id"], {"since": time.monotonic(), "asked": False})
            if seen["asked"] or time.monotonic() - seen["since"] < wait:
                continue
            seen["asked"] = True
            target = self._power_target(meter)
            if target is None:
                logs.info("empty power without a device to switch off", apartment_id=self.apartment_id,
                          device_id=meter["device_id"], watts=watts)
                continue
            self._propose_switch_off(target, meter, watts, str(uuid.uuid4()))

    def _presence_after_checkout(self, item: dict) -> tuple[dict, datetime] | None:
        """F1: the motion sensor that saw someone after the booking's departure time and within
        CHECKOUT_PRESENCE_MINUTES, with when; None without a motion sensor or without such a movement."""
        booking = self.bookings.get(item.get("booking_id") or "")
        if booking is None:
            return None
        now, window = utcnow(), timedelta(minutes=self.setting("CHECKOUT_PRESENCE_MINUTES"))
        seen = []
        for d in self.devices.values():
            last = d["capabilities"].get("motion", {}).get("last_seen")
            if last and booking["checkout"] <= parse_dt(last) and now - parse_dt(last) <= window:
                seen.append((d, parse_dt(last)))
        return max(seen, key=lambda s: s[1]) if seen else None

    def _propose_checkout(self, item: dict, seen: tuple[dict, datetime], correlation_id: str) -> None:
        sensor, last = seen
        booking = self.bookings[item["booking_id"]]
        departure = booking["checkout"].astimezone(ZoneInfo(self.timezone)).strftime("%H:%M")
        minutes = max(int((utcnow() - last).total_seconds() // 60), 0)
        self._new_approval("rule", "Mettere l'appartamento a vuoto dopo il check-out",
                           f"Movimento rilevato {minutes} minuti fa da «{sensor['label']}», dopo l'orario di partenza "
                           f"delle {departure}: gli ospiti potrebbero essere ancora in casa",
                           dict(item["action"]), "approve", correlation_id)

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
        self.log(who, self._approval_target(approval), body["decision"],
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
        # P-60 step 6 (D-130): the hourly telemetry of the power meters (Wh per device and UTC hour). Every bucket up to
        # now is in the series; an hour without readings counts 0 (the contract has no "unknown"). Whole hours: an
        # hour starting before `to` counts entirely. avoided_hvac_hours: null, as the contract allows, until the apartment
        # has at least 4 weeks of real consumption recorded (D-139, registro section 7), when it is computed for real.
        starts, cur, now = [], start, utcnow()
        end = min(to, now)
        while cur < end:
            starts.append(cur)
            cur = next_start(cur)
        sums = {iso(s): 0.0 for s in starts}
        per_device: dict[str, float] = {}
        if starts:
            upper = end.replace(minute=0, second=0, microsecond=0)
            if upper < end:
                upper += timedelta(hours=1)
            for device_id, hour, wh in self.energy_rows(hour_of(start), hour_of(upper)):
                h = datetime.strptime(hour, "%Y-%m-%dT%H:00Z").replace(tzinfo=UTC)
                key = iso(h) if bucket == "hour" else iso(local_midnight(h.astimezone(tz).date()))
                if key in sums:
                    sums[key] += wh
                    per_device[device_id] = per_device.get(device_id, 0.0) + wh
        series = [{"ts": key, "kwh": round(wh / 1000, 3)} for key, wh in sums.items()]
        meters = [d for d in self.devices.values() if "power_meter" in d["capabilities"]]
        known = {d["device_id"] for d in meters}
        by_device = [{"device_id": d["device_id"], "label": d["label"], "kwh": round(per_device.get(d["device_id"], 0.0) / 1000, 3)}
                     for d in meters]
        by_device += [{"device_id": device_id, "label": device_id, "kwh": round(wh / 1000, 3)}   # no longer in the catalog
                      for device_id, wh in sorted(per_device.items()) if device_id not in known]
        return {"from": iso(frm), "to": iso(to), "bucket": bucket, "total_kwh": round(sum(sums.values()) / 1000, 3),
                "avoided_hvac_hours": None, "series": series, "by_device": by_device}

    def energy_rows(self, from_hour: str, to_hour: str) -> list[tuple[str, str, float]]:
        """(device_id, UTC hour, Wh) of the hours from_hour <= hour < to_hour: the telemetry, and for a demonstration
        apartment the invented profile before its engine started (D-130)."""
        return self.store.telemetry_between(from_hour, to_hour) + self.profile_rows(from_hour, to_hour)

    def profile_rows(self, from_hour: str, to_hour: str) -> list[tuple[str, str, float]]:
        """The demonstration's invented consumption, per meter and UTC hour, between ENERGY_PROFILE_START and the
        engine's start (profile_until): repeatable (the same hour gives the same Wh), more in the morning and evening."""
        if self.profile_until is None:
            return []
        tz = ZoneInfo(self.timezone)
        cur = max(datetime.strptime(from_hour, "%Y-%m-%dT%H:00Z").replace(tzinfo=UTC), ENERGY_PROFILE_START)
        cur = cur.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        end = min(datetime.strptime(to_hour, "%Y-%m-%dT%H:00Z").replace(tzinfo=UTC), self.profile_until)
        meters = [d["device_id"] for d in self.devices.values() if "power_meter" in d["capabilities"]]
        out = []
        while cur < end:
            local = cur.astimezone(tz).hour
            busy = 1.4 if 6 <= local <= 9 or 17 <= local <= 23 else 0.5
            hour = hour_of(cur)
            for i, device_id in enumerate(meters):
                share = ENERGY_PROFILE_SHARES[i] if i < len(ENERGY_PROFILE_SHARES) else 0.05
                rnd = random.Random(f"{self.apartment_id}|{device_id}|{hour}")
                out.append((device_id, hour, round((0.15 + rnd.random() * 0.45) * busy * share * 1000, 1)))
            cur += timedelta(hours=1)
        return out

    def _seed_energy_profile(self) -> None:
        """A demonstration apartment: the invented consumption up to the hour the engine starts, saved so that a restart
        on the same engine.db keeps it; today's part of it is in the meters' kwh_today."""
        now = utcnow()
        self.profile_until = now.replace(minute=0, second=0, microsecond=0)
        self.store.put_meta("energy_profile", {"until": iso(self.profile_until)})
        local = now.astimezone(ZoneInfo(self.timezone))
        midnight = datetime(local.year, local.month, local.day, tzinfo=local.tzinfo).astimezone(UTC)
        today: dict[str, float] = {}
        for device_id, _, wh in self.profile_rows(hour_of(midnight), hour_of(self.profile_until)):
            today[device_id] = today.get(device_id, 0.0) + wh
        for device_id, wh in today.items():
            meter = self.meters.get(device_id)
            if meter is None:
                continue
            meter.day, meter.today_wh = local.date().isoformat(), meter.today_wh + wh
            self._save_meter(device_id)
            device = self.devices[device_id]
            device["capabilities"]["power_meter"]["kwh_today"] = round(meter.today_wh / 1000, 3)
            self._save_device(device)

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
        if self.model is not None:                   # P-60 step 9: the real model (engine/assistant.py)
            from .assistant import Assistant
            self.spawn(Assistant(self, self.model).resolve(ask, actor))
        else:                                        # the simulated keyword assistant (conformance, CI)
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
                    action, _ = self._within_limits(climate, {   # R6: within the limits, as a command would be
                        "type": "device_command", "device_id": climate["device_id"], "capability": "climate",
                        "action": "set_climate", "params": {"on": True, "setpoint": setpoint}})
                    what = f"{climate['label']} a {fmt_num(action['params']['setpoint'])} °C"
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
                    done = cmd["params"]["setpoint"]          # R6: maybe brought within the limits
                    extra = "" if done == setpoint else f", nei limiti consentiti (avevi chiesto {fmt_num(setpoint)} °C)"
                    ask.update(status="answered", actions=[{"type": "command", "command_id": cmd["command_id"]}],
                               answer=f"Ho impostato {d['label'].lower()} a {fmt_num(done)} °C{extra}.")
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
        self._mold_check()
        stale = [k for k in self.deferred if self.schedule.get(k, {}).get("status") != "planned"]
        if stale:                                        # deferred actions cancelled or gone meanwhile (D-122)
            for k in stale:
                del self.deferred[k]
            self.store.put_meta("deferred", self.deferred)
        t = time.time()
        self.store.prune_events(t - BUFFER_SECONDS)
        self.idem = {k: v for k, v in self.idem.items() if v[0] > t}
        for key in [k for k, _ in self.store.all("idem")]:
            if key not in self.idem:
                self.store.delete("idem", key)

    def tick(self) -> None:
        now = utcnow()
        self.last_tick = time.monotonic()
        if self.last_tick - self.last_heartbeat >= HEARTBEAT_S:
            self.last_heartbeat = self.last_tick
            self._heartbeat()
        up = self.connector_up()
        if up != self.connector_was_up:
            self.connector_was_up = up
            self._connector_changed(up)
        if up:
            self._watch_empty_power()
        if time.monotonic() - self.last_regulation >= seconds_per_minute():
            self.last_regulation = time.monotonic()
            self.regulate()
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
            self._window_after_hold()
        for a in self.approvals:
            if a["status"] == "pending" and a["expires_at"] and parse_dt(a["expires_at"]) <= now:
                a["status"] = "expired"
                self._save_approval(a)
                corr = str(uuid.uuid4())
                outcome = {"reject": "respinta", "approve": "approvata", "wait": "in attesa"}[a["expires_action"]]
                self.log("system", self._approval_target(a), "expire",
                         "pending", "expired", f"Approvazione scaduta senza risposta: {outcome}", "informational", corr,
                         approval_id=a["approval_id"])
                if a["expires_action"] == "approve":
                    self._execute_proposed(a, "system:engine", corr, "system")
                self._dequeue_approval()
        # by time, and by creation for the same time (a stable sort on the creation order, which engine.db keeps too).
        # An action is closed (done/failed) and saved in this same pass, so a later pass never runs it again. After a
        # crash between its commands and that save it runs again at the restart (within MISSED_AFTER_MINUTES): harmless,
        # commands are states to reach (P-60 step 4).
        for item in sorted(self.schedule.values(), key=lambda s: s["run_at"]):
            if item["status"] != "planned" or parse_dt(item["run_at"]) > now:
                continue
            corr = str(uuid.uuid4())
            labels = {"prearrival": "pre-arrivo", "checkout": "check-out", "empty": "casa vuota", "manual": "manuale"}
            reasoning = f"Azione programmata ({labels[item['kind']]})" + (f", prenotazione {item['booking_id']}" if item["booking_id"] else "")
            act = item["action"]
            if act["type"] == "apartment_mode" and self.hold:
                # D-122: a mode action waits for the end of the hold (at most 12 hours, the contract's 720 minutes)
                if item["schedule_id"] not in self.deferred:
                    self.deferred[item["schedule_id"]] = self.hold["until"]
                    self.store.put_meta("deferred", self.deferred)
                    until = parse_dt(self.hold["until"]).astimezone(ZoneInfo(self.timezone)).strftime("%H:%M")
                    self.log("system", {"type": "schedule"}, "schedule_deferred", item["run_at"], self.hold["until"],
                             f"{reasoning}: rimandata per la forzatura, si esegue alla sua fine (alle {until})",
                             "informational", corr)
                continue
            if self.deferred.pop(item["schedule_id"], None) is not None:
                self.store.put_meta("deferred", self.deferred)
                reasoning += " (rimandata per la forzatura)"
            if item["kind"] == "checkout" and act["type"] == "apartment_mode" and (seen := self._presence_after_checkout(item)):
                self._propose_checkout(item, seen, corr)      # F1 (D-137): the manager decides; approved at expiry
                item.update(status="done", command_ids=[], executed_at=iso(now))
                self._save_schedule(item)
                self.apartment_changed(corr)
                continue
            try:
                if act["type"] == "apartment_mode":
                    item["command_ids"] = self.set_mode(act["mode"], "system:engine", corr, reasoning, "system")
                else:
                    cmd = self.create_command(act["device_id"], act, "system:engine", corr, decision_actor="system",
                                              reasoning=reasoning)
                    item["command_ids"] = [cmd["command_id"]] if cmd else []
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
    def __init__(self, model_for=None) -> None:
        """model_for(apartment_id): the model client of a demonstration apartment (P-60 step 9, D-132 point 5: the BFF's
        demonstrations with the real assistant, within the cap); None keeps the keyword assistant."""
        self.sims: dict[str, ApartmentEngine] = {}
        self.model_for = model_for

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
            sim = self.sims[apartment_id] = ApartmentEngine(
                apartment_id, model=self.model_for(apartment_id) if self.model_for else None)
        sim.ensure_started()
        return sim
