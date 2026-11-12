"""D56 (P-83 review, gravity 3): the text of a question to the assistant («spegni il clima, il sig. Rossi arriva con la
figlia») was copied into the decisions and the approvals it produced, which every member reads, viewers too, while the
questions are an operator's or an admin's (bff/routes/apartments.py, guida-utente). Now they say «Richiesta
all'assistente» without the text; the text stays in the question's own answer. Scenario of the independent
verification (V-B1a/prova_d56.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio
from datetime import timedelta

import pytest

from engine import core
from engine.assistant import Assistant
from engine.connector import simulated
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "operatore@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
TEXT = "spegni il clima, il sig. Rossi arriva con la figlia"


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    for name in ("SENT_AFTER_S", "VERIFYING_AFTER_S", "OUTCOME_AFTER_S"):
        monkeypatch.setattr(simulated, name, 0)


def stop(e):
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


def test_the_keyword_assistant_does_not_copy_the_question():
    async def main():
        e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
        e.ensure_started()
        a = e.create_ask({"text": TEXT}, ACTOR, CORR)
        for _ in range(500):                                   # until the question has its answer (at most 10 s)
            if e.asks[a["ask_id"]]["status"] != "pending":
                break
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.2)
        reasons = [d["reasoning"] for d in e.list_decisions({"limit": "50"})["items"]]
        assert any("Richiesta all'assistente" in r for r in reasons)
        assert not any("Rossi" in r for r in reasons)
        stop(e)
    asyncio.run(main())


def test_the_models_path_does_not_copy_it_in_approvals_nor_decisions():
    async def main():
        e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
        e.ensure_started()
        now = core.utcnow()
        e.bookings = {"b1": {"booking_id": "b1", "cancelled": False, "checked_in": True, "checked_out": False,
                             "checkin": now - timedelta(hours=1), "checkout": now + timedelta(days=2)}}
        ask = {"ask_id": "ask-x", "text": TEXT, "correlation_id": CORR, "approval_id": None, "status": "pending",
               "actions": []}
        proposals = [{"type": "command", "device_id": "dev-clima-soggiorno",
                      "body": {"capability": "climate", "action": "turn_off", "params": {}}}]
        await Assistant(e, None).apply(proposals, ask, ACTOR)
        assert not any("Rossi" in a["reason"] for a in e.list_approvals("all")["items"])
        assert not any("Rossi" in d["reasoning"] for d in e.list_decisions({"limit": "50"})["items"])
        stop(e)
    asyncio.run(main())
