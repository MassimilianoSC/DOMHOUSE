"""D-177 (D-183 points 126-127): the apartment's time zone has one source, the engine (TIMEZONE, in
/apartment.timezone); the BFF reads it from the engine and keeps the registry's copy only as a fallback; a change is
saved and written to the organisation's log by the system (timezone_changed, {from, to}); the admin's PATCH accepts
timezone and ignores it. In-process, dev auth, memory repository, the built-in demonstration engine."""
import asyncio

import httpx

from bff import instances
from bff.main import app
from bff.repository import get_repository

ADMIN, APT = "admin@demo.it", "apt-rimini-01"


def run(coro):
    return asyncio.run(coro)


async def call(method, path, who, **kw):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, path, headers={"X-Dev-User": who}, **kw)


async def entries(tenant_id):
    return [e for e in await get_repository().list_audit(tenant_id, 200) if e.action == "timezone_changed"]


def restore(tz="Europe/Rome"):
    async def main():
        repo = get_repository()
        apt = await repo.get_apartment(APT)
        apt.timezone = tz
        await repo.upsert_apartment(apt)
        app.state.mock_registry.timezones.pop(APT, None)
        sim = app.state.mock_registry.sims.get(APT)
        if sim is not None:
            sim.timezone = tz
    run(main())


def test_the_engines_time_zone_replaces_the_copy_once_with_one_entry():
    async def main():
        repo = get_repository()
        apt = await repo.get_apartment(APT)
        before = {e.audit_id for e in await entries(apt.tenant_id)}
        await instances.sync_timezone(apt, {"timezone": "Europe/London"})
        await instances.sync_timezone(apt, {"timezone": "Europe/London"})       # the same: nothing new
        await instances.sync_timezone(apt, {"timezone": "Not/AZone"})           # not a time zone: ignored
        await instances.sync_timezone(apt, {})                                  # no answer: the copy stays
        stored = await repo.get_apartment(APT)
        new = [e for e in await entries(apt.tenant_id) if e.audit_id not in before]
        return apt, stored, new
    try:
        apt, stored, new = run(main())
        assert apt.timezone == stored.timezone == "Europe/London"
        assert len(new) == 1
        e = new[0]
        assert e.actor.kind == "system" and e.target.type == "apartment" and e.target.id == APT
        assert e.details == {"from": "Europe/Rome", "to": "Europe/London"}
    finally:
        restore()


def test_the_card_reads_the_time_zone_from_the_engine(monkeypatch):
    real = instances.instance_headers

    async def engine_in_london(apt, actor, correlation_id=None):
        headers = await real(apt, actor, correlation_id)
        assert headers["X-Demo-Timezone"] == apt.timezone          # the built-in engine gets the copy
        return {**headers, "X-Demo-Timezone": "Europe/London"}     # as if TIMEZONE had changed on the engine
    monkeypatch.setattr(instances, "instance_headers", engine_in_london)

    async def card():
        engine = httpx.AsyncClient(transport=httpx.ASGITransport(app=app))   # the built-in engine, in-process
        monkeypatch.setattr(instances, "http", lambda: engine)
        instances.invalidate_version(APT)
        try:
            return await call("GET", f"/app/apartments/{APT}", ADMIN)
        finally:
            await engine.aclose()
    try:
        r = run(card())
        assert r.status_code == 200, r.text
        assert r.json()["timezone"] == "Europe/London" and r.json()["apartment"]["timezone"] == "Europe/London"
        assert run(get_repository().get_apartment(APT)).timezone == "Europe/London"
    finally:
        restore()


def test_the_admins_patch_accepts_the_time_zone_and_ignores_it():
    r = run(call("PATCH", f"/app/admin/apartments/{APT}", ADMIN, json={"timezone": "Europe/London"}))
    assert r.status_code == 200 and r.json()["timezone"] == "Europe/Rome"
    r = run(call("PATCH", f"/app/admin/apartments/{APT}", ADMIN, json={"timezone": "Fake/Zone"}))
    assert r.status_code == 200 and r.json()["timezone"] == "Europe/Rome"
