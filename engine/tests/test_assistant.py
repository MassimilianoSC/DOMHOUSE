"""The assistant with a model (P-60 step 9, D-132, D-143, D-144; D-182: no tools, the answer and the actions as a JSON
object in the text, validated by the engine), the model replaced by a script of answers: the state, the recent decisions
and the planned actions in the request; actions checked by the engine's own rules; approvals with guests in or for
actions together (one each, queued); the outcome written by the engine ("Fatto" only when acked); an invalid JSON =
the state, nothing run; the daily limit, the monthly cap, the time limit; no guest data.

Run: python -m pytest engine/tests -q
"""
import asyncio
import json
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


def says(text):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def js(risposta, *azioni):
    """The model's answer as D-182 asks it: a JSON object in the text."""
    return says(json.dumps({"risposta": risposta, "azioni": list(azioni)}, ensure_ascii=False))


def cmd(device_id, capability, action, **params):
    return {"tipo": "comando", "device_id": device_id, "capability": capability, "action": action, "params": params}


def mode(m):
    return {"tipo": "modalita", "modalita": m}


def plan(quando, m):
    return {"tipo": "programma", "quando": quando, "modalita": m}


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


def test_one_call_without_tools_and_fatto_only_when_acked():
    script = Script(js("Accendo la stufetta.", cmd(PRESA, "switch", "turn_on")))
    e = engine(script)
    a = ask(e, "accendi la stufetta in camera")
    assert a["status"] == "answered" and a["approval_id"] is None
    assert a["answer"] == "Accendo la stufetta.\nFatto: accendere presa stufetta camera."
    assert len(script.sent) == 1 and script.sent[0]["tools"] == []                # D-182: no tools
    cmd_ = e.commands[a["actions"][0]["command_id"]]
    assert cmd_["status"] == "acked" and e.devices[PRESA]["capabilities"]["switch"]["on"] is True
    assert e.decisions[-1]["actor"] == "assistant" and "Richiesta all'assistente" in e.decisions[-1]["reasoning"]
    system = script.sent[0]["messages"][0]["content"]
    assert "Non conosci e non chiedi dati degli ospiti" in system and "Non dire mai che un'azione è stata fatta" in system
    assert "Rispondi SOLO con un oggetto JSON" in system and '"tipo": "comando"' in system
    assert "Stato attuale dell'appartamento" in system and PRESA in system and CLIMA in system and '"occupancy"' in system


def test_d182_an_invalid_json_runs_nothing_and_says_the_state(monkeypatch):
    from engine import log
    logged = []
    monkeypatch.setattr(log, "warn", lambda msg, **kw: logged.append((msg, kw)))
    for bad in ("Spengo il clima.",                                              # prose
                '{"risposta": "x", "azioni": [{"tipo": "esplodi"}]}',            # an unknown form
                '{"risposta": "x", "azioni": [{"tipo": "comando", "device_id": "d", "rm": "-rf"}]}'):   # an unknown key
        e = engine(Script(says(bad)))
        a = ask(e, "spegni il clima")
        assert a["status"] == "answered" and e.commands == {}
        assert a["answer"].startswith("Non ho capito la risposta dell'assistente: non ho eseguito niente. Modalità ")
    assert logged[-1] == ("assistant fallback", {"apartment_id": "apt-prova-01", "cause": "json_invalid"})
    assert assistant.parse_answer("```json\n" + json.dumps({"risposta": "ok", "azioni": []}) + "\n```") == {
        "risposta": "ok", "azioni": []}


def test_with_guests_in_switching_off_the_climate_needs_an_approval():
    script = Script(js("Chiedo di spegnere il clima.", cmd(CLIMA, "climate", "turn_off")))
    e = engine(script, occupied=True)
    a = ask(e, "spegni il clima")
    assert a["status"] == "needs_approval" and a["actions"] == []
    approval = e.pending_approval()
    assert a["approval_id"] == approval["approval_id"] and approval["source"] == "assistant"
    assert approval["description"] == "Spegnere climatizzatore soggiorno" and approval["expires_action"] == "reject"
    assert a["answer"].endswith("Spengo climatizzatore soggiorno con ospiti presenti? Rispondi Sì o No qui sotto, "
                                "oppure dalla pagina Approvazioni.")                 # D-154: a question in the chat
    assert e.devices[CLIMA]["capabilities"]["climate"]["on"] is True          # nothing done

    async def yes():
        return e.decide(a["approval_id"], {"decision": "approve"}, "prova@hqe.it", "22222222-2222-2222-2222-222222222222")
    done = asyncio.run(yes())
    assert (done["status"], done["decided_by"]) == ("approved", "prova@hqe.it")
    assert any(d.get("approval_id") == a["approval_id"] and d["action"] == "approve" for d in e.decisions)


