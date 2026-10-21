"""Where the engine keeps its state (P-60 step 3): SQLite for the engine as a service (/data/<apartment_id>/engine.db,
WAL), memory for the BFF's demonstration apartments. Same interface, so engine/core.py has one code path.

Three shapes of data:
- meta: single values by key (the apartment's mode and hold, the rules, the id counter, the approval queue, ...);
- documents: JSON by (collection, id), kept in creation order (an update does not move them): commands, decisions,
  schedule, bookings, processed booking events, approvals, assistant requests, devices, idempotency keys, meters;
  each with the moment it may be deleted (expire_at, epoch seconds) for the retention clean-up;
- events: the stream, with an id that keeps growing across restarts (AUTOINCREMENT), kept one hour for Last-Event-ID.
Plus the hourly telemetry of the power meters (Wh per device and hour).

One writer: the engine's event loop. Every write is committed at once (WAL, synchronous=NORMAL): a crash loses at
most the last instant, never leaves a half-written record.
"""
import json
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path

SCHEMA_VERSION = 1
FIRST_EVENT_ID = 4100        # the first event is 4101, as the demonstration apartments have always numbered them

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS docs (
    collection TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL, expire_at REAL,
    PRIMARY KEY (collection, id));
CREATE INDEX IF NOT EXISTS docs_expire ON docs (expire_at) WHERE expire_at IS NOT NULL;
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, t REAL NOT NULL, data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS events_t ON events (t);
CREATE TABLE IF NOT EXISTS telemetry (
    device_id TEXT NOT NULL, hour TEXT NOT NULL, wh REAL NOT NULL, PRIMARY KEY (device_id, hour));
CREATE INDEX IF NOT EXISTS telemetry_hour ON telemetry (hour);
"""


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class MemoryStore:
    """The demonstration apartments' store: nothing survives the process, as before step 3."""

    def __init__(self):
        self._meta: dict[str, object] = {}
        self._docs: dict[str, dict[str, tuple[object, float | None]]] = {}
        self._events: list[tuple[int, float, dict]] = []
        self._next_event = FIRST_EVENT_ID
        self._telemetry: dict[tuple[str, str], float] = {}

    def close(self) -> None:
        pass

    # meta
    def get_meta(self, key: str, default=None):
        return json.loads(_dumps(self._meta[key])) if key in self._meta else default

    def put_meta(self, key: str, value) -> None:
        self._meta[key] = json.loads(_dumps(value))

    # documents
    def put(self, collection: str, doc_id: str, data, expire_at: float | None = None) -> None:
        self._docs.setdefault(collection, {})[doc_id] = (json.loads(_dumps(data)), expire_at)

    def delete(self, collection: str, doc_id: str) -> None:
        self._docs.get(collection, {}).pop(doc_id, None)

    def all(self, collection: str) -> list[tuple[str, object]]:
        return [(k, json.loads(_dumps(v))) for k, (v, _) in self._docs.get(collection, {}).items()]

    def purge_expired(self, now: float) -> int:
        gone = 0
        for docs in self._docs.values():
            for k in [k for k, (_, exp) in docs.items() if exp is not None and exp <= now]:
                del docs[k]
                gone += 1
        return gone

    # events
    def append_event(self, t: float, data: dict) -> int:
        self._next_event += 1
        self._events.append((self._next_event, t, json.loads(_dumps(data))))
        return self._next_event

    def events_since(self, t: float) -> list[tuple[int, float, dict]]:
        return [(i, tt, json.loads(_dumps(d))) for i, tt, d in self._events if tt >= t]

    def prune_events(self, before: float) -> None:
        self._events = [e for e in self._events if e[1] >= before]

    def ping(self) -> bool:
        """P-60 step 10: the store answers (always, in memory)."""
        return True

    # telemetry
    def add_telemetry(self, device_id: str, hour: str, wh: float) -> None:
        self._telemetry[(device_id, hour)] = self._telemetry.get((device_id, hour), 0.0) + wh

    def telemetry(self, device_id: str | None = None) -> list[tuple[str, str, float]]:
        return sorted((d, h, wh) for (d, h), wh in self._telemetry.items() if device_id in (None, d))

    def telemetry_between(self, from_hour: str, to_hour: str) -> list[tuple[str, str, float]]:
        """The hours from_hour <= hour < to_hour (GET /energy, P-60 step 6)."""
        return sorted((d, h, wh) for (d, h), wh in self._telemetry.items() if from_hour <= h < to_hour)

    def purge_telemetry(self, before_hour: str) -> None:
        self._telemetry = {k: v for k, v in self._telemetry.items() if k[1] >= before_hour}


