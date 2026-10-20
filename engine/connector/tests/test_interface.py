"""Tests common to EVERY connector (engine/connector/connector.md, §2 and §4). Ours: SimulatedConnector and
ShellyConnector must both pass them, unchanged. Each connector is driven through its harness (see fake_device.py):
the simulated one always, and every engine/connector/<name>/tests/harness.py found, with its make_harness() and,
if the connector needs more than the engine's configuration to be built, connector_env(data_dir) -> dict.

Run: python -m pytest engine/connector/tests -q   (no pytest-asyncio: each test runs its own event loop)
"""
import asyncio
import importlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from engine.connector.interface import (CAPABILITIES, CONNECTOR_API_VERSION, LINKS, CommandResult, ConnectorCommand,
                                        ConnectorConfig, ConnectorStatus, DeviceInfo, Room, StateChange)

CONNECTOR_DIR = Path(__file__).resolve().parent.parent
HARNESSES = ["engine.connector.tests.fake_device"] + sorted(
    f"engine.connector.{p.parent.parent.name}.tests.harness" for p in CONNECTOR_DIR.glob("*/tests/harness.py"))
COMMAND_WITHIN_S = 10       # a command's result comes before its deadline (§2.4)


def connector_name(harness_module: str) -> str:
    """engine.connector.tests.fake_device -> simulated; engine.connector.<name>.tests.harness -> <name>."""
    return harness_module.split(".")[2] if harness_module.count(".") > 3 else "simulated"


@pytest.fixture(params=HARNESSES, ids=connector_name)
def harness(request):
    return importlib.import_module(request.param)


@pytest.fixture
def make(harness):
    return harness.make_harness


def run(make, scenario):
    """Builds the harness inside the event loop, runs the scenario, always closes it."""
    async def main():
        h = make()
        await h.connector.start()
        try:
            return await asyncio.wait_for(scenario(h, h.connector), timeout=30)
        finally:
            await h.close()
    return asyncio.run(main())


def command(device_id: str, capability: str, target: dict, n: int = 1) -> ConnectorCommand:
    return ConnectorCommand(command_id=f"cmd-test-{n}", correlation_id=f"corr-test-{n}", device_id=device_id,
                            capability=capability, target=target,
                            deadline=datetime.now(UTC) + timedelta(seconds=COMMAND_WITHIN_S))


def a_switch(conn) -> DeviceInfo:
    dev = next((d for d in conn.devices() if "switch" in d.capabilities and d.online), None)
    if dev is None:
        pytest.skip("no online device with a switch in this connector's catalog")
    return dev


class Collector:
    """Reads changes() in the background, as the engine does; changes() is live, so a test opens it before acting."""

    def __init__(self, conn):
        self.items: list[StateChange] = []
        self.task = asyncio.get_running_loop().create_task(self._read(conn))

    @classmethod
    async def open(cls, conn) -> "Collector":
        c = cls(conn)
        await asyncio.sleep(0.05)
        return c

    async def _read(self, conn):
        async for change in conn.changes():
            self.items.append(change)

    async def wait_for(self, predicate, timeout=5.0) -> list[StateChange]:
        end = asyncio.get_running_loop().time() + timeout
        while not predicate(self.items):
            if asyncio.get_running_loop().time() > end:
                raise AssertionError(f"changes not seen in {timeout} s: {self.items}")
            await asyncio.sleep(0.02)
        return self.items

    def stop(self):
        self.task.cancel()


METHODS = ("start", "stop", "rooms", "devices", "execute", "changes", "status")


def test_make_connector_is_the_engines_entry_point(harness, tmp_path, monkeypatch):
    """The engine builds the connector chosen by CONNECTOR=<name> with engine.connector.<name>.make_connector(config),
    once, at start, before start() (engine/service.py): it must exist and give a Connector of the engine's
    CONNECTOR_API_VERSION. config is a ConnectorConfig (connector.md §2.7): never the engine's key nor its settings,
    and of the environment only the connector's <NAME>_* variables. A connector that needs more (a catalog) adds its
    variables with connector_env(data_dir) -> dict in its harness.py, e.g. {"CATALOG_PATH": <a catalog in data_dir>}."""
    from engine.config import load_config
    from engine.service import load_connector
    name = connector_name(harness.__name__)
    key = "prova-chiave-0123456789"
    own = f"{name.upper()}_PROVA"
    env = {"APARTMENT_ID": "apt-prova-01", "API_KEY": key, "CONNECTOR": name, "DATA_DIR": str(tmp_path),
           "HOST": "127.0.0.1", own: "1", "DOMOTICA_TEST_CONNECTOR_DOWN": "0"}
    extra = getattr(harness, "connector_env", None)
    if extra is not None:
        env.update(extra(tmp_path))
    package = importlib.import_module(f"engine.connector.{name}")
    make_connector = getattr(package, "make_connector", None)
    assert callable(make_connector), f"engine.connector.{name} has no make_connector(config)"
    received = []

    def spy(config):
        received.append(config)
        return make_connector(config)
    monkeypatch.setattr(package, "make_connector", spy)
    connector = load_connector(load_config(env))          # the engine's own path
    assert getattr(connector, "api_version", None) == CONNECTOR_API_VERSION
    missing = [m for m in METHODS if not callable(getattr(connector, m, None))]
    assert not missing, f"the Connector has no {missing}"
    (config,) = received
    assert isinstance(config, ConnectorConfig) and not hasattr(config, "api_key")
    assert (config.apartment_id, config.data_dir) == ("apt-prova-01", tmp_path)
    assert config.env.get(own) == "1"
    assert not {"API_KEY", "HOST", "DATA_DIR", "CONNECTOR", "DOMOTICA_TEST_CONNECTOR_DOWN"} & set(config.env)
    assert key not in repr(config) and key not in config.env.values()