def test_the_modes_by_their_italian_names():
    """D-154, D-158: «casa vuota», not the contract's «empty», in the manager's sentences."""
    e = engine(Script(js("Chiedo la casa vuota.", mode("empty"))), occupied=True)
    a = ask(e, "metti la casa a vuoto")
    assert "Passo alla modalità casa vuota con ospiti presenti?" in a["answer"] and "empty" not in a["answer"]


def test_two_actions_together_need_one_approval_each_queued():
    e = engine(Script(js("Propongo due azioni.", cmd(PRESA, "switch", "turn_on"),
                         cmd(CLIMA, "climate", "set_climate", setpoint=22))))   # empty apartment: still two together
    a = ask(e, "accendi la stufetta e porta il clima a 22")
    assert a["status"] == "needs_approval" and len(e.approval_queue) == 1
    assert a["approval_id"] == e.pending_approval()["approval_id"]
    assert a["answer"].count("Rispondi Sì o No qui sotto") == 2
    assert "Confermi: climatizzatore soggiorno a 22 °C?" in a["answer"] and "Confermi: accendere " in a["answer"]


def test_a_scheduled_action_and_a_wrong_one_said_not_done():
    """The engine checks every action as before; with no second turn, a wrong one is said in the answer."""
    when = (core.utcnow() + timedelta(days=1)).astimezone(assistant.ZoneInfo("Europe/Rome")).strftime("%Y-%m-%dT18:00:00")
    e = engine(Script(js("Metto eco domani alle 18.", cmd("dev-che-non-esiste", "switch", "turn_on"), plan(when, "eco"))))
    a = ask(e, "domani alle 18 metti eco")
    assert a["status"] == "answered" and a["actions"][0]["type"] == "schedule"
    item = e.schedule[a["actions"][0]["schedule_id"]]
    assert item["action"] == {"type": "apartment_mode", "mode": "eco"} and item["source"] == "assistant"
    assert "Non fatto: " in a["answer"] and e.commands == {}
    assert a["answer"].endswith(f"Programmato: modalità eco alle 18:00 del {when[8:10]}/{when[5:7]}.")


def test_why_questions_use_the_recent_decisions_and_no_guest_data_reaches_the_model():
    script = Script(js("Perché la finestra era aperta."))
    e = engine(script)
    e.log("rule:window_open_off", {"type": "device", "device_id": CLIMA}, "turn_off", "on", "off",
          "Finestra camera aperta da oltre 5 minuti", "applied", CORR)
    a = ask(e, "perché si è spento il clima?")
    assert a["answer"] == "Perché la finestra era aperta."
    system = script.sent[0]["messages"][0]["content"]
    assert "Finestra camera aperta da oltre 5 minuti" in system and '"decisioni_recenti"' in system
    assert '"programmazioni"' in system
    text = json.dumps(script.sent, ensure_ascii=False)
    assert "guest" not in text and "@" not in text.replace(ACTOR, "")             # no names, emails, phones


def test_the_daily_limit_the_monthly_cap_and_the_time_limit(monkeypatch):
    e = engine(Script(js("Uno.")), ASK_DAILY_LIMIT=1)
    assert ask(e, "prima domanda")["status"] == "answered"
    second = ask(e, "seconda domanda")
    assert (second["status"], second["reason"]) == ("failed", "daily_limit") and "Limite di 1 domande" in second["answer"]
    capped = ask(engine(Script(fail=assistant.ModelRefused("monthly_cap", "Limite mensile raggiunto, riprova dal mese prossimo"))),
                 "accendi")
    assert (capped["status"], capped["reason"], capped["answer"]) == (
        "failed", "monthly_cap", "Limite mensile raggiunto, riprova dal mese prossimo")
    monkeypatch.setattr(assistant, "ASK_TIMEOUT_S", 0.2)
    slow = ask(engine(Script(js("tardi"), delay=1.0)), "lento")
    assert (slow["status"], slow["reason"]) == ("failed", "timeout")


def _budget(monkeypatch, total=3.0, no_proposal_reserve=2.0):
    monkeypatch.setattr(assistant, "ASK_TIMEOUT_S", total)
    monkeypatch.setattr(assistant, "NO_PROPOSAL_RESERVE_S", no_proposal_reserve)


