"""F-6 (attack-from-outside review, 22 November 2026, medium): no limit on the streams a person opens. One account,
even a reader, could open 750 streams on an apartment it sees and hold every slot of the 3 instances (250 each): the
others waited or got 429 while the script reopened them. Now at most STREAMS_PER_USER (10) open streams per person
and STREAMS_PER_INSTANCE (200) in all, per instance: 429 too_many_streams over them (the site retries it as a
reconnection). A slot is given back however the response ends. In-process, memory repository, the upstream connection switched off."""
import asyncio

import pytest

from bff.auth import CurrentUser
from bff.repository import get_repository
from bff.routes import apartments
from bff.sse_hub import InstanceHub

APT = "apt-rimini-01"


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def opened(monkeypatch):
    monkeypatch.setattr(InstanceHub, "start", lambda self, last: None)
    getattr(apartments, "_open_streams", {}).clear()
    responses = []

    async def connected():
        return False

    def open_one(uid):
        user = CurrentUser(uid, f"{uid}@demo.it", "t-demo", "viewer", "Lettore")
        request = type("R", (), {"headers": {}, "is_disconnected": staticmethod(connected)})()
        r = run(apartments.stream(APT, request, user=user))
        responses.append(r)
        return r
    yield open_one
    getattr(apartments, "_open_streams", {}).clear()


def _status(r):
    return getattr(r, "status_code", 200)


def test_the_eleventh_stream_of_the_same_person_is_429_another_person_still_opens(opened, monkeypatch):
    """10 per person per instance (a6, 22 November: a manager with many tabs on computer, phone and tablet)."""
    monkeypatch.setattr(apartments, "get_tenant_apartment",
                        lambda user, aid: get_repository().get_apartment(aid))
    statuses = [_status(opened("u-f6-a")) for _ in range(11)]
    assert statuses == [200] * 10 + [429], statuses
    assert getattr(apartments, "STREAMS_PER_INSTANCE", None) == 200
    assert _status(opened("u-f6-b")) == 200


def test_the_instance_cap_holds_for_every_person_together(opened, monkeypatch):
    monkeypatch.setattr(apartments, "get_tenant_apartment",
                        lambda user, aid: get_repository().get_apartment(aid))
    monkeypatch.setattr(apartments, "STREAMS_PER_INSTANCE", 3, raising=False)
    assert [_status(opened(f"u-f6-c{i}")) for i in range(4)] == [200, 200, 200, 429]


def test_a_slot_comes_back_when_the_response_ends_even_before_its_first_step(opened, monkeypatch):
    monkeypatch.setattr(apartments, "get_tenant_apartment",
                        lambda user, aid: get_repository().get_apartment(aid))
    first = [opened("u-f6-d") for _ in range(10)]
    assert _status(opened("u-f6-d")) == 429

    async def gone():                                   # the browser went away at once
        return {"type": "http.disconnect"}

    async def send(_message):
        pass
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "method": "GET", "path": "/",
             "headers": []}
    run(first[0](scope, gone, send))
    assert _status(opened("u-f6-d")) == 200


def test_p5_a_failure_before_the_response_gives_the_slot_back(opened, monkeypatch):
    """Rereading of the medium fixes, P-5: the slot was taken before hub(), hub.start() and support.parse(); if one
    raised (a malformed support expiry), the response never existed and the slot never came back."""
    monkeypatch.setattr(apartments, "get_tenant_apartment",
                        lambda user, aid: get_repository().get_apartment(aid))

    def broken(self, last):
        raise RuntimeError("hub rotto")
    monkeypatch.setattr(InstanceHub, "start", broken)
    for _ in range(12):
        with pytest.raises(RuntimeError):
            opened("u-f6-e")
    assert apartments._open_streams.get("u-f6-e", 0) == 0
