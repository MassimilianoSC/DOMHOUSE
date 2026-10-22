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


def name(apartment_id):
    return run(get_repository().get_apartment(apartment_id)).name


@pytest.fixture
def engines(monkeypatch):
    """One real engine per apartment behind GET/PUT /rules; `state.puts` = (apartment, actor, body) of every PUT."""
    state = type("S", (), {})()
    state.engines, state.puts, state.down = {}, [], set()

    async def fake(apt, method, path, **kw):
        e = state.engines.setdefault(apt.apartment_id,
                                     core.ApartmentEngine(apt.apartment_id, SimulatedConnector(), seed=False))
        assert path == "/rules"
        if apt.apartment_id in state.down:
            raise httpx.ConnectError("down")
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
    """The model's call in the tool's flat rows (lot 29): written here as RulePatch for readability."""
    rows = []
    for m in modifiche:
        if "enabled" in m:
            rows.append({"rule_id": m["rule_id"], "parametro": "attiva", "valore": 1 if m["enabled"] else 0})
        for key, value in (m.get("params") or {}).items():
            rows.append({"rule_id": m["rule_id"], "parametro": key, "valore": value})
    return {"tool_calls": [{"type": "function", "function": {"name": "proponi_modifiche", "arguments": json.dumps(
        {"modifiche": rows, "spiegazione": spiegazione})}}]}


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


# -------- 12d: copy the rules to other apartments (D-151 point 22) --------
@pytest.fixture
def more_apartments(engines):
    """Two more apartments of the demo organisation: one disabled, one whose instance does not answer."""
    repo = get_repository()
    rimini = run(repo.get_apartment(RIMINI))
    extra = {"apt-spenta-01": rimini.model_copy(update={"apartment_id": "apt-spenta-01", "name": "Spenta", "enabled": False}),
             "apt-giu-01": rimini.model_copy(update={"apartment_id": "apt-giu-01", "name": "Giù"})}
    for a in extra.values():
        run(repo.upsert_apartment(a))
    yield engines
    for apt_id in extra:
        run(repo.delete_apartment(apt_id))


def copy(path, body, who=ADMIN, apt=BOLOGNA):
    return run(post(f"/app/apartments/{apt}/rules/copy{path}", body, who))


def test_copy_preview_then_one_decision_per_apartment(engines, monkeypatch):
    rimini = core.ApartmentEngine(RIMINI, SimulatedConnector(), seed=False)
    engines.engines[RIMINI] = rimini
    rimini.update_rules({"rules": [{"rule_id": "offline_alert", "params": {"minutes": 60}}]}, "x@hqe.it", "c")
    src = core.ApartmentEngine(BOLOGNA, SimulatedConnector(), seed=False)
    engines.engines[BOLOGNA] = src
    src.update_rules({"rules": [{"rule_id": "window_open_off", "params": {"minutes": 12}},
                                {"rule_id": "prearrival", "enabled": False}]}, "x@hqe.it", "c")
    p = copy("/preview", {"to": [RIMINI]})
    assert p.status_code == 200
    p = p.json()
    t = p["targets"][0]
    assert t["status"] == "changes" and t["name"] == name(RIMINI)
    assert [(c["rule_id"], c["field"], c["old"], c["new"]) for c in t["changes"]] == [
        ("window_open_off", "minutes", 5, 12), ("prearrival", "enabled", True, False), ("offline_alert", "minutes", 60, 15)]
    assert t["customized"] == [{"rule_id": "offline_alert", "label": "Avviso dispositivo offline", "field": "minutes",
                                "value": 60, "default": 15}]          # (d): the warning, before the confirmation
    assert engines.puts == []                                         # the preview changes nothing
    r = copy("", {"to": [RIMINI], "from_based_on": p["from"]["based_on"],
                  "based_on": {x["apartment_id"]: x["based_on"] for x in p["targets"]}})
    assert r.status_code == 200 and r.json()["results"][0]["outcome"] == "applied"
    assert rimini.rule("window_open_off")["params"]["minutes"] == 12 and rimini.rule("prearrival")["enabled"] is False
    d = rimini.decisions[-1]
    assert d["action"] == "update_rules" and actors.is_pseudonym(d["actor"][5:])
    entry = run(get_repository().list_audit("t-flatsharing-demo", 5, None))[0]
    assert entry.action == "rules_changed" and entry.target.id == RIMINI
    assert entry.details["source"] == "copy" and entry.details["from_apartment"] == {"id": BOLOGNA, "name": name(BOLOGNA)}
    assert len(entry.details["changes"]) == 3
    # the same copy again: the destination changed since that preview
    r = copy("", {"to": [RIMINI], "from_based_on": p["from"]["based_on"],
                  "based_on": {x["apartment_id"]: x["based_on"] for x in p["targets"]}})
    assert r.json()["results"][0]["outcome"] == "changed_meanwhile"
    p = copy("/preview", {"to": [RIMINI]}).json()
    assert p["targets"][0]["status"] == "same" and p["targets"][0]["customized"] == []


