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
    get_repository().ai_usage_tenants = {}                # F-13: each organisation's spending too
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


# -------- rereading of the medium fixes, P-1: a negative max_tokens made a negative reservation --------
@pytest.mark.parametrize("value", [-1_000_000, 0, -1, True, 1.5, "100", 4097, 99_999])
def test_p1_max_tokens_outside_1_to_the_setting_is_refused_and_reserves_nothing(model, monkeypatch, value):
    """min(int(-10**9), 4096) reserved about -11,500 €: the cap then let every other call through, and at the settling
    +11,500 € stayed reserved and the assistant stopped for everyone until the month ended."""
    sent, _ = model
    settings(monkeypatch, ai_twin_model="", ai_max_tokens=4096)
    r = run(post({**BODY, "max_tokens": value}))
    assert r.status_code == 422 and r.json()["error"] == "bad_request", (value, r.status_code, r.text[:200])
    assert sent == [] and usage()["reserved_eur"] == 0.0


def test_p1_a_valid_max_tokens_still_passes(model, monkeypatch):
    sent, _ = model
    settings(monkeypatch, ai_twin_model="", ai_max_tokens=4096)
    assert run(post({**BODY, "max_tokens": 4096})).status_code == 200
    assert run(post({**BODY, "max_tokens": 1})).status_code == 200 and sent[-1]["max_tokens"] == 1
    assert run(post(BODY)).status_code == 200 and sent[-1]["max_tokens"] == 4096     # missing: the setting


@pytest.mark.parametrize("amount", [-11_500.0, 0.0, float("nan"), float("inf"), float("-inf")])
def test_p1_the_repository_never_takes_a_reservation_that_is_not_a_positive_number(amount):
    repo = get_repository()
    repo.ai_usage = {}
    assert run(repo.reserve_ai_cost("2026-08", amount, 20.0)) is False
    assert run(repo.get_ai_usage("2026-08"))["reserved_eur"] == 0.0


def test_p1_settling_more_than_reserved_is_said_in_the_log_not_hidden(monkeypatch):
    from bff.repository import base
    seen = []
    monkeypatch.setattr(base, "warn", lambda msg, **kw: seen.append((msg, kw)), raising=False)
    repo = get_repository()
    repo.ai_usage = {}
    assert run(repo.reserve_ai_cost("2026-08", 0.5, 20.0)) is True
    totals = run(repo.settle_ai_cost("2026-08", 0.8, 0.1, 10, 5, 1))
    # rereading B-10: reservations go by key; one not found is said in the log and the others are untouched (the
    # 0.5 € one runs out by itself after an hour), never a negative reservation
    assert totals["reserved_eur"] == pytest.approx(0.5)
    assert [m for m, _ in seen] == ["assistant reservation not found"]


# -------- rereading P-2 and P-11: what the model may bill beyond the reservation --------
def test_p2_text_that_is_not_latin_is_reserved_one_token_per_character(monkeypatch):
    """chars/2 was low for CJK and emoji (one character can be one token or more)."""
    settings(monkeypatch, ai_twin_model="", ai_max_tokens=1)
    text = "电" * 50_000 + "😀" * 1_000
    request = {"messages": [{"role": "user", "content": text}], "max_tokens": 1}
    p_in = ai_gateway.prices()[0]
    assert ai_gateway.cost_ceiling(request) >= 2 * 51_000 * p_in / 1_000_000           # the request and its twin


def test_p2_a_call_cut_after_it_was_sent_is_settled_with_its_input_at_least(model, monkeypatch):
    sent, state = model
    settings(monkeypatch, ai_monthly_cap_eur=20.0, ai_twin_model="", ai_hedge_after_s=30.0)
    state["delay"] = 5.0

    async def cut():
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(ai_gateway.chat(APT, dict(BODY)), timeout=0.1)
    run(cut())
    u = usage()
    assert len(sent) == 1 and u["reserved_eur"] == pytest.approx(0.0) and u["calls"] == 0
    assert u["cost_eur"] > 0                                                          # its input, at least


def test_p2_a_model_timeout_is_settled_with_its_input_and_a_refusal_before_sending_with_nothing(model, monkeypatch):
    sent, state = model
    settings(monkeypatch, ai_monthly_cap_eur=20.0, ai_twin_model="", ai_hedge_after_s=30.0)
    state["fail"] = ai_gateway.GatewayError(504, "timeout", "Il modello non ha risposto in tempo")
    assert run(post(BODY)).status_code == 504
    assert usage()["cost_eur"] > 0
    get_repository().ai_usage = {}
    state["fail"] = ai_gateway.GatewayError(502, "model_error", "Il modello ha risposto 400")
    assert run(post(BODY)).status_code == 502
    assert usage()["cost_eur"] == 0.0                                                 # an error answer is not billed


