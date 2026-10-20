"""D-97 / D-98 (lot 12): demonstration apartments. The built-in mock is mounted also in production (INSTANCE_MODE=real),
reachable only from the BFF itself; an apartment carries `simulated` (set by the platform, always true on mock://);
the simulator and its reset are for admins on simulated apartments only, in every environment. In-process."""
import asyncio
import dataclasses
import re
from pathlib import Path

import httpx
import pytest

from bff import auth, instances, push
from bff.auth import CurrentUser, Identity
from bff.config import get_settings
from bff.main import app
from bff.repository import Apartment, BookingRecord, ExternalIds, Tenant, get_repository
from bff.routes import platform
from bff.sse_hub import hub_manager

ROOT = Path(__file__).resolve().parent.parent
PLAT = Identity(uid="u-plat-sim", email="piattaforma@demo.it", display_name="", user=None, platform_manager=True)
TID = "t-flatsharing-demo"


def run(coro):
    return asyncio.run(coro)


def real(monkeypatch):
    settings = dataclasses.replace(get_settings(), instance_mode="real")
    for module in (instances, platform):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    return settings


async def call(method, path, who="admin@demo.it", target=app, **kw):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=target), base_url="http://t") as c:
        return await c.request(method, path, headers={"X-Dev-User": who, **kw.pop("headers", {})}, **kw)


# -------- a) the mock in production, behind the same barriers --------
def test_mock_is_mounted_in_real_mode_and_only_reachable_from_the_bff(monkeypatch):
    from bff import main

    settings = dataclasses.replace(get_settings(), instance_mode="real")
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    prod = main.create_app()
    base = "/mock/apt-demo/api/v1/devices"
    ok = {"X-API-Key": settings.instance_api_key_fallback, "X-Actor": "system:bff",
          "X-Correlation-Id": "11111111-1111-1111-1111-111111111111"}

    async def get(headers):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=prod), base_url="http://t") as c:
            return await c.get(base, headers=headers)
    assert run(get(ok)).status_code == 200                                         # the BFF's loopback call
    assert run(get({**ok, "X-Forwarded-For": "203.0.113.7"})).status_code == 404   # F2: from the internet
    assert run(get({**ok, "X-API-Key": "sbagliata"})).status_code == 401            # N1: the key is checked


def test_the_mock_key_is_never_fixed_in_the_cloud_run_files():
    setting = re.compile(r"name:\s*INSTANCE_API_KEY_FALLBACK|INSTANCE_API_KEY_FALLBACK\s*=")   # comments may name it
    for name in ("bff/cloudrun.yaml", "bff/cloudrun.staging.yaml", "scripts/deploy.sh"):
        assert not setting.search((ROOT / name).read_text(encoding="utf-8")), name
    # D-99 N3: a developer's bff/.env (with any key or secret) never reaches the image
    ignore = (ROOT / ".gcloudignore").read_text(encoding="utf-8").split()
    assert "**/.env" in ignore and "**/.env.*" in ignore
    assert re.search(r"rm -f [^\n]*bff/\.env", (ROOT / "bff/Dockerfile").read_text(encoding="utf-8"))


def test_real_mode_reaches_mock_apartments_on_loopback_with_the_process_key(monkeypatch):
    s = real(monkeypatch)
    apt = Apartment(apartment_id="apt-demo-real", tenant_id=TID, name="Demo", instance_url="mock://builtin")
    assert instances.instance_url_problem("mock://builtin") is None
    assert instances.base_url(apt) == f"http://127.0.0.1:{s.port}{s.root_path}/mock/apt-demo-real/api/v1"
    assert run(instances.api_key(apt)) == s.instance_api_key_fallback               # never Secret Manager


# -------- b) the simulated field and its rules --------
def test_mock_apartments_are_always_simulated_and_real_ones_start_not():
    assert Apartment(apartment_id="a", tenant_id="t", name="n", instance_url="mock://builtin", simulated=False).simulated
    assert not Apartment(apartment_id="a", tenant_id="t", name="n", instance_url="http://10.0.0.1:8100").simulated
    legacy = Apartment(**{"apartment_id": "a", "tenant_id": "t", "name": "n", "instance_url": "MOCK://builtin"})
    assert legacy.simulated                                                         # records saved before the field


