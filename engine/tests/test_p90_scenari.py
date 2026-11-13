"""P-90 (revisione per scenari, 13 Nov), group (a), the engine's part: S2, S3, S5, S11, S12, S13, S17, S18, S19, S21,
T6. Each test failed on the code before the repair (1f79ba9).

- S2: a hold after the window rule fired lost the return: the boiler (and in eco the climate) stayed off for good.
- S3: a mode's command created and then failed or timed out was never repeated: the boiler kept the old mode's
  temperature (warm in «casa vuota», cold after a prearrival), a climate stayed on in «casa vuota».
- S5: a late check-out or one more night arriving after the check-out action: the guest stayed in «casa vuota».
- S11: «Pre-arrivo» and «Risparmio al check-out» switched off or on did not touch the bookings' actions.
- S12: the «consuma a casa vuota» request (F2) stayed open after leaving «casa vuota».
- S13: the assistant called «Spengo …» a setpoint change on a climate or a boiler that is off.
- S17: «Avviso dispositivo offline» switched off during the wait warned anyway; on again with a device already
  offline it never warned.
- S18: a boiler commanded by hand that loses its sensor: its own decision, heating_unregulated (the BFF's push).
- S19: a prearrival moved by hand and run, then any change of the booking: back to empty with «Arrivo spostato».
- S21: a second cancellation undid the comfort put back by hand; a booking already over planned four commands.
- T6: the chat printed internal codes («no_confirmation») for a command not done.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from engine import core
from engine.assistant import Assistant
from engine.connector.interface import CommandResult
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "user:prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, BOILER, WINDOW, SENSOR = "dev-clima-soggiorno", "dev-caldaia", "dev-finestra-camera", "dev-ambiente-soggiorno"
PLUG = "dev-presa-camera"
MINUTE = 0.2


class FailingConnector(SimulatedConnector):
    """The next command to a capability in `fail` fails (the device did not take it), then all is normal again."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fail: set[str] = set()

    async def execute(self, cmd, on_progress):
        if cmd.capability in self.fail:
            self.fail.discard(cmd.capability)
            return CommandResult("failed", "device_rejected", detail="test")
        return await super().execute(cmd, on_progress)