@pytest.mark.parametrize("content", [[{"type": "image_url", "image_url": {"url": "https://x.example/a.png"}}],
                                     {"text": "ciao"}, 42])
def test_p11_a_message_carries_text_only(model, monkeypatch, content):
    sent, _ = model
    settings(monkeypatch, ai_twin_model="")
    r = run(post({"messages": [{"role": "user", "content": content}]}))
    assert r.status_code == 422 and sent == [], (content, r.status_code)


def test_p9_the_servers_daily_count_stays_above_any_engine_setting():
    """Rereading P-9: ASK_DAILY_LIMIT could be set up to 1000 on an engine, above the server's 100 a day. Now the engine
    takes at most 100 a local day, and the server counts 200 a UTC day (a UTC day holds parts of two local days)."""
    from engine.config import SETTINGS, load_config
    from bff.routes import ai as ai_routes
    assert SETTINGS["ASK_DAILY_LIMIT"][2] == 100
    assert ai_routes.ENGINE_DAILY_CALLS >= 2 * SETTINGS["ASK_DAILY_LIMIT"][2]
    base = {"APARTMENT_ID": "apt-p9", "API_KEY": "chiave-di-prova-0123456789", "CONNECTOR": "simulated"}
    assert load_config({**base, "ASK_DAILY_LIMIT": "100"}).settings["ASK_DAILY_LIMIT"] == 100
    with pytest.raises(Exception, match="ASK_DAILY_LIMIT"):
        load_config({**base, "ASK_DAILY_LIMIT": "101"})


# -------- F-13: a monthly quota per organisation, within the project's cap (answer 1242) --------
def _other_tenant(quota=None):
    from bff.repository import Apartment, Tenant
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-f13-b", name="F-13 B", ai_monthly_quota_eur=quota)))
    run(repo.upsert_apartment(Apartment(apartment_id="apt-f13-b", tenant_id="t-f13-b", name="B",
                                        instance_url="mock://builtin")))
    return "apt-f13-b"


def _set_quota(apartment_id, quota):
    repo = get_repository()
    apt = run(repo.get_apartment(apartment_id))
    run(repo.update_tenant(apt.tenant_id, {"ai_monthly_quota_eur": quota}))
    return apt.tenant_id


async def post_for(apartment, body, client=None):
    headers = {"X-Apartment-Id": apartment, "X-API-Key": get_settings().instance_api_key_fallback}
    if client is not None:
        return await client.post("/internal/ai/chat", json=body, headers=headers)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.post("/internal/ai/chat", json=body, headers=headers)


@pytest.fixture
def two_tenants(model):
    tenant_a = _set_quota(APT, None)
    other = _other_tenant()
    yield tenant_a, other
    _set_quota(APT, None)


def test_f13_an_organisation_over_its_quota_stops_only_its_own_assistant(model, monkeypatch, two_tenants):
    sent, _ = model
    settings(monkeypatch, ai_monthly_cap_eur=20.0, ai_twin_model="", ai_hedge_after_s=30.0)
    tenant_a, other = two_tenants
    _set_quota(APT, 0.10)                               # room for one call of BIG_USAGE (0.048 €), not two reservations
    assert run(post(BODY)).status_code == 200
    r = run(post(BODY))
    assert r.status_code == 429 and r.json()["error"] == "monthly_cap"               # the same quick answer
    assert run(post_for(other, BODY)).status_code == 200                            # B goes on
    month = ai_gateway.month_now()
    assert run(get_repository().get_ai_usage(month, tenant_a))["cost_eur"] == pytest.approx(0.048)
    assert run(get_repository().get_ai_usage(month, "t-f13-b"))["cost_eur"] == pytest.approx(0.048)
    assert usage()["cost_eur"] == pytest.approx(0.096)                               # the project counts both


def test_f13_without_a_quota_only_the_projects_cap_counts(model, monkeypatch, two_tenants):
    settings(monkeypatch, ai_monthly_cap_eur=20.0, ai_twin_model="", ai_hedge_after_s=30.0)
    assert [run(post(BODY)).status_code for _ in range(5)] == [200] * 5