def test_platform_sets_simulated_and_the_log_says_so(monkeypatch):
    real(monkeypatch)
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-sim", name="Sim")))
    row = run(platform.create_tenant_apartment("t-sim", platform.ApartmentCreate(
        apartment_id="apt-sim-1", name="Vera", instance_url="http://10.198.0.2:8301"), identity=PLAT))
    assert row["simulated"] is False
    row = run(platform.relink_tenant_apartment("t-sim", "apt-sim-1", platform.ApartmentLink(simulated=True), identity=PLAT))
    assert row["simulated"] is True                                                 # a real engine in simulated mode
    row = run(platform.relink_tenant_apartment("t-sim", "apt-sim-1", platform.ApartmentLink(instance_url="mock://builtin"),
                                               identity=PLAT))
    assert row["simulated"] is True
    row = run(platform.relink_tenant_apartment("t-sim", "apt-sim-1", platform.ApartmentLink(instance_url="http://10.198.0.2:8302"),
                                               identity=PLAT))
    assert row["simulated"] is False                                                # back to a real address: not simulated
    row = run(platform.relink_tenant_apartment("t-sim", "apt-sim-1", platform.ApartmentLink(simulated=False,
                                               instance_url="mock://builtin"), identity=PLAT))
    assert row["simulated"] is True                                                 # mock:// wins over a false
    changes = [e.details for e in run(repo.list_audit("t-sim", 50)) if e.action == "apartment_simulated_changed"]
    assert changes == [{"from": False, "to": True}, {"from": True, "to": False}, {"from": False, "to": True}]


def test_no_italianway_code_on_a_demo_apartment_in_production(monkeypatch):
    run(get_repository().upsert_tenant(Tenant(tenant_id="t-sim2", name="Sim2")))
    body = platform.ApartmentCreate(apartment_id="apt-sim-code", name="Demo", instance_url="mock://builtin", italianway_id="IW-DEMO-X")
    real(monkeypatch)
    r = run(platform.create_tenant_apartment("t-sim2", body, identity=PLAT))
    assert r.status_code == 409 and b"italianway_on_demo" in r.body
    monkeypatch.undo()                                                              # staging: allowed
    assert run(platform.create_tenant_apartment("t-sim2", body, identity=PLAT))["italianway_id"] == "IW-DEMO-X"
    real(monkeypatch)
    r = run(platform.relink_tenant_apartment("t-sim2", "apt-sim-code", platform.ApartmentLink(italianway_id="IW-DEMO-Y"),
                                             identity=PLAT))
    assert r.status_code == 409


# -------- the simulator per apartment --------
def _real_apartment(simulated: bool) -> str:
    aid = f"apt-sim-gate-{int(simulated)}"
    run(get_repository().upsert_apartment(Apartment(apartment_id=aid, tenant_id=TID, name="Gate", instance_url="http://10.198.0.2:8401",
                                                    simulated=simulated)))
    return aid


def test_simulator_only_on_simulated_apartments_and_only_for_admins():
    aid = _real_apartment(False)
    r = run(call("POST", f"/app/apartments/{aid}/instance/_test/state", json={}))
    assert r.status_code == 403 and r.json()["error"] == "not_simulated"
    r = run(call("POST", f"/app/apartments/{aid}/simulator/booking", json={}))
    assert r.status_code == 403 and r.json()["error"] == "not_simulated"
    r = run(call("POST", "/app/apartments/apt-rimini-01/instance/_test/state", "operatore@demo.it", json={}))
    assert r.status_code == 403 and r.json()["error"] == "forbidden"
    assert "simulator" not in run(call("GET", "/app/me")).json()["env"]
    summary = run(call("GET", "/app/apartments/apt-rimini-01")).json()
    assert summary["simulated"] is True