def test_the_model_gets_all_but_the_reserve_and_a_late_answer_ends_early(monkeypatch):
    """C-10 layer 2 with one call: the model has ASK_TIMEOUT_S - NO_PROPOSAL_RESERVE_S; beyond it the question ends
    then, not at the end of the whole time."""
    _budget(monkeypatch, no_proposal_reserve=0.5)
    assert ask(engine(Script(js("Il clima è acceso."), delay=1.5)), "il clima è acceso?")["answer"] == "Il clima è acceso."
    _budget(monkeypatch)                                                       # 1 s for the model, 3 in all

    async def main():
        e = engine(Script(js("tardi"), delay=1.5))
        e.ensure_started()
        loop = asyncio.get_running_loop()
        start = loop.time()
        a = e.create_ask({"text": "perché?"}, ACTOR, CORR)
        while e.asks[a["ask_id"]]["status"] == "pending":
            await asyncio.sleep(0.02)
        return e.asks[a["ask_id"]], loop.time() - start
    a, took = asyncio.run(main())
    assert (a["status"], a["reason"]) == ("failed", "timeout") and took < 2.0


def _bff(status: int, body: dict | None, delay: float = 0.0, location: str | None = "eu"):
    """A local stand-in for the BFF's /internal/ai/chat: (server, url, seen requests)."""
    import http.server
    import threading
    import time as _time
    seen = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append({"path": self.path, "headers": dict(self.headers),
                         "body": json.loads(self.rfile.read(int(self.headers["Content-Length"])))})
            _time.sleep(delay)
            data = json.dumps(body or {}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if location is not None:
                self.send_header("X-AI-Location", location)          # D-181
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}", seen


def test_the_model_client_maps_the_bffs_answers(monkeypatch):
    server, url, seen = _bff(200, says("ciao"))
    client = assistant.ModelClient(url, "apt-prova-01", "k" * 16)
    assert asyncio.run(client.chat([{"role": "user", "content": "x"}], [])) == says("ciao")
    assert seen[0]["path"] == "/internal/ai/chat" and seen[0]["headers"]["X-Apartment-Id"] == "apt-prova-01"
    assert seen[0]["headers"]["X-API-Key"] == "k" * 16 and seen[0]["body"]["temperature"] == assistant.TEMPERATURE
    assert "tools" not in seen[0]["body"]                                  # D-182: none sent
    server.shutdown()
    server, url, _ = _bff(429, {"error": "monthly_cap", "message": "Limite mensile raggiunto, riprova dal mese prossimo"})
    with pytest.raises(assistant.ModelRefused) as refused:
        asyncio.run(assistant.ModelClient(url, "apt-prova-01", "k" * 16).chat([], []))
    assert refused.value.reason == "monthly_cap"
    server.shutdown()


def test_lot30_a_failure_towards_the_bff_says_its_phase(monkeypatch):
    """The committente's instruction: a separate connection timeout, and the phase of every failure in the log."""
    from engine import log
    logged = []
    monkeypatch.setattr(log, "warn", lambda msg, **kw: logged.append((msg, kw)))
    server, url, _ = _bff(200, says("tardi"), delay=1.0)                 # no answer within the reading time
    monkeypatch.setattr(assistant, "ASK_TIMEOUT_S", 0.3)
    with pytest.raises(assistant.ModelRefused) as refused:
        asyncio.run(assistant.ModelClient(url, "apt-prova-01", "k" * 16).chat([], []))
    assert refused.value.reason == "model_unavailable"
    msg, kw = logged[-1]
    assert msg == "assistant model call failed" and kw["phase"] == "attesa della risposta" and kw["timeout"] is True
    server.shutdown()
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()                                                              # nobody listens there
    monkeypatch.setattr(assistant, "CONNECT_TIMEOUT_S", 1.0)
    with pytest.raises(assistant.ModelRefused):
        asyncio.run(assistant.ModelClient(f"http://127.0.0.1:{port}", "apt-prova-01", "k" * 16).chat([], []))
    assert logged[-1][1]["phase"] == "connessione"
    with pytest.raises(assistant.ModelRefused):
        asyncio.run(assistant.ModelClient("https://domhouse-prova.invalid", "apt-prova-01", "k" * 16).chat([], []))
    assert logged[-1][1]["phase"] == "DNS"


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
    script = Script(js("Ciao dal modello."))
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


