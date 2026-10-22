"""POST /internal/ai/chat (P-60 step 9, D-132, D-143): the engines' way to the model. In-process, memory repository,
the model replaced by a fake: authentication with the instance key, the request the BFF sends, the cost of each call
from its tokens, the monthly cap of the project, the one email at 80 %, the model's failures."""
import asyncio
import dataclasses

import httpx
import pytest

from bff import ai_gateway, invites
from bff.config import get_settings
from bff.main import app
from bff.repository import get_repository

APT = "apt-bologna-01"
USAGE = {"prompt_tokens": 1000, "completion_tokens": 200, "total_tokens": 1500,   # 300 reasoning tokens
         "prompt_tokens_details": {"cached_tokens": 400}}
COST = (600 * 0.83 + 400 * 0.08 + 500 * 4.13) / 1_000_000                       # 0.002595 €


def run(coro):
    return asyncio.run(coro)


class Sent(list):
    """The requests the fake model received; fail = the exception it raises instead of answering."""
    fail = None


@pytest.fixture
def model(monkeypatch):
    sent = Sent()

    async def fake(body):
        sent.append(body)
        if sent.fail:
            raise sent.fail
        return {"choices": [{"message": {"role": "assistant", "content": "Ciao"}}], "usage": USAGE}
    monkeypatch.setattr(ai_gateway, "call_model", fake)
    monkeypatch.setattr(ai_gateway, "_reasoning_refused", False)
    get_repository().ai_usage = {}
    return sent


async def post(body, apartment=APT, key="ok", **headers):
    key = get_settings().instance_api_key_fallback if key == "ok" else key
    h = {k: v for k, v in {"X-Apartment-Id": apartment, "X-API-Key": key, **headers}.items() if v is not None}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.post("/internal/ai/chat", json=body, headers=h)


BODY = {"messages": [{"role": "user", "content": "Che temperatura c'è?"}]}


def test_only_an_engine_with_its_key(model):
    assert run(post(BODY, key=None)).status_code == 401
    assert run(post(BODY, key="chiave-sbagliata")).status_code == 401
    assert run(post(BODY, apartment="apt-che-non-esiste")).status_code == 404
    r = run(post(BODY))
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "Ciao"
    assert len(model) == 1


def test_the_bff_chooses_model_and_tokens_and_forwards_only_what_it_knows(model):
    run(post({**BODY, "model": "un-altro-modello", "max_tokens": 99_999, "stream": True, "temperature": 0.1,
              "tools": [{"type": "function", "function": {"name": "stato"}}]}))
    sent = model[0]
    assert sent["model"] == "google/gemini-3.8-flash" and sent["max_tokens"] == 4096
    assert "stream" not in sent and sent["temperature"] == 0.1 and sent["tools"][0]["function"]["name"] == "stato"
    assert "reasoning_effort" not in sent                                         # D-182: nothing by default
    assert run(post({"messages": []})).status_code == 422


def test_each_call_is_priced_from_its_tokens_reasoning_as_output(model):
    run(post(BODY))
    u = run(get_repository().get_ai_usage(ai_gateway.month_now()))
    assert u["calls"] == 1 and (u["input_tokens"], u["output_tokens"]) == (1000, 500)
    assert u["cost_eur"] == pytest.approx(COST)


def test_at_the_cap_the_project_stops_until_next_month(model):
    get_repository().ai_usage = {ai_gateway.month_now(): {**ai_gateway_empty(), "cost_eur": 20.0}}
    r = run(post(BODY))
    assert r.status_code == 429 and r.json() == {"error": "monthly_cap",
                                                 "message": "Limite mensile raggiunto, riprova dal mese prossimo"}
    assert model == []                                             # the model is not called


def test_one_email_to_the_platform_managers_at_80_percent(model, monkeypatch):
    configured = dataclasses.replace(get_settings(), smtp_user="mittente@esempio.it", smtp_password="x")
    monkeypatch.setattr(ai_gateway, "get_settings", lambda: configured)
    emails = []
    monkeypatch.setattr(invites, "_send", lambda msg: emails.append(msg))
    get_repository().ai_usage = {ai_gateway.month_now(): {**ai_gateway_empty(), "cost_eur": 15.9999}}
    run(post(BODY))                                                # crosses 16 € (80 % of 20)
    run(post(BODY))                                                # still above: no second email this month
    assert len(emails) == 1
    msg = emails[0]
    assert "80 % del tetto mensile" in msg["Subject"] and "20.00 €" in msg.get_content()
    managers = [m.email for m in run(get_repository().list_platform_members())]
    assert managers and all(m in msg["To"] for m in managers)


def test_the_models_failures(model, monkeypatch):
    logged = []
    monkeypatch.setattr(ai_gateway, "warn", lambda msg, **kw: logged.append((msg, kw["error"], "seconds" in kw)))
    model.fail = httpx.ConnectTimeout("lento")
    assert run(post(BODY)).json()["error"] == "timeout"
    model.fail = RuntimeError("nessuna identità")
    r = run(post(BODY))
    assert r.status_code == 502 and r.json()["error"] == "model_unavailable"
    model.fail = ai_gateway.GatewayError(502, "model_error", "Il modello ha risposto 500")
    assert run(post(BODY)).json()["error"] == "model_error"
    assert run(get_repository().get_ai_usage(ai_gateway.month_now()))["calls"] == 0   # nothing is counted
    # lot 28 d: every failed call leaves a line with how long it took (a timeout left none before)
    assert logged == [("assistant model call failed", "timeout", True),
                      ("assistant model call failed", "RuntimeError", True),
                      ("assistant model call failed", "model_error", True)]