@pytest.fixture
def fast(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


async def settle(e, timeout=15.0):
    end = asyncio.get_running_loop().time() + timeout
    await asyncio.sleep(0.05)
    while any(c["status"] not in core.FINAL for c in e.commands.values()) or e.relay_busy:
        assert asyncio.get_running_loop().time() < end, e.commands
        await asyncio.sleep(0.02)


async def minutes(n: float) -> None:
    await asyncio.sleep(n * MINUTE)


async def just_after_a_tick(e) -> None:
    """The engine's loop ticks once a REAL second (_tick_loop), the regulation's checks with it: right after a tick is
    the worst phase for a wait counted from now (giro of 13 Nov on 654375a: a fixed wait lost that race)."""
    seen = e.last_tick
    while e.last_tick == seen:
        await asyncio.sleep(0.005)


async def until(condition, timeout: float = 5.0) -> None:
    end = asyncio.get_running_loop().time() + timeout
    while not condition():
        assert asyncio.get_running_loop().time() < end, "condition not reached"
        await asyncio.sleep(0.02)


def stop(e) -> None:
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


def window(e, open_: bool) -> None:
    e.test_state({"device_id": WINDOW, "capability": "contact", "state": {"open": open_}}, ACTOR, CORR)


def cold(e, celsius: float = 15) -> None:
    e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": celsius}}, ACTOR, CORR)


def boiler(e) -> dict:
    return e.devices[BOILER]["capabilities"]["heating"]


def climate(e) -> dict:
    return e.devices[CLIMA]["capabilities"]["climate"]


async def started(mode="comfort", connector=None):
    e = core.ApartmentEngine("apt-prova-01", connector or SimulatedConnector(), seed=False,
                             settings={"COMPRESSOR_WAIT_SECONDS": 0})
    e.ensure_started()
    cold(e)
    e.set_mode(mode, ACTOR, CORR, "prova")
    await settle(e)
    await minutes(2)
    await settle(e)
    return e


def decisions(e, action):
    return [d for d in e.decisions if d["action"] == action]


# -------- S2 --------
def test_s2_a_hold_after_the_window_rule_keeps_the_return_for_its_end(fast):
    async def main():
        e = await started("comfort")
        window(e, True)
        await minutes(e.rule("window_open_off")["params"]["minutes"] + 1)
        await settle(e)
        assert not boiler(e)["on"] and not climate(e)["on"]
        e.set_hold(60, None, ACTOR, CORR)                               # «Forza comunque», same mode
        await minutes(3)
        window(e, False)
        await minutes(3)
        await settle(e)
        assert not boiler(e)["on"]                                      # during the hold nothing comes back
        e.set_hold(0, None, ACTOR, CORR)                                # the hold ends
        await minutes(8)
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert boiler(e)["on"] and climate(e)["on"]
    assert [d["reasoning"] for d in decisions(e, "window_restore") if d["target"].get("device_id") == BOILER] == [
        "Finestra chiusa: Caldaia riacceso (comfort)"]


def test_s2_a_hold_ending_with_the_window_still_open_waits_for_it(fast):
    async def main():
        e = await started("eco")
        window(e, True)
        await minutes(e.rule("window_open_off")["params"]["minutes"] + 1)
        await settle(e)
        e.set_hold(60, None, ACTOR, CORR)
        await minutes(3)
        e.set_hold(0, None, ACTOR, CORR)
        await minutes(2)
        assert not boiler(e)["on"]                                      # still open: off
        window(e, False)
        await minutes(8)
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert boiler(e)["on"] and boiler(e)["setpoint"] == e.rule("setpoint_limits")["params"]["eco_celsius"]


# -------- S3 --------
def test_s3_a_boiler_command_of_the_mode_that_fails_still_takes_the_modes_temperature(fast):
    async def main():
        conn = FailingConnector()
        e = await started("comfort", conn)
        assert boiler(e)["setpoint"] == 21
        conn.fail.add("heating")
        e.set_mode("empty", ACTOR, CORR, "prova")
        await settle(e)
        await minutes(3)
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    frost = e.rule("frost_protection")["params"]["celsius"]
    assert boiler(e)["setpoint"] == frost and BOILER in e.heating_by_mode
    assert [d for d in decisions(e, "mode_device_pending") if d["target"].get("device_id") == BOILER]


def test_s3_a_climate_command_of_the_mode_that_fails_is_tried_again(fast):
    async def main():
        conn = FailingConnector()
        e = await started("comfort", conn)
        assert climate(e)["on"]
        conn.fail.add("climate")
        e.set_mode("empty", ACTOR, CORR, "prova")
        await settle(e)
        await minutes(3)
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert not climate(e)["on"] and e.mode_pending == {}
    assert [d for d in decisions(e, "mode_device_pending") if d["target"].get("device_id") == CLIMA]   # it failed once


# -------- bookings, with a fake clock (as test_booking_changed) --------
T0 = datetime(2026, 11, 2, 13, 0, tzinfo=UTC)


def at(monkeypatch, moment):
    monkeypatch.setattr(core, "utcnow", lambda: moment)


def in_loop(fn, *args, **kw):
    async def main():
        return fn(*args, **kw)
    return asyncio.run(main())


def tick(e):
    in_loop(e.tick)


def ev(e, bid, kind, ci, co, n):
    return in_loop(e.ingest_booking, {"event_id": f"evt-{bid}-{n}", "type": kind, "booking_id": bid,
                                      "checkin_at": core.iso(ci), "checkout_at": core.iso(co), "source": "manual",
                                      "ts": core.iso(core.utcnow())}, CORR)


def items(e, bid, kind, status="planned"):
    return [s for s in e.schedule.values() if s["booking_id"] == bid and s["kind"] == kind and s["status"] == status]


def booked(monkeypatch):
    """bk-a created three days before; arrival at T0 + 2 h, departure three days later; no movement (no F1)."""
    at(monkeypatch, T0 - timedelta(days=3))
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    for d in e.devices.values():
        if "motion" in d["capabilities"]:
            d["capabilities"]["motion"]["last_seen"] = None
    ci, co = T0 + timedelta(hours=2), T0 + timedelta(days=3)
    ev(e, "bk-a", "booking_created", ci, co, 1)
    return e, ci, co


def test_s5_a_late_check_out_after_the_check_out_action_brings_comfort_back(monkeypatch):
    e, ci, co = booked(monkeypatch)
    at(monkeypatch, T0)
    tick(e)
    at(monkeypatch, ci + timedelta(minutes=10))
    ev(e, "bk-a", "checkin", ci, co, 2)
    at(monkeypatch, co + timedelta(minutes=31))
    tick(e)
    assert e.mode == "empty"                                            # the check-out action ran
    at(monkeypatch, co + timedelta(minutes=45))
    ev(e, "bk-a", "booking_changed", ci, co + timedelta(hours=3), 3)     # late check-out at 13:00
    tick(e)
    assert e.mode == "comfort"
    [again] = items(e, "bk-a", "checkout")
    assert again["run_at"] == core.iso(co + timedelta(hours=3, minutes=30))
    [d] = decisions(e, "booking_extended_comfort")
    assert d["reasoning"] == ("Partenza della prenotazione bk-a spostata al 05/11 17:00, dopo il check-out: appartamento "
                              "rimesso in comfort, check-out riprogrammato")


def test_s5_a_late_check_out_without_the_guests_in_only_plans_it_again(monkeypatch):
    e, ci, co = booked(monkeypatch)
    at(monkeypatch, co + timedelta(minutes=31))
    tick(e)
    assert e.mode == "empty"
    at(monkeypatch, co + timedelta(minutes=45))
    ev(e, "bk-a", "checkout", ci, co, 2)                                # they left
    ev(e, "bk-a", "booking_changed", ci, co + timedelta(hours=3), 3)
    tick(e)
    assert e.mode == "empty" and items(e, "bk-a", "checkout") == [] and decisions(e, "booking_extended_comfort") == []


def test_s19_same_dates_after_a_prearrival_moved_by_hand_no_reset(monkeypatch):
    e, ci, co = booked(monkeypatch)
    at(monkeypatch, T0 - timedelta(hours=4))
    [pre] = items(e, "bk-a", "prearrival")
    in_loop(e.move_schedule, pre["schedule_id"], {"run_at": core.iso(T0 - timedelta(hours=3))}, ACTOR, CORR)
    at(monkeypatch, T0 - timedelta(hours=3) + timedelta(seconds=1))
    tick(e)
    assert e.mode == "comfort"
    at(monkeypatch, T0 - timedelta(hours=2))
    ev(e, "bk-a", "booking_changed", ci, co, 2)                         # the guests' number, same dates
    tick(e)
    assert e.mode == "comfort" and decisions(e, "booking_moved_reset") == []
    assert items(e, "bk-a", "prearrival") == []


def test_s19_the_arrival_moved_later_still_resets(monkeypatch):
    e, ci, co = booked(monkeypatch)
    at(monkeypatch, T0)
    tick(e)
    assert e.mode == "comfort"
    ev(e, "bk-a", "booking_changed", ci + timedelta(days=1), co, 2)
    tick(e)
    assert e.mode == "empty" and len(decisions(e, "booking_moved_reset")) == 1


def test_s21_a_second_cancellation_changes_nothing(monkeypatch):
    e, ci, co = booked(monkeypatch)
    at(monkeypatch, T0)
    tick(e)
    ev(e, "bk-a", "booking_cancelled", ci, co, 2)
    tick(e)
    assert e.mode == "empty"
    in_loop(e.set_mode, "comfort", ACTOR, CORR, "Gestore: comfort", by_hand=True)
    ev(e, "bk-a", "booking_cancelled", ci, co, 3)                       # the same cancellation, another id
    tick(e)
    assert e.mode == "comfort" and len(decisions(e, "booking_cancel_reset")) == 1


def test_s21_a_booking_already_over_plans_nothing(monkeypatch):
    at(monkeypatch, T0)
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    status, result = ev(e, "bk-old", "booking_created", T0 - timedelta(days=4), T0 - timedelta(days=1), 1)
    tick(e)
    assert status == 202 and result["schedule_ids"] == [] and e.commands == {} and e.mode == "empty"


# -------- S11 --------
def test_s11_a_rule_switched_off_cancels_its_bookings_actions_and_on_again_plans_them(monkeypatch):
    e, ci, co = booked(monkeypatch)
    in_loop(e.update_rules, {"rules": [{"rule_id": "checkout_eco", "enabled": False}]}, ACTOR, CORR)
    assert items(e, "bk-a", "checkout") == [] and len(items(e, "bk-a", "checkout", "cancelled")) == 1
    d = decisions(e, "schedule_cancel")[-1]
    assert (d["actor"], d["reasoning"]) == ("rule:checkout_eco", "Regola «Risparmio al check-out» spenta: 1 azione delle "
                                                                 "prenotazioni annullata")
    in_loop(e.update_rules, {"rules": [{"rule_id": "checkout_eco", "enabled": True}]}, ACTOR, CORR)
    [again] = items(e, "bk-a", "checkout")
    assert again["run_at"] == core.iso(co + timedelta(minutes=30))
    d = decisions(e, "schedule_create")[-1]
    assert (d["actor"], d["reasoning"]) == ("rule:checkout_eco", "Regola «Risparmio al check-out» riaccesa: 1 azione "
                                                                 "delle prenotazioni riprogrammata")


def test_s11_a_bookings_action_of_a_rule_off_never_runs(monkeypatch):
    e, ci, co = booked(monkeypatch)
    [pre] = items(e, "bk-a", "prearrival")
    e.rule("prearrival")["enabled"] = False                           # switched off without the update (a rule saved off)
    at(monkeypatch, T0 + timedelta(seconds=1))
    tick(e)
    assert e.mode == "empty" and e.schedule[pre["schedule_id"]]["status"] == "cancelled"


# -------- S12 --------
def test_s12_the_empty_power_request_closes_when_the_apartment_is_no_longer_empty():
    async def main():
        e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
        plug = e.devices[PLUG]
        first = e._propose_switch_off(plug, plug, 900, CORR)
        e._propose_switch_off(e.devices[CLIMA], plug, 800, CORR)       # queued behind the first
        assert first["status"] == "pending" and len(e.approval_queue) == 1
        e.set_mode("comfort", ACTOR, CORR, "prova")
        return e, first
    e, first = asyncio.run(main())
    assert first["status"] == "expired" and e.approval_queue == [] and e.pending_approval() is None
    [d] = [d for d in e.decisions if d.get("approval_id") == first["approval_id"] and d["action"] == "expire"]
    assert d["reasoning"] == "Richiesta chiusa senza eseguire: l'appartamento non è più vuoto"


# -------- S13 --------
def test_s13_a_setpoint_on_a_climate_that_is_off_is_not_switching_it_off():
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    e.guests_in = lambda: True
    a = Assistant(e, None)
    climate(e)["on"] = False
    p = {"type": "command", "device_id": CLIMA, "body": {"capability": "climate", "action": "set_climate",
                                                         "params": {"setpoint": 24}}}
    assert a.describe(p) == "climatizzatore soggiorno a 24 °C" and a.needs_approval(p, False) is False
    boiler(e)["on"] = False
    p = {"type": "command", "device_id": BOILER, "body": {"capability": "heating", "action": "set_heating",
                                                          "params": {"setpoint": 22}}}
    assert a.describe(p) == "caldaia a 22 °C" and a.needs_approval(p, False) is False
    climate(e)["on"] = True                                             # a real switch off still asks
    p = {"type": "command", "device_id": CLIMA, "body": {"capability": "climate", "action": "turn_off"}}
    assert a.describe(p) == "spegnere climatizzatore soggiorno" and a.needs_approval(p, False) is True
    assert '"on": true' in a_prompt()


def a_prompt() -> str:
    from engine import assistant
    return assistant.SYSTEM_PROMPT


# -------- S17 --------
def test_s17_the_offline_alert_follows_the_rule_switched_off_and_on(fast):
    async def main():
        e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
        e.ensure_started()
        minutes_ = e.rule("offline_alert")["params"]["minutes"]
        e.devices[PLUG]["online"] = False
        e._watch_offline(PLUG, False)
        e.update_rules({"rules": [{"rule_id": "offline_alert", "enabled": False}]}, ACTOR, CORR)
        await minutes(minutes_ + 1)
        off = len(decisions(e, "offline_alert"))
        e.update_rules({"rules": [{"rule_id": "offline_alert", "enabled": True}]}, ACTOR, CORR)
        await minutes(minutes_ + 1)
        stop(e)
        return e, off
    e, off = asyncio.run(main())
    assert off == 0 and len(decisions(e, "offline_alert")) == 1


# -------- S18 --------
def test_s18_a_boiler_commanded_by_hand_without_its_sensor_has_its_own_decision(fast):
    async def main():
        e = await started("comfort")
        e.create_command(BOILER, {"capability": "heating", "action": "set_heating", "params": {"on": True, "setpoint": 22}},
                         ACTOR, CORR)
        await settle(e)
        sensor = e.links[BOILER]["sensor_device_id"]
        e.devices[sensor]["online"] = False
        e.regulate()
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    [d] = decisions(e, "heating_unregulated")
    assert d["target"] == {"type": "device", "device_id": BOILER} and "segue il comando manuale" in d["reasoning"]


# -------- T6 --------
def test_t6_the_chat_says_why_in_words_not_codes(fast):
    async def main():
        conn = FailingConnector()
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False, settings={"COMPRESSOR_WAIT_SECONDS": 0})
        e.ensure_started()
        conn.fail.add("switch")
        a = Assistant(e, None)
        ask = {"ask_id": "ask-1", "correlation_id": CORR, "created_at": core.iso(core.utcnow()), "actions": []}
        lines = await a.apply([{"type": "command", "device_id": PLUG,
                                "body": {"capability": "switch", "action": "turn_on"}}], ask, ACTOR)
        stop(e)
        return lines
    lines = asyncio.run(main())
    assert lines == ["Non riuscito: accendere presa stufetta camera (Il dispositivo ha rifiutato il comando)."], lines


