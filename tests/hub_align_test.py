"""D-201: every instance keeps its connections to the engines aligned with the registry, because a change is made on one
instance only. D-198: an apartment created while the server runs sends notifications without waiting for a restart.
Memory repository; the connection to the engines is a fake, the hubs and their tasks are the real ones."""
import asyncio
import dataclasses
import time
from types import SimpleNamespace

import pytest

from bff import instances, push
from bff.auth import CurrentUser
from bff.config import get_settings
from bff.repository import Apartment, get_repository
from bff.routes import apartments as routes
from bff import sse_hub
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
    settings = lambda: dataclasses.replace(get_settings(), fcm_enabled=state.fcm)
    monkeypatch.setattr(push, "get_settings", settings)
    monkeypatch.setattr(sse_hub, "get_settings", settings)
    get_repository().stream_cursors.clear()

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
        assert len(world.connections) == 1 and len(push._loops) == 3
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


# -------- D-201: where a new connection resumes --------
EVENT = ["id: 41", "event: device.state", "data: {}", ""]


def test_a_new_connection_resumes_from_the_saved_id(world):
    run_put(URL_A, age=5)

    async def scenario():
        world.apartments.append(apartment())
        await align()
    play(scenario)
    assert world.connections == [(URL_A + "/api/v1/stream", "40")]


def run_put(url, age, last_id="40"):
    asyncio.run(get_repository().put_stream_cursor(APT, last_id, url, time.time() - age))


def test_the_id_of_another_engine_is_ignored(world):
    run_put(URL_B, age=5)

    async def scenario():
        world.apartments.append(apartment())
        await align()
    play(scenario)
    assert world.connections[0][1] is None


def warnings(monkeypatch):
    seen = []
    monkeypatch.setattr(sse_hub, "warn", lambda msg, **kw: seen.append(msg))
    return seen


@pytest.mark.parametrize("age,expected", [(3000, 0), (4000, 1)])
def test_resuming_past_the_engines_window_is_written_to_the_log(world, monkeypatch, age, expected):
    seen = warnings(monkeypatch)
    run_put(URL_A, age=age)

    async def scenario():
        world.apartments.append(apartment())
        await align()
    play(scenario)
    assert seen.count("stream resumes past the engine's window, events may be lost") == expected
    assert world.connections[0][1] == "40"                      # it asks all the same: the engine gives what it has


def test_a_cursor_that_cannot_be_read_does_not_stop_the_connection(world, monkeypatch):
    seen = warnings(monkeypatch)

    async def broken(_apartment_id):
        raise RuntimeError("Firestore non raggiungibile")
    monkeypatch.setattr(get_repository(), "get_stream_cursor", broken)

    async def scenario():
        world.apartments.append(apartment())
        await align()
    play(scenario)
    assert seen == ["stream cursor not read"] and world.connections[0][1] is None


def test_without_fcm_no_cursor_is_read(world, monkeypatch):
    world.fcm = False
    run_put(URL_A, age=5)

    async def scenario():
        hub_manager.hub(apartment()).start(None)                # a browser has opened it
        await settle()
    play(scenario)
    assert world.connections[0][1] is None


def test_the_id_is_saved_when_it_changes_and_again_after_a_long_while(world):
    world.lines = EVENT
    repo = get_repository()

    async def scenario():
        world.apartments.append(apartment())
        await align()
        t0 = 1_000_000.0
        assert await hub_manager.save_cursors(t0) == 1
        saved = await repo.get_stream_cursor(APT)
        assert (saved["last_id"], saved["instance_url"], saved["saved_at"]) == ("41", URL_A, t0)
        assert await hub_manager.save_cursors(t0 + 30) == 0     # nothing new
        hub_manager.hubs[APT].last_id = "42"
        assert await hub_manager.save_cursors(t0 + 60) == 1
        assert await hub_manager.save_cursors(t0 + 60 + sse_hub.CURSOR_REFRESH_S) == 1
        assert (await repo.get_stream_cursor(APT))["last_id"] == "42"
    play(scenario)


def test_a_connection_that_is_down_saves_nothing(world):
    """A fresh date on a connection that is down would hide what is being missed."""
    world.lines = EVENT

    async def scenario():
        world.apartments.append(apartment())
        await align()
        hub_manager.hubs[APT].connected = False
        assert await hub_manager.save_cursors(1_000_000.0) == 0
    play(scenario)
    assert asyncio.run(get_repository().get_stream_cursor(APT)) is None


def test_an_instance_that_starts_later_does_not_notify_again_what_was_already_sent(world, monkeypatch):
    """The whole path: the event comes again from the engine, the claim stops it."""
    sent = []

    async def fake_send(tenant_id, pref, data, headers):
        sent.append(data["tag"])
        return 1
    monkeypatch.setattr(push, "send_to_tenant", fake_send)
    envelope = '{"id": "41", "event": "approval.pending", "ts": "2026-10-16T10:00:00.000Z", "data": {"approval_id": "apv-41"}}'
    world.lines = ["id: 41", "event: approval.pending", f"data: {envelope}", ""]
    get_repository().work.clear()
    push.register()

    async def scenario():
        world.apartments.append(apartment())
        await align()
        await asyncio.gather(*list(push._tasks))
        hub_manager.drop(APT)                                   # the other instance, started later, gets it again
        await settle()
        await align()
        await asyncio.gather(*list(push._tasks))
    try:
        play(scenario)
    finally:
        hub_manager.hooks.remove(push.on_stream_event)
    assert sent == ["approval:apv-41"] and len(world.connections) == 2


@pytest.mark.parametrize("environment,connections", [("prod", 0), ("staging", 1)])
def test_a_demonstration_gets_no_connection_in_production(world, monkeypatch, environment, connections):
    """D-202: a record left from before, until it is removed."""
    monkeypatch.setattr(instances, "get_settings", lambda: dataclasses.replace(get_settings(), app_env=environment))

    async def scenario():
        world.apartments.append(apartment(instance_url="mock://builtin"))
        await align()
    play(scenario)
    assert len(world.connections) == connections

