"""Approvals from real sources (P-60 step 8, D-137): F1 «check-out with presence» (rule checkout_eco: motion seen
after the departure time asks before going to "empty"; approved at expiry), F2 «power in an empty apartment» (a meter
above EMPTY_POWER_WATTS for EMPTY_POWER_MINUTES asks to switch the device off, once per episode; rejected at expiry
unless EMPTY_POWER_EXPIRED_ACTION says approve). Sources "rule" and "assistant" only: "brain" is reserved.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

import pytest

from engine import core
from engine.config import ConfigError, load_config
from engine.connector.simulated import SimulatedConnector

CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
ACTOR = "prova@hqe.it"
CLIMA, CALDAIA, SENSOR = "dev-clima-soggiorno", "dev-caldaia", "dev-ambiente-soggiorno"
METER = "dev-misura-clima"                                 # the split's own meter (D-139)


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "0.001")        # a "minute" of the rules = 1 ms: 15 minutes = 15 ms


def engine(**settings):
    return core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, settings=settings or None)


def watts(e, device_id, value):
    e.devices[device_id]["capabilities"]["power_meter"]["watts"] = value


def ticks(e, n=2, gap=0.03):
    async def main():
        for _ in range(n):
            e.tick()
            await asyncio.sleep(gap)
    asyncio.run(main())


def approvals_of(e) -> list[dict]:
    return e.approvals + e.approval_queue


# -------- sources and actors --------
def test_the_simulators_trigger_is_an_example_of_f2_never_brain():
    e = engine()
    a = e.trigger_approval(CORR)
    assert a["source"] == "rule" and a["expires_action"] == "reject"
    assert a["proposed_action"] == {"type": "device_command", "device_id": CLIMA, "capability": "climate",
                                    "action": "turn_off"}
    assert a["description"] == "Spegnere climatizzatore soggiorno"
    assert a["reason"].startswith("Prova dal simulatore: esempio di richiesta per climatizzatore soggiorno")
    d = e.decisions[-1]
    assert (d["actor"], d["action"], d["outcome"], d["target"]) == ("system", "turn_off", "pending_approval",
                                                                    {"type": "device", "device_id": CLIMA})
    assert "brain" not in {x["actor"] for x in e.decisions} and "brain" not in {x["source"] for x in e.approvals}


def test_the_assistants_approval_stays_rejected_at_expiry():
    e = engine()
    a = e.trigger_approval(CORR, source="assistant", reason="Richiesta all'assistente")
    assert (a["source"], a["expires_action"], e.decisions[-1]["actor"]) == ("assistant", "reject", "assistant")


# -------- F2: power in an empty apartment --------
def test_f2_asks_once_per_episode_and_never_for_the_boiler():
    e = engine()                                          # not seeded: the apartment is "empty"
    assert e.mode == "empty"
    watts(e, METER, 870)
    watts(e, CALDAIA, 2000)                               # the boiler: never (the frost protection governs it)
    ticks(e)
    asked = approvals_of(e)
    assert len(asked) == 1
    a = asked[0]
    assert a["description"] == "Spegnere climatizzatore soggiorno" and a["expires_action"] == "reject"
    assert a["reason"] == "Climatizzatore soggiorno consuma 870 W da oltre 15 minuti con l'appartamento vuoto"
    assert a["proposed_action"]["device_id"] == CLIMA
    ticks(e)
    assert len(approvals_of(e)) == 1                      # the same episode: once
    watts(e, METER, 0)
    ticks(e, n=1)
    watts(e, METER, 870)
    ticks(e)
    assert len(approvals_of(e)) == 2                      # a new episode asks again (queued behind the first)


def test_f2_waits_its_minutes_and_stays_quiet_outside_empty_or_during_a_hold():
    e = engine(EMPTY_POWER_MINUTES=240)                   # 240 "minutes" = 0,24 s here
    watts(e, METER, 870)
    ticks(e, n=2, gap=0.01)
    assert approvals_of(e) == []                          # not long enough yet
    e = engine()
    e.mode = "comfort"
    watts(e, METER, 870)
    ticks(e)
    assert approvals_of(e) == []
    e = engine()
    e.hold = {"until": core.iso(core.utcnow() + timedelta(hours=1)), "mode": "comfort"}
    watts(e, METER, 870)
    ticks(e)
    assert approvals_of(e) == []
    e = engine(EMPTY_POWER_WATTS=1000)                    # 870 W is under this apartment's threshold
    watts(e, METER, 870)
    ticks(e)
    assert approvals_of(e) == []


def test_f2_expired_is_rejected_by_default_or_approved_by_setting(monkeypatch):
    for setting, commands in (("reject", 0), ("approve", 1)):
        e = engine(EMPTY_POWER_EXPIRED_ACTION=setting)
        a = e.trigger_approval(CORR)
        assert a["expires_action"] == setting
        later = core.parse_dt(a["expires_at"]) + timedelta(seconds=1)

        async def at_expiry():
            monkeypatch.setattr(core, "utcnow", lambda: later)
            e.tick()
            monkeypatch.undo()
        asyncio.run(at_expiry())
        assert e.approvals[0]["status"] == "expired"
        assert len(e.commands) == commands


# -------- F1: check-out with presence --------
def checkout_due(e, motion_minutes_ago):
    """A booking that left 40 minutes ago (its switch to "empty" due 10 minutes ago) and motion seen N minutes ago."""
    now = core.utcnow()
    e.mode = "comfort"
    e.ingest_booking({"event_id": "evt-f1", "type": "booking_created", "booking_id": "bk-f1",
                      "checkin_at": core.iso(now - timedelta(days=2)), "checkout_at": core.iso(now - timedelta(minutes=40)),
                      "source": "manual", "ts": core.iso(now)}, CORR)
    motion = e.devices[SENSOR]["capabilities"]["motion"]       # the simulated catalog saw someone 3 minutes ago
    motion["last_seen"] = None if motion_minutes_ago is None else core.iso(now - timedelta(minutes=motion_minutes_ago))


def test_f1_motion_after_the_departure_asks_first_and_is_approved_at_expiry(monkeypatch):
    e = engine()
    checkout_due(e, motion_minutes_ago=5)
    ticks(e, n=1)
    item = next(s for s in e.schedule.values() if s["kind"] == "checkout")
    assert item["status"] == "done" and item["command_ids"] == [] and e.mode == "comfort"   # not yet "empty"
    a = e.pending_approval()
    assert a["description"] == "Mettere l'appartamento a vuoto dopo il check-out"
    assert a["reason"].startswith("Movimento rilevato 5 minuti fa da «Sensore soggiorno», dopo l'orario di partenza delle ")
    assert a["proposed_action"] == {"type": "apartment_mode", "mode": "empty"} and a["expires_action"] == "approve"
    d = e.decisions[-1]
    assert (d["actor"], d["action"], d["new_value"], d["target"]) == ("rule:checkout_eco", "set_mode", "empty",
                                                                      {"type": "apartment"})
    later = core.parse_dt(a["expires_at"]) + timedelta(seconds=1)

    async def at_expiry():
        monkeypatch.setattr(core, "utcnow", lambda: later)
        e.tick()
        monkeypatch.undo()
    asyncio.run(at_expiry())
    assert e.mode == "empty"                              # approved by itself: light and reversible


@pytest.mark.parametrize("motion_minutes_ago", [None, 120, 50])
def test_f1_without_recent_motion_after_the_departure_goes_to_empty_as_before(motion_minutes_ago):
    # None: no movement known; 120: too long ago; 50: before the departure (40 minutes ago)
    e = engine()
    checkout_due(e, motion_minutes_ago)
    ticks(e, n=1)
    assert e.mode == "empty" and e.pending_approval() is None


# -------- the settings --------
def test_the_new_settings():
    base = {"APARTMENT_ID": "apt-prova-01", "API_KEY": "k" * 16, "CONNECTOR": "simulated"}
    s = load_config(base).settings
    assert (s["CHECKOUT_PRESENCE_MINUTES"], s["EMPTY_POWER_WATTS"], s["EMPTY_POWER_MINUTES"],
            s["EMPTY_POWER_EXPIRED_ACTION"]) == (30, 300, 15, "reject")
    assert load_config({**base, "EMPTY_POWER_EXPIRED_ACTION": "Approve"}).settings["EMPTY_POWER_EXPIRED_ACTION"] == "approve"
    with pytest.raises(ConfigError, match="EMPTY_POWER_EXPIRED_ACTION must be one of: reject, approve"):
        load_config({**base, "EMPTY_POWER_EXPIRED_ACTION": "wait"})
    for name, bad in (("CHECKOUT_PRESENCE_MINUTES", "200"), ("EMPTY_POWER_WATTS", "10"), ("EMPTY_POWER_MINUTES", "1")):
        with pytest.raises(ConfigError, match=name):
            load_config({**base, name: bad})