def test_f13_calls_at_once_never_pass_the_organisations_quota(model, monkeypatch, two_tenants):
    sent, state = model
    settings(monkeypatch, ai_monthly_cap_eur=20.0, ai_twin_model="", ai_hedge_after_s=30.0)
    _set_quota(APT, 0.10)
    state["delay"] = 0.2

    async def burst():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await asyncio.gather(*(post(BODY, c) for _ in range(30)))
    codes = sorted(r.status_code for r in run(burst()))
    assert len(sent) == 1 and codes.count(200) == 1 and codes.count(429) == 29


def test_f13_the_repository_reserves_on_both_atomically():
    repo = get_repository()
    repo.ai_usage = {}
    getattr(repo, "ai_usage_tenants", {}).clear()
    assert run(repo.reserve_ai_cost("2026-07", 0.6, 20.0, "t-x", 1.0)) is True
    assert run(repo.reserve_ai_cost("2026-07", 0.6, 20.0, "t-x", 1.0)) is False           # the quota refuses
    assert run(repo.get_ai_usage("2026-07"))["reserved_eur"] == pytest.approx(0.6)       # the project unchanged
    assert run(repo.reserve_ai_cost("2026-07", 0.6, 20.0, "t-y", None)) is True           # another, no quota
    run(repo.settle_ai_cost("2026-07", 0.6, 0.2, 10, 5, 1, "t-x"))
    assert run(repo.get_ai_usage("2026-07", "t-x"))["cost_eur"] == pytest.approx(0.2)
    assert run(repo.get_ai_usage("2026-07", "t-x"))["reserved_eur"] == pytest.approx(0.0)
    assert run(repo.get_ai_usage("2026-07"))["reserved_eur"] == pytest.approx(0.6)        # t-y's still running
    assert run(repo.reserve_ai_cost("2026-07", 0.6, 1.0, "t-z", 5.0)) is False            # the project refuses


# -------- F-13, the platform's route: GET and PUT /app/platform/tenants/{tid}/ai-quota --------
PLATFORM = {"X-Dev-User": "piattaforma@demo.it"}


async def quota_call(method, tenant, body=None, who=PLATFORM):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, f"/app/platform/tenants/{tenant}/ai-quota", json=body, headers=who)


def test_f13_the_platform_reads_and_sets_a_quota_with_its_log_entries(model, monkeypatch, two_tenants):
    from bff import audit
    settings(monkeypatch, ai_monthly_cap_eur=20.0, ai_twin_model="", ai_hedge_after_s=30.0)
    tenant_a, _ = two_tenants
    assert run(post(BODY)).status_code == 200                                          # 0.048 € spent by A
    r = run(quota_call("GET", tenant_a))
    assert r.status_code == 200, r.text
    got = r.json()
    assert (got["tenant_id"], got["quota_eur"], got["month"]) == (tenant_a, None, ai_gateway.month_now())
    assert got["spent_eur"] == pytest.approx(0.048) and got["project_cap_eur"] == 20.0
    assert got["project_spent_eur"] == pytest.approx(0.048)
    r = run(quota_call("PUT", tenant_a, {"quota_eur": 5.5}))
    assert r.status_code == 200 and r.json()["quota_eur"] == 5.5
    r = run(quota_call("PUT", tenant_a, {"quota_eur": None}))
    assert r.status_code == 200 and r.json()["quota_eur"] is None
    for registry in (tenant_a, None):
        items = run(audit.page(registry, 50, None, viewer="platform"))["items"]
        changed = [(i["details"]["from"], i["details"]["to"]) for i in items if i["action"] == "ai_quota_changed"]
        assert changed[:2] == [(5.5, None), (None, 5.5)], (registry, changed)


def test_f13_a_quota_of_zero_leaves_only_the_quick_assistant(model, monkeypatch, two_tenants):
    sent, _ = model
    settings(monkeypatch, ai_monthly_cap_eur=20.0, ai_twin_model="")
    tenant_a, _ = two_tenants
    assert run(quota_call("PUT", tenant_a, {"quota_eur": 0})).status_code == 200
    assert run(post(BODY)).status_code == 429 and sent == []


