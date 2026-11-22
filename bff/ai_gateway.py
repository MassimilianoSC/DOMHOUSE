"""The assistant's way to the model (P-60 step 9, D-132, D-143 C-4): POST /internal/ai/chat, OpenAI-compatible.

Every engine (one per apartment on the VM, and the demonstration apartments inside this BFF) sends its model calls
here, with its apartment id and its instance key (the X-API-Key the BFF itself uses towards it). The BFF:
- keeps the project's spending of the month (UTC) in Firestore (ai_usage/{YYYY-MM}) and refuses at the cap
  (AI_MONTHLY_CAP_EUR, 20 €): 429 monthly_cap «Limite mensile raggiunto, riprova dal mese prossimo»;
- at AI_ALERT_PERCENT (80 %) sends one email a month to the platform managers;
- calls Agent Platform (Vertex AI, location eu, OpenAI-compatible endpoint) with its own identity (domotica-bff@ needs
  roles/aiplatform.user), on the model it chooses (AI_MODEL) and with at most AI_MAX_TOKENS;
- prices each call from the tokens the model reports: input (cached at their price), and output = total - input,
  so the reasoning tokens are paid as output.
The 50 questions a day per apartment are counted by the engine, before it calls (ASK_DAILY_LIMIT): one question is
several calls here. No guest data reaches this module from the engine's tools (D-132); nothing of the conversation is
logged here, only apartment, tokens and cost.
"""
import asyncio
import hmac
import json
import time
import uuid
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from . import ai_stats, instances, net_phase, vertex_native
from .config import get_settings
from .logs import info, warn
from .repository import get_repository

CAP_MESSAGE = "Limite mensile raggiunto, riprova dal mese prossimo"
_reasoning_refused = False      # C-10: Vertex refused reasoning_effort once: not sent again by this process
_credentials = None


class GatewayError(Exception):
    def __init__(self, status: int, error: str, message: str, phase: str | None = None):
        super().__init__(message)
        self.status, self.error, self.message, self.phase = status, error, message, phase


def _refuse_reasoning(apartment_id: str) -> None:
    global _reasoning_refused
    _reasoning_refused = True
    warn("assistant model: reasoning_effort refused, sent without it from now on", apartment_id=apartment_id)


def month_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def prices(twin: bool = False) -> tuple[float, float, float]:
    """(in, out, cached) € per million tokens: the main model's, or the twin's (D-187) when it is another model; a twin
    price left empty is the main one."""
    s = get_settings()
    main = (s.ai_price_in_eur_per_m, s.ai_price_out_eur_per_m, s.ai_price_cached_eur_per_m)
    if not (twin and s.ai_twin_model):
        return main
    own = (s.ai_twin_price_in_eur_per_m, s.ai_twin_price_out_eur_per_m, s.ai_twin_price_cached_eur_per_m)
    return tuple(o if o is not None else m for o, m in zip(own, main))


def cost_eur(usage: dict, price: tuple[float, float, float] | None = None) -> tuple[float, int, int]:
    """(cost, input tokens, output tokens) of one call from its usage; output = total - input (reasoning included)."""
    p_in, p_out, p_cached = price or prices()
    prompt = int(usage.get("prompt_tokens") or 0)
    total = int(usage.get("total_tokens") or 0) or prompt + int(usage.get("completion_tokens") or 0)
    output = max(total - prompt, int(usage.get("completion_tokens") or 0))
    cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    cost = ((prompt - cached) * p_in + cached * p_cached + output * p_out) / 1_000_000
    return cost, prompt, output


async def authenticate(apartment_id: str | None, key: str | None):
    """The apartment whose engine is calling. F-12 (attack-from-outside review): the same 401 for an unknown apartment
    and a wrong key (a 404 told without any key which apartment ids exist), and the right key of an apartment that
    cannot be used is refused too: switched off, not ready (created from the app, A2) or of a suspended organisation."""
    if not apartment_id or not key:
        raise GatewayError(401, "unauthorized", "Mancano X-Apartment-Id o X-API-Key")
    refused = GatewayError(401, "unauthorized", "Chiave non valida")
    repo = get_repository()
    apt = await repo.get_apartment(apartment_id)
    if apt is None:
        raise refused
    try:
        expected = await instances.api_key(apt)
    except Exception as exc:     # rereading B-2: a secret not there (A2 before it, after a deletion) is the same 401
        warn("assistant: apartment key not read", apartment_id=apartment_id, error=type(exc).__name__)
        raise refused from None
    if not hmac.compare_digest(key.encode(), expected.encode()):
        raise refused
    from .auth import tenant_status
    from .creation import usable
    if not apt.enabled or not usable(apt) or await tenant_status(repo, apt.tenant_id) != "active":
        raise refused
    return apt


