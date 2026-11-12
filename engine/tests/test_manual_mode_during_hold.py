"""D09 (P-83 review, gravity 2), the manual part, decided by the committente (answer 1085 = a): during a hold, a mode
change made by hand (from the app, or asked to the assistant) or an approval of a mode change decided by hand UPDATES
hold.mode with the new mode. The hold goes on until its end, the automatic rules stay suspended, no «Forzatura
annullata»; a decision «hold» says so; at the end of the hold the new mode stays. Before: hold.mode kept the old mode,
and the app showed «Forzatura comfort attiva» with the apartment in eco.

Run: python -m pytest engine/tests -q
"""
import asyncio
import json
from datetime import timedelta

import pytest
from starlette.testclient import TestClient

from engine import core
from engine.api import create_contract_app
from engine.connector.simulated import SimulatedConnector

CORR = "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
ACTOR = "prova@hqe.it"
KEY = "k" * 16


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "0.001")


def engine(**kw):
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, **kw)
    e.mode = "comfort"
    return e


def tick_at(monkeypatch, e, when):
    async def main():
        monkeypatch.setattr(core, "utcnow", lambda: when)
        e.tick()
        await asyncio.sleep(0.03)
        monkeypatch.undo()
    asyncio.run(main())


def inloop(fn):
    """fn inside an event loop, as in the service (commands start tasks), with a moment for them."""
    async def main():
        out = fn()
        await asyncio.sleep(0.03)
        return out
    return asyncio.run(main())


def hold_comfort(e):
    e.set_hold(120, "comfort", ACTOR, CORR)
    assert e.hold["mode"] == "comfort"
    return e.hold["until"]


def the_hold_follows(monkeypatch, e, until, mode):
    """hold.mode is the new mode, the end is the same, no cancel; the decision «hold» says so; the house stays in the
    new mode during the hold and after its end."""
    assert e.mode == mode and e.hold is not None and e.hold["mode"] == mode and e.hold["until"] == until
    assert e.apartment()["hold"]["mode"] == mode                                  # what the app reads
    assert not [d for d in e.decisions if d["action"] == "hold_cancel"]
    follows = [d for d in e.decisions if d["action"] == "hold" and d["old_value"] == "comfort"]
    assert len(follows) == 1 and follows[0]["new_value"].startswith(f"{mode} ")
    assert "la forzatura continua" in follows[0]["reasoning"]
    tick_at(monkeypatch, e, core.parse_dt(until) - timedelta(minutes=1))           # still in the hold
    assert e.hold is not None and e.hold["mode"] == mode and e.mode == mode
    tick_at(monkeypatch, e, core.parse_dt(until) + timedelta(seconds=1))           # the hold ends
    tick_at(monkeypatch, e, core.parse_dt(until) + timedelta(minutes=5))
    assert e.hold is None and e.mode == mode
    assert [d for d in e.decisions if d["action"] == "hold_expired"]


def test_a_mode_change_from_the_app_during_a_hold_updates_the_hold(monkeypatch):
    e = engine()
    until = hold_comfort(e)
    app = create_contract_app(lambda _apt: e, KEY, features=core.ALL_FEATURES, simulated=True,
                              implementation={"name": "prova", "version": "0"}, ping_seconds=25,
                              apartment_id="apt-prova-01")
    with TestClient(app) as client:
        h = {"X-API-Key": KEY, "X-Actor": ACTOR, "X-Correlation-Id": CORR, "Idempotency-Key": "d09-mode-1"}
        r = client.post("/api/v1/apartment/mode", headers=h, content=json.dumps({"mode": "eco"}))
        assert r.status_code == 202, r.text
    the_hold_follows(monkeypatch, e, until, "eco")


def test_an_approval_decided_by_hand_during_a_hold_updates_the_hold(monkeypatch):
    e = engine()
    until = hold_comfort(e)
    a = e._new_approval("assistant", "Modalità eco", "prova", {"type": "apartment_mode", "mode": "eco"}, "reject", CORR)
    inloop(lambda: e.decide(a["approval_id"], {"decision": "approve"}, ACTOR, CORR))
    the_hold_follows(monkeypatch, e, until, "eco")


def test_a_mode_asked_to_the_assistant_during_a_hold_updates_the_hold(monkeypatch):
    from engine.tests.test_assistant import Script, ask, js, mode
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False,
                             model=Script(js("Metto eco.", mode("eco"))))
    e.mode = "comfort"
    until = hold_comfort(e)
    a = ask(e, "metti eco")
    assert a["status"] == "answered", a
    the_hold_follows(monkeypatch, e, until, "eco")


def test_the_same_mode_by_hand_leaves_the_hold_as_it_is():
    e = engine()
    hold_comfort(e)
    inloop(lambda: e.set_mode("comfort", ACTOR, CORR, "Modalità impostata dall'app", by_hand=True))
    assert e.hold["mode"] == "comfort" and [d["action"] for d in e.decisions].count("hold") == 1


def test_automatic_mode_changes_never_touch_the_hold():
    """Only a person's choice moves the hold: an automatic path (none runs during a hold today: schedules and
    approvals at expiry wait for its end, D-122 and D09) would leave it as it is."""
    e = engine()
    hold_comfort(e)
    inloop(lambda: e.set_mode("eco", "system:engine", CORR, "prova", "system"))
    assert e.hold["mode"] == "comfort"
