"""The engine's real health and its heartbeat (P-60 step 10, D-104): engine.db that does not answer is "down" (503), an
inner loop that stopped ticking is "degraded", the assistant is reported as it is, and a log line "engine alive"
comes every HEARTBEAT_S (its absence for 10 minutes is the "silent engine" alert).

Run: python -m pytest engine/tests -q
"""
import asyncio
import time

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore


def test_engine_db_that_does_not_answer_is_down(tmp_path):
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(tmp_path / "engine.db"))
    code, body = e.health()
    assert (code, body["status"], body["database"]) == (200, "ok", {"status": "ok"})
    e.store.close()                                                     # the database is gone
    code, body = e.health()
    assert (code, body["status"], body["database"]) == (503, "down", {"status": "error"})


def test_a_stuck_inner_loop_is_degraded():
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    assert e.loop_alive() and e.health()[1]["status"] == "ok"           # not started yet: nothing to say

    async def main():
        e.ensure_started()
        e.tick()
        assert e.loop_alive() and e.health()[1]["status"] == "ok"
        e.last_tick = time.monotonic() - core.LOOP_STALE_S - 1          # no tick for longer than allowed
        assert not e.loop_alive() and e.health() [0] == 200 and e.health()[1]["status"] == "degraded"
        e.loop_task.cancel()
    asyncio.run(main())


def test_the_assistant_as_it_is():
    class Model:
        pass
    assert core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, model=Model()).health()[1][
        "model_provider"] == {"status": "ok", "provider": "bff-gateway"}
    assert core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False).health()[1]["model_provider"] == {
        "status": "ok", "provider": "mock-keywords"}
    assert core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, simulated=False).health()[1][
        "model_provider"] == {"status": "unknown", "provider": "none"}


def test_one_heartbeat_every_five_minutes(monkeypatch):
    """The clock is the engine's own (time.monotonic, counted from the machine's start): the CI's runner, just switched
    on, had it under 300 s and the first beat did not come (red of the lot 23 push). Here it starts at 120 s."""
    seen = []
    monkeypatch.setattr(core.logs, "info", lambda msg, **fields: seen.append((msg, fields)))
    clock = {"now": 120.0}                                              # a machine switched on two minutes ago
    monkeypatch.setattr(core.time, "monotonic", lambda: clock["now"])
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)

    async def main():
        e.tick()                                                        # the first tick beats at once
        clock["now"] += 1
        e.tick()                                                        # a second later: no new beat
        clock["now"] += core.HEARTBEAT_S
        e.tick()                                                        # five minutes later: the second beat
    asyncio.run(main())
    beats = [f for msg, f in seen if msg == "engine alive"]
    assert len(beats) == 2
    assert beats[0] == {"apartment_id": "apt-prova-01", "connector": "up", "devices_online": len(e.devices),
                        "devices_total": len(e.devices), "commands_running": 0, "database": "ok"}
