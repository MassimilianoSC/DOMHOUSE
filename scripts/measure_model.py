"""How fast and how reliably the assistant's model answers (C-10, D-166, D-167): a real request of the assistant, sent
N times per variant straight to Agent Platform (Vertex AI, OpenAI-compatible endpoint), timed; for every failure its
cause. Writes nothing (no Firestore, no monthly counter): it only calls the model, which costs money (cents).

    # Git Bash, from app/; application default credentials with the quota project already set
    GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python scripts/measure_model.py
    GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python scripts/measure_model.py -n 20 \\
        --model google/gemini-3.8-flash --reasoning default --reasoning low --reasoning none

Two ways to call the model (--endpoint): «openai» (default), the OpenAI-compatible endpoint the BFF uses
(https://aiplatform.googleapis.com/v1/projects/<p>/locations/eu/endpoints/openapi/chat/completions); «nativo», Vertex's
own generateContent, on a regional endpoint (--location europe-west4 or europe-west1, host <region>-aiplatform…) or on
a multi-region (--location eu or us: host aiplatform.<eu|us>.rep.googleapis.com; global: aiplatform.googleapis.com);
eu stays in Europe. --rep-host puts the OpenAI-compatible endpoint on the same host as well. E.g.
https://europe-west4-aiplatform.googleapis.com/v1/projects/<p>/locations/europe-west4/publishers/google/models/
gemini-3.8-flash:generateContent. With «nativo» the same system prompt goes in systemInstruction, the same tools in
functionDeclarations (a «params» object without properties is described with the command's fields: on, mode, setpoint,
fan), --reasoning maps to generationConfig.thinkingConfig (a number = thinkingBudget, a word = thinkingLevel); a model
missing in that region answers 404, shown as the cause.

--endpoint anthropic: Claude on Vertex AI (rawPredict, the Messages API body with anthropic_version vertex-2023-10-16,
the same credentials, no key), --model claude-haiku-5-5 or claude-sonnet-5-5, --location europe-west1, eu or global;
tools as tools/input_schema; --reasoning low|medium|high = output_config.effort, a number = thinking budget; prices with
--price-in/--price-out (€ per million tokens). A model not enabled in the project answers 403 or 404, shown as the cause.

--no-tools (D-179 test 1): no tools declared; the prompt asks the answer and the actions as a JSON object in the text,
which the script validates (shape and allowed values) and counts. The summary ends with a table: model, endpoint, tools
yes/no, timeouts, median, p95, cost per answered question, valid JSON answers, correct JSON answers.

Correct (the committente's test 2, 23 Oct): each question has its expected answer (EXPECTED: device, action, value) and
a valid JSON answer is correct when its actions are exactly that one («spegni il clima»: the living room's climate off;
«metti eco»: the mode eco; «accendi la stufetta in camera»: the bedroom's socket on) or, for the two questions, no
action (and for the temperature the living room's degrees in the sentence). Summary and table: «JSON corretti N su M
validi». Compare models with --model twice, e.g. the lite and the 3.8 flash:

    GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python scripts/measure_model.py -n 20 --endpoint nativo \
        --location eu --no-tools --reasoning 0 --model google/gemini-3.5-flash-lite --model google/gemini-3.8-flash

--prosa (test 3): five decisions of a demonstration apartment (yesterday: check-out to eco at 11, pre-arrival to comfort
at 14:30, the climate heating at 14:35, the window rule switching it off at 15:00; today the climate heating at 8) and
the question «perché il clima si è spento ieri alle 15?», one call per model; the models' answers one under the other,
to be read. -n is not used.

    GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python scripts/measure_model.py -n 20 --endpoint nativo \
        --location europe-west4 --model google/gemini-3.8-flash

Options: -n calls per variant (20); --model (repeatable; AI_MODEL or google/gemini-3.8-flash); --reasoning (repeatable:
default = no reasoning_effort sent, or a value such as low, none; default only); --location (AI_LOCATION or eu);
--max-tokens (AI_MAX_TOKENS or 4096); --timeout seconds to wait for the answer (AI_TIMEOUT_S or 25); --connect-timeout
seconds for DNS, TCP and TLS each (AI_CONNECT_TIMEOUT_S or 5). Each variant is model x reasoning.

The request is the engine's own (engine/assistant.py): its system prompt with the state of a demonstration apartment
(simulated catalog, no guest data), its tools, and five questions in turn («spegni il clima», «che temperatura c'è in
soggiorno?», «perché si è spento il clima?», «metti eco», «accendi la stufetta in camera»). One call each: the time of
one model call, the unit the assistant's budget is made of.

Causes of a failure: «timeout nella fase …» or «errore nella fase …», the phase being DNS, connessione (TCP), TLS,
invio della richiesta, attesa della risposta (no first byte within --timeout), lettura della risposta (bff/net_phase.py,
the same code as the BFF's calls); «troncata: max_tokens esauriti» (finish_reason length with nothing usable: the
reasoning ate the tokens); «endpoint HTTP <code>» (with the first 300 characters of the error; 429 is a quota of Vertex,
not the app's monthly cap, which this script never touches). Each answer shows its network times (DNS, TCP, TLS).
Prices: the app's (AI_PRICE_*), output tokens = total - input, reasoning included.
"""
import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QUESTIONS = ["spegni il clima", "che temperatura c'è in soggiorno?", "perché si è spento il clima?", "metti eco",
             "accendi la stufetta in camera"]


