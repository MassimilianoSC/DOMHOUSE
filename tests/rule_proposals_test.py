"""Rules proposed by the assistant and confirmed by the manager (P-60 step 12, D-151): the proposal checks the limits
and changes nothing; «Applica» checks again, refuses when the rules changed in the meantime and writes the decision
under the manager's pseudonym and «regole modificate» in the activity log; 20 proposals a day per apartment; the
recognizer on the demonstrations without AI_DEMOS, the model (through the gateway) otherwise; readers refused.
In-process, dev auth, memory repository; behind instances.call a real engine (engine/core.py) per apartment."""
import asyncio
import dataclasses
import json

import httpx
import pytest

from bff import actors, ai_gateway, instances
from bff import rule_proposals as rp
from bff.config import get_settings
from bff.main import app
from bff.repository import get_repository
from bff.routes import rules as rules_routes
from engine import core
from engine.connector.simulated import SimulatedConnector

BOLOGNA, RIMINI = "apt-bologna-01", "apt-rimini-01"
ADMIN, OPERATOR, READER = "admin@demo.it", "operatore@demo.it", "lettura@demo.it"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def engines(monkeypatch):
    """One real engine per apartment behind GET/PUT /rules; `state.puts` = (apartment, actor, body) of every PUT."""
    state = type("S", (), {})()
    state.engines, state.puts = {}, []

    async def fake(apt, method, path, **kw):
        e = state.engines.setdefault(apt.apartment_id,
                                     core.ApartmentEngine(apt.apartment_id, SimulatedConnector(), seed=False))
        assert path == "/rules"
        if method == "GET":
            return httpx.Response(200, json=e.ruleset(), request=httpx.Request("GET", "http://x"))
        state.puts.append((apt.apartment_id, kw["actor"], kw["json"]))
        try:
            return httpx.Response(200, json=e.update_rules(kw["json"], kw["actor"], kw["correlation_id"]),
                                  request=httpx.Request("PUT", "http://x"))
        except core.MockError as exc:
            return httpx.Response(exc.status, json=exc.body(), request=httpx.Request("PUT", "http://x"))
    monkeypatch.setattr(instances, "call", fake)
    counts = get_repository().mail_counts
    for key in [k for k in counts if k.startswith("rule_proposal:")]:
        del counts[key]
    yield state
    for key in [k for k in counts if k.startswith("rule_proposal:")]:
        del counts[key]


def model(monkeypatch, answer: dict, seen: list | None = None):
    """AI_DEMOS on and the model replaced: `answer` is its message."""
    monkeypatch.setattr(rules_routes, "get_settings", lambda: dataclasses.replace(get_settings(), ai_demos=True))

    async def fake(body):
        if seen is not None:
            seen.append(body)
        return {"choices": [{"message": answer}], "usage": {"prompt_tokens": 100, "completion_tokens": 20}}
    monkeypatch.setattr(ai_gateway, "call_model", fake)


def tool_call(modifiche, spiegazione="Ok."):
    return {"tool_calls": [{"type": "function", "function": {"name": "proponi_modifiche", "arguments": json.dumps(
        {"modifiche": modifiche, "spiegazione": spiegazione})}}]}


async def post(path, body, who=ADMIN):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.post(path, json=body, headers={"X-Dev-User": who})


def propose(text, apt=BOLOGNA, who=ADMIN):
    return run(post(f"/app/apartments/{apt}/rules/proposal", {"text": text}, who))


def apply(body, apt=BOLOGNA, who=ADMIN):
    return run(post(f"/app/apartments/{apt}/rules/proposal/apply", body, who))


def test_the_model_proposes_nothing_changes_until_apply(engines, monkeypatch):
    seen = []
    model(monkeypatch, tool_call([{"rule_id": "window_open_off", "params": {"minutes": 10}},
                                  {"rule_id": "checkout_eco", "params": {"presence_minutes": 60}}],
                                 "Finestra a 10 minuti e presenza al check-out a 60."), seen)
    r = propose("la finestra aperta spegne dopo 10 minuti e la presenza al check-out guarda l'ultima ora")
    assert r.status_code == 200
    p = r.json()
    assert p["changes"] == [
        {"rule_id": "window_open_off", "label": "Finestra aperta spegne il clima", "field": "minutes", "old": 5, "new": 10},
        {"rule_id": "checkout_eco", "label": "Risparmio al check-out", "field": "presence_minutes", "old": 30, "new": 60}]
    assert p["explanation"] == "Finestra a 10 minuti e presenza al check-out a 60." and engines.puts == []
    system = seen[0]["messages"][0]["content"]
    assert "presence_minutes" in system and "window_open_off" in system and seen[0]["tools"] == [rp.TOOL]
    r = apply({"based_on": p["based_on"], "rules": p["rules"]}, who=OPERATOR)
    assert r.status_code == 200 and engines.engines[BOLOGNA].rule("window_open_off")["params"]["minutes"] == 10
    apt, actor, _ = engines.puts[0]
    assert apt == BOLOGNA and actors.is_pseudonym(actor)                       # the pseudonym, never the email
    d = engines.engines[BOLOGNA].decisions[-1]
    assert d["action"] == "update_rules" and d["actor"] == f"user:{actor}"
    entry = run(get_repository().list_audit("t-flatsharing-demo", 5, None))[0]
    assert entry.action == "rules_changed" and entry.details["source"] == "assistant"
    assert entry.details["changes"][0]["field"] == "minutes" and "text" not in entry.details   # never the text
    r = apply({"based_on": p["based_on"], "rules": p["rules"]})                  # the rules changed since
    assert r.status_code == 409 and r.json()["error"] == "rules_changed"


