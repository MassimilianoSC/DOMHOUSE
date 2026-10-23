"""Decision 120 (D-183 point 129): the assistant's weekly counters ai_stats and GET /app/admin/assistant-stats.
Every question counted once at its final state, the quick answers by cause, the timeouts of the full assistant, the
twins of the gateway, the weeks of Rome, the organisation's totals with the zeros, the threshold of two complete weeks
above 10 %. In-process, dev auth, memory repository, the built-in demonstration engine."""
import asyncio
import dataclasses
from datetime import UTC, datetime

import httpx
import pytest

from bff import ai_gateway, ai_stats, instances
from bff.config import get_settings
from bff.main import app
from bff.repository import get_repository

ADMIN, OPERATOR, APT, OTHER = "admin@demo.it", "operatore@demo.it", "apt-rimini-01", "apt-bologna-01"
NOW = datetime(2026, 10, 21, 10, 0, tzinfo=UTC)                     # Wednesday of week 43 (19-25 October)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def empty():
    get_repository().ai_stats = {}


async def call(method, path, who, **kw):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, path, headers={"X-Dev-User": who}, **kw)


def ask(ask_id, status="answered", reason=None, created_at="2026-10-21T08:00:00.000Z"):
    return {"ask_id": ask_id, "status": status, "reason": reason, "created_at": created_at}


def stats(apartment_id, week):
    return get_repository().ai_stats.get(f"{apartment_id}__{week}")


def test_the_weeks_of_rome():
    assert ai_stats.week_of(datetime(2026, 10, 18, 21, 30, tzinfo=UTC)) == "2026-W42"   # Sunday 23:30 in Rome
    assert ai_stats.week_of(datetime(2026, 10, 18, 22, 30, tzinfo=UTC)) == "2026-W43"   # Monday 00:30 in Rome
    assert ai_stats.bounds("2026-W43") == ("2026-10-19", "2026-10-25")
    assert ai_stats.last_weeks(3, NOW) == ["2026-W43", "2026-W42", "2026-W41"]
    assert ai_stats.last_weeks(2, datetime(2027, 1, 4, 9, tzinfo=UTC)) == ["2027-W01", "2026-W53"]


def test_every_question_once_with_the_quick_answers_and_the_timeouts():
    async def main():
        await ai_stats.count_ask(APT, ask("a1"))
        await ai_stats.count_ask(APT, ask("a1"))                                   # read again: not counted again
        await ai_stats.count_ask(APT, ask("a2", reason="risposta_rapida:timeout"))
        await ai_stats.count_ask(APT, ask("a3", reason="risposta_rapida:json_invalid"))
        await ai_stats.count_ask(APT, ask("a4", reason="risposta_rapida:monthly_cap"))
        await ai_stats.count_ask(APT, ask("a5", status="failed", reason="timeout"))
        await ai_stats.count_ask(APT, ask("a6", status="needs_approval"))
        await ai_stats.count_ask(APT, ask("a7", status="pending"))                 # not final: later
        await ai_stats.count_ask(APT, {"status": "answered"})                     # no ask_id: nothing
    run(main())
    d = stats(APT, "2026-W43")
    assert (d["asks"], d["timeouts"], d["twins"]) == (6, 2, 0)
    assert d["quick"] == {"timeout": 1, "json_invalid": 1, "monthly_cap": 1}
    assert (d["from"], d["to"]) == ("2026-10-19", "2026-10-25")


def test_the_organisations_weeks_with_zeros_and_the_threshold(monkeypatch):
    repo = get_repository()

    async def fill(apartment_id, week, asks, timeouts, batch="a"):
        for i in range(asks):
            await repo.add_ai_stats(apartment_id, week, ai_stats.bounds(week), asks=1,
                                    timeouts=int(i < timeouts), quick="timeout" if i < timeouts else None,
                                    ask_id=f"{apartment_id}-{week}-{batch}{i}")

    async def main():
        await fill(APT, "2026-W43", 5, 5)            # the current week does not count for the threshold
        await fill(APT, "2026-W42", 10, 2)           # 20 %
        await fill(APT, "2026-W41", 20, 2)           # 10 %: not above
        await repo.add_ai_stats(APT, "2026-W42", ai_stats.bounds("2026-W42"), twins=3)
        return await ai_stats.report([APT], 4, NOW)
    out = run(main())
    assert [w["week"] for w in out["weeks"]] == ["2026-W43", "2026-W42", "2026-W41", "2026-W40"]
    assert out["weeks"][1] == {"week": "2026-W42", "from": "2026-10-12", "to": "2026-10-18", "asks": 10, "timeouts": 2,
                               "twins": 3, "quick": {"timeout": 2, "model_unavailable": 0, "monthly_cap": 0,
                                                     "json_invalid": 0}}
    assert out["weeks"][3]["asks"] == 0 and out["threshold_percent"] == 10 and out["over_threshold"] is False
    run(fill(APT, "2026-W41", 1, 1, batch="b"))                 # 3 of 21: above 10 % too
    assert run(ai_stats.report([APT], 1, NOW))["over_threshold"] is True