def test_copy_outcomes_per_apartment_and_who_can(more_apartments):
    engines = more_apartments
    engines.down = {"apt-giu-01"}
    p = copy("/preview", {"to": [RIMINI, "apt-spenta-01", "apt-giu-01"]}).json()
    assert [(t["apartment_id"], t["status"]) for t in p["targets"]] == [
        (RIMINI, "same"), ("apt-spenta-01", "disabled"), ("apt-giu-01", "unreachable")]
    body = {"to": [RIMINI, "apt-spenta-01", "apt-giu-01"], "from_based_on": p["from"]["based_on"],
            "based_on": {t["apartment_id"]: t["based_on"] for t in p["targets"]}}
    assert [r["outcome"] for r in copy("", body).json()["results"]] == ["same", "disabled", "unreachable"]
    assert engines.puts == []
    engines.engines[BOLOGNA].update_rules({"rules": [{"rule_id": "frost_protection", "params": {"celsius": 9}}]}, "x@hqe.it", "c")
    r = copy("", body)                                                  # the source changed since the preview
    assert r.status_code == 409 and r.json()["error"] == "rules_changed"
    assert copy("/preview", {"to": [RIMINI]}, who=OPERATOR).status_code == 403          # (a) admins only
    assert copy("", body, who=OPERATOR).status_code == 403
    assert copy("/preview", {"to": [BOLOGNA]}).status_code == 422                       # not onto itself
    assert copy("/preview", {"to": []}).status_code == 422
    assert copy("/preview", {"to": ["apt-altra-01"]}).status_code == 404               # another organisation's
    assert copy("", {"to": [RIMINI]}).status_code == 422                                # without the preview


# -------- lot 29: the proposal within its time --------
def test_a_simple_phrase_needs_no_model_even_with_one(engines, monkeypatch):
    """One rule and one value: the recognizer answers at once, the model is not called (it took over 25 s in staging)."""
    seen = []
    model(monkeypatch, tool_call([{"rule_id": "window_open_off", "params": {"minutes": 99}}]), seen)
    p = propose("finestra 10 minuti").json()
    assert seen == [] and p["changes"][0]["new"] == 10


def test_the_tool_is_flat_and_the_prompt_short():
    from engine import core as engine_core
    e = engine_core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    items = rp.TOOL["function"]["parameters"]["properties"]["modifiche"]["items"]
    assert set(items["properties"]) == {"rule_id", "parametro", "valore"} and "additionalProperties" not in json.dumps(rp.TOOL)
    text = rp.prompt(e.ruleset())
    assert "compressor_min_off" not in text and "- window_open_off «Finestra aperta spegne il clima»" in text
    assert "minutes=5 (da 1 a 30)" in text
    patches, _ = rp.from_answer({"choices": [{"message": tool_call(
        [{"rule_id": "mold_protection", "enabled": False}, {"rule_id": "setpoint_limits", "params": {"min": 18, "max": 25}}])}]})
    assert patches == [{"rule_id": "mold_protection", "enabled": False},
                       {"rule_id": "setpoint_limits", "params": {"min": 18, "max": 25}}]


def test_a_slow_model_gets_a_clear_answer(engines, monkeypatch):
    monkeypatch.setattr(rp, "PROPOSAL_TIMEOUT_S", 0.2)
    monkeypatch.setattr(rules_routes, "get_settings", lambda: dataclasses.replace(get_settings(), ai_demos=True))

    async def slow(body):
        await asyncio.sleep(1)
        return {"choices": [{"message": {"content": "tardi"}}], "usage": {}}
    monkeypatch.setattr(ai_gateway, "call_model", slow)
    r = propose("la finestra spegne dopo 10 minuti e l'antigelo sta a 9 gradi")      # two rules: the model
    assert r.status_code == 504 and r.json() == {"error": "timeout", "message": rp.TIMEOUT_MESSAGE}