def test_out_of_the_limits_or_not_a_rule_is_said_not_proposed(engines, monkeypatch):
    model(monkeypatch, tool_call([{"rule_id": "window_open_off", "params": {"minutes": 90}}]))
    p = propose("finestra a 90 minuti").json()
    assert p["changes"] == [] and p["rules"] == [] and "tra 1 e 30" in p["explanation"]
    model(monkeypatch, {"content": "Posso cambiare solo le regole della pagina."})
    p = propose("ordina una pizza").json()
    assert p["changes"] == [] and p["explanation"] == "Posso cambiare solo le regole della pagina."
    model(monkeypatch, tool_call([{"rule_id": "compressor_min_off", "params": {"minutes": 5}}]))
    assert "non è modificabile" in propose("compressore a 5").json()["explanation"]
    # apply checks again whatever the site sends
    based_on = engines.engines[BOLOGNA].ruleset()["updated_at"]
    r = apply({"based_on": based_on, "rules": [{"rule_id": "setpoint_limits", "params": {"min": 20, "max": 20.5}},
                                                {"rule_id": "setpoint_limits", "params": {"max": 19}}]})
    assert r.status_code == 422 and engines.puts == []


def test_the_recognizer_on_the_demonstrations_and_the_daily_limit(engines, monkeypatch):
    async def never(body):
        raise AssertionError("no model on a demonstration without AI_DEMOS")
    monkeypatch.setattr(ai_gateway, "call_model", never)
    p = propose("antigelo a 10 gradi").json()
    assert p["changes"] == [{"rule_id": "frost_protection", "label": "Antigelo a casa vuota", "field": "celsius",
                             "old": 8, "new": 10}]
    assert propose("spegni la regola dell'antimuffa").json()["changes"][0] == {
        "rule_id": "mold_protection", "label": "Antimuffa a casa vuota", "field": "enabled", "old": True, "new": False}
    assert propose("presenza al check-out 45 minuti").json()["changes"][0]["field"] == "presence_minutes"
    assert propose("setpoint da 18 a 25").json()["changes"] == [
        {"rule_id": "setpoint_limits", "label": "Limiti del setpoint", "field": "min", "old": 16, "new": 18},
        {"rule_id": "setpoint_limits", "label": "Limiti del setpoint", "field": "max", "old": 24, "new": 25}]
    assert propose("finestra 5 minuti").json()["explanation"].startswith("Le regole sono già così")
    for _ in range(rp.DAILY_LIMIT - 5):
        assert propose("finestra 7 minuti").status_code == 200
    r = propose("finestra 8 minuti")
    assert r.status_code == 429 and r.json()["error"] == "daily_limit"
    assert propose("finestra 8 minuti", apt=RIMINI).status_code == 200            # per apartment


def test_who_can_and_bad_requests(engines):
    assert propose("finestra 10 minuti", who=READER).status_code == 403
    assert apply({"based_on": "x", "rules": []}, who=READER).status_code == 403
    assert propose("finestra 10 minuti", apt="apt-altra-01").status_code == 404   # another tenant's apartment
    assert propose("   ").status_code == 422 and propose("x" * 501).status_code == 422
    assert apply({"rules": []}).status_code == 422


def test_customized_values():
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    assert rp.customized(e.ruleset()) == []                                       # the predefined values
    e.update_rules({"rules": [{"rule_id": "offline_alert", "params": {"minutes": 30}},
                              {"rule_id": "prearrival", "enabled": False}]}, "prova@hqe.it", "c")
    assert [(c["rule_id"], c["field"]) for c in rp.customized(e.ruleset())] == [("prearrival", "enabled"),
                                                                                ("offline_alert", "minutes")]
