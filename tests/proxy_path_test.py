"""F1 (Fable, D-70): the proxy towards the instance accepts only clean paths under the contract's prefixes. A path with
empty, "." or ".." segments (also percent-encoded) or an unknown first segment is refused with 404 BEFORE any call to
the instance; the blocked prefixes keep their 403. In-process (ASGI), dev auth, memory repository."""
import asyncio

import httpx
import pytest

from bff import instances
from bff.main import app

READER = {"X-Dev-User": "lettura@demo.it"}
ADMIN = {"X-Dev-User": "admin@demo.it"}
BASE = "/app/apartments/apt-rimini-01/instance"


@pytest.fixture
def calls(monkeypatch):
    seen = []

    async def fake_call(apt, method, path, **_kw):
        seen.append((apt.apartment_id, method, path))
        return httpx.Response(200, json={"ok": True})
    monkeypatch.setattr(instances, "call", fake_call)
    return seen


def request(method: str, raw_path: str, headers: dict) -> httpx.Response:
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            # percent-encoded segments are sent as written; a literal "/./" is collapsed by the client
            return await c.request(method, httpx.URL("http://t", raw_path=raw_path.encode()), headers=headers)
    return asyncio.run(go())


@pytest.mark.parametrize("suffix", [
    # (a literal "/./" is collapsed by the HTTP client into a clean path of the same apartment: nothing to refuse)
    "/%2e%2e/devices", "/%2E%2E/devices", "/devices/%2e%2e/%2e%2e", "/%2e/devices",
    "//devices", "/devices//commands", "/devices/%2e%2e", "/..%2fdevices",
])
@pytest.mark.parametrize("who", [READER, ADMIN])
def test_dot_or_empty_segments_never_reach_the_instance(calls, suffix, who):
    r = request("GET", BASE + suffix, who)
    assert r.status_code == 404, (suffix, r.status_code, r.text)
    assert calls == []


@pytest.mark.parametrize("method, suffix", [("POST", "/%2e%2e/_test/state"), ("GET", "/%2e%2e/bookings"),
                                            ("GET", "/devices/%2e%2e/stream")])
def test_blocked_prefixes_cannot_be_reached_through_dot_segments(calls, method, suffix):
    assert request(method, BASE + suffix, ADMIN).status_code == 404
    assert calls == []


@pytest.mark.parametrize("suffix", ["/qualcosa", "/api/v1/devices", "/mock", "/admin"])
def test_unknown_first_segment_is_404(calls, suffix):
    assert request("GET", BASE + suffix, ADMIN).status_code == 404
    assert calls == []


@pytest.mark.parametrize("suffix", ["/bookings", "/stream", "/openapi.json"])
def test_blocked_prefixes_keep_403(calls, suffix):
    assert request("GET", BASE + suffix, ADMIN).status_code == 403
    assert calls == []


def test_clean_paths_still_work(calls):
    assert request("GET", BASE + "/devices", READER).status_code == 200
    assert request("GET", BASE + "/devices/dev-1/commands", READER).status_code in (200, 501)
    assert calls[0] == ("apt-rimini-01", "GET", "devices")
