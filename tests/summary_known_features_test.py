"""D27 (P-83 review, gravity 2), the server's part: when the engine stopped answering, the apartment's summary (#7, #8)
kept /version for 60 s and then gave features [] and contract_version None: the site turned every page into
«Funzione non disponibile» while its stream still said «In tempo reale». Now the summary keeps the last list of features
known for that link (apartment and engine address: a new link starts empty), with online False; and with the engine
not answering /health either, it does not wait for the other calls. (The site's part, «Sistema domotico non
raggiungibile» instead of «In tempo reale», is o2's.)"""
import asyncio

import httpx
import pytest

from bff import instances
from bff.repository import Apartment

VERSION = {"contract_version": "1.0.5", "features": ["apartment", "devices", "rules"]}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def engine(monkeypatch):
    """A stand-in engine: answering or not, with the calls it got."""
    state = {"up": True, "calls": []}

    async def call(apt, method, path, **kw):
        state["calls"].append(path)
        if not state["up"]:
            raise httpx.ConnectError("refused")
        body = VERSION if path == "/version" else {"status": "ok"} if path == "/health" else {"items": []}
        return httpx.Response(200, json=body, request=httpx.Request(method, "http://x" + path))
    monkeypatch.setattr(instances, "call", call)
    instances._version_cache.clear()
    instances._version_known.clear()
    return state


def apt(url="http://10.0.0.9:8150"):
    return Apartment(apartment_id="apt-d27", tenant_id="t-d27", name="D27", instance_url=url)


def test_an_engine_that_stops_answering_keeps_its_known_features(engine):
    first = run(instances.summary(apt(), "system:test"))
    assert first["online"] and first["features"]
    engine["up"] = False
    instances.invalidate_version("apt-d27")                # the 60 s are over
    engine["calls"].clear()
    later = run(instances.summary(apt(), "system:test"))
    assert later["online"] is False and later["health"] is None
    assert later["features"] == first["features"] and later["contract_version"] == "1.0.5"
    assert set(engine["calls"]) == {"/version", "/health"}    # no wait for the other calls of an engine that is down


def test_a_new_link_does_not_inherit_the_features(engine):
    run(instances.summary(apt(), "system:test"))
    engine["up"] = False
    instances.invalidate_version("apt-d27")
    other = run(instances.summary(apt("http://10.0.0.9:8151"), "system:test"))
    assert other["features"] == [] and other["contract_version"] is None
