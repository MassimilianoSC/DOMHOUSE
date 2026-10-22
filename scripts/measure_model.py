"""How fast and how reliably the assistant's model answers (C-10, D-166, D-167): a real request of the assistant, sent
N times per variant straight to Agent Platform (Vertex AI, OpenAI-compatible endpoint), timed; for every failure its
cause. Writes nothing (no Firestore, no monthly counter): it only calls the model, which costs money (cents).

    # Git Bash, from app/; application default credentials with the quota project already set
    GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python scripts/measure_model.py
    GCP_PROJECT_ID=domotica-poc-511707 .venv/Scripts/python scripts/measure_model.py -n 20 \\
        --model google/gemini-3.8-flash --reasoning default --reasoning low --reasoning none

Two ways to call the model (--endpoint): «openai» (default), the OpenAI-compatible endpoint the BFF uses
(https://aiplatform.googleapis.com/v1/projects/<p>/locations/eu/endpoints/openapi/chat/completions); «nativo», Vertex's
own generateContent on a regional endpoint (--location europe-west4 or europe-west1: it stays in Europe), e.g.
https://europe-west4-aiplatform.googleapis.com/v1/projects/<p>/locations/europe-west4/publishers/google/models/
gemini-3.8-flash:generateContent. With «nativo» the same system prompt goes in systemInstruction, the same tools in
functionDeclarations (a «params» object without properties is described with the command's fields: on, mode, setpoint,
fan), --reasoning maps to generationConfig.thinkingConfig (a number = thinkingBudget, a word = thinkingLevel); a model
missing in that region answers 404, shown as the cause. --no-tools sends the questions without tools (said in the
summary), in case the endpoint refuses the tools.

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
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QUESTIONS = ["spegni il clima", "che temperatura c'è in soggiorno?", "perché si è spento il clima?", "metti eco",
             "accendi la stufetta in camera"]


def request_messages(question: str) -> tuple[list[dict], list[dict]]:
    """(messages, tools) exactly as the engine's assistant builds its first call."""
    from engine import assistant, core
    from engine.connector.simulated import SimulatedConnector

    e = core.ApartmentEngine("apt-misura-01", SimulatedConnector(), seed=False)
    helper = assistant.Assistant(e, None)
    state = json.dumps({"appartamento": helper.tool("leggi_appartamento", {}, []),
                        **helper.tool("leggi_dispositivi", {}, [])}, ensure_ascii=False, default=str)
    now = datetime.now(ZoneInfo(e.timezone)).strftime("%Y-%m-%d %H:%M")
    system = assistant.SYSTEM_PROMPT.format(now=now, tz=e.timezone, state=state)
    return [{"role": "system", "content": system}, {"role": "user", "content": question}], assistant.TOOLS


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