# -------- S1 (answer 1101 = a) --------
def test_s1_a_split_switched_off_by_its_remote_stays_off_until_the_next_mode(fast):
    """Comfort at 15 °C: the guest switches the split off with its remote (the meter at 0 W, no command running).
    After REMOTE_OFF_MINUTES of low watts the engine believes it off, takes it out of the regulation with a decision,
    and never switches it on again until the mode changes. Before: on again every THERMOSTAT_MIN_SWITCH_MINUTES."""
    async def main():
        e = await started("comfort")
        assert climate(e)["on"] and CLIMA in e.climate_by_mode
        before = len([c for c in e.commands.values() if c["device_id"] == CLIMA])
        await just_after_a_tick(e)                                          # the worst phase, every time
        e.connector._devices[CLIMA].capabilities["climate"]["on"] = False       # its own remote
        e.connector.set_state("dev-misura-clima", "power_meter", {"watts": 0})
        await asyncio.sleep(0.1)
        assert climate(e)["on"]                                             # a few low watts: not yet off
        began = asyncio.get_running_loop().time()
        await until(lambda: not climate(e)["on"])                           # off at a tick after the minutes
        assert asyncio.get_running_loop().time() - began >= e.setting("REMOTE_OFF_MINUTES") * MINUTE - 0.15
        await settle(e)
        assert CLIMA not in e.climate_by_mode
        await minutes(2 * e.setting("THERMOSTAT_MIN_SWITCH_MINUTES") + 2)
        await settle(e)
        after = len([c for c in e.commands.values() if c["device_id"] == CLIMA])
        e.set_mode("eco", ACTOR, CORR, "prova")
        e.set_mode("comfort", ACTOR, CORR, "prova")                        # the next mode: regulated again
        await settle(e)
        stop(e)
        return e, before, after
    e, before, after = asyncio.run(main())
    assert after == before                                                  # never switched on again
    assert CLIMA in e.climate_by_mode
    [d] = decisions(e, "climate_remote_off")
    assert (d["actor"], d["target"], d["outcome"]) == ("system", {"type": "device", "device_id": CLIMA}, "informational")
    assert d["reasoning"] == ("Climatizzatore soggiorno: spento col telecomando (consumo sotto 15 W da 5 minuti); resta "
                              "fuori dalla regolazione fino al prossimo cambio di modalità")


