"""The engine's state on SQLite (P-60 step 3): after a restart on the same engine.db the app sees the same apartment,
and ids (events, commands, decisions) keep growing. The devices keep their state across the restart, as real ones
do: the second engine gets the same connector.

Run: python -m pytest engine/tests -q
"""
import asyncio
import copy
from datetime import timedelta

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import MemoryStore, SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"


def corr(n: int) -> str:
    return f"2f0a6a4e-7a5d-4b0b-9a5e-{n:012d}"


def stop(engine):
    for task in [engine.loop_task, engine.consumer_task, *engine.tasks]:
        if task is not None:
            task.cancel()


async def settle(engine, timeout=10.0):
    """Commands, assistant requests and the thermostat's relay switches (not commands) all done, their changes in."""
    end = asyncio.get_running_loop().time() + timeout
    while any(c["status"] not in core.FINAL for c in engine.commands.values()) or \
            any(a["status"] == "pending" for a in engine.asks.values()) or engine.relay_busy:
        assert asyncio.get_running_loop().time() < end
        await asyncio.sleep(0.05)
    engine.last_regulation = float("inf")               # no new switch while the test reads the state
    await asyncio.sleep(0.1)                            # the last changes reach the engine


def view(engine) -> dict:
    """Everything the app can read, minus what is "now" by definition."""
    apartment = {k: v for k, v in engine.apartment().items() if k != "updated_at"}
    return {
        "apartment": apartment, "devices": copy.deepcopy(list(engine.devices.values())), "rooms": engine.rooms,
        "rules": engine.ruleset(), "schedule": engine.list_schedule(), "approvals": engine.list_approvals("all"),
        "decisions": engine.list_decisions({"limit": "200"}), "commands": copy.deepcopy(engine.commands),
        "asks": copy.deepcopy(engine.asks), "queue": copy.deepcopy(engine.approval_queue),
        "events": [(e["id"], e["event"]) for e in engine.events],
        "idem": {k: v[1:] for k, v in engine.idem.items()}, "processed": copy.deepcopy(engine.processed_events),
    }


def scenario(engine):
    """A bit of everything that changes the state."""
    async def main():
        engine.ensure_started()
        engine.create_command("dev-presa-camera", {"capability": "switch", "action": "turn_on"}, ACTOR, corr(1))
        engine.set_hold(30, "eco", ACTOR, corr(2))
        engine.update_device("dev-presa-camera", {"label": "Stufetta"}, ACTOR, corr(3))
        engine.update_rules({"rules": [{"rule_id": "setpoint_limits", "params": {"min": 17}},
                                       {"rule_id": "prearrival", "params": {"hours_before": 3}}]}, ACTOR, corr(4))
        run_at = core.iso(core.utcnow() + timedelta(days=2))
        item = engine.create_schedule({"run_at": run_at, "action": {"type": "apartment_mode", "mode": "eco"}},
                                      ACTOR, corr(5))
        engine.move_schedule(item["schedule_id"], {"run_at": core.iso(core.utcnow() + timedelta(days=3))}, ACTOR, corr(6))
        later = engine.create_schedule({"run_at": run_at, "action": {"type": "apartment_mode", "mode": "comfort"}},
                                       ACTOR, corr(7))
        engine.cancel_schedule(later["schedule_id"], ACTOR, corr(8))
        ci = core.utcnow() + timedelta(days=5)
        engine.ingest_booking({"event_id": "evt-prova-1", "type": "booking_created", "booking_id": "bk-prova",
                               "checkin_at": core.iso(ci), "checkout_at": core.iso(ci + timedelta(days=2)),
                               "source": "manual", "ts": core.iso(core.utcnow())}, corr(9))
        engine.trigger_approval(corr(10))
        engine.trigger_approval(corr(11))                      # queued behind the first
        engine.trigger_approval(corr(16))                      # still queued at the end
        first = engine.pending_approval()
        engine.decide(first["approval_id"], {"decision": "reject", "note": "no"}, ACTOR, corr(12))
        engine.create_ask({"text": "porta il soggiorno a 22 gradi"}, ACTOR, corr(13))
        engine.remember("POST /apartment/mode " + corr(14), 202, {"mode": "eco", "command_ids": []})
        engine.test_state({"device_id": "dev-finestra-camera", "capability": "contact", "state": {"open": True}},
                          ACTOR, corr(15))
        await settle(engine)
    asyncio.run(main())


def test_restart_on_the_same_database_shows_the_same_apartment(tmp_path):
    db = tmp_path / "engine.db"
    conn = SimulatedConnector()
    first = core.ApartmentEngine("apt-prova-01", conn, seed=True, store=SqliteStore(db))
    assert not first.restored
    scenario(first)
    stop(first)
    before = view(first)
    last_event, counter = int(first.events[-1]["id"]), first.counter
    first.store.close()

    second = core.ApartmentEngine("apt-prova-01", conn, seed=True, store=SqliteStore(db))
    assert second.restored
    after = view(second)
    for key in before:
        assert after[key] == before[key], key
    # ids keep growing: never one given twice, Last-Event-ID still meaningful
    env = second.emit("apartment.changed", second.apartment(), CORR)
    assert int(env["id"]) == last_event + 1
    assert second.next_id("cmd") == f"cmd-{counter + 1:04x}"
    second.store.close()


def test_climate_limits_follow_the_saved_rules(tmp_path):
    db = tmp_path / "engine.db"
    conn = SimulatedConnector()
    first = core.ApartmentEngine("apt-prova-01", conn, seed=False, store=SqliteStore(db))
    first.update_rules({"rules": [{"rule_id": "setpoint_limits", "params": {"min": 18, "max": 22}}]}, ACTOR, CORR)
    first.store.close()
    second = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    climate = second.devices["dev-clima-soggiorno"]["capabilities"]["climate"]
    assert (climate["setpoint_min"], climate["setpoint_max"]) == (18, 22)
    second.store.close()


def test_memory_store_keeps_the_demonstration_as_before():
    """The BFF's demonstration apartments: same numbering as always (first event 4101), seeded at every start."""
    engine = core.ApartmentEngine("apt-rimini-01")
    assert isinstance(engine.store, MemoryStore) and not engine.restored
    assert engine.bookings and engine.decisions          # the demonstration's history
    assert engine.emit("apartment.changed", {}, CORR)["id"] == "4101"
