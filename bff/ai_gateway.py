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
import time
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from . import instances, net_phase
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


def cost_eur(usage: dict) -> tuple[float, int, int]:
    """(cost, input tokens, output tokens) of one call from its usage; output = total - input (reasoning included)."""
    s = get_settings()
    prompt = int(usage.get("prompt_tokens") or 0)
    total = int(usage.get("total_tokens") or 0) or prompt + int(usage.get("completion_tokens") or 0)
    output = max(total - prompt, int(usage.get("completion_tokens") or 0))
    cached = int((usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    cost = ((prompt - cached) * s.ai_price_in_eur_per_m + cached * s.ai_price_cached_eur_per_m
            + output * s.ai_price_out_eur_per_m) / 1_000_000
    return cost, prompt, output


async def authenticate(apartment_id: str | None, key: str | None):
    """The apartment whose engine is calling; 401 for a wrong key, 404 for an unknown apartment."""
    if not apartment_id or not key:
        raise GatewayError(401, "unauthorized", "Mancano X-Apartment-Id o X-API-Key")
    apt = await get_repository().get_apartment(apartment_id)
    if apt is None:
        raise GatewayError(404, "not_found", "Appartamento sconosciuto")
    expected = await instances.api_key(apt)
    if not hmac.compare_digest(key.encode(), expected.encode()):
        raise GatewayError(401, "unauthorized", "Chiave non valida")
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
    """The model's answer (OpenAI chat completion) from Agent Platform. Replaced in the tests."""
    s = get_settings()
    url = (f"https://aiplatform.googleapis.com/v1/projects/{s.gcp_project_id}/locations/{s.ai_location}"
           f"/endpoints/openapi/chat/completions")
    token = await asyncio.to_thread(_token)
    try:                                     # lot 30: a separate connection timeout, and the phase of a failure
        resp = await net_phase.post_traced(url, json=body, headers={"Authorization": f"Bearer {token}"},
                                           connect_s=s.ai_connect_timeout_s, read_s=s.ai_timeout_s)
    except net_phase.PhaseFailure as exc:
        if exc.timeout:
            raise GatewayError(504, "timeout", "Il modello non ha risposto in tempo", phase=exc.phase) from None
        raise GatewayError(502, "model_unavailable", "Modello non raggiungibile", phase=exc.phase) from None
    if resp.status_code != 200:
        raise GatewayError(502, "model_error", f"Il modello ha risposto {resp.status_code}")
    return resp.json()


def _alert_email(to: list[str], month: str, spent: float) -> EmailMessage:
    s = get_settings()
    msg = EmailMessage()
    msg["Subject"] = f"{s.mail_from_name}: assistente all'{s.ai_alert_percent:g} % del tetto mensile"
    msg["From"] = formataddr((s.mail_from_name, s.smtp_user))
    msg["To"] = ", ".join(to)
    msg.set_content(
        f"Nel mese {month} l'assistente ha speso {spent:.2f} € sui {s.ai_monthly_cap_eur:.2f} € del tetto del progetto.\n"
        f"Al tetto l'assistente si ferma fino al mese prossimo e risponde «{CAP_MESSAGE}».\n")
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


async def _hedged(request: dict) -> tuple[dict, int]:
    """C-10 layer 1: the model's answer and which request gave it (1 or 2). A second identical request starts when the
    first is still silent after AI_HEDGE_AFTER_S; the first answer that arrives wins, the other is cancelled. A request
    that fails is not hedged: its error comes back at once (or the other's answer, if one is running)."""
    s = get_settings()
    tasks = [asyncio.create_task(call_model(dict(request)))]
    try:
        done, _ = await asyncio.wait(tasks, timeout=s.ai_hedge_after_s)
        if not done:
            tasks.append(asyncio.create_task(call_model(dict(request))))
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


async def chat(apartment_id: str, body: dict) -> dict:
    """One model call for an engine: cap, model, tokens, cost, alert."""
    s = get_settings()
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list) or not body["messages"]:
        raise GatewayError(422, "bad_request", "messages obbligatorio")
    month = month_now()
    repo = get_repository()
    if (await repo.get_ai_usage(month))["cost_eur"] >= s.ai_monthly_cap_eur:
        raise GatewayError(429, "monthly_cap", CAP_MESSAGE)
    request = {k: v for k, v in body.items() if k in ("messages", "tools", "tool_choice", "temperature")}
    request["model"] = s.ai_model
    request["max_tokens"] = min(int(body.get("max_tokens") or s.ai_max_tokens), s.ai_max_tokens)
    if s.ai_reasoning_effort and not _reasoning_refused:
        request["reasoning_effort"] = s.ai_reasoning_effort
    started = time.monotonic()
    try:
        try:
            answer, attempt = await _hedged(request)
        except GatewayError as exc:
            if "reasoning_effort" not in request or " 400" not in exc.message:
                raise
            _refuse_reasoning(apartment_id)             # the model does not take it: once more without, then never
            request.pop("reasoning_effort")
            answer, attempt = await _hedged(request)
    except GatewayError as exc:              # lot 28 d: every failed call leaves a line, with how long it took
        warn("assistant model call failed", apartment_id=apartment_id, error=exc.error, phase=exc.phase,
             seconds=round(time.monotonic() - started, 2))
        raise
    except httpx.TimeoutException as exc:
        warn("assistant model call failed", apartment_id=apartment_id, error="timeout", phase=net_phase.phase_of(exc),
             seconds=round(time.monotonic() - started, 2))
        raise GatewayError(504, "timeout", "Il modello non ha risposto in tempo", phase=net_phase.phase_of(exc)) from None
    except Exception as exc:                 # network, credentials (e.g. no identity on a developer's PC)
        warn("assistant model call failed", apartment_id=apartment_id, error=type(exc).__name__,
             phase="credenziali o rete", seconds=round(time.monotonic() - started, 2))
        raise GatewayError(502, "model_unavailable", "Modello non raggiungibile") from None
    cost, tokens_in, tokens_out = cost_eur(answer.get("usage") or {})
    totals = await repo.add_ai_usage(month, cost, tokens_in, tokens_out)
    info("assistant model call", apartment_id=apartment_id, input_tokens=tokens_in, output_tokens=tokens_out,
         cost_eur=round(cost, 6), month_eur=round(totals["cost_eur"], 4), seconds=round(time.monotonic() - started, 2),
         attempt=attempt)
    if totals["cost_eur"] >= s.ai_monthly_cap_eur * s.ai_alert_percent / 100:
        await _alert(month, totals["cost_eur"])
    return answer
