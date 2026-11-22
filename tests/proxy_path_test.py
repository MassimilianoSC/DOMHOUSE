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


def test_every_method_of_the_proxy_has_its_own_operation_id():
    """19 November: the proxy was one route with five methods, so the five shared one operationId (taken from whichever
    method came first) and every build of the BFF's OpenAPI warned «Duplicate Operation ID» (CI and local runs). The
    site reads contract/openapi.yaml, not this generated document."""
    import warnings

    from bff.main import create_app
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        spec = create_app().openapi()
    assert not [str(w.message) for w in seen if "Duplicate Operation ID" in str(w.message)]
    item = spec["paths"]["/app/apartments/{apartment_id}/instance/{path}"]
    assert sorted(item) == ["delete", "get", "patch", "post", "put"]
    assert {m: op["operationId"] for m, op in item.items()} == {
        m: f"proxy_app_apartments__apartment_id__instance__path__{m}" for m in item}


# -------- F-7 (attack-from-outside review): «?» and «#» in a segment went around a feature switched off --------
@pytest.fixture
def commands_off(monkeypatch):
    """The administrator switched «Comandi» and «Approvazioni» off for the apartment."""
    from bff.features import APP_FEATURES
    from bff.routes import apartments
    monkeypatch.setattr(apartments, "configured_features",
                        lambda *_a: set(APP_FEATURES) - {"commands", "approvals"})


@pytest.mark.parametrize("method, suffix", [
    ("POST", "/devices/x/commands%3F"), ("POST", "/devices/x/commands%23"), ("POST", "/devices/x/commands%3Fa=1"),
    ("POST", "/approvals/a1/decision%3F"), ("POST", "/approvals/a1/decision%23x"),
    ("POST", "/devices/x/commands%00"), ("POST", "/devices/x/commands%09"),
    ("GET", "/devices%3F"), ("GET", "/devices%23"), ("GET", "/devices%7F"),
])
def test_f7_query_fragment_or_control_characters_never_reach_the_instance(calls, commands_off, method, suffix):
    """Starlette decodes %3F into «?» in the path; the feature check found no feature for «commands?» and skipped,
    then httpx took «?» as the start of the query and called /devices/x/commands: the command ran."""
    r = request(method, BASE + suffix, ADMIN)
    assert r.status_code == 404, (suffix, r.status_code, r.text)
    assert calls == []


def test_f7_a_line_feed_is_cut_by_the_router_and_never_reaches_the_instance(calls, commands_off):
    """The route's {path:path} stops at «\n» (Starlette's regex): «commands%0A» arrives as «commands», refused as
    switched off; nothing reaches the instance either way."""
    assert request("POST", BASE + "/devices/x/commands%0A", ADMIN).status_code in (404, 501)
    assert calls == []


def test_f7_the_switched_off_feature_still_refuses_the_plain_path(calls, commands_off):
    assert request("POST", BASE + "/devices/x/commands", ADMIN).status_code == 501
    assert calls == []


@pytest.mark.parametrize("path", ["devices/x/commands?", "devices#x", "devices/x\ncommands", "devices/\x00"])
def test_f7_the_instance_call_refuses_them_too(path):
    """Defence in depth in bff/instances.py call, as for the dot segments."""
    from bff.repository import Apartment
    apt = Apartment(apartment_id="apt-f7", tenant_id="t", name="F-7", instance_url="mock://builtin")
    with pytest.raises(ValueError):
        asyncio.run(instances.call(apt, "POST", path, actor="system:bff"))
