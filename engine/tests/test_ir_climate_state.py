"""D14 (P-83 review, gravity 2): the state of an infrared split. (1) A start whose effect came after the command's
confirmation window ended in «timeout» and left climate.on False although its meter drew 870 W: a second «Accendi» was
never confirmed (baseline 870) and the window rule skipped it (it believed it off). (2) climate was not among the
engine's own fields kept across a restart, while an infrared split reports none of them (connector-v2 §2.3): after a
restart on False and setpoint 21, invented. Now a split confirmed by a meter follows that meter when no command of its
is running, and an infrared split's state survives a restart (a climate that reports it keeps its own report).
Scenarios of the independent verification (V-D14/test_d14.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import confirmation, core
from engine.connector import simulated
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
SPLIT, METER, WINDOW = "dev-clima-soggiorno", "dev-misura-clima", "dev-finestra-camera"


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    for name in ("SENT_AFTER_S", "VERIFYING_AFTER_S", "OUTCOME_AFTER_S"):
        monkeypatch.setattr(simulated, name, 0)
    monkeypatch.setattr(confirmation, "CONFIRM_UNTIL_S", 0.5)


async def wait_final(engine, cmd):
    while engine.commands[cmd["command_id"]]["status"] not in core.FINAL:
        await asyncio.sleep(0.02)
    await asyncio.sleep(0.05)
    return engine.commands[cmd["command_id"]]


def split_cmds(engine):
    return [c for c in engine.commands.values() if c["device_id"] == SPLIT]


def stop(engine):
    for task in [engine.loop_task, engine.consumer_task, *engine.tasks]:
        if task is not None:
            task.cancel()


def test_a_late_start_is_seen_through_the_meter_and_the_window_rule_turns_it_off():
    async def main():
        conn = SimulatedConnector(variant=1)              # split off, meter 0 W
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
        e.ensure_started()
        conn.lose_infrared(SPLIT)
        first = await wait_final(e, e.create_command(SPLIT, {"capability": "climate", "action": "set_climate",
                                                             "params": {"on": True}}, ACTOR, CORR))
        assert (first["status"], first["reason"]) == ("timeout", "no_confirmation")
        conn._devices[SPLIT].capabilities["climate"]["on"] = True       # it started after the window
        conn.set_state(METER, "power_meter", {"watts": 870})
        await asyncio.sleep(0.2)
        assert e.devices[SPLIT]["capabilities"]["climate"]["on"] is True       # follows its meter
        conn.set_state(WINDOW, "contact", {"open": True})
        await asyncio.sleep(0.2)
        before = len(split_cmds(e))
        e._window_turn_off(WINDOW, "Finestra camera aperta da oltre 5 minuti")
        await asyncio.sleep(0.2)
        assert len(split_cmds(e)) - before == 1 and SPLIT in e.window_off
        stop(e)
    asyncio.run(main())


def test_the_meter_at_zero_turns_the_engines_copy_off(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "0.05")
    async def main():
        conn = SimulatedConnector(variant=1)
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False, settings={"REMOTE_OFF_MINUTES": 1})
        e.ensure_started()
        await wait_final(e, e.create_command(SPLIT, {"capability": "climate", "action": "set_climate",
                                                     "params": {"on": True}}, ACTOR, CORR))
        assert e.devices[SPLIT]["capabilities"]["climate"]["on"] is True
        conn._devices[SPLIT].capabilities["climate"]["on"] = False      # switched off by its own remote
        conn.set_state(METER, "power_meter", {"watts": 0})
        await asyncio.sleep(0.02)
        assert e.devices[SPLIT]["capabilities"]["climate"]["on"] is True        # P-90 S1: after REMOTE_OFF_MINUTES
        await asyncio.sleep(0.1)
        e._remote_off_check()
        assert e.devices[SPLIT]["capabilities"]["climate"]["on"] is False
        stop(e)
    asyncio.run(main())


def ir_connector(world_on: bool) -> SimulatedConnector:
    """A connector as connector-v2.md §2.3 asks for an IR split: climate reports only the catalog's fields."""
    conn = SimulatedConnector(variant=1)
    caps = conn._devices[SPLIT].capabilities["climate"]
    for k in ("on", "mode", "setpoint", "fan"):
        caps.pop(k)
    if world_on:
        conn._devices[METER].capabilities["power_meter"]["watts"] = 870
    return conn


def test_an_infrared_splits_state_survives_a_restart(tmp_path):
    db = tmp_path / "engine.db"

    async def first_life():
        conn = ir_connector(world_on=False)
        conn._devices[SPLIT].capabilities["climate"].update(on=False, mode="heat", setpoint=21, fan="auto")
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False, store=SqliteStore(db))
        e.ensure_started()
        cmd = await wait_final(e, e.create_command(SPLIT, {"capability": "climate", "action": "set_climate",
                                                           "params": {"on": True, "mode": "heat", "setpoint": 22}},
                                                   ACTOR, CORR))
        assert cmd["status"] == "acked" and e.devices[SPLIT]["capabilities"]["climate"]["on"] is True
        stop(e)
        e.store.close()
    asyncio.run(first_life())

    async def second_life():
        e = core.ApartmentEngine("apt-prova-01", ir_connector(world_on=True), seed=False, store=SqliteStore(db))
        e.ensure_started()
        await asyncio.sleep(0.2)
        climate = e.devices[SPLIT]["capabilities"]["climate"]
        assert climate["on"] is True and climate["setpoint"] == 22 and climate["mode"] == "heat"
        e.connector.set_state(WINDOW, "contact", {"open": True})
        await asyncio.sleep(0.2)
        before = len(split_cmds(e))
        e._window_turn_off(WINDOW, "Finestra camera aperta da oltre 5 minuti")
        await asyncio.sleep(0.2)
        assert len(split_cmds(e)) - before == 1
        stop(e)
        e.store.close()
    asyncio.run(second_life())
