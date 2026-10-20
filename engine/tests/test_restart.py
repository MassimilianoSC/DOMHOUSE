"""What a restart interrupts (P-60 step 3): commands half way, pending assistant requests, scheduled actions due while
the engine was down, kwh_today and the hourly telemetry, and the retention clean-up (D-94).

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import UTC, datetime, timedelta

from engine import core
from engine.connector.interface import CommandResult, ConnectorStatus, DeviceInfo, Room
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"


class MeterConnector:
    """One socket with a power meter that reports the raw counter (energy_total_wh); its commands never answer."""
    api_version = "1"

    def __init__(self, total_wh: float):
        self.total_wh = total_wh

    async def start(self):
        pass

    async def stop(self):
        pass

    def rooms(self):
        return [Room("camera", "Camera")]

    def devices(self):
        return [DeviceInfo("dev-presa", "Presa", "camera", True, datetime.now(UTC),
                           {"switch": {"on": False}, "power_meter": {"watts": 0, "energy_total_wh": self.total_wh}})]

    def status(self):
        return ConnectorStatus(True, 1, None)

    async def changes(self):
        await asyncio.Event().wait()
        yield  # pragma: no cover

    async def execute(self, cmd, on_progress):
        on_progress("sent")
        await asyncio.sleep(3600)
        return CommandResult("confirmed")  # pragma: no cover


def stop(engine):
    for task in [engine.loop_task, engine.consumer_task, *engine.tasks]:
        if task is not None:
            task.cancel()


def test_command_half_way_is_failed_with_its_decision(tmp_path):
    db = tmp_path / "engine.db"

    async def first_life():
        engine = core.ApartmentEngine("apt-prova-01", MeterConnector(1000), seed=False, store=SqliteStore(db))
        engine.ensure_started()
        cmd = engine.create_command("dev-presa", {"capability": "switch", "action": "turn_on"}, ACTOR, CORR)
        while engine.commands[cmd["command_id"]]["status"] != "sent":
            await asyncio.sleep(0.02)
        stop(engine)                         # the process dies here
        engine.store.close()
        return cmd["command_id"]
    command_id = asyncio.run(first_life())

    engine = core.ApartmentEngine("apt-prova-01", MeterConnector(1000), seed=False, store=SqliteStore(db))
    cmd = engine.commands[command_id]
    assert (cmd["status"], cmd["reason"]) == ("failed", "internal_error")
    decision = engine.decisions[-1]
    assert (decision["command_id"], decision["outcome"]) == (command_id, "failed")
    assert "riavviato" in decision["reasoning"]
    updates = [e for e in engine.events if e["event"] == "command.updated" and e["data"]["command_id"] == command_id]
    assert updates[-1]["data"]["status"] == "failed"     # the app hears it on the stream
    engine.store.close()


def test_pending_assistant_request_is_failed(tmp_path):
    db = tmp_path / "engine.db"

    async def first_life():
        engine = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
        ask = engine.create_ask({"text": "spegni il clima"}, ACTOR, CORR)
        stop(engine)                          # before the answer (1 s)
        engine.store.close()
        return ask["ask_id"]
    ask_id = asyncio.run(first_life())
    engine = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    assert (engine.asks[ask_id]["status"], engine.asks[ask_id]["reason"]) == ("failed", "internal_error")
    engine.store.close()


def test_schedule_due_while_down_runs_if_recent_else_missed(tmp_path):
    db = tmp_path / "engine.db"
    first = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    now = core.utcnow()
    recent = first.add_schedule(now - timedelta(minutes=10), {"type": "apartment_mode", "mode": "eco"}, "manual", "manual")
    old = first.add_schedule(now - timedelta(hours=2), {"type": "apartment_mode", "mode": "comfort"}, "manual", "manual")
    first.store.close()

    second = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    assert second.schedule[old["schedule_id"]]["status"] == "failed"
    missed = [d for d in second.decisions if d["action"] == "schedule_missed"]
    assert len(missed) == 1 and missed[0]["outcome"] == "failed" and old["run_at"] in missed[0]["reasoning"]
    assert second.schedule[recent["schedule_id"]]["status"] == "planned"

    async def tick():
        second.tick()                         # the first tick runs the recent one, as before
    asyncio.run(tick())
    assert second.schedule[recent["schedule_id"]]["status"] == "done" and second.mode == "eco"
    second.store.close()


def test_kwh_today_and_telemetry_go_on_after_a_restart(tmp_path):
    db = tmp_path / "engine.db"
    first = core.ApartmentEngine("apt-prova-01", MeterConnector(1000), seed=False, store=SqliteStore(db))
    from engine.connector.interface import StateChange
    first._apply_change(StateChange("dev-presa", "state", datetime.now(UTC), capability="power_meter",
                                    state={"watts": 40, "energy_total_wh": 1500}))
    assert first.devices["dev-presa"]["capabilities"]["power_meter"]["kwh_today"] == 0.5
    first.store.close()

    second = core.ApartmentEngine("apt-prova-01", MeterConnector(1600), seed=False, store=SqliteStore(db))
    pm = second.devices["dev-presa"]["capabilities"]["power_meter"]
    assert pm["kwh_today"] == 0.6 and "energy_total_wh" not in pm      # 500 Wh before, 100 Wh while it was down
    assert sum(wh for _, _, wh in second.store.telemetry("dev-presa")) == 600
    second.store.close()


def test_retention_clean_up(tmp_path):
    db = tmp_path / "engine.db"
    first = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    long_ago = core.utcnow() - timedelta(days=31 * 25)                   # beyond the 24 months of D-94
    old = first.log("system", {"type": "apartment"}, "set_mode", None, "eco", "vecchia", "applied", CORR, ts=long_ago)
    new = first.log("system", {"type": "apartment"}, "set_mode", None, "eco", "recente", "applied", CORR)
    first.store.add_telemetry("dev-presa-camera", core.hour_of(long_ago), 100)
    first.store.add_telemetry("dev-presa-camera", core.hour_of(core.utcnow()), 50)
    first.store.close()

    second = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
    ids = {d["decision_id"] for d in second.decisions}
    assert old["decision_id"] not in ids and new["decision_id"] in ids
    assert old["decision_id"] not in dict(second.store.all("decisions"))
    assert [wh for _, _, wh in second.store.telemetry("dev-presa-camera")] == [50]
    second.store.close()
