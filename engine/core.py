"""The engine of one apartment (contract 1.0.5): rules, modes, bookings, schedule, approvals, decisions, assistant,
the commands' life and the event stream. Its state is in a store: SQLite on the VM (engine/store.py SqliteStore, opened
by engine/service.py since P-60 step 3), in memory (MemoryStore) for the BFF's built-in engine and the tests.

Moved here at P-60 step 2 from the BFF's simulated engine of the time (bff/mock_instance/state.py, a file that no
longer exists): one program for the engine and the demonstration apartments, which the BFF still mounts at /mock. The devices are behind the connector
interface (engine/connector/): the catalog comes from the connector, commands go through its execute() and the state
it reports through changes()."""
import asyncio
import calendar
import copy
import random
import re
import time
import traceback
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from . import log as logs
from .connector.interface import LINKS, CommandResult, ConnectorCommand, DeviceInfo, StateChange
from . import confirmation as confirm
from .config import DEFAULT_SETTINGS, SETTINGS
from .mold import mold_action
from .connector.simulated import SimulatedConnector
from .store import MemoryStore

CONTRACT_VERSION = "1.0.5"
COMMAND_DEADLINE_S = 9           # the connector's deadline, inside the contract's 10 s (connector-v2.md §2.2)
# what a command asks the device: only the device's fields of the capability (connector-v2.md §2.4, D-108)
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
# A step of the inner loop that fails is written in the log as "engine loop step failed" (level error: the alert «Motori:
# righe di errore» reads it), at most one line per step and kind of error every TICK_ERROR_EVERY_S, with how many
# failures the line before left unwritten; the other steps go on.
TICK_ERROR_EVERY_S = 600
# D-130, decision 3: a demonstration apartment (seeded) shows an invented, repeatable consumption, per meter, from the
# start of 2026 to the hour its engine started; after that only what its (simulated) meters measure. The BFF finds
# ENERGY_PROFILE_START as the apartment's energy_since, so nothing odd shows. Shares of the meters, in catalog order.
ENERGY_PROFILE_START = datetime(2026, 1, 1, tzinfo=ZoneInfo("Europe/Rome"))
ENERGY_PROFILE_SHARES = (0.62, 0.28, 0.10)
RETENTION_EVERY_S = 3600
# the engine's own fields of a capability, kept across restarts (the device reports the others again)
ENGINE_FIELDS = {"heating": ("on", "setpoint"), "contact": ("since",), "motion": ("last_seen",),
                 "power_meter": ("kwh_today",), "climate": ("on", "mode", "setpoint", "fan")}
# D14 (P-83): an infrared split reports nothing of its state (connector-v2 §2.3): the engine's copy is all there is, and
# it is kept across restarts; a climate that reports these fields keeps its own report (REPORTED_WINS)
REPORTED_WINS = {"climate"}
# the boiler's thermostat (R1, R2, D-126, D-128): heating.on is the intention the app sees; the relay is the engine's
# D-133: the rules' thresholds that the app does not change are settings of the engine per apartment, with defaults
# and limits in engine/config.py (SETTINGS); the engine reads them with self.setting(name)

# D-174: a device's limits when its catalog does not list them (the catalog is the boundary in every case)
DEVICE_LIMITS_FALLBACK = {"climate": (16, 30), "heating": (7, 23)}

QUEUE_FULL = object()       # D-198: in a reader's queue, it stopped reading: end its stream

NAMES = {"apt-rimini-01": "Via Roma 12 – int. 3", "apt-bologna-01": "Corso Italia 5 – int. 7"}

DEFAULT_RULES = [
    {"rule_id": "window_open_off", "label": "Finestra aperta spegne il clima", "enabled": True, "editable": True,
     "params": {"minutes": 5}, "limits": {"minutes": {"min": 1, "max": 30}}},
    # D-161, D-162: the modes' temperatures, parameters added to a fixed rule (Rule.params admits them, D-151):
    # comfort_celsius (boiler and climate heating in comfort), eco_celsius (boiler in eco), comfort_cool_celsius (climate
    # cooling in comfort); eco <= comfort < cool. «Casa vuota» keeps frost_protection.celsius
    {"rule_id": "setpoint_limits", "label": "Limiti del setpoint", "enabled": True, "editable": True,
     # 1098 = b: two ranges. min/max the WINTER one (the boiler, a climate heating: eco and comfort inside it),
     # summer_min/summer_max the SUMMER one (a climate cooling or dehumidifying: the cooling inside it); no tie between
     # them but comfort < cooling (D-162). A rule saved before gets the summer one with its first values (_rule_defaults);
     # first values 16–24 and 18–28 (answer 1099)
     "params": {"min": 16, "max": 24, "comfort_celsius": 21, "eco_celsius": 18, "comfort_cool_celsius": 25,
                "summer_min": 18, "summer_max": 28},
     "limits": {"min": {"min": 7, "max": 20}, "max": {"min": 20, "max": 28}, "comfort_celsius": {"min": 16, "max": 26},
                "eco_celsius": {"min": 10, "max": 22}, "comfort_cool_celsius": {"min": 22, "max": 28},
                "summer_min": {"min": 16, "max": 28}, "summer_max": {"min": 22, "max": 30}}},
    {"rule_id": "frost_protection", "label": "Antigelo a casa vuota", "enabled": True, "editable": True,
     "params": {"celsius": 8}, "limits": {"celsius": {"min": 5, "max": 12}}},
    {"rule_id": "mold_protection", "label": "Antimuffa a casa vuota", "enabled": True, "editable": True,
     "params": {"humidity_percent": 65}, "limits": {"humidity_percent": {"min": 50, "max": 80}}},
    {"rule_id": "prearrival", "label": "Pre-arrivo", "enabled": True, "editable": True,
     "params": {"hours_before": 2}, "limits": {"hours_before": {"min": 0, "max": 6}}},
    # presence_minutes (D-151 points 18-19): the contract's Rule.params admits further numeric parameters
    # (additionalProperties: number), so a parameter added to a fixed rule is not a change of the contract; it is the
    # first. Its first value is CHECKOUT_PRESENCE_MINUTES of the apartment's settings, then the app decides.
    {"rule_id": "checkout_eco", "label": "Risparmio al check-out", "enabled": True, "editable": True,
     "params": {"minutes_after": 30, "presence_minutes": 30},
     "limits": {"minutes_after": {"min": 0, "max": 180}, "presence_minutes": {"min": 5, "max": 180}}},
    {"rule_id": "compressor_min_off", "label": "Pausa minima del compressore", "enabled": True, "editable": False,
     "params": {"minutes": 3}, "limits": {"minutes": {"min": 3, "max": 3}}},
    {"rule_id": "offline_alert", "label": "Avviso dispositivo offline", "enabled": True, "editable": True,
     "params": {"minutes": 15}, "limits": {"minutes": {"min": 5, "max": 120}}},
]


def seconds_per_minute() -> float:
    """MOCK_TIME_SCALE = real seconds per simulated minute: 60 is real time. 1 (the rules' minutes in seconds) only when
    the variable is missing: the BFF's built-in engine run locally and the tests. The engine service sets 60 itself
    (engine/__main__.py: a default with the simulated connector, always with real devices) and both Cloud Run
    manifests set 60."""
    import os

    return float(os.environ.get("MOCK_TIME_SCALE", "1"))


def utcnow() -> datetime:
    return datetime.now(UTC)


# D-219: what a scheduled action is, in the decisions schedule_failed and schedule_missed (new_value) and in their text.
# An action the assistant planned is a manual one in the schedule (kind "manual", source "assistant"): here it has its own.
def range_errors(sl: dict, touched: bool) -> list[tuple[int, str, str]]:
    """«Limiti del setpoint» (1098 = b): the 422s of a rule's parameters, in the order the app shows them (o2's
    sentences). min ≤ eco ≤ comfort ≤ max (winter), summer_min ≤ cooling ≤ summer_max (summer), comfort < cooling
    (D-162). The checks against the ranges only when the patch touches the rule, also off (its temperatures hold
    anyway): a rule saved before them is not refused for another rule; the three of before always. The first only."""
    eco, comfort, cool = sl.get("eco_celsius"), sl.get("comfort_celsius"), sl.get("comfort_cool_celsius")
    smin, smax = sl.get("summer_min"), sl.get("summer_max")
    checks = [
        (sl["min"] > sl["max"], "Il minimo invernale non può superare il massimo invernale"),
        (touched and eco is not None and eco < sl["min"], "La temperatura eco non può essere sotto il minimo invernale"),
        (eco is not None and comfort is not None and eco > comfort, "La temperatura eco non può superare quella comfort"),
        (touched and comfort is not None and comfort > sl["max"],
         "La temperatura comfort non può superare il massimo invernale"),
        (touched and smin is not None and smax is not None and smin > smax,
         "Il minimo estivo non può superare il massimo estivo"),
        (touched and cool is not None and smin is not None and smax is not None and not smin <= cool <= smax,
         "La temperatura di raffrescamento deve stare fra il minimo e il massimo estivi"),
        (comfort is not None and cool is not None and comfort >= cool,
         "La temperatura di raffrescamento deve essere più alta di quella comfort"),
    ]
    return [(422, "invalid_range", message) for broken, message in checks if broken][:1]


CHECKOUT_APPROVAL = "Mettere l'appartamento a vuoto dopo il check-out"
BOOKING_RULES = {"prearrival": "prearrival", "checkout_eco": "checkout"}   # P-90 S11: a booking rule -> its actions' kind   # F1 (D-137); D05 recognises it at expiry
SCHEDULE_LABELS = {"prearrival": "pre-arrivo", "checkout": "check-out", "empty": "casa vuota", "manual": "manuale",
                   "assistant": "dell'assistente"}


def schedule_kind(item: dict) -> str:
    return "assistant" if item.get("kind") == "manual" and item.get("source") == "assistant" else item["kind"]


