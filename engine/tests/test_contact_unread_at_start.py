"""D15 with P7a-2 (P-83 review, gravity 2): after a restart a window contact the connector has not read yet (a BLU sensor
behind its bridge: open missing until the bridge answers, or never while the bridge is offline) was given open False
and «since» now by the engine itself; with what the window rule had turned off waiting, the first regulation brought
the boiler back («Finestra chiusa») with the window really open, without a time limit if the bridge stayed offline.
Now a contact the connector does not report keeps its saved open and since until a reading arrives: an open window
stays open across the restart. The independent verification used the BLU fakes of PR #7 (V-P7a-2/prova_p7a2.py), not
in main yet; the same situation here with the simulated connector made silent on the contact.

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
BOILER, WINDOW, SENSOR = "dev-caldaia", "dev-finestra-camera", "dev-ambiente-soggiorno"
MINUTE = 0.2


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


async def settle(e, timeout=20.0):
    end = asyncio.get_running_loop().time() + timeout
    while any(c["status"] not in core.FINAL for c in e.commands.values()) or e.relay_busy:
        assert asyncio.get_running_loop().time() < end, e.commands
        await asyncio.sleep(0.02)


def stop(e) -> None:
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


def silent_on_the_contact() -> SimulatedConnector:
    """As a BLU contact behind a bridge that has not answered yet: the device is listed, its open is not."""
    conn = SimulatedConnector()
    conn._devices[WINDOW].capabilities["contact"].pop("open", None)
    return conn


def test_an_open_window_not_read_yet_after_the_restart_keeps_the_boiler_off(tmp_path):
    db = tmp_path / "engine.db"

    async def first_life():
        e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, store=SqliteStore(db))
        e.ensure_started()
        e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": 15}}, ACTOR, CORR)
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await settle(e)
        e.test_state({"device_id": WINDOW, "capability": "contact", "state": {"open": True}}, ACTOR, CORR)
        await asyncio.sleep(7 * MINUTE)
        await settle(e)
        assert BOILER in e.window_off and not e.devices[BOILER]["capabilities"]["heating"]["on"]
        stop(e)
        e.store.close()
    asyncio.run(first_life())

    async def second_life():
        conn = silent_on_the_contact()
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False, store=SqliteStore(db))
        e.ensure_started()
        assert e.devices[WINDOW]["capabilities"]["contact"]["open"] is True      # the saved value, not invented
        await asyncio.sleep(10 * MINUTE)                                           # several regulations
        await settle(e)
        assert not e.devices[BOILER]["capabilities"]["heating"]["on"] and not e.relay.get(BOILER)
        assert not any((d["reasoning"] or "").startswith("Finestra chiusa") for d in e.decisions
                       if d["action"] == "window_restore")
        # the reading arrives: the window is really closed now; the boiler comes back after the usual minute
        e._apply_change(core.StateChange(WINDOW, "state", core.utcnow(), capability="contact", state={"open": False}))
        await asyncio.sleep(10 * MINUTE)
        await settle(e)
        assert e.devices[BOILER]["capabilities"]["heating"]["on"]
        stop(e)
        e.store.close()
    asyncio.run(second_life())