def ai_gateway_empty():
    from bff.repository.base import EMPTY_AI_USAGE
    return dict(EMPTY_AI_USAGE)


def test_a_demonstration_engines_client_is_accepted(model):
    """What bff/main.py builds with AI_DEMOS: the demonstration's id and the simulator's key, on the BFF's loopback."""
    from engine.assistant import ModelClient
    client = ModelClient("http://127.0.0.1:1", APT, get_settings().instance_api_key_fallback)
    assert client.url == "http://127.0.0.1:1/internal/ai/chat"
    r = run(post(BODY, apartment=client.apartment_id, key=client.api_key))
    assert r.status_code == 200


# -------- C-10 layer 1 --------
def test_a_refused_reasoning_effort_is_dropped_once_and_for_all(model, monkeypatch):
    monkeypatch.setattr(ai_gateway, "get_settings",
                        lambda: dataclasses.replace(get_settings(), ai_reasoning_effort="low"))
    logged = []
    monkeypatch.setattr(ai_gateway, "warn", lambda msg, **kw: logged.append(msg))
    calls = []

    async def fake(body):
        calls.append(dict(body))
        if "reasoning_effort" in body:
            raise ai_gateway.GatewayError(502, "model_error", "Il modello ha risposto 400")
        return {"choices": [{"message": {"role": "assistant", "content": "Ciao"}}], "usage": USAGE}
    monkeypatch.setattr(ai_gateway, "call_model", fake)
    assert run(post(BODY)).status_code == 200
    assert ["reasoning_effort" in c for c in calls] == [True, False]
    assert logged == ["assistant model: reasoning_effort refused, sent without it from now on"]
    run(post(BODY))
    assert "reasoning_effort" not in calls[-1] and len(calls) == 3                 # not sent again


def test_a_silent_first_request_gets_a_twin_and_the_first_answer_wins(model, monkeypatch):
    monkeypatch.setattr(ai_gateway, "get_settings",
                        lambda: dataclasses.replace(get_settings(), ai_hedge_after_s=0.05))
    calls, logged = [], []
    monkeypatch.setattr(ai_gateway, "info", lambda msg, **kw: logged.append(kw))

    async def fake(body):
        calls.append(body)
        if len(calls) == 1:
            await asyncio.sleep(2)                                                 # the slow tail of the model
        return {"choices": [{"message": {"role": "assistant", "content": f"risposta {len(calls)}"}}], "usage": USAGE}
    monkeypatch.setattr(ai_gateway, "call_model", fake)

    async def timed():
        loop = asyncio.get_running_loop()
        start = loop.time()
        r = await post(BODY)
        return r, loop.time() - start
    r, took = run(timed())
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "risposta 2"
    assert len(calls) == 2 and took < 1.0 and logged[-1]["attempt"] == 2
    assert {"apartment_id": APT, "after_s": 0.05} in logged                    # D-182: the twin recorded
    assert run(get_repository().get_ai_usage(ai_gateway.month_now()))["calls"] == 1   # one answer, one cost


def test_d181_every_answer_says_the_location(model):
    r = run(post(BODY))
    assert r.status_code == 200 and r.headers["X-AI-Location"] == "eu"
    r = run(post(BODY, key="sbagliata"))                                  # errors too
    assert r.status_code == 401 and r.headers["X-AI-Location"] == "eu"


# -------- D-182: Vertex's native endpoint, reasoning off --------
def test_d182_the_native_endpoint_with_reasoning_off(monkeypatch):
    """call_model on the native endpoint: the host of eu, generateContent, thinkingBudget 0, the answer back in the
    OpenAI shape the engine reads, usage for the prices."""
    from bff import net_phase
    sent = []

    async def fake_post(url, json=None, headers=None, connect_s=None, read_s=None, network=None):
        sent.append((url, json))
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": '{"risposta": "Fatto.", "azioni": []}'}]},
                            "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 30, "totalTokenCount": 1030}})
    monkeypatch.setattr(net_phase, "post_traced", fake_post)
    monkeypatch.setattr(ai_gateway, "_token", lambda: "tok")
    monkeypatch.setattr(ai_gateway, "get_settings",
                        lambda: dataclasses.replace(get_settings(), gcp_project_id="progetto-prova"))
    answer = run(ai_gateway.call_model({"model": "google/gemini-3.8-flash", "max_tokens": 4096, "temperature": 0.2,
                                        "messages": [{"role": "system", "content": "S"}, {"role": "user", "content": "q"}]}))
    url, body = sent[0]
    assert url == ("https://aiplatform.eu.rep.googleapis.com/v1/projects/progetto-prova/locations/eu/publishers/google/"
                   "models/gemini-3.8-flash:generateContent")
    assert body["generationConfig"] == {"temperature": 0.2, "maxOutputTokens": 4096, "thinkingConfig": {"thinkingBudget": 0}}
    assert body["systemInstruction"] == {"parts": [{"text": "S"}]} and "tools" not in body
    assert answer["choices"][0]["message"]["content"] == '{"risposta": "Fatto.", "azioni": []}'
    assert ai_gateway.cost_eur(answer["usage"])[1:] == (1000, 30)