class SqliteStore(MemoryStore):
    """The engine's store on disk. The folder is created if missing; the schema version is checked at open."""

    def __init__(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"engine.db has schema {version}, this engine knows up to {SCHEMA_VERSION}")
        self.db.executescript(_SCHEMA)
        if version == 0:
            self.db.execute("INSERT INTO sqlite_sequence (name, seq) SELECT 'events', ? "
                            "WHERE NOT EXISTS (SELECT 1 FROM sqlite_sequence WHERE name = 'events')", (FIRST_EVENT_ID,))
            self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        self.db.close()

    def get_meta(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def put_meta(self, key: str, value) -> None:
        self.db.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                        (key, _dumps(value)))

    def put(self, collection: str, doc_id: str, data, expire_at: float | None = None) -> None:
        # ON CONFLICT ... DO UPDATE keeps the rowid, hence the creation order of the collection
        self.db.execute("INSERT INTO docs (collection, id, data, expire_at) VALUES (?, ?, ?, ?) "
                        "ON CONFLICT (collection, id) DO UPDATE SET data = excluded.data, expire_at = excluded.expire_at",
                        (collection, doc_id, _dumps(data), expire_at))

    def delete(self, collection: str, doc_id: str) -> None:
        self.db.execute("DELETE FROM docs WHERE collection = ? AND id = ?", (collection, doc_id))

    def all(self, collection: str) -> list[tuple[str, object]]:
        rows = self.db.execute("SELECT id, data FROM docs WHERE collection = ? ORDER BY rowid", (collection,))
        return [(i, json.loads(d)) for i, d in rows]

    def purge_expired(self, now: float) -> int:
        return self.db.execute("DELETE FROM docs WHERE expire_at IS NOT NULL AND expire_at <= ?", (now,)).rowcount

    def append_event(self, t: float, data: dict) -> int:
        return self.db.execute("INSERT INTO events (t, data) VALUES (?, ?)", (t, _dumps(data))).lastrowid

    def events_since(self, t: float) -> list[tuple[int, float, dict]]:
        rows = self.db.execute("SELECT id, t, data FROM events WHERE t >= ? ORDER BY id", (t,))
        return [(i, tt, json.loads(d)) for i, tt, d in rows]

    def prune_events(self, before: float) -> None:
        self.db.execute("DELETE FROM events WHERE t < ?", (before,))

    def ping(self) -> bool:
        """P-60 step 10: engine.db answers a read (GET /health says "database": "error" otherwise)."""
        try:
            return self.db.execute("SELECT 1").fetchone() == (1,)
        except Exception:
            return False

    def add_telemetry(self, device_id: str, hour: str, wh: float) -> None:
        self.db.execute("INSERT INTO telemetry (device_id, hour, wh) VALUES (?, ?, ?) "
                        "ON CONFLICT (device_id, hour) DO UPDATE SET wh = wh + excluded.wh", (device_id, hour, wh))

    def telemetry(self, device_id: str | None = None) -> list[tuple[str, str, float]]:
        if device_id is None:
            rows: Iterable = self.db.execute("SELECT device_id, hour, wh FROM telemetry ORDER BY device_id, hour")
        else:
            rows = self.db.execute("SELECT device_id, hour, wh FROM telemetry WHERE device_id = ? ORDER BY hour",
                                   (device_id,))
        return [tuple(r) for r in rows]

    def telemetry_between(self, from_hour: str, to_hour: str) -> list[tuple[str, str, float]]:
        rows = self.db.execute("SELECT device_id, hour, wh FROM telemetry WHERE hour >= ? AND hour < ? "
                               "ORDER BY device_id, hour", (from_hour, to_hour))
        return [tuple(r) for r in rows]

    def purge_telemetry(self, before_hour: str) -> None:
        self.db.execute("DELETE FROM telemetry WHERE hour < ?", (before_hour,))


def now_epoch() -> float:
    return time.time()
