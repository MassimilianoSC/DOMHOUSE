"""D37 (P-83 review, gravity 3): an action the assistant scheduled «alle 21:00», approved at 21:15, ran at once at the
approval: the boiler went off a quarter of an hour late, at a time nobody chose, and the case «a time already past» of
_approved_not_done was never reached. Now an approval of a scheduled action whose time has passed (beyond 30 s) runs
nothing and says so in a failed decision. Scenario of the independent verification (V-B1a/prova_d37.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
BOILER = "dev-caldaia"
PROPOSED = {"type": "device_command", "device_id": BOILER, "capability": "heating", "action": "turn_off", "params": {}}


def approved(minutes_from_now: float):
    async def main():
        e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
        e.ensure_started()
        await asyncio.sleep(0.1)
        before = len(e.commands)
        opened = e._new_approval("assistant", "Programmare spegnere caldaia", "Richiesta all'assistente", dict(PROPOSED),
                                 "reject", CORR)
        approval = opened or e.approval_queue[-1]
        e.schedule_approval(approval["approval_id"], core.iso(core.utcnow() + timedelta(minutes=minutes_from_now)))
        e.decide(approval["approval_id"], {"decision": "approve"}, ACTOR, CORR)
        new = list(e.commands.values())[before:]
        planned = [s for s in e.schedule.values() if s.get("source") == "assistant" and s["status"] == "planned"]
        failed = [d for d in e.decisions if d["outcome"] == "failed"]
        for t in [e.loop_task, e.consumer_task, *e.tasks]:
            if t is not None:
                t.cancel()
        return new, planned, failed
    return asyncio.run(main())


def test_approved_after_its_time_it_runs_nothing_and_says_so():
    new, planned, failed = approved(-15)
    assert new == [] and planned == []
    assert len(failed) == 1 and "passato" in failed[0]["reasoning"]


def test_approved_before_its_time_it_is_scheduled_as_before():
    new, planned, failed = approved(+30)
    assert new == [] and len(planned) == 1 and failed == []