# -------- D-170: a scheduled action with guests in at its time --------
def _booked(e, start, end):
    e.ingest_booking({"event_id": f"evt-{start}", "type": "booking_created", "booking_id": "bk-d170",
                      "checkin_at": core.iso(start), "checkout_at": core.iso(end), "source": "simulator",
                      "ts": core.iso(core.utcnow())}, CORR)


def _at_18_tomorrow():
    tz = assistant.ZoneInfo("Europe/Rome")
    local = (core.utcnow() + timedelta(days=1)).astimezone(tz).replace(hour=18, minute=0, second=0, microsecond=0)
    return local, local.strftime("%Y-%m-%dT18:00:00")


def test_d170_scheduled_with_guests_at_its_time_asks_then_schedules():
    local, when = _at_18_tomorrow()
    e = engine(Script(js("Programmo eco.", plan(when, "eco"))))                  # empty now
    _booked(e, local - timedelta(hours=3), local + timedelta(days=2))           # guests in at 18:00 tomorrow
    a = ask(e, "domani alle 18 metti eco")
    assert a["status"] == "needs_approval"
    approval = e.pending_approval()
    assert approval["description"].startswith("Programmare modalità eco alle 18:00")
    assert approval["proposed_action"] == {"type": "apartment_mode", "mode": "eco"}
    assert "Programmo modalità eco alle 18:00" in a["answer"] and "con ospiti presenti a quell'ora?" in a["answer"]
    assert not [s for s in e.schedule.values() if s["source"] == "assistant"]   # nothing scheduled yet

    async def yes():
        return e.decide(approval["approval_id"], {"decision": "approve"}, ACTOR, "33333333-3333-3333-3333-333333333333")
    asyncio.run(yes())
    planned = [s for s in e.schedule.values() if s["source"] == "assistant"]
    assert len(planned) == 1 and planned[0]["action"] == {"type": "apartment_mode", "mode": "eco"}
    assert core.parse_dt(planned[0]["run_at"]) == local and e.mode != "eco"     # at its time, not now
    assert e.approval_schedules == {}


def test_d170_without_guests_at_its_time_it_is_scheduled_at_once_and_a_no_schedules_nothing():
    local, when = _at_18_tomorrow()
    e = engine(Script(js("Programmo eco.", plan(when, "eco"))))
    a = ask(e, "domani alle 18 metti eco")                                      # no booking then
    assert a["status"] == "answered" and a["actions"][0]["type"] == "schedule"
    e = engine(Script(js("Programmo eco.", plan(when, "eco"))))
    _booked(e, local - timedelta(hours=3), local + timedelta(days=2))
    a = ask(e, "domani alle 18 metti eco")

    async def no():
        return e.decide(a["approval_id"], {"decision": "reject"}, ACTOR, "44444444-4444-4444-4444-444444444444")
    asyncio.run(no())
    assert not [s for s in e.schedule.values() if s["source"] == "assistant"] and e.approval_schedules == {}


# -------- D-181: an answer from outside the EU (or without its location) is refused before anything runs --------
@pytest.mark.parametrize("location", [None, "global", "us"])
def test_d181_an_answer_without_a_european_location_runs_nothing(monkeypatch, location):
    from engine import log
    refused = []
    monkeypatch.setattr(log, "error", lambda msg, **kw: refused.append((msg, kw)))
    server, url, seen = _bff(200, js("Accendo.", cmd(PRESA, "switch", "turn_on")), location=location)
    e = engine(assistant.ModelClient(url, "apt-prova-01", "k" * 16))
    a = ask(e, "accendi la stufetta in camera")
    server.shutdown()
    assert len(seen) == 1                                                  # the model was asked once
    assert (a["status"], a["reason"]) == ("failed", "model_unavailable")
    assert a["answer"] == "L'assistente non è disponibile ora, riprova più tardi"
    assert e.commands == {} and e.devices[PRESA]["capabilities"]["switch"]["on"] is False   # nothing ran
    assert refused == [("model location refused", {"apartment_id": "apt-prova-01", "ai_location": location or "assente"})]


def test_d181_a_european_answer_is_used():
    server, url, _ = _bff(200, js("Accendo.", cmd(PRESA, "switch", "turn_on")), location="eu")
    e = engine(assistant.ModelClient(url, "apt-prova-01", "k" * 16))
    a = ask(e, "accendi la stufetta in camera")
    server.shutdown()
    assert a["status"] == "answered" and e.devices[PRESA]["capabilities"]["switch"]["on"] is True
