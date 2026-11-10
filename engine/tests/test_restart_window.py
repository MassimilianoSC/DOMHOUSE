"""A window open across a restart of the engine (verification of 10 November 2026, point a): the wait of the rule
«Finestra aperta spegne il clima» lives in memory, and before the fix a restart lost it, so the climate stayed on with
the window open until the window was closed and opened again. Now at the start every open window waits again for the
minutes it has left since it opened (from the start, when it opened while the engine was down), and the climate goes
off when the devices can be reached. The rule's minutes run fast here (MOCK_TIME_SCALE = real seconds per minute).

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, WINDOW = "dev-clima-soggiorno", "dev-finestra-camera"
MINUTE = 0.4                                  # the rule's 5 minutes are 2 seconds


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


def stop(e):
    for task in [e.loop_task, e.consumer_task, *e.tasks]:
        if task is not None:
            task.cancel()


async def settle(e, timeout=10.0):
    end = asyncio.get_running_loop().time() + timeout
    while any(c["status"] not in core.FINAL for c in e.commands.values()):
        assert asyncio.get_running_loop().time() < end, e.commands
        await asyncio.sleep(0.02)


def turned_off_by_rule(e) -> list[dict]:
    return [c for c in e.commands.values() if c["device_id"] == CLIMA and c["action"] == "turn_off"]


def first_life(db, conn, open_minutes_ago: float | None, hold: bool = False):
    """The engine runs with the split on; the window opens (open_minutes_ago before the restart, None: not at all);
    the process dies."""
    async def main():
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False, store=SqliteStore(db))
        e.ensure_started()
        await settle(e)
        assert e.devices[CLIMA]["capabilities"]["climate"]["on"]
        if hold:
            e.set_hold(60, "comfort", ACTOR, CORR)
            await settle(e)
        if open_minutes_ago is not None:
            e.test_state({"device_id": WINDOW, "capability": "contact", "state": {"open": True}}, ACTOR, CORR)
            contact = e.devices[WINDOW]["capabilities"]["contact"]
            contact["since"] = core.iso(core.utcnow() - timedelta(seconds=open_minutes_ago * MINUTE))
            e._save_device(e.devices[WINDOW])
        stop(e)
        e.store.close()
    asyncio.run(main())


def second_life(db, conn, watch_s: float, connector_up=None):
    async def main():
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False, store=SqliteStore(db))
        if connector_up is not None:
            e.connector_up = connector_up
        e.ensure_started()
        assert e.devices[WINDOW]["capabilities"]["contact"]["open"] is True
        assert e.devices[CLIMA]["capabilities"]["climate"]["on"]
        await asyncio.sleep(watch_s)
        found = turned_off_by_rule(e)
        stop(e)
        e.store.close()
        return found
    return asyncio.run(main())


def test_open_for_a_while_before_the_restart_goes_off_after_the_minutes_left(tmp_path):
    db, conn = tmp_path / "e.db", SimulatedConnector()
    first_life(db, conn, open_minutes_ago=4.5)            # half a minute (0.2 s) left of the rule's 5
    found = second_life(db, conn, watch_s=1.0)            # well before 5 minutes from the start (2 s)
    assert len(found) == 1                                # before: never


def test_open_longer_than_the_minutes_goes_off_at_once(tmp_path):
    db, conn = tmp_path / "e.db", SimulatedConnector()
    first_life(db, conn, open_minutes_ago=30)
    assert len(second_life(db, conn, watch_s=0.5)) == 1


def test_opened_while_the_engine_was_down_waits_the_whole_minutes_from_the_start(tmp_path):
    db, conn = tmp_path / "e.db", SimulatedConnector()
    first_life(db, conn, open_minutes_ago=None)
    conn.set_state(WINDOW, "contact", {"open": True}, notify=False)     # opened with the engine down
    assert second_life(db, conn, watch_s=1.0) == []                     # not yet: from the start, 5 minutes
    db2, conn2 = tmp_path / "f.db", SimulatedConnector()
    first_life(db2, conn2, open_minutes_ago=None)
    conn2.set_state(WINDOW, "contact", {"open": True}, notify=False)
    assert len(second_life(db2, conn2, watch_s=2.8)) == 1               # after them


def test_with_the_devices_unreachable_it_waits_for_them(tmp_path):
    db, conn = tmp_path / "e.db", SimulatedConnector()
    first_life(db, conn, open_minutes_ago=30)
    up = {"now": False}

    async def main():
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False, store=SqliteStore(db))
        e.connector_up = lambda: up["now"]
        e.ensure_started()
        await asyncio.sleep(0.6)
        before = list(turned_off_by_rule(e))              # nothing yet, and no error
        up["now"] = True
        await asyncio.sleep(1.5)
        after = turned_off_by_rule(e)
        stop(e)
        e.store.close()
        return before, after
    before, after = asyncio.run(main())
    assert before == [] and len(after) == 1


def test_during_a_hold_nothing_at_the_start(tmp_path):
    db, conn = tmp_path / "e.db", SimulatedConnector()
    first_life(db, conn, open_minutes_ago=30, hold=True)
    assert second_life(db, conn, watch_s=0.8) == []        # the end of the hold looks again (R7, test_hold_window)