def _token() -> str:
    """An access token of the BFF's identity, refreshed when it expires."""
    global _credentials
    import google.auth
    import google.auth.transport.requests
    if _credentials is None:
        _credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if not _credentials.valid:
        _credentials.refresh(google.auth.transport.requests.Request())
    return _credentials.token


async def call_model(body: dict) -> dict:
    """The model's answer (OpenAI chat completion) from Agent Platform; the model is body["model"] (the main one or
    the twin's, D-187). Replaced in the tests."""
    s = get_settings()
    native = s.ai_api == "nativo"            # D-182: Vertex's own generateContent, on the location's host
    if native:
        url = vertex_native.url(s.gcp_project_id, s.ai_location, body.get("model") or s.ai_model)
        payload = vertex_native.request(body, s.ai_thinking_budget)
    else:
        url = (f"https://aiplatform.googleapis.com/v1/projects/{s.gcp_project_id}/locations/{s.ai_location}"
               f"/endpoints/openapi/chat/completions")
        payload = body
    token = await asyncio.to_thread(_token)
    try:                                     # lot 30: a separate connection timeout, and the phase of a failure
        resp = await net_phase.post_traced(url, json=payload, headers={"Authorization": f"Bearer {token}"},
                                           connect_s=s.ai_connect_timeout_s, read_s=s.ai_timeout_s)
    except net_phase.PhaseFailure as exc:
        if exc.timeout:
            raise GatewayError(504, "timeout", "Il modello non ha risposto in tempo", phase=exc.phase) from None
        raise GatewayError(502, "model_unavailable", "Modello non raggiungibile", phase=exc.phase) from None
    if resp.status_code != 200:
        raise GatewayError(502, "model_error", f"Il modello ha risposto {resp.status_code}")
    return vertex_native.answer(resp.json()) if native else resp.json()


def _alert_email(to: list[str], month: str, spent: float) -> EmailMessage:
    s = get_settings()
    msg = EmailMessage()
    msg["Subject"] = f"{s.mail_from_name}: assistente all'{s.ai_alert_percent:g} % del tetto mensile"
    msg["From"] = formataddr((s.mail_from_name, s.smtp_user))
    msg["To"] = ", ".join(to)
    msg.set_content(
        f"Nel mese {month} l'assistente ha speso {spent:.2f} € sui {s.ai_monthly_cap_eur:.2f} € del tetto del progetto.\n"
        f"Al tetto il modello dell'assistente non viene più chiamato fino al mese prossimo: alle domande risponde "
        f"la risposta rapida, che capisce i comandi semplici (D-182).\n")
    return msg


async def _alert(month: str, spent: float) -> None:
    """One email a month to the platform managers when the spending passes AI_ALERT_PERCENT of the cap."""
    from .invites import _send
    repo = get_repository()
    if not await repo.mark_ai_alert(month):
        return
    to = [m.email for m in await repo.list_platform_members()]
    warn("assistant spending alert", month=month, spent_eur=round(spent, 4), recipients=len(to))
    if not to or not get_settings().mail_configured:
        warn("assistant spending alert not emailed", reason="no recipient" if not to else "mail not configured")
        return
    try:
        await asyncio.to_thread(_send, _alert_email(to, month, spent))
    except Exception as exc:
        warn("assistant spending alert email failed", error=type(exc).__name__)


async def _hedged(request: dict, apartment_id: str = "", ask_id: str = "",
                  started: list | None = None) -> tuple[dict, int]:
    """C-10 layer 1: the model's answer and which request gave it (1 or 2). A second request starts when the first is
    still silent after AI_HEDGE_AFTER_S; the first answer that arrives wins, the other is cancelled. D-187: the second
    goes to AI_TWIN_MODEL when there is one (another model: failures independent) and then starts at once also when
    the first fails quickly (an error, a 429); with the same model a quick error comes back at once, as before."""
    s = get_settings()
    twin_model = s.ai_twin_model or request.get("model")
    tasks = [asyncio.create_task(call_model(dict(request)))]
    try:
        done, _ = await asyncio.wait(tasks, timeout=s.ai_hedge_after_s)
        failed = bool(done) and tasks[0].exception() is not None
        if not done or (failed and s.ai_twin_model):
            info("assistant model twin started", apartment_id=apartment_id, **_ask(ask_id), after_s=s.ai_hedge_after_s,
                 model=twin_model, reason="errore" if done else "silenzio")
            if apartment_id:
                await ai_stats.count_twin(apartment_id)              # decision 120: the twins of the week
            tasks.append(asyncio.create_task(call_model({**request, "model": twin_model})))
        if started is not None:                                  # F-4: how many requests went to the model
            started.append(len(tasks))
        error: BaseException | None = None
        running = list(tasks)
        while running:
            done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                running.remove(t)
                if t.exception() is None:
                    return t.result(), tasks.index(t) + 1
                error = t.exception()
        raise error
    finally:
        for t in tasks:
            if not t.done():
                t.cancel()