def measure_engine():
    from engine import core
    from engine.connector.simulated import SimulatedConnector

    return core.ApartmentEngine("apt-misura-01", SimulatedConnector(), seed=False)


def request_messages(question: str, engine=None) -> tuple[list[dict], list[dict]]:
    """(messages, tools) exactly as the engine's assistant builds its first call."""
    from engine import assistant

    e = engine or measure_engine()
    return assistant.Assistant(e, None).messages(question), assistant.TOOLS     # the engine's own request (D-182)


CLIMA, PRESA, SENSORE = "dev-clima-soggiorno", "dev-presa-camera", "dev-ambiente-soggiorno"
# test 2: question -> the expected answer (device, action, value), as the summary prints it
EXPECTED = {
    "spegni il clima": (CLIMA, "spegnere", None),
    "che temperatura c'è in soggiorno?": (SENSORE, "nessuna azione", "i gradi del soggiorno nella risposta"),
    "perché si è spento il clima?": (None, "nessuna azione", None),
    "metti eco": (None, "modalità", "eco"),
    "accendi la stufetta in camera": (PRESA, "accendere", None),
}


def json_answer_correct(question: str, data: dict, room_celsius: float | None = None) -> bool:
    """A valid JSON answer against EXPECTED: exactly the expected action, or none for the two questions."""
    acts = data.get("azioni") or []
    if question == "spegni il clima":
        return len(acts) == 1 and acts[0].get("tipo") == "comando" and acts[0].get("device_id") == CLIMA and (
            acts[0].get("action") == "turn_off"
            or (acts[0].get("action") == "set_climate" and (acts[0].get("params") or {}).get("on") is False))
    if question == "accendi la stufetta in camera":
        return len(acts) == 1 and acts[0].get("tipo") == "comando" and acts[0].get("device_id") == PRESA and (
            acts[0].get("action") == "turn_on")
    if question == "metti eco":
        return len(acts) == 1 and acts[0].get("tipo") == "modalita" and acts[0].get("modalita") == "eco"
    if question == "che temperatura c'è in soggiorno?":
        return not acts and (room_celsius is None or str(int(room_celsius)) in data.get("risposta", ""))
    return not acts


def room_celsius(engine) -> float | None:
    return ((engine.devices.get(SENSORE) or {}).get("capabilities", {}).get("temperature") or {}).get("celsius")


PROSE_QUESTION = "perché il clima si è spento ieri alle 15?"


