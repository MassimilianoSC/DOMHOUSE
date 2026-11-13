"""P-90 (revisione per scenari, 13 Nov), group (a), the BFF's part: S7, S14, S15, S17, S18, T1, T6. Each test failed
on the code before the repair (1f79ba9).

- S7: «Esci da tutti i dispositivi» left the push tokens of the other phones: a lost phone kept showing apartments
  and approvals.
- S14: the broker down for more than the minutes: one notification per device besides the system's.
- S15: «Consumi disponibili dal» never moved forward after a new link: false «Consumi alti» for four weeks.
- S17: «Avviso dispositivo offline» switched off during the wait notified anyway; on again with a device already
  offline, the BFF never waited again.
- S18: the engine's heating_unregulated (a boiler commanded by hand without its sensor) becomes a push.
- T1: the rule's meaning for the model says that off it also silences «sistema domotico non raggiungibile» (D-217).
- T6: the mail at the monthly cap said the assistant «si ferma»: the quick assistant answers (D-182).
"""
import asyncio
import dataclasses
import json

import httpx
import pytest

from bff import accounts, ai_gateway, instances, push
from bff import rule_proposals as rp
from bff.auth import Identity
from bff.config import get_settings
from bff.main import app
from bff.repository import Apartment, Tenant, get_repository
from bff.routes import platform
from bff.sse_hub import SseEvent

MEMBER = "m.cracchiolo@hqe.it"
PLAT = Identity(uid="u-plat-p90", email="piattaforma@demo.it", display_name="", user=None, platform_manager=True)
APT = Apartment(apartment_id="apt-p90", tenant_id="t-p90", name="P90", instance_url="mock://builtin")
DEVICES = {"devices": [{"device_id": "dev-presa", "online": False, "label": "Presa", "last_seen": "2026-11-13T10:00:00Z"}]}


def run(coro):
    return asyncio.run(coro)


def stream(apt, event, data, ts="2026-11-13T10:00:00Z"):
    """An event of the engine's stream through the hook, in one loop (its tasks run before the loop ends)."""
    async def main():
        await push.on_stream_event(apt, SseEvent(id="1", event=event, data=json.dumps({"data": data, "ts": ts}),
                                                 received=0.0))
        await asyncio.sleep(0.05)
    asyncio.run(main())


async def call(method, path, who, **kw):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, path, headers={"X-Dev-User": who}, **kw)


# -------- S7 --------
def test_s7_signing_out_everywhere_drops_every_push_token(monkeypatch):
    monkeypatch.setattr(accounts, "revoke_sessions", lambda uid: None)
    repo = get_repository()
    uid = run(repo.get_user_by_email(MEMBER)).uid
    run(repo.update_user_if_present(uid, lambda cur: cur.model_copy(update={"push_tokens": ["tok-lost-phone", "tok-pc"]})))
    r = run(call("POST", "/app/me/revoke-sessions", MEMBER))
    assert r.status_code == 204
    assert run(repo.get_user(uid)).push_tokens == []


# -------- S14 and S17: the wait of the offline notification --------
@pytest.fixture
def watch(monkeypatch):
    state = {"sent": [], "minutes": [0.0]}

    async def minutes(apt):
        return state["minutes"].pop(0) if len(state["minutes"]) > 1 else state["minutes"][0]

    async def call_(apt, method, path, **kw):
        return httpx.Response(200, json=DEVICES, request=httpx.Request("GET", "http://x"))

    async def notify_once(key, tenant_id, kind, *args):
        state["sent"].append(key)
    monkeypatch.setattr(push, "_offline_alert_minutes", minutes)
    monkeypatch.setattr(instances, "call", call_)
    monkeypatch.setattr(push, "notify_once", notify_once)
    push._health_down.discard(APT.apartment_id)
    yield state
    push._health_down.discard(APT.apartment_id)


def test_s14_no_device_notification_when_the_system_is_already_reported_down(watch):
    push._health_down.add(APT.apartment_id)
    run(push._offline_watch(APT, "dev-presa", None, "k"))
    assert watch["sent"] == []


