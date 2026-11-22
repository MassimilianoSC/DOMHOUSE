"""F-4 (attack-from-outside review, 22 November 2026, medium): the assistant's monthly cap was checked only BEFORE a
call and the cost added AFTER it, the messages and the tools were free, and of the twin request (C-10) only the winner
was counted. Whoever had an engine's key could run many large calls at once (250 per instance) and pass the 20 € cap
many times over in one burst. Now the most a call can cost (its input and max_tokens, the twin too) is reserved
atomically before it and settled with the real cost after it (also on a failure or a cancellation); the body has limits
(number of messages, characters, only the engine's own tools); the cancelled twin's input is counted; and the server
keeps its own daily count per apartment on the engines' way. F-13 (a cap per organisation) is not this. In-process."""
import asyncio
import dataclasses

import httpx
import pytest

from bff import ai_gateway
from bff.config import get_settings
from bff.main import app
from bff.repository import get_repository

APT = "apt-bologna-01"
BIG_USAGE = {"prompt_tokens": 2000, "completion_tokens": 5000}          # 0.003 + 0.045 = 0.048 €


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def model(monkeypatch):
    sent = []
    state = {"delay": 0.0, "fail": None, "usage": BIG_USAGE}

    async def fake(body):
        sent.append(body)
        if state["delay"]:
            await asyncio.sleep(state["delay"])
        if state["fail"]:
            raise state["fail"]
        return {"choices": [{"message": {"role": "assistant", "content": "Ciao"}}], "usage": state["usage"]}
    monkeypatch.setattr(ai_gateway, "call_model", fake)
    monkeypatch.setattr(ai_gateway, "_reasoning_refused", False)
    get_repository().ai_usage = {}
    get_repository().mail_counts.clear()
    return sent, state


def settings(monkeypatch, **changes):
    s = dataclasses.replace(get_settings(), **changes)
    monkeypatch.setattr(ai_gateway, "get_settings", lambda: s)
    return s


async def post(body, client=None):
    headers = {"X-Apartment-Id": APT, "X-API-Key": get_settings().instance_api_key_fallback}
    if client is not None:
        return await client.post("/internal/ai/chat", json=body, headers=headers)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.post("/internal/ai/chat", json=body, headers=headers)


BODY = {"messages": [{"role": "system", "content": "Sei l'assistente."}, {"role": "user", "content": "Che ore sono?"}]}


def usage():
    return run(get_repository().get_ai_usage(ai_gateway.month_now()))


# -------- the cap is never passed by calls at the same time --------
def test_50_calls_at_once_with_room_for_one_make_one_model_call(model, monkeypatch):
    sent, state = model
    settings(monkeypatch, ai_monthly_cap_eur=0.10, ai_twin_model="", ai_hedge_after_s=30.0)
    state["delay"] = 0.2

    async def burst():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await asyncio.gather(*(post(BODY, c) for _ in range(50)))
    answers = run(burst())
    codes = sorted(r.status_code for r in answers)
    assert len(sent) == 1, len(sent)
    assert codes.count(200) == 1 and codes.count(429) == 49, codes
    assert all(r.json()["error"] == "monthly_cap" for r in answers if r.status_code == 429)
    assert usage()["cost_eur"] <= 0.10


def test_a_failed_or_cut_call_gives_its_reservation_back(model, monkeypatch):
    sent, state = model
    settings(monkeypatch, ai_monthly_cap_eur=0.10, ai_twin_model="", ai_hedge_after_s=30.0)
    state["fail"] = ai_gateway.GatewayError(502, "model_error", "Il modello ha risposto 500")
    assert run(post(BODY)).status_code == 502
    state["fail"] = None
    assert run(post(BODY)).status_code == 200                      # the room of the failed call is free again
    assert usage()["calls"] == 1

    get_repository().ai_usage = {}                                # room again for one call

    async def cut():                                              # rules.py cuts the call with asyncio.wait_for
        state["delay"] = 5.0
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(ai_gateway.chat(APT, dict(BODY)), timeout=0.1)
    run(cut())
    assert usage().get("reserved_eur", 0) == pytest.approx(0.0)


def test_the_cancelled_twin_is_counted_too(model, monkeypatch):
    sent, state = model
    settings(monkeypatch, ai_monthly_cap_eur=20.0, ai_twin_model="", ai_hedge_after_s=0.05)
    calls = []

    async def first_slow(body):
        calls.append(body)
        await asyncio.sleep(0.5 if len(calls) == 1 else 0.0)
        return {"choices": [{"message": {"role": "assistant", "content": "Ciao"}}], "usage": BIG_USAGE}
    monkeypatch.setattr(ai_gateway, "call_model", first_slow)
    assert run(post(BODY)).status_code == 200 and len(calls) == 2
    winner, _, _ = ai_gateway.cost_eur(BIG_USAGE)
    p_in = ai_gateway.prices()[0]
    assert usage()["cost_eur"] == pytest.approx(winner + BIG_USAGE["prompt_tokens"] * p_in / 1_000_000)


# -------- limits on what reaches the model --------
def test_too_many_messages_or_characters_or_foreign_tools_are_refused(model, monkeypatch):
    sent, _ = model
    settings(monkeypatch, ai_twin_model="")
    many = {"messages": [{"role": "user", "content": ""}] * 10_000}
    assert run(post(many)).status_code in (413, 422)
    some = {"messages": [{"role": "user", "content": "x"}] * 1000}
    r = run(post(some))
    assert r.status_code == 422 and r.json()["error"] == "bad_request", r.text
    long = {"messages": [{"role": "user", "content": "x" * 200_000}]}
    assert run(post(long)).status_code == 422
    tools = {**BODY, "tools": [{"type": "function", "function": {"name": "apri_porta", "parameters": {}}}]}
    assert run(post(tools)).status_code == 422
    assert sent == []


def test_the_engines_own_request_still_passes(model, monkeypatch):
    from engine import assistant
    sent, _ = model
    settings(monkeypatch, ai_twin_model="")
    assert run(post({**BODY, "tools": assistant.TOOLS, "temperature": 0.2})).status_code == 200
    assert run(post(BODY)).status_code == 200 and len(sent) == 2


# -------- the server's own daily count per apartment --------
def test_the_engines_way_has_a_daily_count_per_apartment(model, monkeypatch):
    sent, _ = model
    settings(monkeypatch, ai_twin_model="")
    from bff.routes import ai as ai_routes
    monkeypatch.setattr(ai_routes, "ENGINE_DAILY_CALLS", 3, raising=False)
    codes = [run(post(BODY)).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429], codes
    assert len(sent) == 3
