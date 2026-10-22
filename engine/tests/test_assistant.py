"""The assistant with a model (P-60 step 9, D-132, D-143, D-144), the model replaced by a script of answers: reads,
proposals validated by the engine, approvals with guests in or for actions together (one each, queued), the outcome
written by the engine ("Fatto" only when acked), the daily limit, the monthly cap, the time limit, no guest data.

Run: python -m pytest engine/tests -q
"""
import asyncio
import io
import json
import urllib.error
from datetime import timedelta

import pytest

from engine import assistant, core
from engine.config import ConfigError, load_config
from engine.connector import simulated
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, PRESA = "dev-clima-soggiorno", "dev-presa-camera"


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    for name in ("SENT_AFTER_S", "VERIFYING_AFTER_S", "OUTCOME_AFTER_S"):
        monkeypatch.setattr(simulated, name, 0)


def call(name, **args):
    return {"id": f"call-{name}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def tools(*calls):
    return {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": list(calls)}}]}


def says(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


class Script:
    """A fake model: the answers in order; what it was sent, for the checks."""

    def __init__(self, *answers, fail=None, delay=0.0):
        self.answers, self.fail, self.delay, self.sent = list(answers), fail, delay, []

    async def chat(self, messages, tools_):
        self.sent.append({"messages": [dict(m) for m in messages], "tools": tools_})
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise self.fail
        return self.answers.pop(0)


def engine(script, occupied=False, **settings):
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False, model=script, settings=settings or None)
    if occupied:
        real = e.apartment
        e.apartment = lambda: {**real(), "occupancy": "occupied"}
    return e


def ask(e, text):
    async def main():
        e.ensure_started()
        a = e.create_ask({"text": text}, ACTOR, CORR)
        while e.asks[a["ask_id"]]["status"] == "pending":
            await asyncio.sleep(0.02)
        return e.asks[a["ask_id"]]
    return asyncio.run(main())


def test_a_read_and_a_command_done_says_fatto_only_when_acked():
    script = Script(tools(call("leggi_dispositivi")),
                    tools(call("comanda_dispositivo", device_id=PRESA, capability="switch", action="turn_on")),
                    says("mai chiesta"))
    e = engine(script)
    a = ask(e, "accendi la stufetta in camera")
    assert a["status"] == "answered" and a["approval_id"] is None
    assert a["answer"] == "Fatto: accendere presa stufetta camera."            # lot 28 b: no final call
    assert len(script.sent) == 2
    cmd = e.commands[a["actions"][0]["command_id"]]
    assert cmd["status"] == "acked" and e.devices[PRESA]["capabilities"]["switch"]["on"] is True
    assert e.decisions[-1]["actor"] == "assistant" and "Richiesta all'assistente" in e.decisions[-1]["reasoning"]
    first = script.sent[0]
    system = first["messages"][0]["content"]
    assert "Non conosci e non chiedi dati degli ospiti" in system and "Non dire mai che un'azione è stata fatta" in system
    assert {t["function"]["name"] for t in first["tools"]} >= {"leggi_decisioni", "comanda_dispositivo", "programma"}
    devices = json.loads(script.sent[1]["messages"][-1]["content"])["dispositivi"]
    assert {d["device_id"] for d in devices} >= {CLIMA, PRESA}


def test_with_guests_in_switching_off_the_climate_needs_an_approval():
    script = Script(tools(call("comanda_dispositivo", device_id=CLIMA, capability="climate", action="turn_off")),
                    says("Chiedo di spegnere il clima."))
    e = engine(script, occupied=True)
    a = ask(e, "spegni il clima")
    assert a["status"] == "needs_approval" and a["actions"] == []
    approval = e.pending_approval()
    assert a["approval_id"] == approval["approval_id"] and approval["source"] == "assistant"
    assert approval["description"] == "Spegnere climatizzatore soggiorno" and approval["expires_action"] == "reject"
    assert a["answer"].endswith("Spengo climatizzatore soggiorno con ospiti presenti? Rispondi Sì o No qui sotto, "
                                "oppure dalla pagina Approvazioni.")                 # D-154: a question in the chat
    assert e.devices[CLIMA]["capabilities"]["climate"]["on"] is True          # nothing done
    # «Sì» in the chat is the Approvals page's own call: the same record, author and outcome
    async def yes():
        return e.decide(a["approval_id"], {"decision": "approve"}, "prova@hqe.it", "22222222-2222-2222-2222-222222222222")
    done = asyncio.run(yes())
    assert (done["status"], done["decided_by"]) == ("approved", "prova@hqe.it")
    assert any(d.get("approval_id") == a["approval_id"] and d["action"] == "approve" for d in e.decisions)


def test_the_modes_by_their_italian_names():
    """D-154: «vuoto», not the contract's «empty», in the manager's sentences."""
    script = Script(tools(call("cambia_modalita", modalita="empty")), says("Chiedo la modalità vuoto."))
    e = engine(script, occupied=True)
    a = ask(e, "metti la casa a vuoto")
    assert "Passo alla modalità vuoto con ospiti presenti?" in a["answer"] and "empty" not in a["answer"]


def test_two_actions_together_need_one_approval_each_queued():
    script = Script(tools(call("comanda_dispositivo", device_id=PRESA, capability="switch", action="turn_on"),
                          call("comanda_dispositivo", device_id=CLIMA, capability="climate", action="set_climate",
                               params={"setpoint": 22})),
                    says("Propongo due azioni."))
    e = engine(script)                                                          # empty apartment: still two together
    a = ask(e, "accendi la stufetta e porta il clima a 22")
    assert a["status"] == "needs_approval" and len(e.approval_queue) == 1
    assert a["approval_id"] == e.pending_approval()["approval_id"]
    assert a["answer"].count("Rispondi Sì o No qui sotto") == 2
    assert "Confermi: climatizzatore soggiorno a 22 °C?" in a["answer"] and "Confermi: accendere " in a["answer"]


def test_a_scheduled_action_and_a_wrong_proposal_corrected_by_the_model():
    when = (core.utcnow() + timedelta(days=1)).astimezone(assistant.ZoneInfo("Europe/Rome")).strftime("%Y-%m-%dT18:00:00")
    script = Script(tools(call("comanda_dispositivo", device_id="dev-che-non-esiste", capability="switch",
                               action="turn_on")),
                    tools(call("programma", quando=when, modalita="eco")),
                    says("Metto eco domani alle 18."))
    e = engine(script)
    a = ask(e, "domani alle 18 metti eco")
    assert "errore" in json.loads(script.sent[1]["messages"][-1]["content"])    # told the model, which corrected it
    assert a["status"] == "answered" and a["actions"][0]["type"] == "schedule"
    item = e.schedule[a["actions"][0]["schedule_id"]]
    assert item["action"] == {"type": "apartment_mode", "mode": "eco"} and item["source"] == "assistant"
    assert a["answer"].endswith(f"Programmato: modalità eco alle 18:00 del {when[8:10]}/{when[5:7]}.")


def test_why_questions_read_the_decisions_and_no_guest_data_reaches_the_model():
    script = Script(tools(call("leggi_appartamento"), call("leggi_decisioni", quante=5)), says("Perché la finestra era aperta."))
    e = engine(script)
    e.log("rule:window_open_off", {"type": "device", "device_id": CLIMA}, "turn_off", "on", "off",
          "Finestra camera aperta da oltre 5 minuti", "applied", CORR)
    a = ask(e, "perché si è spento il clima?")
    assert a["answer"] == "Perché la finestra era aperta."
    replies = [json.loads(m["content"]) for m in script.sent[1]["messages"] if m["role"] == "tool"]
    assert set(replies[0]) == {"name", "mode", "occupancy", "hold", "next_checkin", "next_checkout", "online"}
    assert any(d["reasoning"] == "Finestra camera aperta da oltre 5 minuti" for d in replies[1]["decisioni"])
    text = json.dumps(script.sent, ensure_ascii=False)
    assert "guest" not in text and "@" not in text.replace(ACTOR, "")             # no names, emails, phones


def test_the_daily_limit_the_monthly_cap_and_the_time_limit(monkeypatch):
    e = engine(Script(says("Uno.")), ASK_DAILY_LIMIT=1)
    assert ask(e, "prima domanda")["status"] == "answered"
    second = ask(e, "seconda domanda")
    assert (second["status"], second["reason"]) == ("failed", "daily_limit") and "Limite di 1 domande" in second["answer"]
    capped = ask(engine(Script(fail=assistant.ModelRefused("monthly_cap", "Limite mensile raggiunto, riprova dal mese prossimo"))),
                 "accendi")
    assert (capped["status"], capped["reason"], capped["answer"]) == (
        "failed", "monthly_cap", "Limite mensile raggiunto, riprova dal mese prossimo")
    monkeypatch.setattr(assistant, "ASK_TIMEOUT_S", 0.2)
    slow = ask(engine(Script(says("tardi"), delay=1.0)), "lento")
    assert (slow["status"], slow["reason"]) == ("failed", "timeout")


def test_the_model_client_maps_the_bffs_answers(monkeypatch):
    client = assistant.ModelClient("https://bff.example", "apt-prova-01", "k" * 16)
    seen = {}

    def ok(req, timeout):
        seen.update(url=req.full_url, headers=dict(req.header_items()), body=json.loads(req.data))
        return io.BytesIO(json.dumps(says("ciao")).encode())
    monkeypatch.setattr(assistant.urllib.request, "urlopen", ok)
    assert asyncio.run(client.chat([{"role": "user", "content": "x"}], [])) == says("ciao")
    assert seen["url"] == "https://bff.example/internal/ai/chat" and seen["headers"]["X-apartment-id"] == "apt-prova-01"
    assert seen["headers"]["X-api-key"] == "k" * 16 and seen["body"]["temperature"] == assistant.TEMPERATURE

    def capped(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 429, "cap", {}, io.BytesIO(json.dumps(
            {"error": "monthly_cap", "message": "Limite mensile raggiunto, riprova dal mese prossimo"}).encode()))
    monkeypatch.setattr(assistant.urllib.request, "urlopen", capped)
    with pytest.raises(assistant.ModelRefused) as refused:
        asyncio.run(client.chat([], []))
    assert refused.value.reason == "monthly_cap"

    def down(req, timeout):
        raise urllib.error.URLError("rete")
    monkeypatch.setattr(assistant.urllib.request, "urlopen", down)
    with pytest.raises(assistant.ModelRefused) as refused:
        asyncio.run(client.chat([], []))
    assert refused.value.reason == "model_unavailable"


def test_settings_of_the_assistant():
    base = {"APARTMENT_ID": "apt-prova-01", "API_KEY": "k" * 16, "CONNECTOR": "simulated"}
    c = load_config(base)
    assert c.model_base_url is None and c.settings["ASK_DAILY_LIMIT"] == 50
    c = load_config({**base, "MODEL_BASE_URL": "https://domotica-bff.example", "ASK_DAILY_LIMIT": "20"})
    assert c.model_base_url == "https://domotica-bff.example" and c.settings["ASK_DAILY_LIMIT"] == 20
    assert "MODEL_BASE_URL" not in c.for_connector().env
    with pytest.raises(ConfigError, match="MODEL_BASE_URL"):
        load_config({**base, "MODEL_BASE_URL": "domotica-bff"})


def test_the_demonstrations_get_the_model_from_the_registry():
    """D-132 point 5: the BFF's demonstration apartments with the real assistant (AI_DEMOS), the keywords without."""
    script = Script(says("Ciao dal modello."))
    registry = core.Registry(model_for=lambda apartment_id: script if apartment_id == "apt-rimini-01" else None)

    async def main():
        with_model, without = registry.get("apt-rimini-01"), registry.get("apt-bologna-01")
        assert with_model.model is script and without.model is None
        a = with_model.create_ask({"text": "ciao"}, ACTOR, CORR)
        while with_model.asks[a["ask_id"]]["status"] == "pending":
            await asyncio.sleep(0.02)
        return with_model.asks[a["ask_id"]]
    assert asyncio.run(main())["answer"] == "Ciao dal modello."
    assert core.Registry().model_for is None                                  # the default: keywords


# -------- lot 28: within the time --------
def test_the_state_is_in_the_request_and_a_command_needs_one_call():
    """a) the apartment and the devices with their state are already in the request; b) a turn of valid proposals only
    ends the conversation: the engine writes the outcome, the model's words of that turn first."""
    script = Script({"choices": [{"message": {"role": "assistant", "content": "Accendo la stufetta.", "tool_calls": [
        call("comanda_dispositivo", device_id=PRESA, capability="switch", action="turn_on")]}}]})
    e = engine(script)
    a = ask(e, "accendi la stufetta in camera")
    assert len(script.sent) == 1
    assert a["answer"] == "Accendo la stufetta.\nFatto: accendere presa stufetta camera."
    system = script.sent[0]["messages"][0]["content"]
    assert "Stato attuale dell'appartamento" in system and PRESA in system and CLIMA in system
    assert '"occupancy"' in system and "guest" not in system


def test_a_wrong_proposal_still_goes_back_to_the_model():
    script = Script(tools(call("comanda_dispositivo", device_id="dev-che-non-esiste", capability="switch",
                               action="turn_on")),
                    says("Quel dispositivo non c'è."))
    a = ask(engine(script), "accendi il frigo")
    assert len(script.sent) == 2 and a["answer"] == "Quel dispositivo non c'è."


def _budget(monkeypatch, total=3.0, reserve=1.0, min_call=0.5):
    monkeypatch.setattr(assistant, "ASK_TIMEOUT_S", total)
    monkeypatch.setattr(assistant, "APPLY_RESERVE_S", reserve)
    monkeypatch.setattr(assistant, "MIN_CALL_S", min_call)


def test_out_of_the_models_time_what_was_proposed_is_applied(monkeypatch):
    """c) the model's budget is 2 s here: the second call (1.2 s each) is cut, the proposal of the first is applied."""
    _budget(monkeypatch)
    script = Script(tools(call("leggi_decisioni"), call("comanda_dispositivo", device_id=PRESA, capability="switch",
                                                        action="turn_on")),
                    says("troppo tardi"), delay=1.2)
    a = ask(engine(script), "accendi la stufetta e dimmi perché era spenta")
    assert a["status"] == "answered" and a["answer"] == "Fatto: accendere presa stufetta camera."


def test_out_of_the_models_time_with_nothing_proposed_the_answer_comes_early(monkeypatch):
    _budget(monkeypatch)
    script = Script(tools(call("leggi_decisioni")), says("troppo tardi"), delay=1.2)

    async def main():
        e = engine(script)
        e.ensure_started()
        loop = asyncio.get_running_loop()
        start = loop.time()
        a = e.create_ask({"text": "perché?"}, ACTOR, CORR)
        while e.asks[a["ask_id"]]["status"] == "pending":
            await asyncio.sleep(0.02)
        return e.asks[a["ask_id"]], loop.time() - start
    a, took = asyncio.run(main())
    assert (a["status"], a["reason"], a["answer"]) == ("failed", "timeout", assistant.TIMEOUT_ANSWER)
    assert took < 2.6                                       # at the model's budget (2 s), not at the 3 s limit

