"""A scheduled action that started but whose commands did not all succeed (D-219, addition 2 of the client): before, the
pre-arrival was «done» even when the boiler had refused, and nobody knew the guest would find the house cold. Now, when
the last command of the action is over and at least one did not succeed, the decision schedule_partial says which and
why: «Pre-arrivo eseguito in parte: 1 comando non riuscito (Caldaia: …)». The commands never sent (connector down) count
too; a climate start that waited for the compressor's pause belongs to the action, and the decision waits for it. The
index command -> action survives a restart. And the start after the pause stays the mode's (D-169): before, it counted
as a person's and comfort no longer regulated that climate.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

import pytest

from engine import core
from engine.connector.interface import CommandResult
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, BOILER, SENSOR = "dev-clima-soggiorno", "dev-caldaia", "dev-ambiente-soggiorno"
MINUTE = 1.0          # the compressor's 3 minutes are 3 s: longer than a command


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


async def settle(e, timeout=15.0):
    end = asyncio.get_running_loop().time() + timeout
    while any(c["status"] not in core.FINAL for c in e.commands.values()) or e.relay_busy:
        assert asyncio.get_running_loop().time() < end, e.commands
        await asyncio.sleep(0.02)


def stop(e) -> None:
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


def started(store=None, connector=None) -> core.ApartmentEngine:
    e = core.ApartmentEngine("apt-prova-01", connector or SimulatedConnector(), seed=False,
                             **({"store": store} if store else {}))
    e.ensure_started()
    e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": 15}}, ACTOR, CORR)
    return e


def due(e, kind: str, action: dict, source: str = "booking") -> dict:
    return e.add_schedule(core.utcnow() - timedelta(seconds=1), action, kind, source)


COMFORT = {"type": "apartment_mode", "mode": "comfort"}
EMPTY = {"type": "apartment_mode", "mode": "empty"}


def refuse(e, device_id: str, reason: str = "device_rejected") -> None:
    """The device refuses every command (the connector's answer, as a real Shelly that says no)."""
    real = e.connector.execute

    async def execute(cmd, on_progress):
        if cmd.device_id != device_id:
            return await real(cmd, on_progress)
        await asyncio.sleep(0.05)
        on_progress("sent")
        return CommandResult("failed", reason)
    e.connector.execute = execute


async def just_off(e) -> None:
    """The climate has just been turned off for real (comfort, then eco): its compressor's pause starts now."""
    for mode in ("comfort", "eco"):
        e.set_mode(mode, ACTOR, CORR, "prova")
        await settle(e)
    assert not e.devices[CLIMA]["capabilities"]["climate"]["on"] and e.compressor_wait(CLIMA) > 1.5 * MINUTE


def partial(e) -> list[tuple]:
    return [(d["actor"], d["target"], d["action"], d["new_value"], d["outcome"], d["reasoning"])
            for d in e.decisions if d["action"] == "schedule_partial"]


def test_a_prearrival_with_a_command_refused_says_it_once_when_the_last_is_over():
    async def main():
        e = started()
        refuse(e, BOILER)
        item = due(e, "prearrival", COMFORT)
        e.tick()
        early = partial(e)                                          # the commands are still running
        await settle(e)
        await asyncio.sleep(0.05)
        e.tick()
        stop(e)
        return e, item, early
    e, item, early = asyncio.run(main())
    assert early == []
    assert len(e.schedule[item["schedule_id"]]["command_ids"]) == 2   # boiler and climate
    assert partial(e) == [("system", {"type": "schedule", "schedule_id": item["schedule_id"]}, "schedule_partial",
                           "prearrival", "failed",
                           "Pre-arrivo eseguito in parte: 1 comando non riuscito "
                           "(Caldaia: Il dispositivo ha rifiutato il comando)")]
    assert e.schedule_open == {} and e.command_schedule == {}


def test_all_commands_done_no_decision():
    async def main():
        e = started()
        due(e, "prearrival", COMFORT)
        e.tick()
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert partial(e) == [] and e.schedule_open == {}


def test_a_checkout_with_every_command_refused_and_one_not_even_sent(monkeypatch):
    async def main():
        e = started()
        due(e, "prearrival", COMFORT)
        e.tick()
        await settle(e)
        refuse(e, CLIMA, "device_offline")
        refuse(e, BOILER)
        item = due(e, "checkout", {"type": "apartment_mode", "mode": "eco"})
        e.tick()
        await settle(e)
        stop(e)
        return e, item
    e, item = asyncio.run(main())
    [row] = partial(e)
    assert row[3] == "checkout"
    assert row[5] == ("Check-out non riuscito: 2 comandi non riusciti (Climatizzatore soggiorno: Il dispositivo è andato "
                      "offline durante la verifica; Caldaia: Il dispositivo ha rifiutato il comando)")


def test_the_connector_down_the_commands_never_sent_are_counted(monkeypatch):
    async def main():
        e = started()
        monkeypatch.setenv("DOMOTICA_TEST_CONNECTOR_DOWN", "1")
        item = due(e, "prearrival", COMFORT)
        e.tick()
        stop(e)
        return e, item
    e, item = asyncio.run(main())
    assert e.schedule[item["schedule_id"]]["status"] == "done"   # the mode is set: the action ran
    why = "Collegamento ai dispositivi non disponibile; riprova quando torna"
    assert [r[5] for r in partial(e)] == [
        f"Pre-arrivo non riuscito: 2 comandi non riusciti (Climatizzatore soggiorno: {why}; Caldaia: {why})"]


def test_a_device_offline_at_the_time_is_a_command_not_done():
    """The most likely case: the boiler is offline when the pre-arrival comes. Before, the mode skipped it in silence."""
    async def main():
        e = started()
        e.test_state({"device_id": BOILER, "online": False}, ACTOR, CORR)
        due(e, "prearrival", COMFORT)
        e.tick()
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert [r[5] for r in partial(e)] == [
        "Pre-arrivo eseguito in parte: 1 comando non riuscito (Caldaia: dispositivo offline, non comandato)"]


def test_an_offline_climate_the_mode_would_not_command_is_not_counted():
    """In comfort a climate is commanded only with its room outside the comfort band: at 21 °C nothing was due."""
    async def main():
        e = started()
        e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": 21}}, ACTOR, CORR)
        e.test_state({"device_id": CLIMA, "online": False}, ACTOR, CORR)
        due(e, "prearrival", COMFORT)
        e.tick()
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert e.rule("setpoint_limits")["params"]["comfort_celsius"] <= 21 <= e.rule("setpoint_limits")["params"]["comfort_cool_celsius"]
    assert partial(e) == []


def test_a_manual_action_says_it_in_its_words():
    async def main():
        e = started()
        refuse(e, BOILER)
        due(e, "manual", {"type": "device_command", "device_id": BOILER, "capability": "heating",
                          "action": "turn_off"}, source="manual")
        e.tick()
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert [r[5] for r in partial(e)] == [
        "Azione programmata (manuale) non riuscita: 1 comando non riuscito (Caldaia: Il dispositivo ha rifiutato il comando)"]


def test_a_climate_start_that_waits_for_the_compressor_belongs_to_the_action():
    """The climate went off a moment ago: its start waits for the pause and the decision waits for it; when that start
    is refused it is in the list."""
    async def main():
        e = started()
        await just_off(e)
        refuse(e, CLIMA)
        item = due(e, "prearrival", COMFORT)
        e.tick()
        assert len(e.schedule[item["schedule_id"]]["command_ids"]) == 1   # the boiler now; the climate after the pause
        await settle(e)
        before_the_start = partial(e)
        await asyncio.sleep(3 * MINUTE + 0.3)
        await settle(e)
        stop(e)
        return e, item, before_the_start
    e, item, before = asyncio.run(main())
    assert before == []                                              # the boiler is over, the climate not yet
    assert len(e.schedule[item["schedule_id"]]["command_ids"]) == 2   # the start is a command of the action
    assert [r[5] for r in partial(e)] == [
        "Pre-arrivo eseguito in parte: 1 comando non riuscito "
        "(Climatizzatore soggiorno: Il dispositivo ha rifiutato il comando)"]


def test_the_start_after_the_compressor_pause_stays_the_modes():
    """D-169: comfort regulates the climates no person touched. The start that waited for the pause is the mode's own:
    before, it went through as a person's command and the climate left comfort's regulation for good."""
    async def main():
        e = started()
        await just_off(e)
        e.set_mode("comfort", ACTOR, CORR, "prova")
        await asyncio.sleep(3 * MINUTE + 0.3)
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert e.devices[CLIMA]["capabilities"]["climate"]["on"]
    assert CLIMA in e.climate_by_mode


def test_after_a_restart_the_action_is_still_judged(tmp_path):
    """The engine stops while the commands run: at the restart they are failed (outcome unknown) and the action is
    judged with them, from the index kept in the store."""
    db, conn = tmp_path / "e.db", SimulatedConnector()

    async def first_life():
        e = started(store=SqliteStore(db), connector=conn)
        item = due(e, "prearrival", COMFORT)
        e.tick()
        stop(e)                                                      # before any command is over
        e.store.close()
        return item
    item = asyncio.run(first_life())

    async def second_life():
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False, store=SqliteStore(db))
        stop(e)
        e.store.close()
        return e
    e = asyncio.run(second_life())
    why = "Motore riavviato durante il comando: esito sconosciuto, comando non completato"
    assert [r[5] for r in partial(e)] == [
        f"Pre-arrivo non riuscito: 2 comandi non riusciti (Climatizzatore soggiorno: {why}; Caldaia: {why})"]
    assert [r[1] for r in partial(e)] == [{"type": "schedule", "schedule_id": item["schedule_id"]}]
    assert e.schedule_open == {}


def test_after_a_restart_a_start_that_waited_for_the_compressor_did_not_happen(tmp_path):
    db, conn = tmp_path / "e.db", SimulatedConnector()

    async def first_life():
        e = started(store=SqliteStore(db), connector=conn)
        await just_off(e)
        due(e, "prearrival", COMFORT)
        e.tick()
        await settle(e)                                              # the boiler is done, the climate waits
        stop(e)
        e.store.close()
    asyncio.run(first_life())

    async def second_life():
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False, store=SqliteStore(db))
        stop(e)
        e.store.close()
        return e
    e = asyncio.run(second_life())
    assert [r[5] for r in partial(e)] == [
        "Pre-arrivo eseguito in parte: 1 comando non riuscito (Climatizzatore soggiorno: motore riavviato prima "
        "dell'accensione rimandata per la pausa del compressore)"]