def test_api_version(make):
    async def scenario(h, conn):
        assert conn.api_version == CONNECTOR_API_VERSION
    run(make, scenario)


def test_catalog_is_consistent(make):
    async def scenario(h, conn):
        rooms, devices = conn.rooms(), conn.devices()
        assert rooms and devices
        assert all(isinstance(r, Room) for r in rooms) and all(isinstance(d, DeviceInfo) for d in devices)
        room_ids = [r.room_id for r in rooms]
        assert len(set(room_ids)) == len(room_ids)
        by_id = {d.device_id: d for d in devices}
        assert len(by_id) == len(devices), "device ids must be unique"
        for d in devices:
            assert d.room_id in room_ids, d
            assert d.label and d.capabilities and set(d.capabilities) <= set(CAPABILITIES), d
            assert d.last_seen is None or d.last_seen.tzinfo is not None, d
            for key, linked in d.links.items():
                assert key in LINKS, f"unknown link {key}"
                own, other = LINKS[key]
                assert own in d.capabilities and linked in by_id and other in by_id[linked].capabilities, d
    run(make, scenario)


def test_status_has_its_shape(make):
    async def scenario(h, conn):
        st = conn.status()
        assert isinstance(st, ConnectorStatus) and isinstance(st.up, bool)
        assert isinstance(st.connected_devices, int) and st.connected_devices >= 0
        assert st.last_event_at is None or st.last_event_at.tzinfo is not None
    run(make, scenario)


def test_command_reaches_the_target(make):
    async def scenario(h, conn):
        dev = a_switch(conn)
        changes = await Collector.open(conn)
        target = {**dev.capabilities["switch"], "on": not dev.capabilities["switch"].get("on")}
        progress: list[str] = []
        result = await asyncio.wait_for(conn.execute(command(dev.device_id, "switch", target), progress.append),
                                        COMMAND_WITHIN_S)
        assert isinstance(result, CommandResult) and result.outcome in ("confirmed", "delivered"), result
        assert progress and progress[0] == "sent" and set(progress) <= {"sent", "verifying"}, progress
        if result.outcome == "confirmed":
            assert result.state["on"] is target["on"]
            seen = await changes.wait_for(lambda xs: any(
                c.device_id == dev.device_id and c.kind == "state" and c.capability == "switch"
                and c.state.get("on") is target["on"] for c in xs))
            assert all(c.ts.tzinfo is not None for c in seen)
        now = next(d for d in conn.devices() if d.device_id == dev.device_id)
        assert now.capabilities["switch"]["on"] is target["on"] or result.outcome == "delivered"
        changes.stop()
    run(make, scenario)


def test_offline_device_fails_with_device_offline(make):
    async def scenario(h, conn):
        dev = a_switch(conn)
        h.set_online(dev.device_id, False)
        target = {**dev.capabilities["switch"], "on": not dev.capabilities["switch"].get("on")}
        result = await asyncio.wait_for(conn.execute(command(dev.device_id, "switch", target), lambda s: None),
                                        COMMAND_WITHIN_S)
        assert (result.outcome, result.reason) == ("failed", "device_offline"), result
    run(make, scenario)


def test_changes_come_in_order(make):
    async def scenario(h, conn):
        dev = next((d for d in conn.devices() if "temperature" in d.capabilities), None)
        if dev is None:
            pytest.skip("no temperature sensor in this connector's catalog")
        changes = await Collector.open(conn)
        for celsius in (18.0, 18.5, 19.0):
            h.set_state(dev.device_id, "temperature", {"celsius": celsius})
        seen = await changes.wait_for(lambda xs: any(c.capability == "temperature" and c.state["celsius"] == 19.0
                                                     for c in xs))
        temps = [c.state["celsius"] for c in seen if c.device_id == dev.device_id and c.capability == "temperature"]
        assert temps[-3:] == [18.0, 18.5, 19.0]
        assert [c.ts for c in seen] == sorted(c.ts for c in seen)
        changes.stop()
    run(make, scenario)