def prose_engine():
    """test 3: the demonstration apartment with five decisions, in the engine's own words."""
    import uuid
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    e = measure_engine()
    tz = ZoneInfo(e.timezone)
    today = datetime.now(tz).date()

    def at(days_ago, hour, minute=0):
        day = today - timedelta(days=days_ago)
        return datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
    clima = {"type": "device", "device_id": CLIMA}
    for ts, actor, target, action, old, new, why in (
            (at(1, 11), "system", {"type": "apartment"}, "set_mode", "comfort", "eco",
             "Azione programmata (check-out), prenotazione bk-90001"),
            (at(1, 14, 30), "system", {"type": "apartment"}, "set_mode", "eco", "comfort",
             "Azione programmata (pre-arrivo), prenotazione bk-77812"),
            (at(1, 14, 35), "system", clima, "set_climate", "off", "on", "Climatizzatore soggiorno: 19 °C, sotto 21 °C: scalda"),
            (at(1, 15), "rule:window_open_off", clima, "turn_off", "on", "off",
             "Finestra della camera aperta da 5 minuti con il clima acceso"),
            (at(0, 8), "system", clima, "set_climate", "off", "on", "Climatizzatore soggiorno: 19,5 °C, sotto 21 °C: scalda")):
        e.log(actor, target, action, old, new, why, "applied", str(uuid.uuid4()), ts=ts, emit=False)
    return e


def parse_json_answer(text: str | None) -> dict | None:
    """The answer's JSON object when it is the one asked (json_answer_valid), else None."""
    return json.loads(_json_raw(text)) if json_answer_valid(text) else None


def _json_raw(text: str | None) -> str:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").split("\n", 1)[-1] if "\n" in raw else ""
        raw = raw.rsplit("```", 1)[0].strip()
    return raw


PARAMS_FIELDS = {"type": "object", "properties": {
    "on": {"type": "boolean"}, "mode": {"type": "string", "description": "cool, heat, dry, fan"},
    "setpoint": {"type": "number"}, "fan": {"type": "string", "description": "auto, low, mid, high"}}}


def native_schema(schema: dict) -> dict:
    """An OpenAI tool's JSON schema for Vertex's functionDeclarations: an object without properties gets the command's."""
    out = dict(schema)
    if out.get("type") == "object" and not out.get("properties"):
        return dict(PARAMS_FIELDS)
    if "properties" in out:
        out["properties"] = {k: native_schema(v) for k, v in out["properties"].items()}
    return out


def host_for(location: str) -> str:
    """Google's hosts (docs: vertex-ai/generative-ai/docs/learn/locations): the multi-regions eu and us on
    aiplatform.<eu|us>.rep.googleapis.com, global on aiplatform.googleapis.com, a single region on <region>-aiplatform…"""
    if location in ("eu", "us"):
        return f"aiplatform.{location}.rep.googleapis.com"
    if location == "global":
        return "aiplatform.googleapis.com"
    return f"{location}-aiplatform.googleapis.com"


def native_url(project: str, location: str, model: str) -> str:
    return (f"https://{host_for(location)}/v1/projects/{project}/locations/{location}/publishers/google/models/"
            f"{model.split('/')[-1]}:generateContent")


def native_body(messages: list[dict], tools: list[dict] | None, max_tokens: int, reasoning: str) -> dict:
    body = {"systemInstruction": {"parts": [{"text": messages[0]["content"]}]},
            "contents": [{"role": "user", "parts": [{"text": m["content"]}]} for m in messages[1:]],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens}}
    if tools:
        body["tools"] = [{"functionDeclarations": [
            {"name": t["function"]["name"], "description": t["function"].get("description", ""),
             "parameters": native_schema(t["function"]["parameters"])} for t in tools]}]
    if reasoning != "default":
        body["generationConfig"]["thinkingConfig"] = (
            {"thinkingBudget": int(reasoning)} if reasoning.isdigit() else {"thinkingLevel": reasoning})
    return body


def classify_native(answer: dict) -> str | None:
    """None when the answer is usable (text or a function call), else the cause."""
    cand = (answer.get("candidates") or [{}])[0]
    parts = (cand.get("content") or {}).get("parts") or []
    if any(p.get("functionCall") or (p.get("text") or "").strip() for p in parts):
        return None
    if cand.get("finishReason") == "MAX_TOKENS":
        return "troncata: max_tokens esauriti"
    return f"vuota (finishReason {cand.get('finishReason')})"


def native_usage(answer: dict) -> dict:
    """Vertex's usageMetadata in the OpenAI shape the prices read."""
    u = answer.get("usageMetadata") or {}
    return {"prompt_tokens": u.get("promptTokenCount", 0), "total_tokens": u.get("totalTokenCount", 0),
            "completion_tokens": u.get("candidatesTokenCount", 0),
            "completion_tokens_details": {"reasoning_tokens": u.get("thoughtsTokenCount")}}