SENT_PHASES = ("invio della richiesta", "attesa della risposta", "lettura della risposta")   # bff/net_phase.py
MAX_MESSAGES = 20                 # F-4: the engine sends 2 (D-182), a rules' proposal 2
MAX_CHARACTERS = 160_000          # F-4: the engine's largest request, 200 devices, is about 79,000 (twice that)
ROLES = ("system", "user", "assistant", "tool")


def _body_problem(body: dict) -> str | None:
    """F-4: what reaches the model, besides the 256 KiB of bff/body_limit.py: a few messages of known roles, a bounded
    number of characters, and tools only if they are the engine's own (engine/assistant.py TOOLS)."""
    messages = body["messages"]
    if len(messages) > MAX_MESSAGES:
        return f"Al massimo {MAX_MESSAGES} messaggi"
    if not all(isinstance(m, dict) and m.get("role") in ROLES for m in messages):
        return "Messaggi non validi"
    # rereading P-11: text only (an image or a file costs many tokens in few characters); null only for an assistant's
    # turn that carries tool calls
    if not all(isinstance(m.get("content"), str) or (m.get("content") is None and m.get("role") == "assistant")
               for m in messages):
        return "Messaggi non validi: solo testo"
    if len(json.dumps(messages, ensure_ascii=False)) > MAX_CHARACTERS:
        return "Richiesta troppo lunga"
    tools = body.get("tools")
    if tools:
        from engine.assistant import TOOLS
        if tools != TOOLS:
            return "Strumenti non ammessi"
    return None


def input_tokens_ceiling(request: dict) -> int:
    """F-4, rereadings P-2 and B-1: a true maximum of the input's tokens: its UTF-8 bytes. A token covers at least one
    byte (a tokenizer splits each digit, and falls back to bytes, up to 4 a character, outside its vocabulary), so the
    model cannot bill more; Italian text costs about a quarter of that, the rest of the reservation comes back at the
    settling."""
    text = json.dumps(request.get("messages") or [], ensure_ascii=False) + json.dumps(request.get("tools") or [])
    return len(text.encode("utf-8")) + 1


def cost_ceiling(request: dict) -> float:
    """F-4: the most this request can cost, reserved before it: its input (input_tokens_ceiling), max_tokens of output,
    and the twin request too (C-10, D-187), at its own prices."""
    tokens_in, tokens_out = input_tokens_ceiling(request), int(request["max_tokens"])
    total = 0.0
    for twin in (False, True):
        p_in, p_out, _ = prices(twin)
        total += (tokens_in * p_in + tokens_out * p_out) / 1_000_000
    return total


def _ask(ask_id: str) -> dict:
    """The question in the log lines, when the engine said it (X-Ask-Id); nothing for the rules' proposals."""
    return {"ask_id": ask_id} if ask_id else {}