def test_reconnection_sends_online_then_a_snapshot(make):
    async def scenario(h, conn):
        dev = a_switch(conn)
        changes = await Collector.open(conn)
        h.set_online(dev.device_id, False)
        h.set_online(dev.device_id, True)
        seen = await changes.wait_for(lambda xs: any(c.kind == "online" and c.online for c in xs)
                                      and any(c.kind == "state" and c.capability == "switch" for c in xs))
        mine = [c for c in seen if c.device_id == dev.device_id]
        flags = [c.online for c in mine if c.kind == "online"]
        assert flags[-2:] == [False, True], flags
        back = max(i for i, c in enumerate(mine) if c.kind == "online" and c.online)
        assert {c.capability for c in mine[back + 1:] if c.kind == "state"} == set(dev.capabilities)
        assert next(d for d in conn.devices() if d.device_id == dev.device_id).online
        changes.stop()
    run(make, scenario)


def test_cancelled_command_leaves_the_connector_usable(make):
    async def scenario(h, conn):
        dev = a_switch(conn)
        target = {**dev.capabilities["switch"], "on": not dev.capabilities["switch"].get("on")}
        task = asyncio.get_running_loop().create_task(conn.execute(command(dev.device_id, "switch", target), lambda s: None))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        result = await asyncio.wait_for(conn.execute(command(dev.device_id, "switch", target, 2), lambda s: None),
                                        COMMAND_WITHIN_S)
        assert result.outcome in ("confirmed", "delivered"), result
    run(make, scenario)


class Recorder:
    """The harness's connector as the engine sees it, recording what it is asked to do."""

    def __init__(self, inner):
        self.inner, self.commands = inner, []
        self.api_version = inner.api_version

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def execute(self, cmd, on_progress):
        self.commands.append(cmd)
        return await self.inner.execute(cmd, on_progress)


def test_engine_asks_only_the_device_fields(make):
    """D-108, connector.md §2.4: the engine's command to the connector carries only the device's fields of the
    capability: heating -> on; climate -> on, mode, setpoint, fan. Limits, confirmation and the boiler's setpoint stay
    with the engine, which still shows them to the app."""
    async def scenario(h, conn):
        from engine.core import ApartmentEngine
        rec = Recorder(conn)
        engine = ApartmentEngine("apt-prova-01", rec, seed=False)
        engine.ensure_started()
        try:
            def first(cap):
                return next((d for d in engine.devices.values() if cap in d["capabilities"] and d["online"]), None)
            heating, climate = first("heating"), first("climate")
            if heating is None and climate is None:
                pytest.skip("no heating and no climate in this connector's catalog")
            asked = {}
            if heating:
                h_state = heating["capabilities"]["heating"]
                asked["heating"] = min(h_state["setpoint_min"] + 1, h_state["setpoint_max"])
                engine.create_command(heating["device_id"], {"capability": "heating", "action": "set_heating",
                                                             "params": {"on": True, "setpoint": asked["heating"]}},
                                      "prova@hqe.it", "corr-heating")
            if climate:
                c_state = climate["capabilities"]["climate"]
                asked["climate"] = c_state["setpoint_min"]
                engine.create_command(climate["device_id"], {"capability": "climate", "action": "set_climate",
                                                             "params": {"setpoint": asked["climate"]}},
                                      "prova@hqe.it", "corr-climate")
            end = asyncio.get_running_loop().time() + COMMAND_WITHIN_S
            while any(c["status"] not in ("acked", "failed", "timeout") for c in engine.commands.values()):
                assert asyncio.get_running_loop().time() < end, engine.commands
                await asyncio.sleep(0.05)
            targets = {c.capability: c.target for c in rec.commands}
            assert set(targets) == set(asked), targets
            if heating:
                assert set(targets["heating"]) == {"on"}, targets["heating"]
            if climate:
                assert set(targets["climate"]) == {"on", "mode", "setpoint", "fan"}, targets["climate"]
            for cmd in engine.commands.values():
                if cmd["status"] == "acked":      # what the app sees still has the engine's fields, updated
                    shown = engine.devices[cmd["device_id"]]["capabilities"][cmd["capability"]]
                    assert shown["setpoint"] == asked[cmd["capability"]] and "setpoint_min" in shown, shown
        finally:
            for task in [engine.loop_task, engine.consumer_task, *engine.tasks]:
                if task is not None:
                    task.cancel()
    run(make, scenario)


def test_stop_ends_changes(make):
    async def scenario(h, conn):
        changes = await Collector.open(conn)
        await asyncio.sleep(0.05)
        await conn.stop()
        await asyncio.wait_for(changes.task, 5)
    run(make, scenario)