def classify(answer: dict) -> str | None:
    """None when the answer is usable (text or tool calls), else the cause."""
    choice = (answer.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    if msg.get("tool_calls") or (msg.get("content") or "").strip():
        return None
    if choice.get("finish_reason") == "length":
        return "troncata: max_tokens esauriti"
    return f"vuota (finish_reason {choice.get('finish_reason')})"


JSON_INSTRUCTIONS = """

Non hai strumenti. Rispondi SOLO con un oggetto JSON, senza altro testo e senza blocchi di codice:
{"risposta": "<frase breve per il gestore>", "azioni": [<zero o più azioni>]}
Ogni azione è una di queste tre forme:
{"tipo": "modalita", "modalita": "comfort" | "eco" | "empty"}
{"tipo": "comando", "device_id": "<id del dispositivo>", "capability": "switch" | "climate" | "heating",
 "action": "turn_on" | "turn_off" | "set_climate" | "set_heating",
 "params": {"on": true | false, "mode": "cool" | "heat" | "dry" | "fan", "setpoint": <numero>, "fan": "auto" | "low" | "mid" | "high"}}
{"tipo": "programma", "quando": "<data e ora ISO 8601>", "modalita": "comfort" | "eco" | "empty"}"""

_ACTION_KEYS = {"modalita": {"tipo", "modalita"}, "comando": {"tipo", "device_id", "capability", "action", "params"},
                "programma": {"tipo", "quando", "modalita", "device_id", "capability", "action", "params"}}


def json_answer_valid(text: str | None) -> bool:
    """The no-tools test (1): the answer is the JSON object asked, with actions of the three forms and allowed values."""
    try:
        data = json.loads(_json_raw(text))
    except ValueError:
        return False
    if not isinstance(data, dict) or not isinstance(data.get("risposta"), str) or not isinstance(data.get("azioni"), list):
        return False
    for a in data["azioni"]:
        if not isinstance(a, dict) or a.get("tipo") not in _ACTION_KEYS or not set(a) <= _ACTION_KEYS[a["tipo"]]:
            return False
        if (a["tipo"] == "modalita" or (a["tipo"] == "programma" and "device_id" not in a))                 and a.get("modalita") not in ("comfort", "eco", "empty"):
            return False
        if a["tipo"] == "comando":
            if a.get("capability") not in ("switch", "climate", "heating") or not isinstance(a.get("device_id"), str):
                return False
            if a.get("action") not in ("turn_on", "turn_off", "set_climate", "set_heating"):
                return False
            params = a.get("params") or {}
            if not isinstance(params, dict) or not set(params) <= {"on", "mode", "setpoint", "fan"}:
                return False
    return True


def anthropic_url(project: str, location: str, model: str) -> str:
    """Claude on Vertex AI (rawPredict, Messages API), on the location's host."""
    return (f"https://{host_for(location)}/v1/projects/{project}/locations/{location}/publishers/anthropic/models/"
            f"{model.split('/')[-1]}:rawPredict")


def anthropic_body(messages: list[dict], tools: list[dict] | None, max_tokens: int, reasoning: str) -> dict:
    body = {"anthropic_version": "vertex-2023-10-16", "max_tokens": max_tokens, "system": messages[0]["content"],
            "messages": [{"role": "user", "content": m["content"]} for m in messages[1:]], "temperature": 0.2}
    if tools:
        body["tools"] = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                          "input_schema": t["function"]["parameters"]} for t in tools]
    if reasoning.isdigit():                         # extended thinking: a budget of tokens (temperature must be 1)
        body["thinking"] = {"type": "enabled", "budget_tokens": int(reasoning)}
        body.pop("temperature")
    elif reasoning in ("low", "medium", "high"):    # the effort of the answer (adaptive thinking by default)
        body["output_config"] = {"effort": reasoning}
    return body


def classify_anthropic(answer: dict) -> str | None:
    blocks = answer.get("content") or []
    if any(b.get("type") == "tool_use" or (b.get("type") == "text" and (b.get("text") or "").strip()) for b in blocks):
        return None
    if answer.get("stop_reason") == "max_tokens":
        return "troncata: max_tokens esauriti"
    return f"vuota (stop_reason {answer.get('stop_reason')})"