async def chat(apartment_id: str, body: dict, ask_id: str = "") -> dict:
    """One model call for an engine: cap, model, tokens, cost, alert. ask_id: only for the log lines."""
    s = get_settings()
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list) or not body["messages"]:
        raise GatewayError(422, "bad_request", "messages obbligatorio")
    if problem := _body_problem(body):
        raise GatewayError(422, "bad_request", problem)
    month = month_now()
    repo = get_repository()
    request = {k: v for k, v in body.items() if k in ("messages", "tools", "tool_choice", "temperature")}
    request["model"] = s.ai_model
    # rereading P-1: an integer from 1 to AI_MAX_TOKENS, or missing (the setting); never clamped in silence (a negative
    # one made a negative reservation)
    asked = body.get("max_tokens")
    if asked is not None and (type(asked) is not int or not 1 <= asked <= s.ai_max_tokens):
        raise GatewayError(422, "bad_request", f"max_tokens deve essere un intero da 1 a {s.ai_max_tokens}")
    request["max_tokens"] = s.ai_max_tokens if asked is None else asked
    if s.ai_reasoning_effort and not _reasoning_refused:
        request["reasoning_effort"] = s.ai_reasoning_effort
    # F-4 (attack-from-outside review): the cap was checked only before the call and the cost added after it, so calls
    # at the same time all passed. Now the most the call can cost is reserved atomically first, and settled after it
    # with the real cost, whatever happens in between (a failure, a cancellation by rules.py's time limit)
    reserved = cost_ceiling(request)
    # F-13 (answer 1242): the organisation's quota too, in the same reservation; without one only the project's cap.
    # Over either, the same 429 monthly_cap: the engine answers with the quick assistant
    apt = await repo.get_apartment(apartment_id)
    tenant_id = apt.tenant_id if apt else None
    tenant = await repo.get_tenant(tenant_id) if tenant_id else None
    quota = tenant.ai_monthly_quota_eur if tenant else None
    key = uuid.uuid4().hex                       # rereading B-10: the reservation by its key, with an expiry
    if not await repo.reserve_ai_cost(month, reserved, s.ai_monthly_cap_eur, tenant_id, quota, key=key):
        raise GatewayError(429, "monthly_cap", CAP_MESSAGE)
    started = time.monotonic()
    cost, tokens_in, tokens_out, counted = 0.0, 0, 0, 0
    went: list = []
    # rereadings P-2 and B-5: a call cut after it was sent (rules.py's time limit, the model's timeout, the model lost
    # after the request went) may be billed for its input: settled with that at least, for each request that went (the
    # twin at its own price), never 0
    tokens_ceiling = input_tokens_ceiling(request)

    def input_cost() -> float:
        price = prices()[0] + (prices(True)[0] if went and went[-1] == 2 else 0.0)
        return tokens_ceiling * price / 1_000_000
    try:
        answer, attempt = await _call(request, apartment_id, ask_id, went)
        twin = attempt == 2 and bool(s.ai_twin_model)
        cost, tokens_in, tokens_out = cost_eur(answer.get("usage") or {}, prices(twin))   # D-187: the winner's prices
        if went and went[-1] == 2:
            # F-4 (ESITO point 3): the other request, cancelled or failed, read the same input: counted at its input
            # price (what it may have written is not known; the bill is checked in the live verifications, point 9)
            cost += tokens_in * prices(not twin and bool(s.ai_twin_model))[0] / 1_000_000
        counted = 1
    except (asyncio.CancelledError, TimeoutError):
        cost = input_cost()
        raise
    except GatewayError as exc:
        if exc.error == "timeout" or (exc.error == "model_unavailable" and exc.phase in SENT_PHASES):
            cost = input_cost()
        raise
    finally:
        totals = await asyncio.shield(repo.settle_ai_cost(month, reserved, cost, tokens_in, tokens_out, counted,
                                                          tenant_id, key=key))
    info("assistant model call", apartment_id=apartment_id, **_ask(ask_id),
         model=s.ai_twin_model if twin else s.ai_model, input_tokens=tokens_in, output_tokens=tokens_out,
         cost_eur=round(cost, 6), month_eur=round(totals["cost_eur"], 4), seconds=round(time.monotonic() - started, 2),
         attempt=attempt, requests=went[-1] if went else 1)
    if totals["cost_eur"] >= s.ai_monthly_cap_eur * s.ai_alert_percent / 100:
        await _alert(month, totals["cost_eur"])
    return answer


async def _call(request: dict, apartment_id: str, ask_id: str, went: list) -> tuple[dict, int]:
    """The call with its twin (C-10), once more without reasoning_effort when the model refuses it; every failure leaves
    a line and becomes a GatewayError. went: how many requests went to the model (F-4)."""
    started = time.monotonic()
    try:
        try:
            answer, attempt = await _hedged(request, apartment_id, ask_id, went)
        except GatewayError as exc:
            if "reasoning_effort" not in request or " 400" not in exc.message:
                raise
            _refuse_reasoning(apartment_id)             # the model does not take it: once more without, then never
            request.pop("reasoning_effort")
            went.clear()
            answer, attempt = await _hedged(request, apartment_id, ask_id, went)
    except GatewayError as exc:              # lot 28 d: every failed call leaves a line, with how long it took
        warn("assistant model call failed", apartment_id=apartment_id, **_ask(ask_id), error=exc.error, phase=exc.phase,
             seconds=round(time.monotonic() - started, 2))
        raise
    except httpx.TimeoutException as exc:
        warn("assistant model call failed", apartment_id=apartment_id, **_ask(ask_id), error="timeout", phase=net_phase.phase_of(exc),
             seconds=round(time.monotonic() - started, 2))
        raise GatewayError(504, "timeout", "Il modello non ha risposto in tempo", phase=net_phase.phase_of(exc)) from None
    except Exception as exc:                 # network, credentials (e.g. no identity on a developer's PC)
        warn("assistant model call failed", apartment_id=apartment_id, **_ask(ask_id), error=type(exc).__name__,
             phase="credenziali o rete", seconds=round(time.monotonic() - started, 2))
        raise GatewayError(502, "model_unavailable", "Modello non raggiungibile") from None
    return answer, attempt
