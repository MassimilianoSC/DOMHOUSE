"""Item 15, E2 (answer 1232 = a): the engine's decision heating_not_rising («la temperatura non risale») becomes a push
in the category «Dispositivi e sistema domotico offline» (notification_prefs.offline), as frost_inactive and
heating_unregulated: one per decision (the engine writes one per episode), grouped per boiler by its tag, kept a day.
FCM is replaced by a fake send_each_for_multicast; no network, memory repository."""
import asyncio
import dataclasses
import json
from types import SimpleNamespace

import pytest
from firebase_admin import messaging

from bff import push
from bff.config import get_settings
from bff.repository import Apartment, NotificationPrefs, Tenant, User, get_repository
from bff.sse_hub import SseEvent

TENANT = "t-not-rising"
APT = Apartment(apartment_id="apt-nr", tenant_id=TENANT, name="Milano Centro", instance_url="mock://builtin")
TS = "2026-11-23T10:00:00.000Z"
REASON = "Caldaia: accesa da 120 minuti, ma la temperatura resta sotto l'antigelo (8 °C). Controlla la caldaia."


def event(event_id: str, data: dict) -> SseEvent:
    env = {"id": event_id, "event": "decision.logged", "ts": TS, "apartment_id": APT.apartment_id,
           "correlation_id": None, "data": data}
    return SseEvent(id=event_id, event="decision.logged", data=json.dumps(env), received=0.0)


async def drain():
    while push._tasks:
        await asyncio.gather(*list(push._tasks), return_exceptions=True)


@pytest.fixture
def setup(monkeypatch):
    async def users():
        repo = get_repository()
        await repo.upsert_tenant(Tenant(tenant_id=TENANT, name="Prova"))
        await repo.upsert_user(User(uid="u-nr-1", email="nr1@test.it", tenant_id=TENANT, role="admin",
                                    push_tokens=["tok-on"]))
        await repo.upsert_user(User(uid="u-nr-2", email="nr2@test.it", tenant_id=TENANT, role="operator",
                                    push_tokens=["tok-off"], notification_prefs=NotificationPrefs(offline=False)))
    asyncio.run(users())
    get_repository().work.clear()
    monkeypatch.setattr(push, "get_settings", lambda: dataclasses.replace(get_settings(), fcm_enabled=True))
    sent = []

    def fake_send(msg, dry_run=False, app=None):
        sent.append(msg)
        return SimpleNamespace(responses=[SimpleNamespace(success=True, exception=None) for _ in msg.tokens],
                               success_count=len(msg.tokens), failure_count=0)
    monkeypatch.setattr(messaging, "send_each_for_multicast", fake_send)
    return sent


def test_the_message():
    data, headers = push.heating_not_rising_push(APT, "dev-caldaia", REASON, TS)
    assert data == {"title": "Milano Centro: la temperatura non risale", "body": REASON,
                    "link": "/a/apt-nr/decisioni", "tag": "notrising:apt-nr:dev-caldaia", "kind": "heating_not_rising",
                    "apartment_id": "apt-nr", "device_id": "dev-caldaia", "ts": TS}
    assert headers == {"Urgency": "high", "TTL": "86400"}
    data, _ = push.heating_not_rising_push(APT, "dev-caldaia", "  ", TS)
    assert data["body"] == "La caldaia è accesa, ma la temperatura resta sotto l'antigelo. Controlla la caldaia."


def test_the_decision_goes_to_who_wants_offline_once(setup):
    data = {"decision_id": "dec-nr-1", "action": "heating_not_rising",
            "target": {"type": "device", "device_id": "dev-caldaia"}, "reasoning": REASON}

    async def scenario():
        await push.on_stream_event(APT, event("e-nr-1", data))
        await push.on_stream_event(APT, event("e-nr-1", data))      # the same event from a second instance
        await drain()
    asyncio.run(scenario())
    assert len(setup) == 1
    assert setup[0].data["kind"] == "heating_not_rising" and setup[0].data["device_id"] == "dev-caldaia"
    assert setup[0].tokens == ["tok-on"]                            # u-nr-2 turned «offline» off


def test_other_decisions_of_the_season_are_not_pushes(setup):
    async def scenario():
        await push.on_stream_event(APT, event("e-nr-2", {"decision_id": "dec-nr-2", "action": "heating_season",
                                                         "target": {"type": "apartment"},
                                                         "reasoning": "Fine della stagione del riscaldamento"}))
        await drain()
    asyncio.run(scenario())
    assert setup == []