def one_call(url: str, token: str, body: dict, timeout: float, connect: float = 5.0,
             network: dict | None = None, native: bool = False) -> tuple[float, str | None, dict]:
    """(seconds, cause or None, usage); `network` receives the DNS, TCP and TLS seconds of a call that got that far."""
    import asyncio

    from bff import net_phase

    started = time.monotonic()
    try:
        resp = asyncio.run(net_phase.post_traced(url, json=body, headers={"Authorization": f"Bearer {token}"},
                                                 connect_s=connect, read_s=timeout, network=network))
    except net_phase.PhaseFailure as exc:
        return exc.seconds, f"{'timeout' if exc.timeout else 'errore'} nella fase «{exc.phase}»", {}
    took = time.monotonic() - started
    if resp.status_code != 200:
        words = " ".join(resp.text.split())[:300]          # enough to read the allowed values of a 400
        return took, f"endpoint HTTP {resp.status_code}: {words}", {}
    answer = resp.json()
    if native:
        return took, classify_native(answer), native_usage(answer)
    return took, classify(answer), answer.get("usage") or {}


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
    ap.add_argument("--endpoint", choices=("openai", "nativo"), default="openai")
    ap.add_argument("--no-tools", action="store_true")
    a = ap.parse_args()
    project = os.environ.get("GCP_PROJECT_ID", "").strip()
    if not project:
        print("Manca GCP_PROJECT_ID: scrivi GCP_PROJECT_ID=<progetto> prima del comando.")
        return 2
    os.environ.setdefault("APP_ENV", "dev")                   # the BFF's settings for its prices, nothing else
    from bff import ai_gateway

    models = a.model or [os.environ.get("AI_MODEL", "google/gemini-3.8-flash")]
    reasonings = a.reasoning or ["default"]
    native = a.endpoint == "nativo"
    if native and a.location in ("eu", "global"):
        print("Con --endpoint nativo serve una regione, per esempio --location europe-west4 (oppure europe-west1).")
        return 2
    url = (f"https://aiplatform.googleapis.com/v1/projects/{project}/locations/{a.location}"
           f"/endpoints/openapi/chat/completions")
    print(f"Endpoint {'nativo regionale (generateContent)' if native else 'compatibile OpenAI'}, "
          f"strumenti {'no' if a.no_tools else 'sì'}")
    print(f"Misura del modello: progetto {project}, località {a.location}, {a.n} chiamate per variante, "
          f"max_tokens {a.max_tokens}, attesa della risposta {a.timeout:g} s, connessione {a.connect_timeout:g} s")
    try:
        token = ai_gateway._token()
    except Exception as exc:
        print(f"Credenziali non disponibili ({type(exc).__name__}): gcloud auth application-default login, poi "
              f"gcloud auth application-default set-quota-project {project}")
        return 2
    rows, total_cost = [], 0.0
    for model in models:
        for reasoning in reasonings:
            label = f"{model} · reasoning {reasoning} · {'nativo ' + a.location if native else 'openai ' + a.location}"
            if native:
                url = (f"https://{a.location}-aiplatform.googleapis.com/v1/projects/{project}/locations/{a.location}"
                       f"/publishers/google/models/{model.split('/')[-1]}:generateContent")
            print(f"\n== {label}")
            times, causes, cost = [], {}, 0.0
            for i in range(a.n):
                messages, tools = request_messages(QUESTIONS[i % len(QUESTIONS)])
                if a.no_tools:
                    tools = None
                if native:
                    body = native_body(messages, tools, a.max_tokens, reasoning)
                else:
                    body = {"model": model, "messages": messages, "temperature": 0.2, "max_tokens": a.max_tokens}
                    if tools:
                        body["tools"] = tools
                    if reasoning != "default":
                        body["reasoning_effort"] = reasoning
                network: dict = {}
                took, cause, usage = one_call(url, token, body, a.timeout, a.connect_timeout, network, native)
                if usage:
                    c, _, _ = ai_gateway.cost_eur(usage)
                    cost += c
                reasoning_tokens = ((usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
                                    if usage else None)
                net = (f"  rete: DNS {network['dns'] * 1000:.0f} ms, TCP {network['connessione'] * 1000:.0f} ms, "
                       f"TLS {network['tls'] * 1000:.0f} ms") if "tls" in network else ""
                print(f"  {i + 1:2d}. {took:5.1f} s  {cause or 'ok'}"
                      + (f"  (ragionamento {reasoning_tokens} token)" if reasoning_tokens else "") + net)
                if cause:
                    causes[cause] = causes.get(cause, 0) + 1
                else:
                    times.append(took)
            total_cost += cost
            rows.append((label, times, causes, cost))
    print("\n=== Riepilogo (tempi delle sole risposte riuscite)")
    for label, times, causes, cost in rows:
        ok = len(times)
        stats = (f"min {min(times):.1f} s, mediana {statistics.median(times):.1f} s, p95 {p95(times):.1f} s, "
                 f"max {max(times):.1f} s") if times else "nessuna risposta riuscita"
        failed = "; ".join(f"{k}: {v}" for k, v in sorted(causes.items())) or "nessuno"
        print(f"{label}\n  riuscite {ok} su {a.n} · {stats}\n  fallimenti: {failed}\n  costo stimato {cost:.4f} €")
    print(f"\nCosto stimato totale: {total_cost:.4f} €")
    return 0


if __name__ == "__main__":
    sys.exit(main())