def test_the_route_sums_only_the_organisations_apartments(monkeypatch):
    async def main():
        week = ai_stats.week_of(datetime.now(UTC))
        await ai_stats.count_ask(APT, ask("r1", created_at=datetime.now(UTC).isoformat()))
        await get_repository().add_ai_stats("apt-altra-org", week, ai_stats.bounds(week), asks=7)
        return await call("GET", "/app/admin/assistant-stats?weeks=8", ADMIN)
    r = run(main())
    assert r.status_code == 200 and len(r.json()["weeks"]) == 8 and r.json()["weeks"][0]["asks"] == 1
    for bad in ("0", "27", "x"):
        r = run(call("GET", f"/app/admin/assistant-stats?weeks={bad}", ADMIN))
        assert r.status_code == 422 and r.json()["error"] == "bad_request"
    assert run(call("GET", "/app/admin/assistant-stats", OPERATOR)).status_code == 403


def test_the_proxy_counts_the_final_state_once(monkeypatch):
    async def main():
        engine = httpx.AsyncClient(transport=httpx.ASGITransport(app=app))     # the built-in engine, in-process
        monkeypatch.setattr(instances, "http", lambda: engine)
        try:
            r = await call("POST", f"/app/apartments/{APT}/instance/ask", ADMIN, json={"text": "che temperatura c'è?"})
            assert r.status_code in (200, 202), r.text
            ask_id = r.json()["ask_id"]
            for _ in range(100):
                r = await call("GET", f"/app/apartments/{APT}/instance/ask/{ask_id}", ADMIN)
                if r.json()["status"] != "pending":
                    break
                await asyncio.sleep(0.05)
            await call("GET", f"/app/apartments/{APT}/instance/ask/{ask_id}", ADMIN)     # read again
            return r.json()
        finally:
            await engine.aclose()
    final = run(main())
    assert final["status"] in ai_stats.FINAL
    d = stats(APT, ai_stats.week_of(datetime.now(UTC)))
    assert d["asks"] == 1 and d["ask_ids"] == [final["ask_id"]]


def test_the_gateways_twins(monkeypatch):
    monkeypatch.setattr(ai_gateway, "get_settings", lambda: dataclasses.replace(get_settings(), ai_hedge_after_s=0.05))
    calls = []

    async def fake(body):
        calls.append(body)
        if len(calls) == 1:
            await asyncio.sleep(2)
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}}], "usage": {}}
    monkeypatch.setattr(ai_gateway, "call_model", fake)
    run(ai_gateway.chat(OTHER, {"messages": [{"role": "user", "content": "ciao"}]}))
    assert stats(OTHER, ai_stats.week_of(datetime.now(UTC)))["twins"] == 1


def test_a_quick_answer_for_timeout_on_a_demonstration_counts_a_timeout(monkeypatch):
    """23 Oct, 10:50 in staging: an answer «risposta rapida» with cause timeout read by the site through the proxy must
    count one question and one timeout. A demonstration whose model never answers in time, end to end in-process."""
    from engine import assistant as eng_assistant

    class Silent:                                    # the model that does not answer within the question's time
        async def chat(self, messages, tools):
            await asyncio.sleep(30)

    monkeypatch.setattr(eng_assistant, "ASK_TIMEOUT_S", 1.5)
    monkeypatch.setattr(eng_assistant, "NO_PROPOSAL_RESERVE_S", 0.5)
    registry = app.state.mock_registry
    registry.reset("apt-bologna-01")
    monkeypatch.setattr(registry, "model_for", lambda apartment_id: Silent())

    async def main():
        engine = httpx.AsyncClient(transport=httpx.ASGITransport(app=app))
        monkeypatch.setattr(instances, "http", lambda: engine)
        try:
            r = await call("POST", "/app/apartments/apt-bologna-01/instance/ask", ADMIN, json={"text": "che tempo fa?"})
            ask_id = r.json()["ask_id"]
            for _ in range(100):
                r = await call("GET", f"/app/apartments/apt-bologna-01/instance/ask/{ask_id}", ADMIN)
                if r.json()["status"] != "pending":
                    break
                await asyncio.sleep(0.05)
            return r.json()
        finally:
            await engine.aclose()
            registry.reset("apt-bologna-01")
    final = run(main())
    assert final["status"] == "answered" and final["reason"] == "risposta_rapida:timeout", final
    d = stats("apt-bologna-01", ai_stats.week_of(datetime.now(UTC)))
    assert (d["asks"], d["timeouts"], d["quick"]) == (1, 1, {"timeout": 1})
