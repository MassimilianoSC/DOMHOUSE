"""An approved action that cannot start (verification of 10 November 2026, point c): before, _execute_proposed dropped
the engine's refusal («except MockError: pass») and the manager saw only «Approvata dal gestore», with the action
never done. Now a decision with outcome failed says so, with the reason; also at the expiry that approves, and for the
action to schedule of D-170.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "gestore@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"


def engine():
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    e.ensure_started()
    return e


def socket(e) -> str:
    return next(d["device_id"] for d in e.devices.values() if "switch" in d["capabilities"])


def ask(e, device_id: str, expires_action: str = "reject") -> dict:
    e._new_approval("rule", "Spegnere la presa", "Consumo a casa vuota", {
        "type": "device_command", "device_id": device_id, "capability": "switch", "action": "turn_off"},
        expires_action, CORR)
    return e.pending_approval()


def stop(e):
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


def after(e, n: int) -> list[tuple]:
    return [(d["actor"], d["action"], d["outcome"], d["reasoning"], d["approval_id"]) for d in e.decisions[n:]]


def test_device_offline_the_approval_says_the_action_was_not_done():
    async def main():
        e = engine()
        dev = socket(e)
        apr = ask(e, dev)
        e.test_state({"device_id": dev, "online": False}, ACTOR, CORR)
        n = len(e.decisions)
        out = e.decide(apr["approval_id"], {"decision": "approve"}, ACTOR, CORR)
        stop(e)
        return out, after(e, n), apr["approval_id"]
    out, rows, apr = asyncio.run(main())
    assert out["status"] == "approved"
    assert rows == [
        ("user:gestore@hqe.it", "approve", "applied", "Approvata dal gestore", apr),
        ("user:gestore@hqe.it", "turn_off", "failed",
         "Azione approvata ma non eseguita: Il dispositivo non è raggiungibile; riprova quando torna online", apr)]


def test_connector_down_the_same():
    async def main():
        e = engine()
        apr = ask(e, socket(e))
        e.connector_up = lambda: False
        n = len(e.decisions)
        e.decide(apr["approval_id"], {"decision": "approve"}, ACTOR, CORR)
        stop(e)
        return after(e, n)
    rows = asyncio.run(main())
    assert rows[-1][2:4] == ("failed", "Azione approvata ma non eseguita: Collegamento ai dispositivi non disponibile; "
                                       "riprova quando torna")


def test_approved_at_the_expiry_with_the_device_offline():
    async def main():
        e = engine()
        dev = socket(e)
        apr = ask(e, dev, expires_action="approve")
        e.test_state({"device_id": dev, "online": False}, ACTOR, CORR)
        apr["expires_at"] = core.iso(core.utcnow() - timedelta(seconds=1))
        n = len(e.decisions)
        e.tick()
        stop(e)
        return after(e, n)
    rows = asyncio.run(main())
    assert [r[:3] for r in rows] == [("system", "expire", "informational"), ("system", "turn_off", "failed")]
    assert rows[1][3].startswith("Azione approvata ma non eseguita: Il dispositivo non è raggiungibile")


def test_an_action_to_schedule_that_cannot_be_scheduled_says_so():
    async def main():
        e = engine()
        apr = ask(e, socket(e))
        apr["proposed_action"] = {"type": "device_command", "device_id": "dev-sparito", "capability": "switch",
                                  "action": "turn_off"}                       # no longer in the catalog
        e.approval_schedules[apr["approval_id"]] = core.iso(core.utcnow() + timedelta(hours=2))   # D-170
        n = len(e.decisions)
        e.decide(apr["approval_id"], {"decision": "approve"}, ACTOR, CORR)
        stop(e)
        return after(e, n), e.schedule
    rows, schedule = asyncio.run(main())
    assert not schedule
    assert rows[-1][1:3] == ("turn_off", "failed") and rows[-1][3].startswith("Azione approvata ma non programmata: ")


def test_an_action_that_starts_writes_no_failure():
    async def main():
        e = engine()
        apr = ask(e, socket(e))
        n = len(e.decisions)
        e.decide(apr["approval_id"], {"decision": "approve"}, ACTOR, CORR)
        rows = after(e, n)
        stop(e)
        return rows
    assert [r[2] for r in asyncio.run(main())] == ["applied"]
