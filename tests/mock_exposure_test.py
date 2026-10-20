"""F2 (Fable, D-70): the built-in mock instance, mounted at /mock when INSTANCE_MODE=mock, must be reachable only by the
BFF itself (a loopback call), never from the internet. Cloud Run's front end always adds X-Forwarded-For to external
requests; the BFF's own call to 127.0.0.1 carries none. In-process (ASGI), dev mode."""
import asyncio

import httpx
import pytest

from bff.config import get_settings
from bff.main import app

MOCK = "/mock/apt-rimini-01/api/v1"
KEY = get_settings().instance_api_key_fallback
INTERNAL = {"X-API-Key": KEY, "X-Actor": "system:bff", "X-Correlation-Id": "11111111-1111-1111-1111-111111111111"}
EXTERNAL = {**INTERNAL, "X-Forwarded-For": "203.0.113.7"}   # as added by Cloud Run for a request from the internet


def get(path: str, headers: dict) -> httpx.Response:
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.get(path, headers=headers)
    return asyncio.run(go())


@pytest.mark.parametrize("path", [f"{MOCK}/health", f"{MOCK}/version", f"{MOCK}/decisions", f"{MOCK}/devices"])
def test_external_requests_to_the_mock_are_refused(path):
    assert get(path, EXTERNAL).status_code == 404


def test_internal_loopback_call_still_reaches_the_mock():
    assert get(f"{MOCK}/health", INTERNAL).status_code == 200
    assert get(f"{MOCK}/devices", INTERNAL).status_code == 200


@pytest.mark.parametrize("headers", [
    {**INTERNAL, "X-API-Key": "chiave-sbagliata"},                       # wrong key
    {k: v for k, v in INTERNAL.items() if k != "X-API-Key"},             # no key
])
def test_loopback_without_the_right_key_is_refused(headers):
    # N1 (D-71): the contract guard must check the key also when the mock is mounted under /mock
    assert get(f"{MOCK}/devices", headers).status_code == 401
    assert get(f"{MOCK}/decisions", headers).status_code == 401


def test_loopback_with_bad_actor_or_correlation_is_refused():
    assert get(f"{MOCK}/devices", {**INTERNAL, "X-Actor": "non-valido"}).status_code == 400
    assert get(f"{MOCK}/devices", {**INTERNAL, "X-Correlation-Id": "non-uuid"}).status_code == 400


def test_mock_key_is_not_the_fixed_placeholder():
    # a key left to generate must not be the value once hard-coded in cloudrun.staging.yaml, and the old value
    # must not open the mock
    assert KEY and KEY != "staging-mock-key"
    assert get(f"{MOCK}/devices", {**INTERNAL, "X-API-Key": "staging-mock-key"}).status_code == 401


def test_barriers_hold_under_a_root_path():
    # Fable D-75 note 1: both barriers compare the path relative to the app, so a root path in front changes nothing
    async def go(headers):
        transport = httpx.ASGITransport(app=app, root_path="/api")
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            return await c.get(f"/api{MOCK}/devices", headers=headers)
    assert asyncio.run(go(INTERNAL)).status_code == 200
    assert asyncio.run(go(EXTERNAL)).status_code == 404
    assert asyncio.run(go({**INTERNAL, "X-API-Key": "chiave-sbagliata"})).status_code == 401