def duration_words(span: timedelta) -> str:
    """D-217: a stretch of time in Italian, as a person says it: «25 minuti», «1 ora», «3 ore e 10 minuti»,
    «2 giorni e 4 ore»; never «e 0 minuti». Minutes and hours are counted down, never up."""
    minutes = int(span.total_seconds() // 60)
    if minutes < 1:
        return "meno di un minuto"
    def unit(n: int, one: str, many: str) -> str:
        return f"{n} {one if n == 1 else many}"
    if minutes < 60:
        return unit(minutes, "minuto", "minuti")
    hours, rest = divmod(minutes, 60)
    if hours < 24:
        return unit(hours, "ora", "ore") + (f" e {unit(rest, 'minuto', 'minuti')}" if rest else "")
    days, hours = divmod(hours, 24)
    return unit(days, "giorno", "giorni") + (f" e {unit(hours, 'ora', 'ore')}" if hours else "")


def at_local_hour(run: datetime, hh: int, mm: int) -> str:
    """D-212: «alle HH:MM» said with the hour the action really runs at. On the day summer time starts an hour that
    does not exist (02:30) runs an hour later; on the day it ends an hour that comes twice runs the first time."""
    real = run.astimezone(UTC).astimezone(run.tzinfo)
    if (real.hour, real.minute) != (hh, mm):
        return f"alle {real:%H:%M}: quel giorno le {hh:02d}:{mm:02d} non esistono, per il passaggio all'ora legale"
    if run.replace(fold=1).utcoffset() != run.replace(fold=0).utcoffset():
        return f"alle {hh:02d}:{mm:02d}, la prima delle due volte (ancora con l'ora legale)"
    return f"alle {hh:02d}:{mm:02d}"


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
    """kwh_today of one power meter, from the connector's raw cumulative counter (energy_total_wh, connector-v2.md §2.3)
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
                 model=None, variant: str | None = None):
        """Without a connector: the demonstration apartment, a SimulatedConnector chosen by the apartment's id. seed
        (by default: without a connector) adds the demonstration's bookings and decisions; otherwise the history
        starts empty and the apartment in mode "empty". store: where the state lives (engine/store.py), in memory by
        default; a store that already holds an apartment is loaded instead of seeded. variant (P-72): «vuoto» or
        «occupato» for the demonstration; otherwise the connector's own (a simulated one on the VM, DEMO_VARIANT), else
        by the apartment's id as before P-72."""
        self.apartment_id = apartment_id
        self.name = NAMES.get(apartment_id, apartment_id)
        self.timezone = "Europe/Rome"
        from .connector.simulated import variant_of
        if variant is None and connector is not None and hasattr(connector, "variant"):
            variant_n = connector.variant
        else:
            variant_n = variant_of(apartment_id, variant)
        variant = variant_n
        seeded = connector is None if seed is None else seed
        self.connector = SimulatedConnector(variant) if connector is None else connector
        self.store = store if store is not None else MemoryStore()
        self.simulated = simulated
        self.implementation = implementation or {"name": "bff-mock-instance", "version": "0.1.0"}
        self.meters: dict[str, EnergyCounter] = {}
        # D-131, D-133: the apartment's settings (engine/config.py), the defaults when not given
        self.settings = {**DEFAULT_SETTINGS, **(settings or {})}
        self.timezone = str(self.settings["TIMEZONE"])  # D-177: TIMEZONE, declared in /apartment.timezone
        if confirm_watts:
            self.settings["CONFIRM_ON_WATTS"], self.settings["CONFIRM_OFF_WATTS"] = confirm_watts
        self.power_waiters: dict[str, list[tuple[str, float, asyncio.Future]]] = {}   # meter -> commands watching it
        self.rooms = [{"room_id": r.room_id, "name": r.name} for r in self.connector.rooms()]
        self.rules = copy.deepcopy(DEFAULT_RULES)
        self._compressor_from_settings()
        self._presence_from_settings(fresh=True)
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
        self.approval_schedules: dict[str, str] = {}   # D-170: approval -> the time of the scheduled action it asks
        self.deferred: dict[str, str] = {}      # schedule_id -> the hold's end, for mode actions waiting for it (D-122)
        # D-219 (2): a scheduled action whose commands are not all over yet: schedule_id -> {"corr", "refused" (device
        # and why, the commands never created), "waiting" (devices whose start waits for the compressor's pause)};
        # command_schedule is the index command -> its action, rebuilt from the items' command_ids at a restart
        self.schedule_open: dict[str, dict] = {}
        self.command_schedule: dict[str, str] = {}
        self._schedule_run: str | None = None   # the scheduled action whose commands are being created now
        self.compressor_off: dict[str, float] = {}   # climate device -> when it went off (monotonic), R4
        self.offline_watch: dict[str, object] = {}   # device -> the offline episode being watched, R5
        self.links: dict[str, dict[str, str]] = {}   # device -> its links (connector-v2.md §2.2), never shown to the app
        self.relay: dict[str, bool] = {}             # boiler -> its relay as the device reports it (R2, D-128)
        self.relay_switched: dict[str, float] = {}   # boiler -> when the thermostat last switched it (monotonic)
        self.relay_busy: set[str] = set()            # boilers with a thermostat switch running
        self.thermostat_issue: dict[str, str] = {}   # boiler -> the sensor episode already reported (D-164)
        self.heating_by_mode: set[str] = set()       # D-164: boilers whose intention a mode set (not a person)
        self.climate_by_mode: set[str] = set()       # D-169: climates comfort regulates (no person touched them since)
        self.climate_switched: dict[str, float] = {}  # D-169: climate -> monotonic time of its last automatic change
        self._auto_climate = False                   # D-169: a climate command of the mode or of the regulation
        self._frost_command = False                  # D-183 point 125: the boiler's commands of «casa vuota»
        self.catalog_limits: dict[tuple[str, str], tuple] = {}   # D-174: (device, cap) -> the catalog's (min, max)
        self.limits_conflicts: set[str] = set(self.store.get_meta("limits_conflicts", []) or [])
        # 1097 = a: climates on whose setpoint narrower limits cut, waiting for their command (offline, window open,
        # busy): device -> {"from", "to"}; the episode of a rule saved with the modes' temperatures outside its limits
        self.limits_push: dict[str, dict] = dict(self.store.get_meta("limits_push", {}) or {})
        self.modes_outside: bool = bool(self.store.get_meta("modes_outside", False))
        self.mode_notes: dict[str, str] = {}         # device -> the note of its last mode command cut by the limits
        # P-90 S3: command -> {"mode", "body", "at", "retried"} of the commands of a mode, until their outcome
        self.mode_cmds: dict[str, dict] = {}
        self.remote_low: dict[str, float] = {}       # P-90 S1: split -> monotonic since its meter is low, no command
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
        self.last_heartbeat = float("-inf")         # "never": the first tick beats, also on a machine just switched on
        self.tick_errors: dict[tuple[str, str], list] = {}   # (step, error kind) -> [monotonic of its last line, unwritten]
        self.windows_armed = False                  # the window rule's waits live in memory: armed again at the start
        # D-218 point 1 (answer 811): what the window rule turned off, to bring back when the windows are closed again:
        # device -> {"cap", "by_mode", "state"}; kept in the store. The wait of each open window, cancelled when it closes
        self.window_off: dict[str, dict] = {}
        self.window_reflexes: dict[str, asyncio.Task] = {}
        # D03 (P-83): the open windows whose rule's minutes ran out; while one stays open the rule holds (window_in_force)
        self.window_fired: set[str] = set()
        self.windows_closed_at = float("-inf")      # monotonic: when the last open window closed
        self._window_command = False                # the rule's own turn_off: not a person's (the mode is kept)
        self.commanded_at: dict[str, float] = {}    # D13: device -> monotonic of its last non-automatic command
        self._mode_in_progress: str | None = None   # D13: the mode set_mode is setting (its commands are made first)
        # D16 (P-83): device -> {"body", "mode", "at"}: a mode's command for a device unreachable when it was set
        self.mode_pending: dict[str, dict] = {}
        self.profile_until: datetime | None = None   # D-130: end of the demonstration's invented consumption
        self.connector_was_up = self.connector_up()  # D-131: a change is an event and a decision (tick)
        self.empty_power: dict[str, dict] = {}       # D-137 F2: meter -> {"since": monotonic, "asked": bool}, one episode
        self.no_sensor_noted: set[str] = set()        # D-162: climates without a room sensor, noted in this comfort
        self.model = model                           # P-60 step 9: engine/assistant.ModelClient, None = keywords
        self.restored = bool(self.store.get_meta("initialized"))
        if self.restored:
            self._load()
        else:
            self.devices = {d.device_id: self._device_from(d) for d in self.connector.devices()}
            self._apply_limits()
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

    def _rule_defaults(self) -> None:
        """A rule saved before a parameter existed (D-151, D-161) gets it with its default and limits; a value already
        there is never changed."""
        defaults = {r["rule_id"]: r for r in DEFAULT_RULES}
        for rule in self.rules:
            base = defaults.get(rule["rule_id"])
            if not base:
                continue
            for key, value in base["params"].items():
                if key not in rule["params"]:
                    rule["params"][key] = value
                    rule["limits"][key] = dict(base["limits"][key])

    def _presence_from_settings(self, fresh: bool = False) -> None:
        """D-151: checkout_eco's presence_minutes starts from the setting CHECKOUT_PRESENCE_MINUTES (a rule saved before
        the parameter existed gets it too); once the rule holds a value, the app's value wins. Limits from the setting's
        table (engine/config.py)."""
        _default, low, high = SETTINGS["CHECKOUT_PRESENCE_MINUTES"]
        for rule in self.rules:
            if rule["rule_id"] == "checkout_eco":
                if fresh or "presence_minutes" not in rule["params"]:
                    value = self.setting("CHECKOUT_PRESENCE_MINUTES")
                    rule["params"]["presence_minutes"] = int(value) if value == int(value) else value
                rule["limits"]["presence_minutes"] = {"min": int(low), "max": int(high)}

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

    def schedule_approval(self, approval_id: str, run_at: str) -> None:
        """D-170: this approval asks a scheduled action at run_at."""
        self.approval_schedules[approval_id] = run_at
        self.store.put_meta("approval_schedules", self.approval_schedules)

    def _take_schedule(self, approval_id: str) -> str | None:
        run_at = self.approval_schedules.pop(approval_id, None)
        if run_at is not None:
            self.store.put_meta("approval_schedules", self.approval_schedules)
        return run_at

    def guests_in(self) -> bool:
        """D18 (P-83): guests in now, for the assistant's approvals: the occupancy says so (a check-in), or a booking in
        course, not cancelled and not checked out, says so (Italianway may never send the check-in)."""
        if self.apartment().get("occupancy") == "occupied":
            return True
        now = utcnow()
        return any(not b["cancelled"] and not b["checked_out"] and b["checkin"] <= now < b["checkout"]
                   for b in self.bookings.values())

    def occupied_at(self, when: datetime) -> bool:
        """D-170: the bookings' calendar says guests are in at that time (a booking not cancelled covering it)."""
        return any(not b["cancelled"] and b["checkin"] <= when < b["checkout"] for b in self.bookings.values())

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
        self._presence_from_settings()
        self._rule_defaults()                  # after presence_minutes, which takes its first value from the setting
        self.rules_updated_at = apt.get("rules_updated_at", self.rules_updated_at)
        self.counter = st.get_meta("counter", self.counter)
        self.heating_by_mode = set(st.get_meta("heating_by_mode", []) or [])
        self.climate_by_mode = set(st.get_meta("climate_by_mode", []) or [])
        self.window_off = dict(st.get_meta("window_off", {}) or {})
        self.mode_pending = {k: {**v, "at": float("-inf")} for k, v in (st.get_meta("mode_pending", {}) or {}).items()}
        self.meters ={k: EnergyCounter(self.timezone, v) for k, v in st.all("meters")}
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
                        reported = info.capabilities.get(cap) or {}
                        for f in fields:
                            if cap in REPORTED_WINS and f in reported:
                                continue                # D14: the device said it itself
                            if f in old["capabilities"][cap]:
                                device["capabilities"][cap][f] = old["capabilities"][cap][f]
                contact, was = device["capabilities"].get("contact"), old["capabilities"].get("contact")
                if contact and was and "open" not in (info.capabilities.get("contact") or {}):
                    # D15 / P7a-2 (P-83): not read yet (a BLU contact behind its bridge): the saved value stays until a
                    # reading arrives; before, open False was invented and the window rule's return brought the
                    # boiler back with the window open
                    contact["open"], contact["since"] = was.get("open", False), was.get("since", contact.get("since"))
                elif contact and was and contact.get("open") != was.get("open"):
                    contact["since"] = iso(utcnow())    # it changed while the engine was down
                if device["last_seen"] is None and old.get("last_seen"):
                    device["last_seen"] = old["last_seen"]     # D12: the connector does not know it yet
            self.devices[info.device_id] = device
            self._save_device(device)
        self._apply_limits()                               # D-174: the manager's inside the catalog's
        self.commands = dict(st.all("commands"))
        self.decisions = [d for _, d in st.all("decisions")]
        self.schedule = dict(st.all("schedule"))
        self.bookings = {k: {**b, "checkin": parse_dt(b["checkin"]), "checkout": parse_dt(b["checkout"])}
                         for k, b in st.all("bookings")}
        self.processed_events = dict(st.all("processed_events"))
        self.approvals = [a for _, a in st.all("approvals")]
        self.approval_queue = st.get_meta("approval_queue", [])
        self.approval_schedules = st.get_meta("approval_schedules", {}) or {}
        self.deferred = st.get_meta("deferred", {})
        self.schedule_open = dict(st.get_meta("schedule_open", {}) or {})
        self.command_schedule = {c: sid for sid in self.schedule_open
                                 for c in (self.schedule.get(sid) or {}).get("command_ids") or []}
        # D-218: the compressors' pauses, from the UTC instant each one went off (the in-memory clock starts again)
        for device_id, at in (st.get_meta("compressor_off", {}) or {}).items():
            elapsed = (utcnow() - parse_dt(at)).total_seconds()
            if elapsed >= 0:
                self.compressor_off[device_id] = time.monotonic() - elapsed
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
            # D-219: new_value is the action's kind (the BFF's notification picks its category from it); the time
            # in the apartment's local hour, not the ISO instant
            local = parse_dt(item["run_at"]).astimezone(ZoneInfo(self.timezone))
            self.log("system", {"type": "schedule"}, "schedule_missed", item["run_at"], schedule_kind(item),
                     f"Azione programmata ({SCHEDULE_LABELS.get(schedule_kind(item), schedule_kind(item))}) non eseguita: "
                     f"il motore era fermo all'orario previsto, alle {local:%H:%M} del {local:%d/%m}, "
                     f"oltre {fmt_num(self.setting('MISSED_AFTER_MINUTES'))} minuti fa", "failed", str(uuid.uuid4()))
        # D-219 (2): an action whose commands the restart interrupted is judged now; a start that waited for the
        # compressor's pause died with the process: it did not happen
        for sid, run in list(self.schedule_open.items()):
            for device_id in run.get("waiting") or []:
                run.setdefault("refused", []).append(
                    [device_id, "motore riavviato prima dell'accensione rimandata per la pausa del compressore"])
            run["waiting"] = []
            self._schedule_check(sid)
        if self.schedule_open:
            self.store.put_meta("schedule_open", self.schedule_open)

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.get_running_loop().create_task(coro)
        self.tasks.add(task)

        def done(t: asyncio.Task) -> None:
            self.tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:     # before, lost without a line
                self._step_failed(f"task {getattr(coro, '__name__', 'unknown')}", t.exception())
        task.add_done_callback(done)
        return task

    def _step_failed(self, step: str, exc: BaseException) -> None:
        """An error of the inner loop or of a background task: one line per step and kind every TICK_ERROR_EVERY_S."""
        key, now = (step, type(exc).__name__), time.monotonic()
        seen = self.tick_errors.get(key)
        if seen and now - seen[0] < TICK_ERROR_EVERY_S:
            seen[1] += 1
            return
        frames = traceback.extract_tb(exc.__traceback__)
        logs.error("engine loop step failed", apartment_id=self.apartment_id, step=step, error_type=key[1],
                   error=str(exc)[:200], at=f"{frames[-1].name}:{frames[-1].lineno}" if frames else None,
                   unwritten_before=seen[1] if seen else 0)
        self.tick_errors[key] = [now, 0]

    def _guarded(self, step: str, fn, *args) -> None:
        """One step of the tick: an error is written and the other steps go on."""
        try:
            fn(*args)
        except Exception as exc:
            self._step_failed(step, exc)

    def ensure_started(self) -> None:
        if self.loop_task is None or self.loop_task.done():
            self.loop_task = asyncio.get_running_loop().create_task(self._tick_loop())
            self.device_locks = {}          # a new event loop (the tests run one per case): locks belong to a loop
            if not self.windows_armed:
                self.windows_armed = True
                self._windows_at_start()
                self._offline_at_start()
                self._modes_outside_check()               # 1097 = a: a rule saved before the check
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
            for key, value in self._starting_values(d.device_id, cap, state).items():
                state.setdefault(key, value)
            caps[cap] = state
        return {"device_id": d.device_id, "label": d.label, "room_id": d.room_id, "online": d.online,
                "last_seen": iso(d.last_seen) if d.last_seen else None, "capabilities": caps}

    def _starting_values(self, device_id: str, cap: str, state: dict) -> dict:
        """The engine's fields before anything is known (a catalog lists `switch: {}`); sensors' readings have none."""
        def clamp(value, lo, hi):
            return min(max(value, lo), hi)
        if cap == "climate":
            lo, hi, _ = self.effective_limits(device_id, cap, "heat")
            return {"on": False, "mode": "heat", "setpoint": clamp(21, lo, hi), "fan": "auto", "setpoint_min": lo,
                    "setpoint_max": hi, "confirmation": "none"}
        if cap == "heating":
            lo, hi, _ = self.effective_limits(device_id, cap)
            frost = self.rule("frost_protection")["params"]["celsius"]     # D-183 point 125: the device's limits only
            return {"on": False, "setpoint": clamp(frost, *self.frost_limits(device_id)), "setpoint_min": lo,
                    "setpoint_max": hi}
        return {"switch": {"on": False}, "power_meter": {"watts": 0, "kwh_today": 0},
                "contact": {"open": False, "since": None}, "motion": {"detected": False, "last_seen": None}}.get(cap, {})

    def _contract_part(self, device_id: str, cap: str, raw: dict, ts: datetime, current: dict) -> dict:
        """The contract's fields out of what the connector reports, plus what the engine computes (connector-v2.md §2.3):
        kwh_today from energy_total_wh, contact's since, motion's last_seen."""
        out = {k: copy.deepcopy(v) for k, v in raw.items() if k in CONTRACT_FIELDS[cap]}
        if cap in DEVICE_LIMITS_FALLBACK and ("setpoint_min" in raw or "setpoint_max" in raw):
            lo, hi = self.device_limits(device_id, cap)       # D-174: the catalog's, kept; the app sees the effective
            self.catalog_limits[(device_id, cap)] = (raw.get("setpoint_min", lo), raw.get("setpoint_max", hi))
            out["setpoint_min"], out["setpoint_max"], _ = self.effective_limits(device_id, cap,
                                                                                raw.get("mode", current.get("mode")))
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
            self._contact_online(device)
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
        if cap == "climate":
            self._climate_pair(change.device_id, state)      # 1098 = b: its mode may have changed
        if cap == "power_meter":
            self._power_seen(change.device_id, state)
        self._note_climate(change.device_id, cap, was_on, state.get("on"))
        if cap == "contact" and state.get("open") and not was_open:
            self._window_opened(change.device_id)
        elif cap == "contact" and was_open and not state.get("open"):
            self._window_closed(change.device_id)
        device["last_seen"] = iso(change.ts)
        self._save_device(device)
        self.emit("device.state", {"device_id": device["device_id"], "capability": cap, "state": state}, corr)

    # ---- rules of P-60 step 5 (D-126) ----------------------------------------------------------------------------
    def _note_climate(self, device_id: str, cap: str, was_on, is_on) -> None:
        """R4: when a split's compressor stops, its minimum pause starts."""
        if cap == "climate" and was_on and not is_on:
            self.compressor_off[device_id] = time.monotonic()
            # D-218: also as a UTC instant in the store, so that a restart does not cut the pause short
            offs = self.store.get_meta("compressor_off", {}) or {}
            offs[device_id] = iso(utcnow())
            self.store.put_meta("compressor_off", offs)

    def compressor_wait(self, device_id: str) -> float:
        """R4: seconds left of the compressor's minimum pause (rule compressor_min_off), 0 when it may start."""
        rule = self.rule("compressor_min_off")
        off = self.compressor_off.get(device_id)
        if not rule["enabled"] or off is None:
            return 0.0
        return max(0.0, rule["params"]["minutes"] * seconds_per_minute() - (time.monotonic() - off))

    def device_limits(self, device_id: str, cap: str) -> tuple:
        """D-174: the device's own limits, from the catalog (DEVICE_LIMITS_FALLBACK when it lists none)."""
        return self.catalog_limits.get((device_id, cap), DEVICE_LIMITS_FALLBACK[cap])

    def frost_limits(self, device_id: str) -> tuple:
        """D-183 point 125: the only limits of the frost protection, the boiler's own (never the manager's). Every place
        that sets or keeps a boiler on the frost protection asks here (E-24: a new apartment, the mode, the commands of
        «casa vuota», a change of the rules)."""
        return self.device_limits(device_id, "heating")

    def rule_range(self, cap: str, mode: str | None) -> tuple | None:
        """1098 = b: the manager's range for a device working in this mode: the boiler and a climate heating the winter
        one (min/max); a climate cooling or dehumidifying (dry: the cold cycle, the warm season) the summer one
        (summer_min/summer_max); a climate only ventilating (fan: its setpoint drives nothing) none, the device's
        limits only."""
        params = self.rule("setpoint_limits")["params"]
        if cap == "heating" or mode == "heat":
            return params["min"], params["max"]
        if mode in ("cool", "dry"):
            return params.get("summer_min", params["min"]), params.get("summer_max", params["max"])
        return None

    def effective_limits(self, device_id: str, cap: str, mode: str | None = None) -> tuple:
        """D-174 (D-183 point 124): (min, max, conflict). «Limiti del setpoint» on = the manager's limits inside the
        device's, for climate and boiler; off = the device's; an empty intersection = the device's, conflict True.
        1098 = b: a climate's of the mode it works in (`mode`, by default its current one; a new climate heats)."""
        lo, hi = self.device_limits(device_id, cap)
        rule = self.rule("setpoint_limits")
        if not rule["enabled"]:
            return lo, hi, False
        if cap == "climate" and mode is None:
            device = getattr(self, "devices", {}).get(device_id)
            mode = (device["capabilities"].get("climate") or {}).get("mode", "heat") if device else "heat"
        rng = self.rule_range(cap, mode)
        if rng is None:
            return lo, hi, False
        mlo, mhi = max(lo, rng[0]), min(hi, rng[1])
        if mlo > mhi:
            return lo, hi, True
        return mlo, mhi, False

    def command_limits(self, device: dict, cap: str, mode: str | None = None) -> tuple:
        """The limits a command is checked against: the state's (the effective ones); the boiler's commands of «casa
        vuota» only the device's (D-183 point 125: the frost protection never follows the manager's limits). 1098 = b:
        a climate command that changes the mode, the new mode's."""
        if cap == "heating" and self._frost_command:
            return self.frost_limits(device["device_id"])
        state = device["capabilities"][cap]
        if cap == "climate" and mode is not None and mode != state.get("mode"):
            return self.effective_limits(device["device_id"], cap, mode)[:2]
        return state["setpoint_min"], state["setpoint_max"]

    def _climate_pair(self, device_id: str, state: dict) -> None:
        """1098 = b: a climate's setpoint_min/setpoint_max follow the mode it works in (a command, the device's own
        report). Only the pair: a setpoint chosen with the remote control is shown as it is, never brought inside."""
        state["setpoint_min"], state["setpoint_max"], _ = self.effective_limits(device_id, "climate", state.get("mode"))

    def _apply_limits(self, correlation_id: str | None = None, emit: bool = False) -> None:
        """D-174: every climate and boiler gets its effective limits and its setpoint inside them; in «casa vuota» a
        boiler a mode set, or one switched off, only inside the device's: its setpoint is the frost protection's (D-183
        point 125; staging, 23 Oct: a new «Demo vuoto» showed 16 °C instead of 8). An empty intersection is one decision
        per episode (D-183 point 124), the episode ends when the limits overlap again."""
        conflicts = set()
        for d in self.devices.values():
            for cap in ("climate", "heating"):
                c = d["capabilities"].get(cap)
                if not c:
                    continue
                lo, hi, conflict = self.effective_limits(d["device_id"], cap)
                key = f"{d['device_id']}:{cap}"
                if conflict:
                    conflicts.add(key)
                    if key not in self.limits_conflicts:
                        self._note_limits_conflict(d, cap, correlation_id)
                frost = cap == "heating" and self.mode == "empty" and (d["device_id"] in self.heating_by_mode
                                                                       or not c.get("on"))
                bound = self.frost_limits(d["device_id"]) if frost else (lo, hi)
                sp = c.get("setpoint")
                fixed = min(max(sp, bound[0]), bound[1]) if isinstance(sp, (int, float)) else sp
                if (c.get("setpoint_min"), c.get("setpoint_max"), sp) != (lo, hi, fixed):
                    if cap == "climate" and c.get("on") and fixed != sp:
                        # 1097 = a: the split keeps its own setpoint, the copy alone is not enough: a command (_push_limits)
                        was = self.limits_push.get(d["device_id"], {}).get("from", sp)
                        self.limits_push[d["device_id"]] = {"from": was, "to": fixed}
                        self.store.put_meta("limits_push", self.limits_push)
                    c["setpoint_min"], c["setpoint_max"], c["setpoint"] = lo, hi, fixed
                    self._save_device(d)
                    if emit:
                        self.emit("device.state", {"device_id": d["device_id"], "capability": cap, "state": c},
                                  correlation_id)
        if conflicts != self.limits_conflicts:
            self.limits_conflicts = conflicts
            self.store.put_meta("limits_conflicts", sorted(conflicts))

    def _note_limits_conflict(self, device: dict, cap: str, correlation_id: str | None) -> None:
        rmin, rmax = self.rule_range(cap, (device["capabilities"].get(cap) or {}).get("mode"))   # 1098 = b: its mode's
        lo, hi = self.device_limits(device["device_id"], cap)
        self.log("rule:setpoint_limits", {"type": "device", "device_id": device["device_id"]}, "setpoint_limits_ignored",
                 f"{fmt_num(rmin)}–{fmt_num(rmax)}", f"{fmt_num(lo)}–{fmt_num(hi)}",
                 f"{device['label']}: i limiti del setpoint ({fmt_num(rmin)}–{fmt_num(rmax)} °C) sono fuori "
                 f"da quelli del dispositivo ({fmt_num(lo)}–{fmt_num(hi)} °C): valgono quelli del dispositivo",
                 "informational", correlation_id or str(uuid.uuid4()))

    def _within_limits(self, device: dict, body: dict) -> tuple[dict, str | None]:
        """R6: a setpoint asked by an automatic path (mode, schedule, assistant, rule) is brought inside the device's
        limits, with a note for the decision; a manual command out of limits stays a 422."""
        params = body.get("params") if isinstance(body, dict) else None
        cap = body.get("capability") if isinstance(body, dict) else None
        state = device["capabilities"].get(cap) if isinstance(cap, str) else None
        if not isinstance(params, dict) or not state or "setpoint" not in params or "setpoint_min" not in state:
            return body, None
        sp, (lo, hi) = params["setpoint"], self.command_limits(device, cap, params.get("mode"))
        if not isinstance(sp, (int, float)) or isinstance(sp, bool) or lo <= sp <= hi:
            return body, None
        fixed, note = self._clamped(device, cap, sp, lo, hi)
        return {**body, "params": {**params, "setpoint": fixed}}, note

    def _mode_change_setpoint(self, device: dict, body: dict) -> tuple[dict, str | None]:
        """1098 = b: a climate command that changes the mode without a setpoint, while the current setpoint is outside
        the new mode's range (heat at 21 to cool with the summer range 22–28): the setpoint brought inside goes with
        it, in the command and in the state, with the note for the decision. Not a 422: nobody chose that setpoint."""
        params = body.get("params") if isinstance(body, dict) else None
        state = device["capabilities"].get("climate")
        if (body.get("capability") != "climate" or not isinstance(params, dict) or not state
                or params.get("mode") not in CLIMATE_MODES or "setpoint" in params):
            return body, None
        sp = state.get("setpoint")
        if not isinstance(sp, (int, float)) or isinstance(sp, bool):
            return body, None
        lo, hi = self.command_limits(device, "climate", params["mode"])
        fixed, note = self._clamped(device, "climate", sp, lo, hi)
        if note is None:
            return body, None
        return {**body, "params": {**params, "setpoint": fixed}}, note

    def _clamped(self, device: dict, cap: str, target, lo, hi) -> tuple:
        """(the setpoint inside lo–hi, the note for the decision or None): R6's note; when the device's own limits cut
        it, it says so with them (1097 = a: «Limiti del setpoint» 16–26, a split 16–24 cools to 24, not 25)."""
        fixed = min(max(target, lo), hi)
        if fixed == target:
            return target, None
        dlo, dhi = self.device_limits(device["device_id"], cap)
        if (target > hi and hi == dhi) or (target < lo and lo == dlo):
            where = f"limiti del dispositivo {fmt_num(dlo)}–{fmt_num(dhi)}"
        else:
            where = f"limiti {fmt_num(lo)}–{fmt_num(hi)}"
        return fixed, f"setpoint {fmt_num(target)} °C riportato a {fmt_num(fixed)} °C ({where})"

    def _push_limits(self, correlation_id: str | None = None) -> None:
        """1097 = a: a climate on whose setpoint narrower limits cut gets a command to the new setpoint, as the system's
        (it does not take the climate away from comfort). It waits, and tries again at every regulation's minute and
        after a restart, while the devices cannot be reached, the climate is offline, a command of its own is running
        (a turn_off in flight: the compressor's pause comes after it) or a window is open with its rule active (the
        rule turns it off). Off, or commanded by anyone meanwhile (create_command): nothing more to send."""
        if not self.limits_push:
            return
        for device_id, push in list(self.limits_push.items()):
            device = self.devices.get(device_id)
            c = device["capabilities"].get("climate") if device else None
            if not c or not c.get("on") or c.get("setpoint") != push["to"]:
                self.limits_push.pop(device_id, None)
                continue
            busy = any(x["device_id"] == device_id and x["status"] not in FINAL for x in self.commands.values())
            if (not self.connector_up() or not device["online"] or busy or device_id in self.window_off
                    or any(r[0] == device_id for r in self.inflight)
                    or (self.window_open() and self.window_rule_active())):
                continue
            self.limits_push.pop(device_id, None)
            self._auto_climate = True
            try:
                self.create_command(device_id, {"capability": "climate", "action": "set_climate",
                                                "params": {"setpoint": push["to"]}},
                                    "system:engine", correlation_id or str(uuid.uuid4()), decision_actor="system",
                                    reasoning=f"Limiti del setpoint cambiati: {device['label']} portato da "
                                              f"{fmt_num(push['from'])} °C a {fmt_num(push['to'])} °C")
            except MockError as exc:
                logs.warn("limits command not created", apartment_id=self.apartment_id, device_id=device_id,
                          error=exc.error)
            finally:
                self._auto_climate = False
        self.store.put_meta("limits_push", self.limits_push)

    def _booking_rule_switched(self, rule_id: str, correlation_id: str) -> None:
        """P-90 S11: «Pre-arrivo» or «Risparmio al check-out» switched off cancels the planned actions of the bookings
        of that kind; on again plans them for the bookings still to come (not cancelled, the guests not in or not gone,
        the time ahead). One decision each time, when something changed."""
        rule, kind = self.rule(rule_id), BOOKING_RULES[rule_id]
        now, changed = utcnow(), []
        if not rule["enabled"]:
            for item in self.schedule.values():
                if item["kind"] == kind and item["source"] == "booking" and item["status"] == "planned":
                    item["status"] = "cancelled"
                    self._save_schedule(item)
                    changed.append(item)
            verb = "spenta", "annullata", "annullate"
        else:
            for b in self.bookings.values():
                if b["cancelled"] or any(s["booking_id"] == b["booking_id"] and s["kind"] == kind
                                         and s["status"] in ("planned", "done") for s in self.schedule.values()):
                    continue
                if kind == "prearrival":
                    run_at, mode, gone = b["checkin"] - timedelta(hours=rule["params"]["hours_before"]), "comfort", \
                        b["checked_in"] or b["checked_out"]
                else:
                    run_at, mode, gone = b["checkout"] + timedelta(minutes=rule["params"]["minutes_after"]), "empty", \
                        b["checked_out"]
                if run_at > now and not gone:
                    changed.append(self.add_schedule(run_at, {"type": "apartment_mode", "mode": mode}, kind, "booking",
                                                     b["booking_id"]))
            verb = "riaccesa", "riprogrammata", "riprogrammate"
        if changed:
            n = len(changed)
            self.log(f"rule:{rule_id}", {"type": "schedule"}, "schedule_cancel" if not rule["enabled"] else "schedule_create",
                     None, str(n), f"Regola «{rule['label']}» {verb[0]}: {n} {'azione' if n == 1 else 'azioni'} delle "
                     f"prenotazioni {verb[1] if n == 1 else verb[2]}", "applied", correlation_id)
            self.apartment_changed(correlation_id)

    def _offline_rule_switched(self) -> None:
        """P-90 S17: off, the waits running give nothing; on again, the devices already offline wait again (as D30 does
        for the windows)."""
        self.offline_watch.clear()
        if self.rule("offline_alert")["enabled"]:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return                                       # no loop: the start arms them (D12)
            for device_id, d in self.devices.items():
                if not d["online"]:
                    self._watch_offline(device_id, False)

    def _modes_outside_check(self, correlation_id: str | None = None) -> None:
        """1097 = a: a rule saved before the check (first values 24 and 25) with the modes' temperatures outside its
        limits, while on: one decision per episode, also across restarts; not refused nor corrected on its own. The
        episode ends when the rule is corrected or switched off."""
        rule = self.rule("setpoint_limits")
        sl = rule["params"]
        winter, summer = (sl["min"], sl["max"]), (sl.get("summer_min", sl["min"]), sl.get("summer_max", sl["max"]))
        parts = [f"{name} {fmt_num(sl[key])} °C ({season} {fmt_num(rng[0])}–{fmt_num(rng[1])} °C)"
                 for key, name, season, rng in (("eco_celsius", "eco", "inverno", winter),
                                                ("comfort_celsius", "comfort", "inverno", winter),
                                                ("comfort_cool_celsius", "raffrescamento", "estate", summer))
                 if key in sl and not rng[0] <= sl[key] <= rng[1]]
        now = bool(rule["enabled"] and parts)
        if now and not self.modes_outside:
            self.log("rule:setpoint_limits", {"type": "rules"}, "limits_modes_outside", None, ", ".join(parts),
                     f"Temperature delle modalità fuori dai limiti del setpoint: {', '.join(parts)}. Clima e caldaia "
                     f"restano dentro i limiti: correggi la regola «Limiti del setpoint»", "informational",
                     correlation_id or str(uuid.uuid4()))
        if now != self.modes_outside:
            self.modes_outside = now
            self.store.put_meta("modes_outside", now)

    def _offline_at_start(self) -> None:
        """D12 (P-83): a device already offline at the start (unplugged while the engine was down, or never connected)
        is watched as if it had just gone offline (one offline_alert decision after the rule's minutes, the BFF's
        push), and the apps hear it at once (device.online false, with the last_seen known)."""
        corr = str(uuid.uuid4())
        for device in self.devices.values():
            if device["online"]:
                continue
            self._watch_offline(device["device_id"], False)
            self.emit("device.online", {"device_id": device["device_id"], "online": False,
                                        "last_seen": device["last_seen"]}, corr)

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
            if (self.offline_watch.get(device_id) is episode and device and not device["online"]
                    and self.rule("offline_alert")["enabled"]):          # P-90 S17: switched off meanwhile, nothing
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
        """The catalog's links, checked at start (connector-v2.md §2.2, P-60 step 7b): a link with an unknown key, to a
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
                if "on" in info.capabilities["heating"]:
                    self.relay[info.device_id] = bool(info.capabilities["heating"]["on"])
                else:                                # P7a-1 (P-83): not read (a failed snapshot): unknown, not open
                    self.relay.pop(info.device_id, None)
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
        never suspended). Without a usable sensor (D-164) the relay follows only a person's intention, as a plain
        switch; a mode's intention and the frost protection keep it off: nothing heats by itself unregulated."""
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
            return enabled and device["device_id"] not in self.heating_by_mode, None, setpoint, frost_only
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
        self._mode_pending_send()                            # D16: what the mode could not send before
        self._push_limits()                                  # 1097 = a: and what narrower limits could not send
        self._remote_off_check()                             # P-90 S1: a split switched off by its remote
        self._restore_after_window()                         # D-218 point 1: first, so the boiler's relay follows now
        self._keep_window_off()                              # D03: and what is still on with the window open goes off
        in_force = self.window_in_force()
        for device in self.devices.values():
            if "heating" not in device["capabilities"] or not device["online"]:
                continue
            device_id = device["device_id"]
            _, _, problem = self._sensor(device)
            episode = self._sensor_episode(device, problem)
            if episode != self.thermostat_issue.get(device_id):
                self._sensor_issue(device, problem, episode)
            if device_id in self.relay_busy or any(r[0] == device_id for r in self.inflight):
                continue
            want, temperature, setpoint, frost = self.thermostat(device)
            if want and in_force and not frost:
                want = False                                 # D03: never closed by the thermostat with the window open
            if device_id in self.relay and want == self.relay[device_id]:
                continue                                     # P7a-1: an unknown relay is commanded either way
            since = time.monotonic() - self.relay_switched.get(device_id, -1e18)
            if since < self.setting("THERMOSTAT_MIN_SWITCH_MINUTES") * seconds_per_minute():
                continue
            self.relay_busy.add(device_id)
            self.spawn(self._switch_relay(device, want, temperature, setpoint, frost))
        self._regulate_climates()

    def _mode_heating_setpoint(self, device: dict) -> float:
        """The boiler's setpoint of the current mode, as mode_commands gives it."""
        sl = self.rule("setpoint_limits")["params"]
        h = device["capabilities"]["heating"]
        target = {"comfort": sl["comfort_celsius"], "eco": sl["eco_celsius"],
                  "empty": self.rule("frost_protection")["params"]["celsius"]}[self.mode]
        lo, hi = self.frost_limits(device["device_id"]) if self.mode == "empty" else (h["setpoint_min"], h["setpoint_max"])
        return min(max(target, lo), hi)

    def _restore_after_window(self) -> None:
        """D-218 point 1 (answer 811): what the window rule turned off comes back when no window is open any more and they
        have been closed for a regulation's minute (a window that bangs in the wind sends nothing). A boiler or a climate
        of the mode goes back to the mode: the boiler's intention again, its relay switched by the thermostat (at most one
        switch every THERMOSTAT_MIN_SWITCH_MINUTES); the climate by the comfort regulation, once its pause and the
        compressor's are over. One a person had turned on goes back as it was. A command meanwhile took it out of here
        (create_command); during a hold nothing comes back, the hold wins, and the return waits for its end (P-90 S2:
        before, the hold cleared it, and the boiler stayed off for the rest of the stay). Each return is a decision."""
        if not self.window_off:
            return
        if self.hold:
            return                                           # S2: kept, it comes back after the hold
        if self.window_open() and self.window_rule_active():
            return
        if time.monotonic() - self.windows_closed_at < seconds_per_minute():
            return
        wait = self.setting("THERMOSTAT_MIN_SWITCH_MINUTES") * seconds_per_minute()
        for device_id, entry in list(self.window_off.items()):
            device = self.devices.get(device_id)
            cap = entry["cap"]
            if device is None or cap not in device["capabilities"]:
                self.window_off.pop(device_id, None)
                continue
            if not device["online"] or any(r[0] == device_id for r in self.inflight):
                continue                                     # later, when it can be reached
            state = device["capabilities"][cap]
            if state.get("on") and not entry.get("mode_blocked"):
                self.window_off.pop(device_id, None)         # already back on (by itself, or the mode)
                continue
            by_mode = device_id in (self.heating_by_mode if cap == "heating" else self.climate_by_mode)
            if not by_mode and entry["by_mode"]:
                self.window_off.pop(device_id, None)         # the mode changed meanwhile and keeps it off
                continue
            if cap == "climate" and (self.compressor_wait(device_id) > 0
                                     or time.monotonic() - self.climate_switched.get(device_id, -1e18) < wait):
                continue                                     # the compressor's pause, the regulation's minutes
            self.window_off.pop(device_id, None)
            words = f"riacceso ({self.mode})" if by_mode else "riacceso come prima"
            reasoning = f"Finestra chiusa: {device['label']} {words}"
            corr = str(uuid.uuid4())
            if cap == "heating":
                setpoint = self._mode_heating_setpoint(device) if by_mode else entry["state"].get("setpoint", state.get("setpoint"))
                state.update(on=True, setpoint=setpoint)    # the intention: the thermostat switches the relay
                self._save_device(device)
                self.emit("device.state", {"device_id": device_id, "capability": cap, "state": state}, corr)
            else:
                params = (self._comfort_climate(device, state) if by_mode
                          else {k: v for k, v in entry["state"].items() if k in ("mode", "setpoint", "fan")})
                if params is None:
                    reasoning = f"Finestra chiusa: {device['label']} torna alla regolazione ({self.mode})"
                else:
                    self.climate_switched[device_id] = time.monotonic()
                    self._auto_climate = True
                    try:
                        self.create_command(device_id, {"capability": "climate", "action": "set_climate",
                                                        "params": {"on": True, **params}},
                                            "system:engine", corr, decision_actor="rule:window_open_off", reasoning=reasoning)
                    except MockError:
                        pass
                    finally:
                        self._auto_climate = False
            self.log("rule:window_open_off", {"type": "device", "device_id": device_id}, "window_restore", "off", "on",
                     reasoning, "applied", corr)
        self.store.put_meta("window_off", self.window_off)

    def _comfort_climate(self, device: dict, c: dict) -> dict | None:
        """The comfort regulation's command for a climate (mode and setpoint), None when its room needs nothing."""
        room = self.room_temperature(device)
        if room is None:
            return None
        sl = self.rule("setpoint_limits")["params"]
        heat, cool = sl["comfort_celsius"], sl["comfort_cool_celsius"]
        margin = self.setting("THERMOSTAT_HYSTERESIS_C")
        if room < heat - margin:
            climate_mode, target = "heat", heat
        elif room > cool + margin:
            climate_mode, target = "cool", cool
        else:
            return None
        # the mode's temperature as it is: create_command brings it inside the limits with the note (R6, 1097 = a)
        return {"mode": climate_mode, "setpoint": target}

    def _regulate_climates(self) -> None:
        """D-169: in comfort, every "minute", each climate the mode set and no person changed since follows its room's
        sensor: heating to comfort_celsius below it minus the hysteresis, cooling to comfort_cool_celsius above it plus
        the hysteresis, left as it is in between; at most one automatic change every THERMOSTAT_MIN_SWITCH_MINUTES (the
        compressor's pause applies as to any command). Not during a hold (comfort rules suspended) nor with a window
        open (its rule is stronger). Without a sensor: nothing, one decision per episode. Each change is a decision."""
        if self.mode != "comfort" or self.hold:
            return
        sl = self.rule("setpoint_limits")["params"]
        heat, cool = sl["comfort_celsius"], sl["comfort_cool_celsius"]
        margin = self.setting("THERMOSTAT_HYSTERESIS_C")
        wait = self.setting("THERMOSTAT_MIN_SWITCH_MINUTES") * seconds_per_minute()
        for device_id in sorted(self.climate_by_mode):
            device = self.devices.get(device_id)
            if not device or not device["online"] or "climate" not in device["capabilities"]:
                continue
            if device_id in self.window_off:
                continue                                    # D-218: its return after the window comes first
            room = self.room_temperature(device)
            if room is None:
                self._note_no_sensor(device, None)
                continue
            self.no_sensor_noted.discard(device_id)
            if any(r[0] == device_id for r in self.inflight):
                continue
            if time.monotonic() - self.climate_switched.get(device_id, -1e18) < wait:
                continue
            if self.window_open() and self.window_rule_active():
                continue
            c = device["capabilities"]["climate"]
            if room < heat - margin and not (c["on"] and c["mode"] == "heat"):
                climate_mode, target, words = "heat", heat, f"sotto {fmt_num(heat)} °C: scalda"
            elif room > cool + margin and not (c["on"] and c["mode"] == "cool"):
                climate_mode, target, words = "cool", cool, f"sopra {fmt_num(cool)} °C: raffresca"
            else:
                continue
            lo, hi, _ = self.effective_limits(device_id, "climate", climate_mode)   # 1098 = b: the new mode's
            setpoint, note = self._clamped(device, "climate", target, lo, hi)
            if note:
                words += f"; {note}"                        # 1097 = a: the device's limits cut it
            self.climate_switched[device_id] = time.monotonic()
            self._auto_climate = True
            try:
                self.create_command(device_id, {"capability": "climate", "action": "set_climate",
                                                "params": {"on": True, "mode": climate_mode, "setpoint": setpoint}},
                                    "system:engine", str(uuid.uuid4()), decision_actor="system",
                                    reasoning=f"{device['label']}: {fmt_num(room)} °C, {words}")
            except MockError:
                pass
            finally:
                self._auto_climate = False

    def _sensor_episode(self, device: dict, problem: str | None) -> str | None:
        """D-164: None (the sensor answers), «manuale» (a person's intention, followed unregulated), «antigelo» (in
        «casa vuota» with the frost protection on: it cannot act), «regolazione» (a mode's intention: kept off)."""
        if not problem:
            return None
        heating = device["capabilities"]["heating"]
        if heating.get("on") and device["device_id"] not in self.heating_by_mode:
            return "manuale"
        if self.mode == "empty" and self.rule("frost_protection")["enabled"]:
            return "antigelo"
        return "regolazione"

    def _sensor_issue(self, device: dict, problem: str | None, episode: str | None) -> None:
        device_id = device["device_id"]
        action = "thermostat_sensor"
        if episode is None:
            self.thermostat_issue.pop(device_id, None)
            reasoning = f"{device['label']}: sensore di nuovo disponibile, regolazione ripresa"
        else:
            self.thermostat_issue[device_id] = episode
            if episode == "antigelo":           # the BFF turns it into a push (category «Dispositivi e istanza offline»)
                action = "frost_inactive"
                reasoning = f"{device['label']}: sensore di temperatura mancante, antigelo non attivo ({problem})"
            elif episode == "regolazione":
                reasoning = (f"{device['label']}: sensore di temperatura mancante, regolazione automatica disattivata "
                             f"({problem})")
            else:                               # P-90 S18: its own action, the BFF's push «caldaia senza regolazione»
                action = "heating_unregulated"
                reasoning = f"{device['label']}: {problem}; segue il comando manuale senza regolazione"
        self.log("system", {"type": "device", "device_id": device_id}, action, None,
                 "problema" if episode else "ok", reasoning, "informational", str(uuid.uuid4()))

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
            try:
                q.put_nowait(env)
            except asyncio.QueueFull:                # the reader reconnects and asks again from its last event
                self.subscribers.discard(q)
                while not q.empty():
                    q.get_nowait()
                q.put_nowait(QUEUE_FULL)
                logs.warn("stream closed: too many events waiting", apartment_id=self.apartment_id, limit=q.maxsize)
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

    def room_temperature(self, device: dict) -> float | None:
        """D-162: the temperature of the room of a climate, from a sensor with «temperature» in the same room, online;
        None without one (the explicit link sensor_device_id is the boiler's, connector-v2.md §2.2)."""
        for d in sorted(self.devices.values(), key=lambda x: x["device_id"]):
            t = d["capabilities"].get("temperature")
            if (d["room_id"] == device["room_id"] and d["device_id"] != device["device_id"] and t and d["online"]
                    and isinstance(t.get("celsius"), (int, float))):
                return float(t["celsius"])
        return None

    def mode_commands(self, mode: str, correlation_id: str | None = None,
                      include_offline: bool = False) -> list[tuple[str, dict]]:
        """The commands of a mode (D-161, D-162). Boiler: comfort_celsius, eco_celsius, or the frost protection's in
        «casa vuota». Climate: off in eco and «casa vuota»; in comfort by the room's sensor: heating to
        comfort_celsius under it, cooling to comfort_cool_celsius over that, nothing in between; without a sensor no
        automatic command (only manual ones) and one decision per episode, which ends when the apartment leaves comfort
        or the sensor answers again."""
        out = []
        sl = self.rule("setpoint_limits")["params"]
        frost = self.rule("frost_protection")["params"]["celsius"]
        if mode != "comfort":
            self.no_sensor_noted.clear()
        for d in self.devices.values():
            caps = d["capabilities"]
            if not d["online"] and not include_offline:
                if self._schedule_run and self._mode_would_command(d, mode):
                    # D-219 (2): a device of a scheduled action that is offline at its time is a command not done
                    self._schedule_refused(self._schedule_run, d["device_id"], "dispositivo offline, non comandato")
                continue
            if "climate" in caps:
                c = caps["climate"]
                if mode != "comfort":
                    out.append((d["device_id"], {"capability": "climate", "action": "turn_off"}))
                else:
                    room = self.room_temperature(d)
                    if room is None:
                        self._note_no_sensor(d, correlation_id)
                    else:
                        self.no_sensor_noted.discard(d["device_id"])
                        heat, cool = sl["comfort_celsius"], sl["comfort_cool_celsius"]
                        if room < heat or room > cool:
                            climate_mode, target = ("heat", heat) if room < heat else ("cool", cool)
                            lo, hi, _ = self.effective_limits(d["device_id"], "climate", climate_mode)   # 1098 = b
                            sp, note = self._clamped(d, "climate", target, lo, hi)
                            self._mode_note(d["device_id"], note)
                            out.append((d["device_id"], {"capability": "climate", "action": "set_climate",
                                                         "params": {"on": True, "mode": climate_mode, "setpoint": sp}}))
            if "heating" in caps:
                h = caps["heating"]
                target = {"comfort": sl["comfort_celsius"], "eco": sl["eco_celsius"], "empty": frost}[mode]
                lo, hi = (self.frost_limits(d["device_id"]) if mode == "empty"     # D-183 point 125
                          else (h["setpoint_min"], h["setpoint_max"]))
                sp, note = self._clamped(d, "heating", target, lo, hi)
                self._mode_note(d["device_id"], note)
                out.append((d["device_id"], {"capability": "heating", "action": "set_heating",
                                             "params": {"on": True, "setpoint": sp}}))
        return out

    def _mode_note(self, device_id: str, note: str | None) -> None:
        """The note of a mode's setpoint cut by the limits (1097 = a), for set_mode's decision of that command."""
        if note:
            self.mode_notes[device_id] = note
        else:
            self.mode_notes.pop(device_id, None)

    def _mode_would_command(self, device: dict, mode: str) -> bool:
        """Whether the mode would send this device a command if it were online (the same choice as mode_commands,
        without its decisions): a boiler always; a climate off outside comfort, in comfort only with its room's
        temperature outside the comfort band."""
        caps = device["capabilities"]
        if "heating" in caps:
            return True
        if "climate" not in caps:
            return False
        if mode != "comfort":
            return True
        room = self.room_temperature(device)
        sl = self.rule("setpoint_limits")["params"]
        return room is not None and (room < sl["comfort_celsius"] or room > sl["comfort_cool_celsius"])

    def _mode_wait(self, device_id: str, body: dict, mode: str, correlation_id: str) -> None:
        """D16 (P-83): a device the mode could not reach (offline, or the connector down). The boiler's intention is the
        engine's: it takes the mode's now and the relay follows when the boiler is back (regulate). A climate's command
        waits (mode_pending) and goes when the climate is reachable again (_mode_pending_send). A decision says it."""
        device = self.devices[device_id]
        if body["capability"] == "heating":
            heating = device["capabilities"]["heating"]
            heating.update(on=bool(body["params"].get("on")), setpoint=body["params"].get("setpoint", heating.get("setpoint")))
            self._heating_set_by(device_id, mode=True)
            self._save_device(device)
            self.emit("device.state", {"device_id": device_id, "capability": "heating", "state": heating}, correlation_id)
            what = "impostata ora, il relè la segue quando torna raggiungibile"
        else:
            self.mode_pending[device_id] = {"body": copy.deepcopy(body), "mode": mode, "at": time.monotonic()}
            what = "il comando parte quando torna raggiungibile"
        self.log("system", {"type": "device", "device_id": device_id}, "mode_device_pending", None, mode,
                 f"{device['label']} non raggiungibile durante il passaggio a {mode}: {what}", "informational",
                 correlation_id)

    def _mode_command_failed(self, cmd: dict) -> None:
        """P-90 S3: a command of the current mode created and then failed or timed out (D16 covered only a device
        unreachable before its command). The boiler takes the mode's intention anyway, an engine's value its relay
        follows (regulate); a climate's command waits and goes again once (_mode_pending_send). Not when the mode
        changed or a person commanded the device meanwhile."""
        entry = self.mode_cmds.pop(cmd["command_id"], None)
        if (entry is None or entry["retried"] or entry["mode"] != self.mode
                or self.commanded_at.get(cmd["device_id"], float("-inf")) > entry["at"]
                or cmd["device_id"] not in self.devices):
            return
        self._mode_wait(cmd["device_id"], entry["body"], entry["mode"], cmd["correlation_id"])
        self.store.put_meta("mode_pending", {k: {"body": v["body"], "mode": v["mode"]} for k, v in self.mode_pending.items()})

    def _mode_pending_send(self) -> None:
        """D16: the waiting commands of the mode, for the devices reachable again; dropped when the mode changed or
        someone commanded the device meanwhile (D13's commanded_at)."""
        if not self.mode_pending or not self.connector_up():
            return
        for device_id, wait in list(self.mode_pending.items()):
            device = self.devices.get(device_id)
            if device is None or wait["mode"] != self.mode or self.commanded_at.get(device_id, float("-inf")) > wait["at"]:
                self.mode_pending.pop(device_id, None)
                continue
            if not device["online"]:
                continue
            self.mode_pending.pop(device_id, None)
            self._auto_climate = True
            try:
                cmd = self.create_command(device_id, wait["body"], "system:engine", str(uuid.uuid4()),
                                          decision_actor="system",
                                          reasoning=f"Modalità {self.mode}: {device['label']} di nuovo raggiungibile")
                if cmd:                                      # S3: a retry that fails is not tried again
                    self.mode_cmds[cmd["command_id"]] = {"mode": self.mode, "body": copy.deepcopy(wait["body"]),
                                                         "at": time.monotonic(), "retried": True}
            except MockError as exc:
                logs.warn("waiting mode command not sent", apartment_id=self.apartment_id, device_id=device_id,
                          error=exc.error)
            finally:
                self._auto_climate = False
        self.store.put_meta("mode_pending", {k: {"body": v["body"], "mode": v["mode"]} for k, v in self.mode_pending.items()})

    def _heating_set_by(self, device_id: str, mode: bool) -> None:
        (self.heating_by_mode.add if mode else self.heating_by_mode.discard)(device_id)
        self.store.put_meta("heating_by_mode", sorted(self.heating_by_mode))

    def _note_no_sensor(self, device: dict, correlation_id: str | None) -> None:
        """D-162: one decision per episode for a climate without a temperature sensor in its room."""
        if device["device_id"] in self.no_sensor_noted:
            return
        self.no_sensor_noted.add(device["device_id"])
        self.log("system", {"type": "device", "device_id": device["device_id"]}, "auto_regulation_off", None, None,
                 f"{device['label']}: sensore di temperatura mancante, regolazione automatica disattivata",
                 "informational", correlation_id or str(uuid.uuid4()))

    def set_mode(self, mode: str, actor: str, correlation_id: str, reasoning: str, decision_actor: str | None = None,
                 by_hand: bool = False) -> list[str]:
        """by_hand: a person chose it now (the app, the assistant, an approval decided by hand); during a hold it
        becomes the hold's mode (D09). The automatic paths leave it False."""
        if mode not in MODES:
            raise bad_request("Modalità non valida")
        command_ids = []
        self._auto_climate = True
        self._frost_command = mode == "empty"
        self._mode_in_progress = mode
        self.mode_cmds = {}                              # S3: the previous mode's commands that fail are not repeated
        try:
            self.mode_pending = {}                       # D16: a new mode replaces what the previous one left waiting
            sent: set[str] = set()
            for device_id, body in self.mode_commands(mode, correlation_id):
                try:
                    note = self.mode_notes.get(device_id)
                    cmd = self.create_command(device_id, body, actor, correlation_id, decision_actor=decision_actor,
                                              reasoning=f"Modalità {mode}" + (f"; {note}" if note else ""))
                    if cmd:
                        command_ids.append(cmd["command_id"])
                        self.mode_cmds[cmd["command_id"]] = {"mode": mode, "body": copy.deepcopy(body),
                                                             "at": time.monotonic(), "retried": False}
                    sent.add(device_id)
                except MockError as exc:
                    if self._schedule_run:                     # D-219 (2): a command of a scheduled action not sent
                        self._schedule_refused(self._schedule_run, device_id, exc.message)
                    continue
                if body["capability"] == "heating":
                    self._heating_set_by(device_id, mode=True)        # D-164: a mode's intention, never unregulated
            for device_id, body in self.mode_commands(mode, correlation_id, include_offline=True):
                if device_id not in sent:
                    self._mode_wait(device_id, body, mode, correlation_id)
        finally:
            self._auto_climate = False
            self._frost_command = False
            self._mode_in_progress = None
        if mode != "empty":
            self._close_empty_power_requests(correlation_id)      # P-90 S12
        # D-169: in comfort every climate is the regulation's until a person changes it; in eco and «casa vuota» none
        self.climate_by_mode = ({d["device_id"] for d in self.devices.values() if "climate" in d["capabilities"]}
                                if mode == "comfort" else set())
        self.store.put_meta("climate_by_mode", sorted(self.climate_by_mode))
        self.store.put_meta("mode_pending", {k: {"body": v["body"], "mode": v["mode"]} for k, v in self.mode_pending.items()})
        old = self.mode
        self.mode = mode
        self._save_apartment()
        self.log(decision_actor or actor_of(actor), {"type": "apartment"}, "set_mode", old, mode, reasoning,
                 "applied", correlation_id)
        if by_hand and self.hold and self.hold.get("mode") != mode:
            # D09 (P-83, answer 1085 = a): a mode chosen by a person during a hold becomes the hold's mode; the hold
            # goes on to its end with the rules suspended, and at its end the new mode stays
            before = self.hold.get("mode")
            self.hold["mode"] = mode
            self._save_apartment()
            until = parse_dt(self.hold["until"]).astimezone(ZoneInfo(self.timezone)).strftime("%H:%M")
            name = {"empty": "casa vuota"}.get(mode, mode)
            self.log(decision_actor or actor_of(actor), {"type": "apartment"}, "hold", before, f"{mode} fino alle {until}",
                     f"Modalità {name} scelta a mano: la forzatura continua in {name} fino alle {until}", "applied",
                     correlation_id)
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
            lo, hi = self.command_limits(device, cap, params.get("mode"))      # 1098 = b: the new mode's range
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
        """An open window; P-90 S6 (answer 1102 = a): a contact offline counts as closed (its last «open» may be days
        old, a battery or a bridge unplugged), with a decision when it goes silent while open (_contact_online)."""
        for d in self.devices.values():
            c = d["capabilities"].get("contact")
            if c and c["open"] and d["online"]:
                return d
        return None

    def window_rule_active(self) -> bool:
        return self.rule("window_open_off")["enabled"] and self.hold is None

    def window_in_force(self) -> dict | None:
        """D03 (P-83): an open window whose rule's minutes ran out, with the rule active (no hold): what it turned off
        must stay off, not only be turned off once."""
        if not self.window_rule_active():
            return None
        for window_id in sorted(self.window_fired):
            d = self.devices.get(window_id)
            contact = d["capabilities"].get("contact") if d else None
            if contact and contact.get("open") and d["online"]:         # P-90 S6: offline = closed
                return d
        return None

    def _keep_window_off(self) -> None:
        """D03 (P-83): once a regulation's minute, while a window is in force, every climate and boiler still on and
        reachable is turned off again: one offline when the minutes ran out, one whose turn_off failed or was not
        confirmed. Never twice at once (a command of its still running), at most once a minute (the regulation)."""
        window = self.window_in_force()
        if window is None:
            return
        minutes = self.rule("window_open_off")["params"]["minutes"]
        busy = {c["device_id"] for c in self.commands.values() if c["status"] not in FINAL}
        self._window_turn_off(window["device_id"], f"{window['label']} aperta da oltre {fmt_num(minutes)} minuti",
                              skip=busy | {r[0] for r in self.inflight} | set(self.relay_busy))

    def create_command(self, device_id: str, body: dict, actor: str, correlation_id: str,
                       decision_actor: str | None = None, reasoning: str | None = None) -> dict | None:
        """A command, or None when an automatic one waits for the compressor's pause (R4) and starts after it."""
        device = self.get_device(device_id)
        if self.limits_push.pop(device_id, None) is not None:   # 1097 = a: any command replaces the one of the limits
            self.store.put_meta("limits_push", self.limits_push)
        self.remote_low.pop(device_id, None)                    # P-90 S1: a command, a new situation
        if not self._window_command and not self._auto_climate:
            self.commanded_at[device_id] = time.monotonic()   # D13: a deferred automatic start must not undo it
        if not self._window_command and not self._auto_climate and self.window_off.pop(device_id, None) is not None:
            self.store.put_meta("window_off", self.window_off)  # D-218: commanded meanwhile, it stays as it is left
        if body.get("capability") == "heating" and device_id in self.heating_by_mode and not self._window_command:
            self._heating_set_by(device_id, mode=False)       # D-164: a person's (or a scheduled) command
        if body.get("capability") == "climate" and device_id in self.climate_by_mode and not self._auto_climate \
                and not self._window_command:
            self.climate_by_mode.discard(device_id)          # D-169: never against a person, until the next mode
            self.store.put_meta("climate_by_mode", sorted(self.climate_by_mode))
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
        body, note = self._mode_change_setpoint(device, body)
        if note:                                             # 1098 = b: also a person's, nobody chose that setpoint
            default = "Comando manuale dall'app" if manual else "Comando automatico"
            reasoning = f"{reasoning or default}; {note}"
        cap, action, params = self.validate_command(device, body)
        turning_off = cap == "climate" and any(
            c["device_id"] == device_id and c["status"] not in FINAL and c["capability"] == cap
            and not self.target_state(device, cap, c["action"], c["params"]).get("on", True)
            for c in self.commands.values())
        if cap == "climate" and not manual and who != "assistant" \
                and self.target_state(device, cap, action, params)["on"] \
                and (not device["capabilities"][cap]["on"] or turning_off):
            wait = self.compressor_wait(device_id)
            if turning_off:                                  # D11: its pause starts when that turn_off is over
                rule = self.rule("compressor_min_off")
                wait = rule["params"]["minutes"] * seconds_per_minute() if rule["enabled"] else 0.0
            if wait > 0:                                     # R4: an automatic start waits for the pause
                self.log("rule:compressor_min_off", {"type": "device", "device_id": device_id}, action, "off", "on",
                         f"{reasoning or 'Accensione automatica'}: rimandata di {int(wait) + 1} s per la pausa minima "
                         f"del compressore", "informational", correlation_id)

                # the start after the pause is the same automatic command: of the mode or of the regulation as it was
                # (before, it counted as a person's and took the climate away from comfort, D-169), of the scheduled
                # action it belongs to (D-219 (2))
                auto, frost, window_cmd, sid = (self._auto_climate, self._frost_command, self._window_command,
                                                self._schedule_run)
                if sid:
                    self._schedule_wait(sid, device_id)
                snap = self._start_snapshot(device_id)

                async def later():
                    await asyncio.sleep(wait)
                    if why := self._start_not_wanted(device_id, snap):   # D13: the situation it was made for is gone
                        self._start_dropped(device_id, why, correlation_id)
                        if sid:
                            self._schedule_refused(sid, device_id, f"non eseguita: {why}")
                            self._schedule_wait(sid, device_id, done=True)
                        return
                    saved = (self._auto_climate, self._frost_command, self._window_command, self._schedule_run)
                    self._auto_climate, self._frost_command, self._window_command, self._schedule_run = \
                        auto, frost, window_cmd, sid
                    try:
                        cmd = self.create_command(device_id, body, actor, correlation_id, decision_actor, reasoning)
                        if sid and cmd:
                            self._schedule_link(sid, cmd["command_id"])
                    except MockError as exc:
                        logs.warn("deferred command not created", apartment_id=self.apartment_id, device_id=device_id,
                                  error=exc.error)
                        if sid:
                            self._schedule_refused(sid, device_id, exc.message)
                    finally:
                        self._auto_climate, self._frost_command, self._window_command, self._schedule_run = saved
                        if sid:
                            self._schedule_wait(sid, device_id, done=True)
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
        if cap == "climate":
            self._climate_pair(device["device_id"], merged)  # 1098 = b: the pair of the new mode
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
        try:
            await self._execute_command(cmd, decision_actor, reasoning)
        finally:
            # D-219 (2): the last command of a scheduled action judges it (an interrupted one at the restart)
            if (sid := self.command_schedule.get(cmd["command_id"])) and cmd["status"] in FINAL:
                self._schedule_check(sid)

    def _start_snapshot(self, device_id: str) -> dict:
        """D13 (P-83): what an automatic start put off for the compressor's pause was made for."""
        if self._mode_in_progress is not None:            # a mode's own command: made before the mode is recorded
            return {"mode": self._mode_in_progress, "hold": (self.hold or {}).get("until"),
                    "by_mode": self._mode_in_progress == "comfort", "at": time.monotonic()}
        return {"mode": self.mode, "hold": (self.hold or {}).get("until"), "by_mode": device_id in self.climate_by_mode,
                "at": time.monotonic()}

    def _start_not_wanted(self, device_id: str, snap: dict) -> str | None:
        """D13: why a start put off is no longer wanted when the pause ends, or None."""
        if self.mode != snap["mode"]:
            return f"la modalità è cambiata ({self.mode})"
        if self.hold and self.hold.get("until") != snap["hold"] and self.hold.get("mode") != snap["mode"]:
            return f"è iniziata una forzatura in {self.hold['mode']}"
        if snap["by_mode"] and device_id not in self.climate_by_mode:
            return "il climatizzatore non segue più la modalità"
        if self.commanded_at.get(device_id, float("-inf")) > snap["at"]:
            return "nel frattempo è stato comandato"
        return None

    def _start_dropped(self, device_id: str, why: str, correlation_id: str) -> None:
        device = self.devices.get(device_id)
        self.log("rule:compressor_min_off", {"type": "device", "device_id": device_id}, "set_climate", "off", "off",
                 f"Accensione automatica di {device['label'].lower() if device else device_id} rimandata per la pausa "
                 f"del compressore e non eseguita: {why}", "informational", correlation_id)

    async def _refused_by_pause(self, cmd: dict, decision_actor: str, reasoning: str, target: dict, old, new_state: dict,
                                pause: float) -> None:
        """D11: a start that finds the compressor's pause inside the lock. A person's (or the assistant's) is refused
        saying when to try again; an automatic one (the mode, the regulation, the rules) is created again when the
        pause ends, as create_command does for an automatic start (R4)."""
        cap = cmd["capability"]
        automatic = decision_actor == "system" or decision_actor.startswith("rule:")
        self._set_status(cmd, "sent")
        await asyncio.sleep(0.2)
        self._set_status(cmd, "failed", "blocked_by_rule")
        if not automatic:
            self.log(decision_actor, target, cmd["action"], old, describe(cap, new_state),
                     f"Comando bloccato dalla regola «Pausa minima del compressore»: riprova tra {int(pause) + 1} secondi",
                     "rejected", cmd["correlation_id"], command_id=cmd["command_id"])
            return
        device_id = cmd["device_id"]
        self.log("rule:compressor_min_off", target, cmd["action"], "off", "on",
                 f"{reasoning or 'Accensione automatica'}: rimandata di {int(pause) + 1} s per la pausa minima "
                 f"del compressore", "informational", cmd["correlation_id"])
        body = {"capability": cap, "action": cmd["action"], **({"params": cmd["params"]} if cmd.get("params") else {})}
        snap = self._start_snapshot(device_id)

        async def later():
            await asyncio.sleep(pause)
            if why := self._start_not_wanted(device_id, snap):   # D13
                self._start_dropped(device_id, why, cmd["correlation_id"])
                return
            self._auto_climate = True
            try:
                self.create_command(device_id, body, "system:engine", cmd["correlation_id"], decision_actor, reasoning)
            except MockError as exc:
                logs.warn("deferred command not created", apartment_id=self.apartment_id, device_id=device_id,
                          error=exc.error)
            finally:
                self._auto_climate = False
        self.spawn(later())

    async def _execute_command(self, cmd: dict, decision_actor: str, reasoning: str) -> None:
        device = self.devices[cmd["device_id"]]
        cap = cmd["capability"]
        target = {"type": "device", "device_id": device["device_id"]}
        old = describe(cap, device["capabilities"][cap])
        new_state = self.target_state(device, cap, cmd["action"], cmd["params"])
        window = self.window_open()
        current = device["capabilities"][cap]
        lowering = (cap == "heating" and current.get("on") and isinstance(new_state.get("setpoint"), (int, float))
                    and isinstance(current.get("setpoint"), (int, float)) and new_state["setpoint"] <= current["setpoint"])
        if cap in ("climate", "heating") and new_state["on"] and window and self.window_rule_active() and not lowering:
            # the engine's rule: the device is never asked; the app sees the same steps as before P-60 (sent, failed)
            if device["device_id"] in (self.heating_by_mode if cap == "heating" else self.climate_by_mode):
                # D08 (P-83): a mode's command (the mode's own heating or climate): it applies when the windows are
                # closed again, with the mode of that moment, also when the window closes before the rule's minutes
                self.window_off[device["device_id"]] = {"cap": cap, "by_mode": True, "mode_blocked": True, "state": {
                    k: new_state[k] for k in ("on", "mode", "setpoint", "fan") if k in new_state}}
                self.store.put_meta("window_off", self.window_off)
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
        async with self._device_lock(device["device_id"]):       # at most one command per device (connector-v2.md §2.5)
            # D32 (P-83): what it asks is computed from the state the command before it left (it was computed at its
            # creation: «fan high» sent while the split was being turned on turned it off again), and its time starts
            # here, where it gets the device
            fresh = self.target_state(device, cap, cmd["action"], cmd["params"])
            if fresh != new_state:
                old, new_state = describe(cap, device["capabilities"][cap]), fresh
                if waiter is not None:
                    self._unwatch_power(check[0]["device_id"], waiter)
                check = self._power_check(device, cap, new_state)
                waiter = self._watch_power(check) if check and check[0]["online"] else None
            deadline = max(deadline, utcnow() + timedelta(seconds=COMMAND_DEADLINE_S))
            if cap == "climate" and new_state["on"] and not device["capabilities"][cap]["on"]:
                # D11 (P-83): the pause checked again here, where a turn_off sent before this command is over (its
                # pause starts when it is settled): before, a start queued behind a turn_off ran at once
                pause = self.compressor_wait(device["device_id"])
                if 0 < pause <= self.setting("COMPRESSOR_WAIT_SECONDS"):
                    await asyncio.sleep(pause)
                    pause = 0.0
                if pause > 0:
                    if waiter is not None:
                        self._unwatch_power(check[0]["device_id"], waiter)
                    await self._refused_by_pause(cmd, decision_actor, reasoning, target, old, new_state, pause)
                    return
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
            self._mode_command_failed(cmd)
            return
        if result.outcome == "failed":
            logs.warn("command failed", apartment_id=self.apartment_id, reason=result.reason, detail=result.detail, **ids)
            reason = result.reason or "internal_error"
            self._set_status(cmd, "failed", reason)
            why = {"device_offline": "Il dispositivo è andato offline durante la verifica",
                   "device_rejected": "Il dispositivo ha rifiutato il comando"}.get(reason, "Errore interno del collegamento")
            self.log(decision_actor, target, cmd["action"], old, describe(cap, new_state), why, "failed",
                     cmd["correlation_id"], command_id=cmd["command_id"])
            self._mode_command_failed(cmd)
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
        self.mode_cmds.pop(cmd["command_id"], None)
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
        """A meter's new watts: the commands watching it that they confirm are confirmed; D14, a split confirmed by this
        meter and with no command running follows it (drawing: on; nothing: off), so a start that came after its
        command's window, or a split switched by its own remote, is seen as it is (the window rule turns it off)."""
        watts = float(state.get("watts") or 0)
        for direction, baseline, waiter in self.power_waiters.get(meter_id, []):
            if not waiter.done() and confirm.power_confirms(direction, baseline, watts, self.confirm_on_watts,
                                                            self.confirm_off_watts):
                waiter.set_result(True)
        busy = {c["device_id"] for c in self.commands.values() if c["status"] not in FINAL} | {r[0] for r in self.inflight}
        for split in self.devices.values():
            climate = split["capabilities"].get("climate")
            if (not climate or climate.get("confirmation") != "power" or split["device_id"] in busy
                    or (self.confirmation_meter(split["device_id"]) or {}).get("device_id") != meter_id):
                continue
            seen_on = (True if watts >= self.confirm_on_watts else False if watts < self.confirm_off_watts else None)
            if seen_on is not False:
                self.remote_low.pop(split["device_id"], None)
            if seen_on is None or seen_on == bool(climate.get("on")):
                continue
            if seen_on is False:
                # P-90 S1: off only after REMOTE_OFF_MINUTES of low watts (_remote_off_check), then out of the regulation
                self.remote_low.setdefault(split["device_id"], time.monotonic())
                continue
            climate["on"] = seen_on
            self._note_climate(split["device_id"], "climate", not seen_on, seen_on)
            self._save_device(split)
            self.emit("device.state", {"device_id": split["device_id"], "capability": "climate", "state": climate},
                      str(uuid.uuid4()))

    def _remote_off_check(self) -> None:
        """P-90 S1 (answer 1101 = a): a split whose meter has stayed low for REMOTE_OFF_MINUTES, with no command of its
        running, was switched off by its remote: the engine's copy goes off and, if the mode regulated it, it leaves the
        regulation until the next mode (D-169: never against a person), with a decision. Before, the regulation switched
        it on again every THERMOSTAT_MIN_SWITCH_MINUTES (and a beep each time, at night)."""
        if not self.remote_low:
            return
        wait = self.setting("REMOTE_OFF_MINUTES") * seconds_per_minute()
        busy = {c["device_id"] for c in self.commands.values() if c["status"] not in FINAL} | {r[0] for r in self.inflight}
        for device_id, since in list(self.remote_low.items()):
            split = self.devices.get(device_id)
            climate = split["capabilities"].get("climate") if split else None
            if not climate or not climate.get("on") or device_id in busy:
                self.remote_low.pop(device_id, None)
                continue
            if time.monotonic() - since < wait:
                continue
            self.remote_low.pop(device_id, None)
            climate["on"] = False
            self._note_climate(device_id, "climate", True, False)
            self._save_device(split)
            corr = str(uuid.uuid4())
            self.emit("device.state", {"device_id": device_id, "capability": "climate", "state": climate}, corr)
            reasoning = (f"{split['label']}: spento col telecomando (consumo sotto {fmt_num(self.confirm_off_watts)} W "
                         f"da {fmt_num(self.setting('REMOTE_OFF_MINUTES'))} minuti)")
            if device_id in self.climate_by_mode:
                self.climate_by_mode.discard(device_id)
                self.store.put_meta("climate_by_mode", sorted(self.climate_by_mode))
                reasoning += "; resta fuori dalla regolazione fino al prossimo cambio di modalità"
            self.log("system", {"type": "device", "device_id": device_id}, "climate_remote_off", "on", "off", reasoning,
                     "informational", corr)

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
        self._arm_window(device_id)

    def _contact_online(self, device: dict) -> None:
        """P-90 S6 (answer 1102 = a): a window's contact that goes offline while open counts as closed (window_open):
        its wait stops, and what the rule turned off comes back like after a closing, with a decision that says why;
        the device's offline notification stays. Back online and still open, the rule's wait starts again."""
        contact = device["capabilities"].get("contact")
        if not contact or not contact.get("open"):
            return
        device_id = device["device_id"]
        if not device["online"]:
            self.log("rule:window_open_off", {"type": "device", "device_id": device_id}, "window_contact_offline",
                     "aperta", "chiusa", f"{device['label']} senza segnale mentre era aperta: considerata chiusa per la "
                     f"regola «Finestra aperta spegne il clima» finché non torna raggiungibile", "informational",
                     str(uuid.uuid4()))
            self._window_closed(device_id)
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return                                               # no loop: the start arms it (_windows_at_start)
        self._window_opened(device_id)

    def _arm_window(self, device_id: str, delay: float | None = None) -> None:
        """The wait of one window, one at a time: a new one replaces the old (D-218: a window that bangs in the wind
        counts its minutes from its last opening)."""
        if (old := self.window_reflexes.pop(device_id, None)) and not old.done():
            old.cancel()
        self.window_reflexes[device_id] = self.spawn(self._window_reflex(device_id, delay))

    def _window_closed(self, device_id: str) -> None:
        """D-218 point 1: a window closed. Its wait is cancelled; when none is open any more, what the rule turned off
        comes back at the regulation's next round, after a minute with the windows closed (_restore_after_window)."""
        if (task := self.window_reflexes.pop(device_id, None)) and not task.done():
            task.cancel()
        self.window_fired.discard(device_id)
        if not self.window_open():
            self.windows_closed_at = time.monotonic()

    async def _window_reflex(self, device_id: str, delay: float | None = None) -> None:
        minutes = self.rule("window_open_off")["params"]["minutes"]
        await asyncio.sleep(minutes * seconds_per_minute() if delay is None else delay)
        while True:
            contact = self.devices[device_id]["capabilities"]["contact"]
            if not contact["open"] or not self.window_rule_active():
                return                   # closed meanwhile, or a hold: the end of the hold looks again (R7)
            if self.connector_up():
                break
            await asyncio.sleep(1.0)     # the devices cannot be reached (also just after a start): off when they can
        self._window_turn_off(device_id, f"{self.devices[device_id]['label']} aperta da oltre {fmt_num(minutes)} minuti")

    def _windows_at_start(self) -> None:
        """Verification of 10 November 2026, point a: the wait of the window rule lives in memory, and before this a
        restart lost it; a window already open then turned nothing off until it was closed and opened again. At the
        start every open window waits again for the minutes it has left, counted from when it opened (contact.since;
        from the start when that is not known, or when it opened while the engine was down): the more prudent choice,
        the climate goes off when it would have without the restart, never later. During a hold nothing: its end looks
        again (R7)."""
        rule = self.rule("window_open_off")
        if not rule["enabled"] or not self.window_rule_active():
            return
        minutes = rule["params"]["minutes"]
        for d in self.devices.values():
            contact = d["capabilities"].get("contact")
            if not contact or not contact.get("open"):
                continue
            open_s = (utcnow() - parse_dt(contact["since"])).total_seconds() if contact.get("since") else 0.0
            self._arm_window(d["device_id"], delay=max(0.0, minutes * seconds_per_minute() - open_s))

    def _window_turn_off(self, window_id: str, why: str, skip: set[str] | frozenset = frozenset()) -> None:
        self.window_fired.add(window_id)                     # D03: the rule now holds while this window stays open
        # D08 (P-83): a device with a command still running (the mode's turn_off or its new setpoint) is left to it: a
        # turn_off made now would carry the state of before (a boiler back to 21 °C), and one being turned off would be
        # remembered as «on» and come back on when the window closes, in «casa vuota» too. The next regulation's minute
        # looks again (_keep_window_off, D03)
        skip = set(skip) | {c["device_id"] for c in self.commands.values() if c["status"] not in FINAL}
        corr = str(uuid.uuid4())
        frost = self.mode == "empty" and self.rule("frost_protection")["enabled"]
        for d in list(self.devices.values()):
            for cap in ("climate", "heating"):
                st = d["capabilities"].get(cap)
                if st and st["on"] and d["online"] and d["device_id"] not in skip:
                    # R8: safety stays stronger than the window: in an empty apartment the frost protection goes on
                    extra = "; l'antigelo resta attivo" if cap == "heating" and frost else ""
                    device_id = d["device_id"]
                    # D-218 point 1: remembered to bring back, and not a person's command (the mode keeps it); D03: a
                    # second try keeps what was remembered the first time
                    by_mode = device_id in (self.heating_by_mode if cap == "heating" else self.climate_by_mode)
                    self.window_off.setdefault(device_id, {"cap": cap, "by_mode": by_mode, "state": {
                        k: st[k] for k in ("on", "mode", "setpoint", "fan") if k in st}})
                    self._window_command = True
                    try:
                        self.create_command(device_id, {"capability": cap, "action": "turn_off"}, "system:engine", corr,
                                            decision_actor="rule:window_open_off",
                                            reasoning=f"{why} con {d['label'].lower()} acceso{extra}")
                    finally:
                        self._window_command = False
                    # a switch like any other: the return waits the boiler's minimum and the regulation's minutes
                    (self.relay_switched if cap == "heating" else self.climate_switched)[device_id] = time.monotonic()
        self.store.put_meta("window_off", self.window_off)

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
                self._arm_window(d["device_id"], delay=left)

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
            self._contact_online(device)
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
            if cap == "climate":
                self._climate_pair(device_id, state)         # 1098 = b
            if cap == "contact" and state.get("open") != was_open:
                state["since"] = iso(seen)
            if cap == "motion" and state.get("detected") and "last_seen" not in body["state"]:
                state["last_seen"] = iso(seen)          # D-140: a simulated movement is recorded as a real sensor's
            device["last_seen"] = iso(seen)
            self._save_device(device)
            self.emit("device.state", {"device_id": device_id, "capability": cap, "state": state}, correlation_id)
            if cap == "contact" and state.get("open") and not was_open:
                self._window_opened(device_id)
            elif cap == "contact" and was_open and not state.get("open"):
                self._window_closed(device_id)

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
        for status, error, message in range_errors(sl, any(p.get("rule_id") == "setpoint_limits" for p in patches)):
            raise MockError(status, error, message)
        self.rules = staged
        self.rules_updated_at = iso(utcnow())
        self._save_apartment()
        changed = ", ".join(p["rule_id"] for p in patches)
        self.log(actor_of(actor), {"type": "rules"}, "update_rules", None, changed, "Regole modificate dall'app",
                 "applied", correlation_id)
        self._apply_limits(correlation_id, emit=True)       # D-174: the switch and the limits take effect now
        self._modes_outside_check(correlation_id)           # 1097 = a: the episode of a rule saved before ends here
        for p in patches:
            if p.get("rule_id") in BOOKING_RULES and "enabled" in p:
                self._booking_rule_switched(p["rule_id"], correlation_id)     # P-90 S11
        if any(p.get("rule_id") == "offline_alert" and "enabled" in p for p in patches):
            self._offline_rule_switched()                                       # P-90 S17
        try:
            asyncio.get_running_loop()
            self._push_limits(correlation_id)                # 1097 = a: the climates the new limits cut, now
        except RuntimeError:
            pass                                             # no loop: the next regulation's minute sends them
        if any(p.get("rule_id") == "window_open_off" for p in patches):
            # D30 (P-83): turned on, or its minutes changed: every open window waits again from when it opened (past
            # the minutes, at once); before, a wait that ended with the rule off was never planned again
            try:
                asyncio.get_running_loop()
                self._windows_at_start()
            except RuntimeError:
                pass                                         # no loop (a call outside the engine's): the start arms them
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
            ts = parse_dt(ev["ts"])
        except ValueError:
            raise bad_request("Date non valide")
        if checkout <= checkin:
            raise MockError(422, "invalid_dates", "Il check-out deve essere successivo al check-in")
        bid = ev["booking_id"]
        known = self.bookings.get(bid)
        if known is not None and known.get("last_ts") and ts < parse_dt(known["last_ts"]):
            # D07 (P-83): older than the last event applied to this booking (a retry after a 502 arriving late):
            # acknowledged, so it is not sent again, and changes nothing
            result = {"event_id": ev["event_id"], "accepted": True, "duplicate": False, "schedule_ids": []}
            self.processed_events[ev["event_id"]] = result
            self._save_processed(ev["event_id"], result, known["checkout"])
            self.log("system", {"type": "schedule"}, "booking_event_stale", None, bid,
                     f"Evento «{ev['type']}» della prenotazione {bid} più vecchio dell'ultimo applicato: ignorato",
                     "informational", correlation_id, emit=emit)
            return 200, result
        booking = self.bookings.setdefault(bid, {"booking_id": bid, "checkin": checkin, "checkout": checkout,
                                                 "cancelled": False, "checked_in": False, "checked_out": False})
        items = [s for s in self.schedule.values() if s["booking_id"] == bid]
        ids: list[str] = []
        moved_reset = False
        reset = False
        extended = False
        old_checkin = booking["checkin"]
        if ev["type"] == "booking_cancelled" and booking["cancelled"]:
            # P-90 S21: already cancelled (the same cancellation again, another id): acknowledged, nothing changes
            reasoning = f"Prenotazione {bid} già cancellata: niente da fare"
        elif ev["type"] == "booking_cancelled":
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
            now = utcnow()
            for kind, run_at, mode in plan:
                existing = next((s for s in items if s["kind"] == kind and s["status"] == "planned"), None)
                done = any(s["kind"] == kind and s["status"] == "done" for s in items)
                if existing:
                    existing["run_at"] = iso(run_at)
                    ids.append(existing["schedule_id"])
                    continue
                if checkout <= now and (kind == "prearrival" or self.mode == "empty"):
                    continue        # P-90 S21: a stay already over (received late): no warming, no «casa vuota» again
                if done and kind == "checkout" and run_at > now and not booking["checked_out"]:
                    # P-90 S5: a late check-out or one more night after the check-out action: planned again, and with
                    # the guests in (the stay in course) the comfort back now, through the scheduler
                    ids.append(self.add_schedule(run_at, {"type": "apartment_mode", "mode": mode}, kind, "booking",
                                                 bid)["schedule_id"])
                    if booking["checkin"] <= now and self.mode != "comfort":
                        ids.append(self.add_schedule(now, {"type": "apartment_mode", "mode": "comfort"}, "prearrival",
                                                     "booking", bid)["schedule_id"])
                        extended = True
                    continue
                if done and kind == "prearrival" and checkin == old_checkin:
                    continue        # P-90 S19: the arrival did not change (a prearrival moved by hand ran): nothing
                if done and (run_at <= now or booking["checked_in"] or booking["checked_out"]):
                    continue        # D06 (P-83): already done for this booking, its time past or the guests in or gone
                if done and kind == "prearrival" and not moved_reset and not self._booking_needs_comfort(bid):
                    # D06: the arrival moved to the future after the prearrival: back to empty now, as a cancellation
                    # does (D-121), through the scheduler; warmed again at the new time
                    ids.append(self.add_schedule(now, {"type": "apartment_mode", "mode": "empty"}, "empty", "booking",
                                                 bid)["schedule_id"])
                    moved_reset = True
                ids.append(self.add_schedule(run_at, {"type": "apartment_mode", "mode": mode}, kind, "booking", bid)["schedule_id"])
            reasoning = f"Prenotazione {bid} {'ricevuta' if ev['type'] == 'booking_created' else 'modificata'}: pre-arrivo e check-out programmati"
        booking["last_ts"] = iso(ts)                     # D07: the time of the last event applied
        result = {"event_id": ev["event_id"], "accepted": True, "duplicate": False, "schedule_ids": ids}
        self.processed_events[ev["event_id"]] = result
        self._save_booking(booking)
        for item in self.schedule.values():
            if item["booking_id"] == bid:
                self._save_schedule(item)
        self._save_processed(ev["event_id"], result, booking["checkout"])
        self.log("system", {"type": "schedule"}, ev["type"], None, bid, reasoning, "informational", correlation_id, emit=emit)
        if moved_reset:
            arrival = booking["checkin"].astimezone(ZoneInfo(self.timezone)).strftime("%d/%m %H:%M")
            self.log("system", {"type": "apartment"}, "booking_moved_reset", self.mode, "empty",
                     f"Arrivo della prenotazione {bid} spostato al {arrival}, dopo il pre-arrivo: appartamento rimesso a "
                     f"vuoto, si riscalda al nuovo pre-arrivo", "informational", correlation_id, emit=emit)
        if extended:
            departure = booking["checkout"].astimezone(ZoneInfo(self.timezone)).strftime("%d/%m %H:%M")
            self.log("system", {"type": "apartment"}, "booking_extended_comfort", self.mode, "comfort",
                     f"Partenza della prenotazione {bid} spostata al {departure}, dopo il check-out: appartamento "
                     f"rimesso in comfort, check-out riprogrammato", "informational", correlation_id, emit=emit)
        if reset:   # its own decision, which the BFF turns into a push to the managers (D-121)
            self.log("system", {"type": "apartment"}, "booking_cancel_reset", self.mode, "empty",
                     f"Prenotazione {bid} annullata dopo il pre-arrivo: appartamento rimesso a vuoto", "informational",
                     correlation_id, emit=emit)
        if emit:
            self.apartment_changed(correlation_id)
        return 202, result

    def _booking_needs_comfort(self, other_than: str | None) -> bool:
        return self._booking_needing_comfort(other_than) is not None

    def _booking_needing_comfort(self, other_than: str | None) -> dict | None:
        """Another booking, not cancelled nor checked out, that is in course now, whose prearrival already ran, or
        (D05, P-83) whose arrival is within the prearrival's hours: its warmth must not be taken away."""
        now = utcnow()
        pre = self.rule("prearrival")
        soon = timedelta(hours=pre["params"]["hours_before"]) if pre["enabled"] else None
        for b in sorted(self.bookings.values(), key=lambda b: b["checkin"]):
            if b["booking_id"] == other_than or b["cancelled"] or b["checked_out"] or b["checkout"] <= now:
                continue                                     # D05: a stay already over needs nothing
            if b["checkin"] <= now < b["checkout"] or (soon is not None and now < b["checkin"] <= now + soon) or any(
                    s["booking_id"] == b["booking_id"] and s["kind"] == "prearrival" and s["status"] == "done"
                    for s in self.schedule.values()):
                return b
        return None

    def _checkout_keeps_comfort(self, booking_id: str | None, correlation_id: str) -> bool:
        """D05 (P-83): a check-out about to empty the apartment while another booking needs it (back to back): the mode
        stays, and a decision says why. True when it stays."""
        other = self._booking_needing_comfort(booking_id)
        if other is None:
            return False
        arrival = other["checkin"].astimezone(ZoneInfo(self.timezone)).strftime("%d/%m %H:%M")
        self.log("system", {"type": "apartment"}, "checkout_kept_comfort", self.mode, self.mode,
                 f"Check-out della prenotazione {booking_id or '?'}: l'appartamento non va a vuoto, c'è la prenotazione "
                 f"{other['booking_id']} (arrivo {arrival})", "informational", correlation_id)
        return True

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
            # D76 (P-83): described like the commands' own decisions, the new value from the state the command gives
            # (the new value was always "off": «from off to off» for a socket turned on)
            device, cap = self.devices.get(pa["device_id"]), pa["capability"]
            if device and cap in device["capabilities"]:
                state = device["capabilities"][cap]
                action, old = pa["action"], describe(cap, state)
                new = describe(cap, self.target_state(device, cap, pa["action"], pa.get("params") or {}))
            else:
                action, old, new = pa["action"], "off", "on" if pa["action"] == "turn_on" else "off"
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

    def _close_empty_power_requests(self, correlation_id: str | None) -> None:
        """P-90 S12: the requests «Spegnere … con l'appartamento vuoto» (F2) lose their reason when the apartment is no
        longer empty: the open one closes without running (status expired, with its decision), the queued ones go."""
        def f2(a: dict) -> bool:
            return a["source"] == "rule" and a["proposed_action"]["type"] == "device_command"
        queued = [a for a in self.approval_queue if f2(a)]
        if queued:
            self.approval_queue = [a for a in self.approval_queue if not f2(a)]
            self._save_queue()
        closed = False
        for a in self.approvals:
            if a["status"] == "pending" and f2(a):
                a["status"] = "expired"
                self._save_approval(a)
                self.log("system", self._approval_target(a), "expire", "pending", "expired",
                         "Richiesta chiusa senza eseguire: l'appartamento non è più vuoto", "informational",
                         correlation_id or str(uuid.uuid4()), approval_id=a["approval_id"])
                closed = True
        if closed:
            self._dequeue_approval()

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
        checkout_eco's presence_minutes (D-151), with when; None without a motion sensor or without such a movement."""
        booking = self.bookings.get(item.get("booking_id") or "")
        if booking is None:
            return None
        now, window = utcnow(), timedelta(minutes=self.rule("checkout_eco")["params"]["presence_minutes"])
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
        self._new_approval("rule", CHECKOUT_APPROVAL,
                           f"Movimento rilevato {minutes} minuti fa da «{sensor['label']}», dopo l'orario di partenza "
                           f"delle {departure}: gli ospiti potrebbero essere ancora in casa",
                           dict(item["action"]), "approve", correlation_id)

    def list_approvals(self, status: str) -> dict:
        if status not in ("pending", "all"):
            raise bad_request("status deve essere pending o all")
        # «the closed ones of the last 7 days» (contract): 7 days of the apartment's calendar, from its midnight. Before,
        # 7×24 hours back from now, and the weekly summary made on Monday after 08:00 lost the approvals of the Monday
        # before until that hour (verification of 10 November 2026, point e); also in the week of 169 hours.
        tz = ZoneInfo(self.timezone)
        cutoff = datetime.combine(utcnow().astimezone(tz).date() - timedelta(days=7), datetime.min.time(), tzinfo=tz)
        items = [a for a in self.approvals if a["status"] == "pending" or (status == "all" and parse_dt(a["created_at"]) >= cutoff)]
        return {"items": copy.deepcopy(sorted(items, key=lambda a: a["created_at"], reverse=True))}

    def _execute_proposed(self, approval: dict, actor: str, correlation_id: str, decision_actor: str,
                          by_hand: bool = False) -> None:
        pa = approval["proposed_action"]
        run_at = self._take_schedule(approval["approval_id"])
        if run_at is not None and parse_dt(run_at) < utcnow() - timedelta(seconds=30):
            # D37 (P-83): approved after its time: nothing runs at a time nobody chose
            at = parse_dt(run_at).astimezone(ZoneInfo(self.timezone)).strftime("%d/%m %H:%M")
            self._approved_not_done(approval, decision_actor, correlation_id, "non eseguita",
                                    MockError(422, "run_at_in_past", f"l'orario ({at}) è già passato"))
            return
        if run_at is not None and parse_dt(run_at) > utcnow() + timedelta(seconds=30):
            try:                                          # D-170: approved, the action is scheduled at its time
                self.create_schedule({"run_at": run_at, "action": pa}, actor, correlation_id, source="assistant")
            except MockError as exc:
                self._approved_not_done(approval, decision_actor, correlation_id, "non programmata", exc)
            return
        try:
            if pa["type"] == "apartment_mode":
                self.set_mode(pa["mode"], actor, correlation_id, "Azione approvata", decision_actor, by_hand=by_hand)
            else:
                self.create_command(pa["device_id"], pa, actor, correlation_id, decision_actor=decision_actor,
                                    reasoning=f"Azione approvata: {approval['description']}")
        except MockError as exc:
            self._approved_not_done(approval, decision_actor, correlation_id, "non eseguita", exc)

    def _approved_not_done(self, approval: dict, actor: str, correlation_id: str, what: str, exc: MockError) -> None:
        """Verification of 10 November 2026, point c: an approved action refused at once (device or connector
        unreachable, an action no longer valid, a time already past) was dropped without a word, and the manager saw
        only «Approvata». Now a decision with outcome failed says so, with the engine's reason."""
        pa = approval["proposed_action"]
        action, new = ("set_mode", pa.get("mode")) if pa["type"] == "apartment_mode" else (pa.get("action"), None)
        self.log(actor, self._approval_target(approval), action, None, new,
                 f"Azione approvata ma {what}: {exc.message}", "failed", correlation_id,
                 approval_id=approval["approval_id"])

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
            self._execute_proposed(approval, actor, correlation_id, who, by_hand=True)
        else:
            self._take_schedule(approval_id)
        self._dequeue_approval()
        return copy.deepcopy(approval)

    def _dequeue_approval(self) -> None:
        if self.approval_queue and not self.pending_approval():
            approval = self.approval_queue.pop(0)
            self._save_queue()
            self._open_approval(approval)

    # ---- reachability (D-217): the BFF says when it could not reach this engine ---------------------------------------
    def note_reachable(self, body, correlation_id: str) -> tuple[int, dict]:
        """POST /_internal/reachability, outside the contract: the BFF could not reach this engine from `from` to `to`
        (UTC) and now can. One decision says so, «Sistema domotico di nuovo raggiungibile dopo …», sent live like
        every decision. The same interval twice gives the same decision (kept in the store's meta, the last 50)."""
        if not isinstance(body, dict) or not isinstance(body.get("from"), str) or not isinstance(body.get("to"), str):
            raise bad_request("from e to sono obbligatori: istanti ISO 8601 con il fuso")
        try:
            frm, to = parse_dt(body["from"]), parse_dt(body["to"])
        except ValueError:
            raise bad_request("from e to devono essere istanti ISO 8601 con il fuso") from None
        if frm >= to:
            raise bad_request("from deve venire prima di to")
        if to > utcnow() + timedelta(minutes=1):
            raise bad_request("to non può essere nel futuro")
        key = f"{iso(frm)}|{iso(to)}"
        notes = self.store.get_meta("reachability_notes", {}) or {}
        if key in notes:
            done = next((d for d in self.decisions if d["decision_id"] == notes[key]), None)
            return 200, done or {"decision_id": notes[key]}
        d = self.log("system", {"type": "apartment"}, "instance_reachable", "unreachable", "reachable",
                     f"Sistema domotico di nuovo raggiungibile dopo {duration_words(to - frm)}", "informational",
                     correlation_id)
        notes[key] = d["decision_id"]
        self.store.put_meta("reachability_notes", dict(list(notes.items())[-50:]))
        return 201, d

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
        off = re.search(r"\b(spegni|disattiva)\b", text)
        try:
            # D-189: with guests in only switching the boiler off asks first; switching it on or a temperature does not
            if "caldaia" in text and off and self.guests_in():      # D18
                pending = self.pending_approval()
                if pending:
                    ask.update(status="answered", approval_id=pending["approval_id"],
                               answer="C'è già un'approvazione in attesa: decidi prima quella.")
                else:
                    approval = self.trigger_approval(corr, source="assistant",
                                                     reason="Richiesta all'assistente. Ospiti presenti nell'appartamento.")   # D56: not its text
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
                    what = f"la modalità {'casa vuota' if mode == 'empty' else mode}"   # decision 55
                item = self.create_schedule({"run_at": iso(run), "action": action}, actor, corr, source="assistant")
                ask.update(status="answered", actions=[{"type": "schedule", "schedule_id": item["schedule_id"]}],
                           answer=f"Ho programmato {what} {at_local_hour(run, hh, mm)}.")
            elif "spegni" in text:
                d = self._match_device(text)
                cap = next(c for c in ACTIONS if c in d["capabilities"])
                cmd = self.create_command(d["device_id"], {"capability": cap, "action": "turn_off"}, actor, corr,
                                          decision_actor="assistant", reasoning="Richiesta all'assistente")
                ask.update(status="answered", actions=[{"type": "command", "command_id": cmd["command_id"]}],
                           answer=f"Ho spento {d['label'].lower()}.")
            elif "caldaia" in text:                       # D-189: the boiler on, at a temperature if given
                d = self._match_device(text, "heating")
                if d is None:
                    raise MockError(422, "no_heating", "Nessuna caldaia nell'appartamento")
                params = {"on": True, **({"setpoint": setpoint} if setpoint is not None else {})}
                cmd = self.create_command(d["device_id"], {"capability": "heating", "action": "set_heating",
                                                           "params": params}, actor, corr, decision_actor="assistant",
                                          reasoning="Richiesta all'assistente")
                done = cmd["params"].get("setpoint")
                ask.update(status="answered", actions=[{"type": "command", "command_id": cmd["command_id"]}],
                           answer=(f"Ho acceso {d['label'].lower()} a {fmt_num(done)} °C." if done is not None
                                   else f"Ho acceso {d['label'].lower()}."))
            elif "gradi" in text or "temperatura" in text:
                d = self._match_device(text, "climate")
                if setpoint is None:
                    ask.update(status="answered", answer="Indica la temperatura, ad esempio «porta il soggiorno a 21 gradi».")
                else:
                    cmd = self.create_command(d["device_id"], {"capability": "climate", "action": "set_climate",
                                                               "params": {"on": True, "setpoint": setpoint}}, actor, corr,
                                              decision_actor="assistant", reasoning="Richiesta all'assistente")
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
            except Exception as exc:                      # each step is guarded: this is the tick's own frame
                self._step_failed("tick", exc)

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
        """Once a second. Each step is guarded (_guarded): one that fails is written in the log and the others go on; an
        approval or a scheduled action that fails does not stop the next ones."""
        now = utcnow()
        self.last_tick = time.monotonic()
        if self.last_tick - self.last_heartbeat >= HEARTBEAT_S:
            self.last_heartbeat = self.last_tick
            self._guarded("heartbeat", self._heartbeat)
        self._guarded("connector", self._tick_connector)
        if time.monotonic() - self.last_regulation >= seconds_per_minute():
            self.last_regulation = time.monotonic()
            self._guarded("regulate", self.regulate)
        if time.monotonic() - self.last_housekeeping >= 60:
            self.last_housekeeping = time.monotonic()
            self._guarded("housekeeping", self.housekeeping)
        self._guarded("hold", self._tick_hold, now)
        for a in self.approvals:
            if a["status"] == "pending" and a["expires_at"] and parse_dt(a["expires_at"]) <= now:
                self._guarded("approval_expiry", self._expire_approval, a)
        # by time, and by creation for the same time (a stable sort on the creation order, which engine.db keeps too).
        # An action is closed (done/failed) and saved in this same pass, so a later pass never runs it again. After a
        # crash between its commands and that save it runs again at the restart (within MISSED_AFTER_MINUTES): harmless,
        # commands are states to reach (P-60 step 4).
        for item in sorted(self.schedule.values(), key=lambda s: s["run_at"]):
            if item["status"] != "planned" or parse_dt(item["run_at"]) > now:
                continue
            try:
                self._run_scheduled(item, now)
            except Exception as exc:
                # an unexpected error: the action is closed as failed, so that it does not run again every second
                self._step_failed("schedule", exc)
                item.update(status="failed", executed_at=iso(now))
                self._guarded("schedule", self._save_schedule, item)
                self._guarded("schedule", self._schedule_not_done, item, str(uuid.uuid4()),
                              "errore interno del motore")

    def _tick_connector(self) -> None:
        up = self.connector_up()
        if up != self.connector_was_up:
            self.connector_was_up = up
            self._connector_changed(up)
        if up:
            self._watch_empty_power()

    def _tick_hold(self, now: datetime) -> None:
        if self.hold and parse_dt(self.hold["until"]) <= now:
            self.hold = None
            self._save_apartment()
            corr = str(uuid.uuid4())
            self.log("system", {"type": "apartment"}, "hold_expired", None, None,
                     "Forzatura scaduta: le regole tornano attive", "informational", corr)
            self.apartment_changed(corr)
            self._window_after_hold()

    def _expire_approval(self, a: dict) -> None:
        a["status"] = "expired"
        self._save_approval(a)
        corr = str(uuid.uuid4())
        outcome = {"reject": "respinta", "approve": "approvata", "wait": "in attesa"}[a["expires_action"]]
        self.log("system", self._approval_target(a), "expire",
                 "pending", "expired", f"Approvazione scaduta senza risposta: {outcome}", "informational", corr,
                 approval_id=a["approval_id"])
        late = utcnow() - parse_dt(a["expires_at"]) if a.get("expires_at") else timedelta(0)
        try:
            if a["expires_action"] == "approve" and late > timedelta(minutes=self.setting("MISSED_AFTER_MINUTES")):
                # D10 (P-83): it expired while the engine was down, longer ago than a scheduled action may run late:
                # closed without running, as schedule_missed does
                at = parse_dt(a["expires_at"]).astimezone(ZoneInfo(self.timezone)).strftime("%d/%m %H:%M")
                self._take_schedule(a["approval_id"])
                self.log("system", self._approval_target(a), "expire", "pending", "expired",
                         f"Approvazione scaduta alle {at}, mentre il sistema era fermo: azione non eseguita "
                         f"({a['description']})", "failed", corr, approval_id=a["approval_id"])
            elif a["expires_action"] == "approve" and a["description"] == CHECKOUT_APPROVAL and \
                    self._checkout_keeps_comfort(None, corr):
                pass                                     # D05: approved at expiry, but the next guest arrived meanwhile
            elif a["expires_action"] == "approve" and self.hold and a["proposed_action"].get("type") == "apartment_mode":
                # D09 (P-83): like a scheduled mode change (D-122), it waits for the end of the hold: an action due now,
                # which the scheduler defers with the decision «rimandata per la forzatura»
                pa = dict(a["proposed_action"])           # kind and source within the contract's values
                self.add_schedule(utcnow(), pa, "empty" if pa.get("mode") == "empty" else "manual",
                                  "booking" if a["description"] == CHECKOUT_APPROVAL else "manual")
            elif a["expires_action"] == "approve":
                self._execute_proposed(a, "system:engine", corr, "system")
            else:
                self._take_schedule(a["approval_id"])
        finally:
            # the next approval in the queue opens also when the action above failed unexpectedly (o1's review of
            # 5287e4b): otherwise it stayed queued until another event
            self._dequeue_approval()

    def _run_scheduled(self, item: dict, now: datetime) -> None:
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
            return
        rule_id = next((r for r, k in BOOKING_RULES.items() if k == item["kind"]), None)
        if item["source"] == "booking" and rule_id and not self.rule(rule_id)["enabled"]:
            # P-90 S11: its rule is off (the switch cancels them; this one was left, e.g. a rule saved off)
            item.update(status="cancelled", executed_at=iso(now))
            self._save_schedule(item)
            self.log(f"rule:{rule_id}", {"type": "schedule"}, "schedule_cancel", item["run_at"], None,
                     f"{reasoning}: annullata, la regola «{self.rule(rule_id)['label']}» è spenta", "applied", corr)
            self.apartment_changed(corr)
            return
        if self.deferred.pop(item["schedule_id"], None) is not None:
            self.store.put_meta("deferred", self.deferred)
            reasoning += " (rimandata per la forzatura)"
        if (item["kind"] == "checkout" and act["type"] == "apartment_mode" and act.get("mode") == "empty"
                and self._checkout_keeps_comfort(item["booking_id"], corr)):
            item.update(status="done", command_ids=[], executed_at=iso(now))   # D05: the next guest keeps the warmth
            self._save_schedule(item)
            self.apartment_changed(corr)
            return
        if item["kind"] == "checkout" and act["type"] == "apartment_mode" and (seen := self._presence_after_checkout(item)):
            self._propose_checkout(item, seen, corr)      # F1 (D-137): the manager decides; approved at expiry
            item.update(status="done", command_ids=[], executed_at=iso(now))
            self._save_schedule(item)
            self.apartment_changed(corr)
            return
        sid = item["schedule_id"]
        self.schedule_open[sid] = {"corr": corr, "refused": [], "waiting": []}
        self._schedule_run = sid
        try:
            if act["type"] == "apartment_mode":
                item["command_ids"] = self.set_mode(act["mode"], "system:engine", corr, reasoning, "system")
            else:
                cmd = self.create_command(act["device_id"], act, "system:engine", corr, decision_actor="system",
                                          reasoning=reasoning)
                item["command_ids"] = [cmd["command_id"]] if cmd else []
            item["status"] = "done"
        except MockError as exc:
            item["status"] = "failed"
            self.schedule_open.pop(sid, None)            # refused as a whole: schedule_failed says it
            self._schedule_not_done(item, corr, exc.message)
        finally:
            self._schedule_run = None
        item["executed_at"] = iso(now)
        self._save_schedule(item)
        if sid in self.schedule_open:
            for command_id in item["command_ids"]:
                self.command_schedule[command_id] = sid
            self.store.put_meta("schedule_open", self.schedule_open)
            self._schedule_check(sid)                    # nothing sent, or everything refused: judged at once
        self.apartment_changed(corr)

    # ---- D-219 (2): a scheduled action whose commands did not all succeed --------------------------------------------
    def _schedule_refused(self, sid: str, device_id: str, why: str) -> None:
        run = self.schedule_open.get(sid)
        if run is not None:
            run["refused"].append([device_id, why])
            self.store.put_meta("schedule_open", self.schedule_open)

    def _schedule_wait(self, sid: str, device_id: str, done: bool = False) -> None:
        """A start of the action waits for the compressor's pause (done=False), or is over (created or refused)."""
        run = self.schedule_open.get(sid)
        if run is None:
            return
        if not done:
            run["waiting"].append(device_id)
        elif device_id in run["waiting"]:
            run["waiting"].remove(device_id)
        self.store.put_meta("schedule_open", self.schedule_open)
        if done:
            self._schedule_check(sid)

    def _schedule_link(self, sid: str, command_id: str) -> None:
        """The start that waited for the compressor's pause is a command of the action (in GET /schedule too)."""
        item = self.schedule.get(sid)
        if item is None or sid not in self.schedule_open:
            return
        item["command_ids"] = [*(item.get("command_ids") or []), command_id]
        self.command_schedule[command_id] = sid
        self._save_schedule(item)

    def _command_failure(self, cmd: dict) -> str:
        """Why a command did not succeed, in the words of its decision; its code when there is none."""
        for d in reversed(self.decisions):
            if d.get("command_id") == cmd["command_id"] and d["outcome"] in ("failed", "rejected"):
                return d["reasoning"]
        return {"device_offline": "dispositivo offline", "device_rejected": "rifiutato dal dispositivo",
                "blocked_by_rule": "bloccato da una regola", "no_confirmation": "nessuna conferma"}.get(
            cmd.get("reason"), "errore interno")

    def _schedule_check(self, sid: str) -> None:
        """When the last command of a scheduled action is over (and no start waits for the compressor): with at least
        one that did not succeed, the decision schedule_partial lists them («Pre-arrivo eseguito in parte: 2 comandi
        non riusciti (…)»); new_value is the action's kind, as in schedule_failed, for the BFF's notification."""
        run, item = self.schedule_open.get(sid), self.schedule.get(sid)
        if run is None:
            return
        cmds = [self.commands.get(c) for c in (item or {}).get("command_ids") or []]
        if item is not None and (run["waiting"] or any(c is not None and c["status"] not in FINAL for c in cmds)):
            return
        del self.schedule_open[sid]
        for c in [c for c, s in self.command_schedule.items() if s == sid]:
            del self.command_schedule[c]
        self.store.put_meta("schedule_open", self.schedule_open)
        if item is None:
            return
        def label(device_id: str) -> str:
            return self.devices.get(device_id, {}).get("label", device_id)
        failed = [(label(d), why) for d, why in run["refused"]]
        failed += [(label(c["device_id"]), self._command_failure(c)) for c in cmds if c is not None and c["status"] != "acked"]
        if not failed:
            return
        some_done = any(c is not None and c["status"] == "acked" for c in cmds)
        kind = schedule_kind(item)
        if kind in ("prearrival", "checkout"):
            name = SCHEDULE_LABELS[kind].capitalize()
            head = f"{name} eseguito in parte" if some_done else f"{name} non riuscito"
        else:
            name = f"Azione programmata ({SCHEDULE_LABELS.get(kind, kind)})"
            head = f"{name} eseguita in parte" if some_done else f"{name} non riuscita"
        n = len(failed)
        count = "1 comando non riuscito" if n == 1 else f"{n} comandi non riusciti"
        details = "; ".join(f"{who}: {why}" for who, why in failed)
        self.log("system", {"type": "schedule", "schedule_id": sid}, "schedule_partial", item["run_at"], kind,
                 f"{head}: {count} ({details})", "failed", run.get("corr") or str(uuid.uuid4()))

    def _schedule_not_done(self, item: dict, correlation_id: str, why: str) -> None:
        """A scheduled action the engine refused at its time (devices or their connection unreachable, an action no
        longer valid) became «failed» without a word: now a decision says so, with the engine's reason (D-198, the
        same defect as point c of the verification of 10 November)."""
        kind = schedule_kind(item)                     # D-219: in new_value, for the BFF's notification
        self.log("system", {"type": "schedule"}, "schedule_failed", item["run_at"], kind,
                 f"Azione programmata ({SCHEDULE_LABELS.get(kind, kind)}) non eseguita: {why}", "failed",
                 correlation_id)

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
        demonstrations with the real assistant, within the cap); None keeps the keyword assistant. variants (P-72):
        apartment_id -> «vuoto» | «occupato», as the BFF last sent it (X-Demo-Variant); used when the apartment's
        engine is built: at the first call and after «Ripristina» (reset). timezones (D-177): apartment_id -> the time
        zone the BFF sends (X-Demo-Timezone, the registry's copy), the demonstration's TIMEZONE; an engine already
        built takes a new one at once."""
        self.sims: dict[str, ApartmentEngine] = {}
        self.model_for = model_for
        self.variants: dict[str, str] = {}
        self.timezones: dict[str, str] = {}

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
            tz = self.timezones.get(apartment_id)
            sim = self.sims[apartment_id] = ApartmentEngine(
                apartment_id, model=self.model_for(apartment_id) if self.model_for else None,
                variant=self.variants.get(apartment_id), settings={"TIMEZONE": tz} if tz else None)
        elif apartment_id in self.timezones:
            sim.timezone = self.timezones[apartment_id]
        sim.ensure_started()
        return sim
