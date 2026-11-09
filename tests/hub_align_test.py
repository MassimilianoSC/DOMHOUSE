"""D-201: every instance keeps its connections to the engines aligned with the registry, because a change is made on one
instance only. D-198: an apartment created while the server runs sends notifications without waiting for a restart.
Memory repository; the connection to the engines is a fake, the hubs and their tasks are the real ones."""
import asyncio
import dataclasses
from types import SimpleNamespace

import pytest

from bff import instances, push
from bff.auth import CurrentUser
from bff.config import get_settings
from bff.repository import Apartment, get_repository
from bff.routes import apartments as routes
from bff.sse_hub import InstanceHub, hub_manager

APT, URL_A, URL_B = "apt-hub", "http://motore-a.test", "http://motore-b.test"


def apartment(**kw) -> Apartment:
    return Apartment(**{"apartment_id": APT, "tenant_id": "t-hub", "name": "Prova", "instance_url": URL_A, **kw})


class Upstream:
    """Stays open after sending its lines, as an engine with nothing to say."""
    status_code = 200

    def __init__(self, lines):
        self.lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def aiter_lines(self):
        for line in self.lines:
            yield line
        await asyncio.sleep(3600)


@pytest.fixture
def world(monkeypatch):
    state = SimpleNamespace(apartments=[], connections=[], lines=[], fcm=True)
    monkeypatch.setattr(push, "get_settings", lambda: dataclasses.replace(get_settings(), fcm_enabled=state.fcm))

    async def headers(apt, actor, correlation_id=None):
        return {}

    def stream(method, url, headers, timeout):
        state.connections.append((url, headers.get("Last-Event-ID")))
        return Upstream(state.lines)

    async def listed():
        return list(state.apartments)
    monkeypatch.setattr(instances, "instance_headers", headers)
    monkeypatch.setattr(instances, "http", lambda: SimpleNamespace(stream=stream))
    monkeypatch.setattr(get_repository(), "list_apartments", listed)
    hub_manager.hubs.clear()
    push._offline_timers.clear()
    yield state
    hub_manager.hubs.clear()
    push._offline_timers.clear()


def play(scenario):
    async def main():
        try:
            return await scenario()
        finally:
            push.stop_background()
            await hub_manager.stop_all()
    return asyncio.run(main())


async def settle():
    for _ in range(10):
        await asyncio.sleep(0)


async def align():
    await push.align_hubs_once()
    await settle()


def test_an_apartment_created_while_running_gets_its_connection(world):
    """D-198: until now it sent no notifications until the server restarted."""
    async def scenario():
        await align()
        assert hub_manager.hubs == {}
        world.apartments.append(apartment())
        await align()
    play(scenario)
    assert world.connections == [(URL_A + "/api/v1/stream", None)]


@pytest.mark.parametrize("change", ["removed", "disabled"])
def test_a_connection_no_longer_wanted_is_closed(world, change):
    async def scenario():
        world.apartments.append(apartment())
        await align()
        hub = hub_manager.hubs[APT]
        browser = asyncio.Queue()
        hub.subscribers.add(browser)
        timer = asyncio.create_task(asyncio.sleep(3600))
        push._offline_timers[(APT, "dev-1")] = timer
        if change == "removed":
            world.apartments.clear()
        else:
            world.apartments[0] = apartment(enabled=False)
        await align()
        assert APT not in hub_manager.hubs and hub.task.cancelled() and timer.cancelled()
        assert browser.get_nowait() is None
    play(scenario)
    assert len(world.connections) == 1


@pytest.mark.parametrize("change", [{"instance_url": URL_B}, {"port": 8443}, {"instance_secret_name": "altro"}])
def test_a_changed_link_is_connected_again_and_the_browsers_reload(world, change):
    async def scenario():
        world.apartments.append(apartment())
        await align()
        old = hub_manager.hubs[APT]
        old.last_id = "41"                                     # numbered by the engine it was connected to
        browser = asyncio.Queue()
        old.subscribers.add(browser)
        world.apartments[0] = apartment(**change)
        await align()
        assert hub_manager.hubs[APT] is not old and old.task.cancelled()
        assert browser.get_nowait() is None
    play(scenario)
    assert len(world.connections) == 2 and world.connections[1][1] is None


def test_a_hub_keeps_the_link_it_started_with_until_the_round_changes_it(world):
    """hub_manager.hub() puts the new record on the hub at once: a reconnection must not reach the new engine with the old
    numbering before the round has made a new hub."""
    async def scenario():
        world.apartments.append(apartment())
        await align()
        hub = hub_manager.hubs[APT]
        new = apartment(instance_url=URL_B)
        hub_manager.hub(new)
        assert hub.apt is new and hub.link[0] == URL_A
    play(scenario)


def test_nothing_changed_nothing_touched(world):
    async def scenario():
        world.apartments.append(apartment())
        await align()
        hub, task = hub_manager.hubs[APT], hub_manager.hubs[APT].task
        world.apartments[0] = apartment(address="Via nuova")   # not part of the link
        await align()
        assert hub_manager.hubs[APT] is hub and hub.task is task and not task.done()
        assert hub.apt.address == "Via nuova"
    play(scenario)
    assert len(world.connections) == 1


def test_without_fcm_nothing_is_opened_but_what_is_not_wanted_is_closed(world):
    world.fcm = False

    async def scenario():
        world.apartments.append(apartment())
        await align()
        assert hub_manager.hubs == {}
        hub_manager.hub(apartment()).start(None)               # a browser has opened it
        await settle()
        world.apartments.clear()
        await align()
        assert hub_manager.hubs == {}
    play(scenario)


def test_a_disabled_apartment_without_connection_keeps_its_browser(world):
    """Closing it would make the browser reopen and be closed again every minute."""
    world.fcm = False

    async def scenario():
        world.apartments.append(apartment(enabled=False))
        hub = hub_manager.hub(world.apartments[0])
        browser = asyncio.Queue()
        hub.subscribers.add(browser)
        await align()
        assert hub_manager.hubs[APT] is hub and browser.empty()
    play(scenario)
    assert world.connections == []


def test_the_stream_of_a_disabled_apartment_opens_no_connection(world, monkeypatch):
    started = []
    monkeypatch.setattr(InstanceHub, "start", lambda self, last: started.append(self.apt.apartment_id))

    async def gate(user, apartment_id):
        return apartment(enabled=False)
    monkeypatch.setattr(routes, "get_tenant_apartment", gate)
    user = CurrentUser("dev-admin", "admin@demo.it", "t-hub", "admin", "Amministratore")
    asyncio.run(routes.stream(APT, SimpleNamespace(headers={}), user))
    assert started == []


def test_at_start_the_connections_open_without_waiting_for_the_round(world):
    world.apartments.append(apartment())

    async def scenario():
        await push.start_background_hubs()
        await settle()
        assert len(world.connections) == 1 and len(push._loops) == 2
    play(scenario)
    assert push._loops == []


def test_without_fcm_only_the_alignment_runs(world):
    world.fcm = False
    world.apartments.append(apartment())

    async def scenario():
        await push.start_background_hubs()
        await settle()
        assert world.connections == [] and len(push._loops) == 1
    play(scenario)