def test_s1_low_watts_for_less_than_the_minutes_change_nothing(fast):
    """A split at its temperature that stops its fan for a while (S9): watts back up before the minutes, still on."""
    async def main():
        e = await started("comfort")
        e.connector.set_state("dev-misura-clima", "power_meter", {"watts": 3})
        await minutes(2)
        e.connector.set_state("dev-misura-clima", "power_meter", {"watts": 600})
        await minutes(e.setting("REMOTE_OFF_MINUTES") + 1)
        await settle(e)
        stop(e)
        return e
    e = asyncio.run(main())
    assert climate(e)["on"] and CLIMA in e.climate_by_mode and decisions(e, "climate_remote_off") == []


# -------- S6 (answer 1102 = a) --------
def test_s6_a_window_contact_offline_while_open_counts_as_closed(fast):
    """The window rule turned boiler and climate off; the contact goes silent while open (battery, bridge unplugged):
    before, everything stayed off until it came back, for days. Now an offline contact counts as closed, with a
    decision, and what the rule turned off comes back; back online and still open, the rule starts again."""
    async def main():
        e = await started("comfort")
        window(e, True)
        await minutes(e.rule("window_open_off")["params"]["minutes"] + 1)
        await settle(e)
        assert not boiler(e)["on"] and not climate(e)["on"]
        e.test_state({"device_id": WINDOW, "online": False}, ACTOR, CORR)
        await minutes(8)
        await settle(e)
        back = boiler(e)["on"] and climate(e)["on"]
        e.test_state({"device_id": WINDOW, "online": True}, ACTOR, CORR)
        await minutes(e.rule("window_open_off")["params"]["minutes"] + 2)
        await settle(e)
        stop(e)
        return e, back
    e, back = asyncio.run(main())
    assert back                                                         # it came back with the contact silent
    assert not boiler(e)["on"]                                          # the contact back, still open: off again
    [d] = decisions(e, "window_contact_offline")
    assert (d["actor"], d["target"]) == ("rule:window_open_off", {"type": "device", "device_id": WINDOW})
    assert d["reasoning"] == ("Finestra camera senza segnale mentre era aperta: considerata chiusa per la regola "
                              "«Finestra aperta spegne il clima» finché non torna raggiungibile")