def test_s17_the_rule_switched_off_during_the_wait_sends_nothing(watch):
    watch["minutes"] = [0.0, None]                     # on at the start of the wait, off at its end
    run(push._offline_watch(APT, "dev-presa", None, "k"))
    assert watch["sent"] == []


def test_s17_the_rule_on_again_waits_again_for_the_devices_already_offline(watch, monkeypatch):
    started = []

    async def resume(apt):
        started.append(apt.apartment_id)
    monkeypatch.setattr(push, "resume_watches", resume)
    data = {"decision_id": "dec-1", "action": "update_rules", "new_value": "offline_alert", "outcome": "applied"}
    stream(APT, "decision.logged", data)
    assert started == [APT.apartment_id]


# -------- S15 --------
def test_s15_a_new_link_starts_the_consumption_date_again(monkeypatch):
    settings = dataclasses.replace(get_settings(), instance_mode="real")
    for module in (instances, platform):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-p90-link", name="Link")))
    run(platform.create_tenant_apartment("t-p90-link", platform.ApartmentCreate(
        apartment_id="apt-p90-link", name="Link", instance_url="http://10.198.0.2:8311"), identity=PLAT))
    apt = run(repo.get_apartment("apt-p90-link"))
    run(repo.upsert_apartment(apt.model_copy(update={"energy_since": "2026-01-01T00:00:00Z"})))
    run(platform.relink_tenant_apartment("t-p90-link", "apt-p90-link", platform.ApartmentLink(italianway_id="IW-P90"),
                                         identity=PLAT))
    assert run(repo.get_apartment("apt-p90-link")).energy_since == "2026-01-01T00:00:00Z"   # same link
    run(platform.relink_tenant_apartment("t-p90-link", "apt-p90-link",
                                         platform.ApartmentLink(instance_url="http://10.198.0.2:8312"), identity=PLAT))
    assert run(repo.get_apartment("apt-p90-link")).energy_since is None


# -------- S18 --------
def test_s18_a_boiler_without_regulation_is_a_push(monkeypatch):
    sent = []

    async def notify_once(key, tenant_id, pref, data, headers):
        sent.append((key, pref, data))
    monkeypatch.setattr(push, "notify_once", notify_once)
    data = {"decision_id": "dec-2", "action": "heating_unregulated", "target": {"type": "device", "device_id": "dev-caldaia"},
            "reasoning": "Caldaia: sensore offline; segue il comando manuale senza regolazione"}
    stream(APT, "decision.logged", data)
    [(key, pref, payload)] = sent
    assert pref == "offline" and payload["kind"] == "heating_unregulated"
    assert payload["title"] == "P90: caldaia senza regolazione"
    assert payload["body"] == "Caldaia: sensore offline; segue il comando manuale senza regolazione"
    assert push.TTL_SECONDS["heating_unregulated"] == 86400


# -------- T1 and T6: texts --------
def test_t1_the_offline_rule_says_the_system_alert_does_not_depend_on_it():
    """1104 = a: the system's alert always comes, after a fixed 15 minutes (before, D-217: silenced with the rule)."""
    assert rp.MEANING["offline_alert"] == ("avvisa quando un dispositivo resta offline più di minutes minuti; l'avviso "
                                           "«sistema domotico non raggiungibile» non dipende da questa regola: arriva "
                                           "sempre dopo 15 minuti")
    assert push.SYSTEM_ALERT_MINUTES == 15.0


def test_t6_the_cap_mail_says_the_quick_assistant_answers(monkeypatch):
    settings = dataclasses.replace(get_settings(), smtp_user="mittente@example.com")
    monkeypatch.setattr(ai_gateway, "get_settings", lambda: settings)
    text = ai_gateway._alert_email(["admin@example.com"], "2026-11", 9.5).get_content()
    assert "si ferma" not in text and "risposta rapida" in text