# -------- c) the reset --------
def test_reset_brings_the_demo_back_and_keeps_the_rest():
    repo = get_repository()
    registry = app.state.mock_registry

    async def prepare():   # the simulated engine lives in an event loop
        s = registry.get("apt-bologna-01")
        s.set_mode("eco", "system:prova", "11111111-1111-1111-1111-111111111111", "prova")
        return s
    sim = run(prepare())
    run(repo.upsert_booking(BookingRecord(apartment_id="apt-bologna-01", booking_id="RES-RESET", checkin_at="2026-10-01T14:00:00.000Z",
                                          checkout_at="2026-10-03T10:00:00.000Z", source="simulator")))
    hub = hub_manager.hub(run(repo.get_apartment("apt-bologna-01")))
    listener: asyncio.Queue = asyncio.Queue()
    hub.subscribers.add(listener)
    push._health_down.add("apt-bologna-01")
    before = run(repo.get_apartment("apt-bologna-01"))

    assert run(call("POST", "/app/apartments/apt-bologna-01/simulator/reset", "operatore@demo.it")).status_code == 403
    r = run(call("POST", "/app/apartments/apt-bologna-01/simulator/reset"))
    assert r.status_code == 204, r.text
    assert "apt-bologna-01" not in registry.sims and sim.loop_task.cancelled()        # gone, its loop stopped

    async def fresh():
        return registry.get("apt-bologna-01")
    assert run(fresh()) is not sim                                                  # rebuilt from the seed
    assert run(repo.list_bookings("apt-bologna-01")) == []                          # the BFF's stays too
    assert listener.get_nowait() is None and "apt-bologna-01" not in hub_manager.hubs   # streams closed
    assert "apt-bologna-01" not in push._health_down
    after = run(repo.get_apartment("apt-bologna-01"))
    assert after.model_dump() == before.model_dump()                                # the apartment record is untouched
    entry = run(repo.list_audit(TID, 5))[0]
    assert entry.action == "simulator_reset" and entry.target.id == "apt-bologna-01"


def test_reset_refused_where_it_cannot_apply():
    r = run(call("POST", f"/app/apartments/{_real_apartment(False)}/simulator/reset"))
    assert r.status_code == 403 and r.json()["error"] == "not_simulated"
    r = run(call("POST", f"/app/apartments/{_real_apartment(True)}/simulator/reset"))
    assert r.status_code == 409 and r.json()["error"] == "reset_not_available"       # a real engine: no reset in the contract



# -------- D-99 (Fable on lot 12) --------
def test_mock_without_slash_is_404_from_the_internet_too(monkeypatch):
    """N1: /mock (no trailing slash) answered 307 from outside; now 404 like everything under it."""
    from bff import main

    monkeypatch.setattr(main, "get_settings", lambda: dataclasses.replace(get_settings(), instance_mode="real"))
    prod = main.create_app()

    async def get(path):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=prod), base_url="http://t") as c:
            return await c.get(path, headers={"X-Forwarded-For": "203.0.113.7"})
    for path in ("/mock", "/mock/", "/mock/apt-demo/api/v1/devices"):
        assert run(get(path)).status_code == 404, path


def test_webhook_never_feeds_a_demo_apartment_in_production(monkeypatch):
    """F1: a mock:// apartment with an Italianway code (allowed in staging, or saved before D-98) must not receive the
    real bookings in production: 409, logged for its organisation, nothing forwarded to the simulated engine."""
    import hashlib
    import hmac
    import json

    from bff.routes import webhooks

    repo = get_repository()
    run(repo.upsert_apartment(Apartment(apartment_id="apt-demo-code", tenant_id=TID, name="Demo", instance_url="mock://builtin",
                                        external_ids=ExternalIds(italianway="IW-DEMO-F1"))))
    settings = dataclasses.replace(get_settings(), instance_mode="real", italianway_webhook_secret="replace-me")
    monkeypatch.setattr(webhooks, "get_settings", lambda: settings)
    forwarded = []

    async def no_forward(*a, **k):
        forwarded.append(a)
    monkeypatch.setattr(webhooks, "forward", no_forward)
    raw = json.dumps({"event": "reservation.created", "id": "iw-ev-f1", "sent_at": "2026-11-01T10:00:00Z",
                      "reservation": {"id": "RES-F1", "apartment_id": "IW-DEMO-F1", "checkin": "2026-12-01T15:00:00Z",
                                      "checkout": "2026-12-03T10:00:00Z", "guests": 2}}).encode()
    sig = hmac.new(b"replace-me", raw, hashlib.sha256).hexdigest()
    r = run(call("POST", "/webhooks/italianway", content=raw, headers={"X-Signature": sig, "Content-Type": "application/json"}))
    assert r.status_code == 409 and r.json()["error"] == "italianway_on_demo" and forwarded == []
    log = run(repo.list_webhook_logs(TID))[0]
    assert (log.apartment_id, log.outcome, log.status_code) == ("apt-demo-code", "italianway_on_demo", 409)


