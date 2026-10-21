"""Rules of P-60 step 5 (D-126), first part: R4 the compressor's minimum pause, R5 the offline decision, R6 limits
on the automatic paths, R3 the mold warning (warning only, engine/mold.py). The rules' minutes run fast here:
MOCK_TIME_SCALE is the real seconds per simulated minute.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, CALDAIA, PRESA = "dev-clima-soggiorno", "dev-caldaia", "dev-presa-camera"


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "0.02")         # a "minute" of the rules = 20 ms


def engine(variant_apartment="apt-prova-01", wait=0.0):
    """wait: COMPRESSOR_WAIT_SECONDS (D-133); 0 here, never wait for the pause: refuse, as in real time."""
    return core.ApartmentEngine(variant_apartment, SimulatedConnector(), seed=False,
                                settings={"COMPRESSOR_WAIT_SECONDS": wait})


async def settle(e, timeout=10.0):
    end = asyncio.get_running_loop().time() + timeout
    while any(c["status"] not in core.FINAL for c in e.commands.values()):
        assert asyncio.get_running_loop().time() < end, e.commands
        await asyncio.sleep(0.02)


def climate_on(e) -> bool:
    return e.devices[CLIMA]["capabilities"]["climate"]["on"]


# ---- R4 ------------------------------------------------------------------------------------------------------------
def test_manual_start_during_the_compressor_pause_is_refused_then_allowed():
    async def main():
        e = engine()
        e.ensure_started()
        e.create_command(CLIMA, {"capability": "climate", "action": "turn_off"}, ACTOR, CORR)
        await settle(e)
        assert not climate_on(e) and e.compressor_wait(CLIMA) > 0
        cmd = e.create_command(CLIMA, {"capability": "climate", "action": "set_climate", "params": {"on": True}}, ACTOR, CORR)
        await settle(e)
        assert (e.commands[cmd["command_id"]]["status"], e.commands[cmd["command_id"]]["reason"]) == \
            ("failed", "blocked_by_rule")
        refused = e.decisions[-1]
        assert refused["outcome"] == "rejected" and "Pausa minima del compressore" in refused["reasoning"]
        await asyncio.sleep(3 * 0.02 + 0.05)                # the pause is over
        again = e.create_command(CLIMA, {"capability": "climate", "action": "set_climate", "params": {"on": True}}, ACTOR, CORR)
        await settle(e)
        assert e.commands[again["command_id"]]["status"] == "acked" and climate_on(e)
    asyncio.run(main())


def test_automatic_start_waits_for_the_pause():
    async def main():
        e = engine()
        e.ensure_started()
        e.create_command(CLIMA, {"capability": "climate", "action": "turn_off"}, ACTOR, CORR)
        await settle(e)
        ids = e.set_mode("comfort", "system:engine", CORR, "prova", "system")     # comfort turns the split on
        deferred = [d for d in e.decisions if d["actor"] == "rule:compressor_min_off"]
        assert deferred and "rimandata" in deferred[-1]["reasoning"]
        assert not any(e.commands[i]["device_id"] == CLIMA for i in ids)        # not created yet
        await asyncio.sleep(3 * 0.02 + 0.1)
        await settle(e)
        assert climate_on(e)                                                     # started after the pause
    asyncio.run(main())


# ---- R5 ------------------------------------------------------------------------------------------------------------
def test_offline_decision_once_per_episode():
    async def main():
        e = engine()
        e.ensure_started()
        minutes = e.rule("offline_alert")["params"]["minutes"]
        e.test_state({"device_id": PRESA, "online": False}, ACTOR, CORR)
        e.test_state({"device_id": PRESA, "online": False}, ACTOR, CORR)        # same episode: one watch
        await asyncio.sleep(minutes * 0.02 + 0.1)
        alerts = [d for d in e.decisions if d["action"] == "offline_alert"]
        assert len(alerts) == 1 and alerts[0]["target"]["device_id"] == PRESA and alerts[0]["outcome"] == "informational"
        e.test_state({"device_id": PRESA, "online": True}, ACTOR, CORR)
        e.test_state({"device_id": PRESA, "online": False}, ACTOR, CORR)
        e.test_state({"device_id": PRESA, "online": True}, ACTOR, CORR)         # back before the minutes: nothing
        await asyncio.sleep(minutes * 0.02 + 0.1)
        assert len([d for d in e.decisions if d["action"] == "offline_alert"]) == 1
    asyncio.run(main())


# ---- R6 ------------------------------------------------------------------------------------------------------------
def test_automatic_setpoints_are_brought_within_limits_manual_ones_refused():
    async def main():
        e = engine()
        e.ensure_started()
        with pytest.raises(core.MockError) as exc:                             # manual: 422 as before
            e.create_command(CLIMA, {"capability": "climate", "action": "set_climate", "params": {"setpoint": 30}},
                             ACTOR, CORR)
        assert exc.value.status == 422
        hi = e.devices[CLIMA]["capabilities"]["climate"]["setpoint_max"]
        cmd = e.create_command(CLIMA, {"capability": "climate", "action": "set_climate", "params": {"setpoint": 30}},
                               "system:engine", CORR, decision_actor="rule:prova", reasoning="Regola di prova")
        assert cmd["params"]["setpoint"] == hi
        await settle(e)
        applied = [d for d in e.decisions if d["command_id"] == cmd["command_id"]][-1]
        assert "riportato" in applied["reasoning"] and e.devices[CLIMA]["capabilities"]["climate"]["setpoint"] == hi
    asyncio.run(main())


def test_assistant_setpoint_within_limits_says_so(monkeypatch):
    async def no_wait(_s):
        return None

    async def main():
        e = engine()
        monkeypatch.setattr(core.asyncio, "sleep", no_wait)
        ask = e.create_ask({"text": "porta il soggiorno a 30 gradi"}, ACTOR, CORR)
        await asyncio.gather(*list(e.tasks))
        return e, e.asks[ask["ask_id"]]
    e, answer = asyncio.run(main())
    hi = e.devices[CLIMA]["capabilities"]["climate"]["setpoint_max"]
    assert answer["status"] == "answered" and f"a {core.fmt_num(hi)} °C" in answer["answer"]
    assert "avevi chiesto 30 °C" in answer["answer"]


# ---- R3 ------------------------------------------------------------------------------------------------------------
def test_mold_warning_once_a_day_when_empty_suspended_by_a_hold(monkeypatch):
    e = engine("apt-bologna-01")                         # starts empty
    threshold = e.rule("mold_protection")["params"]["humidity_percent"]
    e.devices["dev-ambiente-soggiorno"]["capabilities"]["humidity"]["percent"] = threshold + 5
    e.mode = "comfort"
    e._mold_check()
    assert not [d for d in e.decisions if d["action"] == "mold_warning"]         # not empty: nothing
    e.mode = "empty"
    e._mold_check()
    e._mold_check()                                                              # same day: one only
    warnings = [d for d in e.decisions if d["action"] == "mold_warning"]
    assert len(warnings) == 1 and "solo avviso" in warnings[0]["reasoning"] and not e.commands
    tomorrow = core.utcnow() + timedelta(days=1)
    monkeypatch.setattr(core, "utcnow", lambda: tomorrow)
    e.hold = {"mode": "empty", "until": core.iso(tomorrow + timedelta(hours=1)), "set_by": ACTOR}
    e._mold_check()                                    # a hold suspends it (R7) and the decision says so (R8)
    warnings = [d for d in e.decisions if d["action"] == "mold_warning"]
    assert len(warnings) == 2 and "sospesa dalla forzatura" in warnings[-1]["reasoning"]
    e.hold = None
    e._mold_check()                                    # still the same day: nothing more
    after = tomorrow + timedelta(days=1)
    monkeypatch.setattr(core, "utcnow", lambda: after)
    e._mold_check()
    assert "solo avviso" in [d for d in e.decisions if d["action"] == "mold_warning"][-1]["reasoning"]
    assert len([d for d in e.decisions if d["action"] == "mold_warning"]) == 3  # the next day, again


def test_a_pause_ending_within_the_command_time_is_waited_for(monkeypatch):
    """With the conformance suite's time scale (1 s per minute) the pause lasts 3 s: a manual start waits for it and
    is acked (scenario C11 turns the split on right after the previous one turned it off)."""
    async def main():
        e = engine(wait=7.0)
        e.ensure_started()
        e.create_command(CLIMA, {"capability": "climate", "action": "turn_off"}, ACTOR, CORR)
        await settle(e)
        cmd = e.create_command(CLIMA, {"capability": "climate", "action": "set_climate", "params": {"on": True}}, ACTOR, CORR)
        await settle(e)
        assert e.commands[cmd["command_id"]]["status"] == "acked" and climate_on(e)
    asyncio.run(main())