@pytest.mark.parametrize("value", [-0.01, 20.01, 1.234, "5", True, float("nan")], ids=str)
def test_f13_a_quota_out_of_its_rules_is_refused_in_italian(model, monkeypatch, two_tenants, value):
    settings(monkeypatch, ai_monthly_cap_eur=20.0)
    tenant_a, _ = two_tenants
    body = '{"quota_eur": NaN}' if value != value else None
    if body:
        async def raw():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
                return await c.put(f"/app/platform/tenants/{tenant_a}/ai-quota", content=body,
                                   headers={**PLATFORM, "Content-Type": "application/json"})
        r = run(raw())
    else:
        r = run(quota_call("PUT", tenant_a, {"quota_eur": value}))
    assert r.status_code == 422 and r.json() == {
        "error": "invalid_quota",
        "message": "La quota deve essere un importo da 0 a 20,00 € (al massimo due decimali), oppure vuota per usare il "
                   "tetto del progetto."}, (value, r.text[:200])
    assert run(quota_call("PUT", tenant_a, {})).status_code == 422                    # the field is required


def test_f13_only_the_platform_and_only_an_existing_organisation(model, two_tenants):
    tenant_a, _ = two_tenants
    assert run(quota_call("GET", tenant_a, who={"X-Dev-User": "admin@demo.it"})).status_code == 403
    assert run(quota_call("GET", "t-che-non-esiste")).status_code == 404


# -------- rereading of the low fixes, B-1: the input's estimate is a true maximum --------
@pytest.mark.parametrize("text, per_char", [("1234567890" * 1_000, 1), ("\U000f0000" * 5_000, 4), ("电" * 5_000, 3)],
                         ids=["digits", "private-use", "cjk"])
def test_b1_the_input_is_reserved_as_its_utf8_bytes(monkeypatch, text, per_char):
    """A tokenizer splits each digit, and falls back to bytes for characters outside its vocabulary (up to 4 tokens a
    character): one token covers at least one UTF-8 byte, so the bytes are a ceiling the model cannot pass."""
    settings(monkeypatch, ai_twin_model="", ai_max_tokens=1)
    request = {"messages": [{"role": "user", "content": text}], "max_tokens": 1}
    assert ai_gateway.input_tokens_ceiling(request) >= per_char * len(text)


# -------- rereading of the low fixes, B-5 and B-10 --------
def test_b5_a_call_cut_after_its_twin_started_is_settled_with_both_inputs(model, monkeypatch):
    sent, state = model
    settings(monkeypatch, ai_monthly_cap_eur=20.0, ai_twin_model="", ai_hedge_after_s=0.05)
    state["delay"] = 5.0

    async def cut():
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(ai_gateway.chat(APT, dict(BODY)), timeout=0.3)
    run(cut())
    assert len(sent) == 2                                                               # the twin had started
    one = ai_gateway.input_tokens_ceiling({"messages": BODY["messages"]}) * ai_gateway.prices()[0] / 1_000_000
    assert usage()["cost_eur"] == pytest.approx(2 * one)


@pytest.mark.parametrize("phase, billed", [("attesa della risposta", True), ("lettura della risposta", True),
                                           ("invio della richiesta", True), ("DNS", False), ("connessione", False)])
def test_b5_model_unavailable_after_sending_is_settled_with_its_input(model, monkeypatch, phase, billed):
    sent, state = model
    settings(monkeypatch, ai_monthly_cap_eur=20.0, ai_twin_model="", ai_hedge_after_s=30.0)
    state["fail"] = ai_gateway.GatewayError(502, "model_unavailable", "Modello non raggiungibile", phase=phase)
    assert run(post(BODY)).status_code == 502
    assert (usage()["cost_eur"] > 0) is billed, phase


def test_b10_a_reservation_never_settled_stops_counting_after_an_hour(monkeypatch):
    from bff.repository import base
    repo = get_repository()
    repo.ai_usage = {}
    now = [100_000.0]
    monkeypatch.setattr(base, "reservation_clock", lambda: now[0])
    assert run(repo.reserve_ai_cost("2026-05", 0.6, 1.0, key="perduta")) is True       # its instance died
    assert run(repo.reserve_ai_cost("2026-05", 0.6, 1.0, key="seconda")) is False
    now[0] += 3601
    assert run(repo.get_ai_usage("2026-05"))["reserved_eur"] == pytest.approx(0.0)
    assert run(repo.reserve_ai_cost("2026-05", 0.6, 1.0, key="seconda")) is True
    seen = []
    monkeypatch.setattr(base, "warn", lambda msg, **kw: seen.append(msg))
    run(repo.settle_ai_cost("2026-05", 0.6, 0.1, 10, 5, 1, key="perduta"))           # too late: said, never negative
    assert seen == ["assistant reservation not found"]
    assert run(repo.get_ai_usage("2026-05"))["reserved_eur"] == pytest.approx(0.6)       # «seconda» still counts