def test_demo_apartments_with_a_code_are_reported_at_startup(monkeypatch):
    """F1: in production a mock:// apartment with an Italianway code is reported in the log when the BFF starts."""
    from bff.routes import webhooks

    run(get_repository().upsert_apartment(Apartment(apartment_id="apt-demo-warn", tenant_id=TID, name="Demo",
                                                    instance_url="mock://builtin", external_ids=ExternalIds(italianway="IW-DEMO-W"))))
    seen = []
    monkeypatch.setattr(webhooks, "warn", lambda msg, **f: seen.append((msg, f)))
    monkeypatch.setattr(webhooks, "get_settings", lambda: dataclasses.replace(get_settings(), instance_mode="real"))
    run(webhooks.report_demo_codes())
    assert ("demo apartment with an Italianway code", {"apartment_id": "apt-demo-warn"}) in seen
    seen.clear()
    monkeypatch.setattr(webhooks, "get_settings", lambda: dataclasses.replace(get_settings(), instance_mode="mock"))
    run(webhooks.report_demo_codes())
    assert seen == []                                                               # staging: allowed, nothing to say


def test_reset_restarts_the_background_hub_when_pushes_are_on(monkeypatch):
    """N2: with FCM on the BFF keeps one upstream stream per apartment for the pushes; the reset must bring it back."""
    from bff.routes import apartments

    monkeypatch.setattr(apartments, "get_settings", lambda: dataclasses.replace(get_settings(), fcm_enabled=True))

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/app/apartments/apt-bologna-01/simulator/reset", headers={"X-Dev-User": "admin@demo.it"})
        hub = hub_manager.hubs.get("apt-bologna-01")
        started = hub is not None and hub.task is not None and not hub.task.done()
        if hub is not None and hub.task:
            hub.task.cancel()
        return r.status_code, started
    assert run(scenario()) == (204, True)


def test_reset_in_one_loop_stops_the_engine_tasks_and_touches_no_other_apartment():
    """The reset cancels the simulated engine's loop and pending tasks (one event loop, as in the server), and leaves
    every other apartment, of the same organisation or another, exactly as it was."""
    repo = get_repository()
    registry = app.state.mock_registry

    async def scenario():
        demo = registry.get("apt-bologna-01")
        pending = asyncio.get_running_loop().create_task(asyncio.sleep(3600))
        demo.tasks.add(pending)
        same_org, other_org = registry.get("apt-rimini-01"), registry.get("apt-altra-01")
        same_org.set_mode("eco", "system:prova", "11111111-1111-1111-1111-111111111111", "prova")
        for aid in ("apt-rimini-01", "apt-altra-01"):
            await repo.upsert_booking(BookingRecord(apartment_id=aid, booking_id=f"RES-KEEP-{aid}",
                                                    checkin_at="2026-10-01T14:00:00.000Z",
                                                    checkout_at="2026-10-03T10:00:00.000Z", source="simulator"))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            r = await c.post("/app/apartments/apt-bologna-01/simulator/reset", headers={"X-Dev-User": "admin@demo.it"})
        await asyncio.sleep(0)                                                      # let the cancellations land
        return (r.status_code, demo.loop_task.cancelled(), pending.cancelled(),
                registry.sims.get("apt-rimini-01") is same_org, registry.sims.get("apt-altra-01") is other_org, same_org.mode,
                [b.booking_id for b in await repo.list_bookings("apt-rimini-01")],
                [b.booking_id for b in await repo.list_bookings("apt-altra-01")])
    status, loop_cancelled, pending_cancelled, same_kept, other_kept, mode, rimini, altra = run(scenario())
    assert (status, loop_cancelled, pending_cancelled) == (204, True, True)
    assert same_kept and other_kept and mode == "eco"
    assert "RES-KEEP-apt-rimini-01" in rimini and "RES-KEEP-apt-altra-01" in altra