# -------- S10 (answer 1103 = a) --------
def manual_eco_with_guests(monkeypatch, mode="eco", guests=True):
    """bk-a in course (checked in) and in comfort; at T0 + 1 day an action «mode» set by hand in Programmazione."""
    e, ci, co = booked(monkeypatch)
    at(monkeypatch, T0)
    tick(e)
    if guests:
        at(monkeypatch, ci + timedelta(minutes=10))
        ev(e, "bk-a", "checkin", ci, co, 2)
    else:
        ev(e, "bk-a", "booking_cancelled", ci, co, 2)
        tick(e)
        in_loop(e.set_mode, "comfort", ACTOR, CORR, "Gestore", by_hand=True)
    when = T0 + timedelta(days=1)
    in_loop(e.create_schedule, {"run_at": core.iso(when), "action": {"type": "apartment_mode", "mode": mode}}, ACTOR, CORR)
    at(monkeypatch, when + timedelta(seconds=1))
    tick(e)
    return e, when


@pytest.mark.parametrize("mode, name", [("eco", "eco"), ("empty", "casa vuota")])
def test_s10_a_manual_eco_or_empty_with_guests_in_asks_first(monkeypatch, mode, name):
    e, when = manual_eco_with_guests(monkeypatch, mode)
    assert e.mode == "comfort"
    a = e.pending_approval()
    assert a["description"] == f"Passare alla modalità {name} con ospiti in casa"
    assert a["reason"] == ("Azione programmata a mano per le 14:00 del 03/11: alla sua ora c'è una prenotazione in corso, "
                           "gli ospiti potrebbero essere in casa")
    assert a["proposed_action"] == {"type": "apartment_mode", "mode": mode} and a["expires_action"] == "reject"
    assert a["source"] == "rule"
    d = [d for d in e.decisions if d.get("approval_id") == a["approval_id"]][-1]
    assert (d["actor"], d["outcome"]) == ("system", "pending_approval")
    at(monkeypatch, core.parse_dt(a["expires_at"]) + timedelta(seconds=1))
    tick(e)
    assert a["status"] == "expired" and e.mode == "comfort"            # no answer: rejected, the guests stay warm


def test_s10_without_guests_it_runs_as_before(monkeypatch):
    e, when = manual_eco_with_guests(monkeypatch, "eco", guests=False)
    assert e.mode == "eco" and e.pending_approval() is None
