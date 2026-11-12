"""D41 (P-83 review, gravity 3): when the offline_alert minutes ran out, the BFF read the engine's /devices once; a
timeout, an error or a 5xx with a JSON body ended the wait without a notification and without a line in the log,
and nothing tried again (only a dropped stream or the next alignment rearmed it). Now a failed read is logged and tried
again, three times, a short while apart."""
import asyncio

import httpx
import pytest

from bff import instances, push
from bff.repository import Apartment

APT = Apartment(apartment_id="apt-d41", tenant_id="t-d41", name="D41", instance_url="mock://builtin")
DEVICES = {"devices": [{"device_id": "dev-presa", "online": False, "label": "Presa", "last_seen": "2026-11-11T10:00:00Z"}]}


@pytest.fixture
def watch(monkeypatch):
    state = {"answers": [], "sent": [], "warned": []}

    async def minutes(apt):
        return 0.0

    async def call(apt, method, path, **kw):
        answer = state["answers"].pop(0) if state["answers"] else "ok"
        if answer == "raise":
            raise httpx.ReadTimeout("muto")
        code = 500 if answer == "500" else 200
        return httpx.Response(code, json=DEVICES if code == 200 else {"error": "x"}, request=httpx.Request("GET", "http://x"))

    async def notify_once(key, tenant_id, kind, *args):
        state["sent"].append(key)
    monkeypatch.setattr(push, "_offline_alert_minutes", minutes)
    monkeypatch.setattr(instances, "call", call)
    monkeypatch.setattr(push, "notify_once", notify_once)
    monkeypatch.setattr(push, "warn", lambda msg, **kw: state["warned"].append(msg))
    monkeypatch.setattr(push, "OFFLINE_READ_RETRY_S", 0.01, raising=False)
    return state


@pytest.mark.parametrize("first", ["raise", "500"])
def test_a_failed_read_is_logged_and_tried_again(watch, first):
    watch["answers"] = [first]
    asyncio.run(push._offline_watch(APT, "dev-presa", None, "push:offline:apt-d41:dev-presa"))
    assert len(watch["sent"]) == 1 and watch["warned"]


def test_three_failures_leave_a_line_and_no_notification(watch):
    watch["answers"] = ["raise", "500", "raise"]
    asyncio.run(push._offline_watch(APT, "dev-presa", None, "k"))
    assert watch["sent"] == [] and len(watch["warned"]) == 3


def test_a_device_back_online_sends_nothing(watch, monkeypatch):
    async def call(apt, method, path, **kw):
        body = {"devices": [{**DEVICES["devices"][0], "online": True}]}
        return httpx.Response(200, json=body, request=httpx.Request("GET", "http://x"))
    monkeypatch.setattr(instances, "call", call)
    asyncio.run(push._offline_watch(APT, "dev-presa", None, "k"))
    assert watch["sent"] == [] and watch["warned"] == []