def anthropic_usage(answer: dict) -> dict:
    u = answer.get("usage") or {}
    prompt = int(u.get("input_tokens") or 0) + int(u.get("cache_read_input_tokens") or 0)
    out = int(u.get("output_tokens") or 0)
    return {"prompt_tokens": prompt, "completion_tokens": out, "total_tokens": prompt + out,
            "prompt_tokens_details": {"cached_tokens": int(u.get("cache_read_input_tokens") or 0)}}


def text_of(kind: str, answer: dict) -> str:
    if kind == "nativo":
        parts = (((answer.get("candidates") or [{}])[0]).get("content") or {}).get("parts") or []
        return "".join(p.get("text") or "" for p in parts if not p.get("thought"))
    if kind == "anthropic":
        return "".join(b.get("text") or "" for b in answer.get("content") or [] if b.get("type") == "text")
    return (((answer.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""


def cost_of(usage: dict, price_in: float, price_out: float, price_cached: float) -> float:
    prompt = int(usage.get("prompt_tokens") or 0)
    total = int(usage.get("total_tokens") or 0) or prompt + int(usage.get("completion_tokens") or 0)
    cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    return ((prompt - cached) * price_in + cached * price_cached + max(total - prompt, 0) * price_out) / 1_000_000


def one_call(url: str, token: str, body: dict, timeout: float, connect: float = 5.0,
             network: dict | None = None, kind: str = "openai") -> tuple[float, str | None, dict, str]:
    """(seconds, cause or None, usage, text of the answer); `network` receives the DNS, TCP and TLS seconds."""
    import asyncio

    from bff import net_phase

    started = time.monotonic()
    try:
        resp = asyncio.run(net_phase.post_traced(url, json=body, headers={"Authorization": f"Bearer {token}"},
                                                 connect_s=connect, read_s=timeout, network=network))
    except net_phase.PhaseFailure as exc:
        return exc.seconds, f"{'timeout' if exc.timeout else 'errore'} nella fase «{exc.phase}»", {}, ""
    took = time.monotonic() - started
    if resp.status_code != 200:
        words = " ".join(resp.text.split())[:300]          # enough to read the allowed values of a 400
        return took, f"endpoint HTTP {resp.status_code}: {words}", {}, ""
    answer = resp.json()
    if kind == "nativo":
        return took, classify_native(answer), native_usage(answer), text_of(kind, answer)
    if kind == "anthropic":
        return took, classify_anthropic(answer), anthropic_usage(answer), text_of(kind, answer)
    return took, classify(answer), answer.get("usage") or {}, text_of(kind, answer)


def call_body(kind: str, model: str, messages: list[dict], tools, max_tokens: int, reasoning: str) -> dict:
    if kind == "nativo":
        return native_body(messages, tools, max_tokens, reasoning)
    if kind == "anthropic":
        return anthropic_body(messages, tools, max_tokens, reasoning)
    body = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": max_tokens}
    if tools:
        body["tools"] = tools
    if reasoning != "default":
        body["reasoning_effort"] = reasoning
    return body


def model_url(kind: str, project: str, location: str, model: str, openai_url: str) -> str:
    if kind == "nativo":
        return native_url(project, location, model)
    if kind == "anthropic":
        return anthropic_url(project, location, model)
    return openai_url


def prose(a, project: str, token: str, models: list[str], reasoning: str, kind: str, openai_url: str) -> int:
    """test 3: one call per model with the five decisions; the answers one under the other."""
    messages, _ = request_messages(PROSE_QUESTION, prose_engine())
    print(f"\n=== Prova di prosa: «{PROSE_QUESTION}» (cinque decisioni del dimostrativo; ragionamento {reasoning})")
    total = 0.0
    for model in models:
        body = call_body(kind, model, messages, None, a.max_tokens, reasoning)
        took, cause, usage, text = one_call(model_url(kind, project, a.location, model, openai_url), token, body,
                                            a.timeout, a.connect_timeout, {}, kind)
        cost = cost_of(usage, a.price_in, a.price_out, a.price_cached) if usage else 0.0
        total += cost
        data = parse_json_answer(text)
        shown = data["risposta"] if data else (text.strip() or "(nessun testo)")
        print(f"\n--- {model} · {took:.1f} s · {cause or 'ok'} · {cost:.5f} €"
              + ("" if data or cause else " · JSON NON valido: testo così com'è"))
        print(shown)
        if data and data.get("azioni"):
            print(f"(azioni proposte: {json.dumps(data['azioni'], ensure_ascii=False)})")
    print(f"\nCosto stimato totale: {total:.4f} €")
    return 0


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, round(0.95 * len(ordered)) - 1))]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", type=int, default=20)
    ap.add_argument("--model", action="append", default=[])
    ap.add_argument("--reasoning", action="append", default=[])
    ap.add_argument("--location", default=os.environ.get("AI_LOCATION", "eu"))
    ap.add_argument("--max-tokens", type=int, default=int(os.environ.get("AI_MAX_TOKENS", "4096")))
    ap.add_argument("--timeout", type=float, default=float(os.environ.get("AI_TIMEOUT_S", "25")))
    ap.add_argument("--connect-timeout", type=float, default=float(os.environ.get("AI_CONNECT_TIMEOUT_S", "5")))
    ap.add_argument("--endpoint", choices=("openai", "nativo", "anthropic"), default="openai")
    ap.add_argument("--no-tools", action="store_true")
    ap.add_argument("--prosa", action="store_true", help="test 3: «perché il clima si è spento ieri alle 15?», "
                                                         "one answer per model, to be read")
    ap.add_argument("--rep-host", action="store_true",
                    help="with --endpoint openai: Google's host for the location (aiplatform.eu.rep.googleapis.com for eu) "
                         "instead of aiplatform.googleapis.com, which the BFF uses today")
    ap.add_argument("--price-in", type=float, default=float(os.environ.get("AI_PRICE_IN_EUR_PER_M", "0.83")))
    ap.add_argument("--price-out", type=float, default=float(os.environ.get("AI_PRICE_OUT_EUR_PER_M", "4.13")))
    ap.add_argument("--price-cached", type=float, default=float(os.environ.get("AI_PRICE_CACHED_EUR_PER_M", "0.08")))
    a = ap.parse_args()
    project = os.environ.get("GCP_PROJECT_ID", "").strip()
    if not project:
        print("Manca GCP_PROJECT_ID: scrivi GCP_PROJECT_ID=<progetto> prima del comando.")
        return 2
    if a.endpoint == "anthropic" and not a.model:
        print("Con --endpoint anthropic indica il modello, per esempio --model claude-haiku-5-5.")
        return 2
    os.environ.setdefault("APP_ENV", "dev")                   # the BFF's settings (credentials), nothing else
    from bff import ai_gateway

    models = a.model or [os.environ.get("AI_MODEL", "google/gemini-3.8-flash")]
    reasonings = a.reasoning or ["default"]
    kind = a.endpoint
    url = (f"https://{host_for(a.location) if a.rep_host else 'aiplatform.googleapis.com'}/v1/projects/{project}"
           f"/locations/{a.location}/endpoints/openapi/chat/completions")
    tools_label = "no (JSON nel testo)" if a.no_tools else "sì"
    print(f"Endpoint {kind}{(' su ' + url.split('/')[2]) if kind == 'openai' else ''}, strumenti {tools_label}, "
          f"prezzi {a.price_in:g}/{a.price_out:g} €/M")
    print(f"Misura del modello: progetto {project}, località {a.location}, {a.n} chiamate per variante, "
          f"max_tokens {a.max_tokens}, attesa della risposta {a.timeout:g} s, connessione {a.connect_timeout:g} s")
    try:
        token = ai_gateway._token()
    except Exception as exc:
        print(f"Credenziali non disponibili ({type(exc).__name__}): gcloud auth application-default login, poi "
              f"gcloud auth application-default set-quota-project {project}")
        return 2
    european = a.location == "eu" or a.location.startswith("europe-")
    excluded = "" if european else f" ({a.location}: escluso dagli ambienti, D-180; solo diagnosi)"
    if excluded:
        print(f"Attenzione: {a.location} è escluso dagli ambienti (D-180: eu o europe-…); questa misura serve solo "
              f"alla diagnosi.")
    if a.prosa:
        return prose(a, project, token, models, reasonings[0], kind, url)
    room = room_celsius(measure_engine())
    rows, total_cost = [], 0.0
    for model in models:
        for reasoning in reasonings:
            label = f"{model} · reasoning {reasoning} · {kind} {a.location}{excluded}"
            if kind == "nativo":
                url = native_url(project, a.location, model)
            elif kind == "anthropic":
                url = anthropic_url(project, a.location, model)
            print(f"\n== {label}")
            times, causes, cost, valid, correct = [], {}, 0.0, 0, 0
            for i in range(a.n):
                question = QUESTIONS[i % len(QUESTIONS)]
                messages, tools = request_messages(question)
                if a.no_tools:
                    tools = None
                    if "Rispondi SOLO con un oggetto JSON" not in messages[0]["content"]:     # the engine asks it already
                        messages[0] = {"role": "system", "content": messages[0]["content"] + JSON_INSTRUCTIONS}
                body = call_body(kind, model, messages, tools, a.max_tokens, reasoning)
                network: dict = {}
                took, cause, usage, text = one_call(url, token, body, a.timeout, a.connect_timeout, network, kind)
                if usage:
                    cost += cost_of(usage, a.price_in, a.price_out, a.price_cached)
                reasoning_tokens = ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
                                    if usage else None)
                net = (f"  rete: DNS {network['dns'] * 1000:.0f} ms, TCP {network['connessione'] * 1000:.0f} ms, "
                       f"TLS {network['tls'] * 1000:.0f} ms") if "tls" in network else ""
                checked = ""
                if a.no_tools and not cause:
                    data = parse_json_answer(text)
                    valid += data is not None
                    if data is None:
                        checked = "  JSON NON valido"
                    elif json_answer_correct(question, data, room):
                        correct += 1
                        checked = "  JSON valido, corretto"
                    else:
                        device, action, value = EXPECTED[question]
                        expected = ", ".join(str(x) for x in (device, action, value) if x)
                        checked = f"  JSON valido, NON corretto (atteso: {expected}; azioni: " \
                                  f"{json.dumps(data.get('azioni'), ensure_ascii=False)})"
                print(f"  {i + 1:2d}. {took:5.1f} s  {cause or 'ok'}{checked}"
                      + (f"  (ragionamento {reasoning_tokens} token)" if reasoning_tokens else "") + net)
                if cause:
                    causes[cause] = causes.get(cause, 0) + 1
                else:
                    times.append(took)
            total_cost += cost
            rows.append((model, label, times, causes, cost, valid, correct))
    print("\n=== Riepilogo (tempi delle sole risposte riuscite)")
    for model, label, times, causes, cost, valid, correct in rows:
        ok = len(times)
        stats = (f"min {min(times):.1f} s, mediana {statistics.median(times):.1f} s, p95 {p95(times):.1f} s, "
                 f"max {max(times):.1f} s") if times else "nessuna risposta riuscita"
        failed = "; ".join(f"{k}: {v}" for k, v in sorted(causes.items())) or "nessuno"
        print(f"{label}\n  riuscite {ok} su {a.n} · {stats}\n  fallimenti: {failed}\n  costo stimato {cost:.4f} €"
              + (f"\n  risposte JSON valide {valid} su {ok}\n  JSON corretti {correct} su {valid} validi"
                 if a.no_tools else ""))
    print(f"\nCosto stimato totale: {total_cost:.4f} €")
    print(f"\n=== Tabella\n| modello | endpoint | strumenti | timeout su {a.n} | mediana | p95 | costo per domanda | JSON valide | JSON corretti |")
    print("|---|---|---|---|---|---|---|---|---|")
    for model, label, times, causes, cost, valid, correct in rows:
        timeouts = sum(v for k, v in causes.items() if k.startswith("timeout"))
        med = f"{statistics.median(times):.1f} s" if times else "–"
        top = f"{p95(times):.1f} s" if times else "–"
        per = f"{cost / len(times):.5f} €" if times else "–"
        js = f"{valid} su {len(times)}" if a.no_tools else "–"
        right = f"{correct} su {valid}" if a.no_tools else "–"
        print(f"| {model} | {kind} {a.location}{excluded} | {tools_label} | {timeouts} | {med} | {top} | {per} | {js} "
              f"| {right} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
