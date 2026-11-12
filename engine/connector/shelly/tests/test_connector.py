"""ShellyConnector on FakeTransport (connector.md §2, §3): connection and snapshot, partial notifications, commands,
silence, unknown devices, the order of ts, status, stop, make_connector; then the Shelly 1 Gen4 and the EM Mini Gen4;
last the BLU sensors through a bridge.
No pytest-asyncio: asyncio.run per test.
"""
import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from engine.connector.interface import ConnectorCommand, StateChange
from engine.connector.shelly import connector as connector_module
from engine.connector.shelly import make_connector
from engine.connector.shelly.catalog import CatalogError, parse_catalog
from engine.connector.shelly.connector import ShellyConnector
from engine.connector.shelly.offline import load_thresholds
from engine.connector.shelly.transport.base import Notification
from engine.connector.shelly.transport.mqtt import MqttConfigError, MqttTransport
from engine.connector.shelly.translate import notification_ts

from . import fake_device
from .fake_device import FakeBluDoorWindow, FakeBluHT, FakeBluMotion, FakeMiniEMG4, FakePlugMG3, FakeS1G4
from .fake_mqtt import load_capture
from .fake_transport import FakeTransport
from .harness import CATALOG_YAML, FAKE_MQTT_ENV

SID_A, SID_B = "shellyplugmg3-000000000001", "shellyplugmg3-000000000002"
DEV_A, DEV_B = "dev-presa-a", "dev-presa-b"


def catalog(*pairs, offline_after_s=None):
    devices = []
    for device_id, shelly_id in pairs:
        shelly = {"id": shelly_id, "type": "plug"}
        if offline_after_s is not None:
            shelly["offline_after_s"] = offline_after_s
        devices.append({"device_id": device_id, "label": device_id, "room_id": "camera",
                        "capabilities": {"switch": {}, "power_meter": {}}, "shelly": shelly})
    return parse_catalog({"rooms": [{"room_id": "camera", "name": "Camera"}], "devices": devices}, load_thresholds())


class World:
    """One connector, its fake transport and plugs, and a reader of changes() opened before anything happens."""

    def __init__(self, n_plugs=1, extra_plugs=(), latency_s=0.0, **kwargs):
        pairs = [(DEV_A, SID_A), (DEV_B, SID_B)][:n_plugs]
        self.plugs = {sid: FakePlugMG3(sid, energy_wh=1000.0) for _, sid in pairs}
        for plug in self.plugs.values():
            plug.online = False               # they connect when the test says so
        self.extra = list(extra_plugs)
        self.transport = FakeTransport(*self.plugs.values(), *self.extra, latency_s=latency_s)
        self.conn = ShellyConnector(catalog(*pairs, offline_after_s=kwargs.pop("offline_after_s", None)),
                                    self.transport, **kwargs)
        self.changes: list[StateChange] = []
        self._task = None

    async def __aenter__(self):
        await self.conn.start()
        self._task = asyncio.get_running_loop().create_task(self._read())
        await asyncio.sleep(0.02)
        return self

    async def __aexit__(self, *exc):
        await self.conn.stop()
        if self._task is not None:
            await asyncio.wait_for(self._task, 2)

    async def _read(self):
        async for change in self.conn.changes():
            self.changes.append(change)

    async def wait_for(self, predicate, timeout=3.0):
        end = asyncio.get_running_loop().time() + timeout
        while not predicate(self.changes):
            assert asyncio.get_running_loop().time() < end, f"not seen in {timeout} s: {self.changes}"
            await asyncio.sleep(0.01)
        return self.changes

    async def settle(self, s=0.1):
        await asyncio.sleep(s)

    async def connect(self, sid=SID_A):
        self.transport.set_online(sid, True)
        device_id = DEV_A if sid == SID_A else DEV_B
        await self.wait_for(lambda xs: {c.capability for c in xs if c.device_id == device_id
                                        and c.kind == "state"} >= {"switch", "power_meter"})

    def mine(self, device_id=DEV_A):
        return [c for c in self.changes if c.device_id == device_id]

    def info(self, device_id=DEV_A):
        return next(d for d in self.conn.devices() if d.device_id == device_id)


def run(scenario, **world):
    async def main():
        async with World(**world) as w:
            return await asyncio.wait_for(scenario(w), 20)
    return asyncio.run(main())


def cmd(target_on: bool, device_id=DEV_A, capability="switch", n=1, within_s=9.0) -> ConnectorCommand:
    return ConnectorCommand(command_id=f"cmd-{n}", correlation_id=f"corr-{n}", device_id=device_id,
                            capability=capability, target={"on": target_on},
                            deadline=datetime.now(UTC) + timedelta(seconds=within_s))


@pytest.fixture
def warnings(monkeypatch):
    """The warn lines of engine.log, as (msg, fields)."""
    seen = []
    monkeypatch.setattr(connector_module.log, "warn", lambda msg, **fields: seen.append((msg, fields)))
    return seen


def kinds(changes):
    return [(c.kind, c.online if c.kind == "online" else c.capability) for c in changes]


# --- connection and snapshot -------------------------------------------------------------------------------------

def test_connection_sends_online_then_the_full_snapshot():
    async def scenario(w):
        assert not w.info().online and w.info().capabilities == {"switch": {}, "power_meter": {}}
        await w.connect()
        assert kinds(w.mine()) == [("online", True), ("state", "switch"), ("state", "power_meter")]
        assert w.mine()[1].state == {"on": False}
        assert w.mine()[2].state == {"watts": 0.0, "energy_total_wh": 1000.0}
        assert [m for _, m, _ in w.transport.calls] == ["Shelly.GetDeviceInfo", "Shelly.GetStatus"]
        info = w.info()
        assert info.online and info.last_seen is not None and info.last_seen.tzinfo is not None
        assert info.capabilities == {"switch": {"on": False}, "power_meter": {"watts": 0.0, "energy_total_wh": 1000.0}}
        assert info.battery_percent is None and info.links == {}
        w.transport.set_online(SID_A, False)
        await w.wait_for(lambda xs: xs[-1].kind == "online" and xs[-1].online is False)
        assert not w.info().online and w.info().capabilities["switch"] == {"on": False}   # last known state kept
    run(scenario)


def test_wrong_model_stays_offline_and_warns_once_per_connection(monkeypatch, warnings):
    monkeypatch.setitem(fake_device.DEVICE_INFO, "app", "Plus1PM")

    async def scenario(w):
        w.transport.set_online(SID_A, True)
        await w.wait_for(lambda xs: kinds(xs) == [("online", True), ("online", False)])
        plug = w.plugs[SID_A]
        plug.press_button()
        plug.add_energy(5)
        await w.settle()
        assert kinds(w.mine()) == [("online", True), ("online", False)], "its notifications are ignored"
        assert not w.info().online
        result = await w.conn.execute(cmd(True), lambda s: None)
        assert (result.outcome, result.reason) == ("failed", "device_offline")
        assert [m for m, _ in warnings].count("device model not supported") == 1
        w.transport.set_online(SID_A, False)
        w.transport.set_online(SID_A, True)
        await w.wait_for(lambda xs: [m for m, _ in warnings].count("device model not supported") == 2)
    run(scenario)


def test_model_check_failing_keeps_the_catalog_profile(warnings):
    async def scenario(w):
        w.plugs[SID_A].hang_next("Shelly.GetDeviceInfo")
        await w.connect()
        assert w.info().online and ("device model check failed", {"device_id": DEV_A, "error_type": "TransportTimeout"}) \
            in warnings
    run(scenario, rpc_timeout_s=0.1)


def test_snapshot_failing_keeps_the_device_online(warnings):
    """GetStatus fails at the connection: online without a snapshot, warned once; a NotifyFullStatus that comes before
    the next silence check (30 s here) fills the state, and nothing is tried again after it."""
    async def scenario(w):
        w.plugs[SID_A].fail_next("Shelly.GetStatus")
        w.transport.set_online(SID_A, True)
        await w.wait_for(lambda xs: any(m == "device snapshot failed" for m, _ in warnings))
        assert w.info().online and kinds(w.mine()) == [("online", True)]
        w.plugs[SID_A].reboot()                     # the next full status fills the state
        await w.wait_for(lambda xs: {c.capability for c in xs if c.kind == "state"} == {"switch", "power_meter"})
        assert [m for m, _ in warnings].count("device snapshot failed") == 1
        assert [m for _, m, _ in w.transport.calls].count("Shelly.GetStatus") == 1
    run(scenario)


def test_snapshot_failing_is_tried_again_at_the_silence_checks_until_it_succeeds(warnings):
    """GetStatus fails at the connection and at the next two silence checks: warned once; the third retry gives the
    full snapshot, and then GetStatus is not asked again."""
    async def scenario(w):
        for _ in range(3):
            w.plugs[SID_A].fail_next("Shelly.GetStatus")
        w.transport.set_online(SID_A, True)
        await w.wait_for(lambda xs: {c.capability for c in xs if c.kind == "state"} == {"switch", "power_meter"})
        assert kinds(w.mine()) == [("online", True), ("state", "switch"), ("state", "power_meter")]
        assert w.mine()[2].state == {"watts": 0.0, "energy_total_wh": 1000.0}
        assert [m for m, _ in warnings].count("device snapshot failed") == 1
        assert [m for _, m, _ in w.transport.calls].count("Shelly.GetStatus") == 4
        await w.settle(0.3)                         # several silence checks later: no more GetStatus
        assert [m for _, m, _ in w.transport.calls].count("Shelly.GetStatus") == 4 and w.info().online
    run(scenario, silence_check_s=0.05)


# --- notifications -----------------------------------------------------------------------------------------------

def test_partial_notifications_complete_the_capability():
    async def scenario(w):
        await w.connect()
        start = len(w.changes)
        w.plugs[SID_A].press_button()           # output+source, then apower, then current (three partials)
        await w.wait_for(lambda xs: len(xs) >= start + 2)
        await w.settle(0.05)
        new = w.changes[start:]
        assert [(c.capability, c.state) for c in new] == [
            ("switch", {"on": True}), ("power_meter", {"watts": 12.2, "energy_total_wh": 1000.0})]
        w.plugs[SID_A].add_energy(2.5)
        await w.wait_for(lambda xs: xs[-1].state == {"watts": 12.2, "energy_total_wh": 1002.5})
        w.plugs[SID_A].reboot()                 # NotifyFullStatus: a full snapshot, counter at zero
        await w.wait_for(lambda xs: xs[-1].capability == "power_meter" and xs[-1].state["energy_total_wh"] == 0.0)
        assert kinds(w.changes[-2:]) == [("state", "switch"), ("state", "power_meter")]
        assert w.info().capabilities["power_meter"] == {"watts": 12.2, "energy_total_wh": 0.0}
    run(scenario)


def test_notify_event_changes_nothing_but_last_seen():
    async def scenario(w):
        await w.connect()
        before, count = w.info().last_seen, len(w.changes)
        later = datetime.now(UTC) + timedelta(seconds=1)
        w.transport.inject(Notification("NotifyEvent", SID_A, {"ts": later.timestamp(), "events": [
            {"component": "sys", "event": "scheduled_restart"}]}, later))
        await w.settle()
        assert len(w.changes) == count and w.info().last_seen == later > before
    run(scenario)


# --- commands ----------------------------------------------------------------------------------------------------

def test_command_confirmed():
    async def scenario(w):
        await w.connect()
        progress = []
        result = await w.conn.execute(cmd(True), progress.append)
        assert (result.outcome, result.state, progress) == ("confirmed", {"on": True}, ["sent", "verifying"])
        await w.wait_for(lambda xs: any(c.capability == "switch" and c.state == {"on": True} for c in xs))
        assert w.plugs[SID_A].on
    run(scenario)


def test_command_to_an_offline_device_fails_at_once_without_rpc():
    async def scenario(w):
        result = await w.conn.execute(cmd(True), lambda s: pytest.fail("no progress for an offline device"))
        assert (result.outcome, result.reason) == ("failed", "device_offline") and w.transport.calls == []
        await w.connect()
        calls = len(w.transport.calls)
        w.transport.set_online(SID_A, False)            # the connector has not seen it yet: the transport has
        result = await w.conn.execute(cmd(True, n=2), lambda s: None)
        assert (result.outcome, result.reason) == ("failed", "device_offline") and len(w.transport.calls) == calls
    run(scenario)


def test_command_rejected_by_the_device_keeps_no_device_text():
    async def scenario(w):
        await w.connect()
        w.plugs[SID_A].fail_next("Switch.Set")
        result = await w.conn.execute(cmd(True), lambda s: None)
        assert (result.outcome, result.reason, result.detail) == ("failed", "device_rejected", "rpc error -103")
        w.plugs[SID_A].protection_trips = True
        result = await w.conn.execute(cmd(True, n=2), lambda s: None)
        assert (result.outcome, result.reason) == ("failed", "device_rejected")
    run(scenario)


def test_command_timeout_is_internal_error():
    async def scenario(w):
        await w.connect()
        w.plugs[SID_A].hang_next("Switch.GetStatus")
        w.plugs[SID_A].hang_next("Switch.GetStatus")
        result = await w.conn.execute(cmd(True), lambda s: None)
        assert (result.outcome, result.reason, result.detail) == ("failed", "internal_error",
                                                                  "read back failed: transport timeout")
        assert w.info().online
    run(scenario, rpc_timeout_s=0.1)


def test_command_within_the_deadline():
    async def scenario(w):
        await w.connect()
        w.plugs[SID_A].hang_next("Switch.Set")
        loop = asyncio.get_running_loop()
        began = loop.time()
        result = await w.conn.execute(cmd(True, within_s=0.3), lambda s: None)
        assert result.outcome == "failed" and loop.time() - began < 1.0     # never beyond cmd.deadline
    run(scenario)


def test_cancelled_command_leaves_nothing_half_done():
    async def scenario(w):
        await w.connect()
        w.transport.latency_s = 0.2
        task = asyncio.get_running_loop().create_task(w.conn.execute(cmd(True), lambda s: None))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await w.settle(0.3)
        assert not w.plugs[SID_A].on and w.info().online
        result = await w.conn.execute(cmd(True, n=2), lambda s: None)
        assert result.outcome == "confirmed"
    run(scenario)


def test_connection_dropping_during_a_command_puts_the_device_offline():
    async def scenario(w):
        await w.connect()
        w.plugs[SID_A].drop_next("Switch.Set")
        result = await w.conn.execute(cmd(True), lambda s: None)
        assert (result.outcome, result.reason) == ("failed", "device_offline")
        await w.wait_for(lambda xs: xs[-1].kind == "online" and xs[-1].online is False)
        assert not w.info().online
        start = len(w.changes)
        w.plugs[SID_A].add_energy(1)          # it speaks again, still connected: a return, with a snapshot
        await w.wait_for(lambda xs: kinds(xs[start:])[:3] == [("online", True), ("state", "switch"),
                                                               ("state", "power_meter")])
    run(scenario)


def test_unknown_device_and_capability_are_internal_errors():
    async def scenario(w):
        await w.connect()
        for command in (cmd(True, device_id="dev-che-non-esiste"), cmd(True, capability="power_meter")):
            result = await w.conn.execute(command, lambda s: None)
            assert (result.outcome, result.reason) == ("failed", "internal_error")
    run(scenario)


# --- silence -----------------------------------------------------------------------------------------------------

def test_silence_beyond_the_threshold_puts_the_device_offline(warnings):
    shift = [timedelta(0)]

    async def scenario(w):
        await w.connect()
        shift[0] = timedelta(seconds=100)            # threshold of a plug: 120 s
        await w.settle(0.2)
        assert w.info().online
        shift[0] = timedelta(seconds=200)
        await w.wait_for(lambda xs: xs[-1].kind == "online" and xs[-1].online is False)
        assert any(m == "device silent beyond threshold" for m, _ in warnings)
        start = len(w.changes)
        w.plugs[SID_A].add_energy(1)                 # it speaks again
        await w.wait_for(lambda xs: kinds(xs[start:])[:1] == [("online", True)]
                         and {c.capability for c in xs[start:] if c.kind == "state"} == {"switch", "power_meter"})
    run(scenario, clock=lambda: datetime.now(UTC) + shift[0], silence_check_s=0.05)


def test_silence_uses_the_device_threshold():
    shift = [timedelta(0)]

    async def scenario(w):
        await w.connect()
        shift[0] = timedelta(seconds=40)             # beyond 30 s of the catalog's offline_after_s
        await w.wait_for(lambda xs: xs[-1].kind == "online" and xs[-1].online is False)
    run(scenario, clock=lambda: datetime.now(UTC) + shift[0], silence_check_s=0.05, offline_after_s=30)


# --- unknown devices ---------------------------------------------------------------------------------------------

def test_unknown_device_is_ignored_with_one_warning(warnings):
    stranger = FakePlugMG3("shellyplugmg3-0000000000ff")

    async def scenario(w):
        await w.connect()
        count = len(w.changes)
        stranger.press_button()
        stranger.add_energy(3)
        await w.settle()
        assert len(w.changes) == count and {d.device_id for d in w.conn.devices()} == {DEV_A}
        unknown = [f for m, f in warnings if m == "unknown shelly device ignored"]
        assert unknown == [{"shelly_id": "shellyplugmg3-0000000000ff"}]
    run(scenario, extra_plugs=[stranger])


# --- order of ts -------------------------------------------------------------------------------------------------

def capture_full_status_b():
    """Session B of the bench capture: the NotifyFullStatus sent on reconnection, with the device's clock hours
    behind (ts 1794302570.25 received at 11:14:36 UTC)."""
    line = next(x for x in load_capture("B") if "NotifyFullStatus" in x["payload"])
    params = json.loads(line["payload"])["params"]
    return params, datetime.strptime(line["received_at"], "%Y-%m-%dT%H:%M:%S%z").astimezone(UTC)


def test_ts_never_goes_back_with_a_device_clock_off():
    params, received_at = capture_full_status_b()
    device_time = datetime.fromtimestamp(params["ts"], UTC)

    async def scenario(w):
        await w.connect(SID_A)
        await w.connect(SID_B)
        # 1. as captured: hours off, beyond the trusted skew -> our reception time
        assert notification_ts(params, received_at) == received_at
        # plug A reports after everything emitted so far (and after the capture's reception)
        a_time = max(received_at, datetime.now(UTC)) + timedelta(seconds=30)
        w.transport.inject(Notification("NotifyStatus", SID_A, {"ts": a_time.timestamp(),
                                                                "switch:0": {"apower": 0.0}}, a_time))
        await w.wait_for(lambda xs: any(c.device_id == DEV_A and c.ts == a_time for c in xs))
        # 2. the same snapshot from plug B, its clock only 200 s behind: trusted, but earlier than A's last change
        received_b = device_time + timedelta(seconds=200)
        assert notification_ts(params, received_b) == device_time < a_time
        start = len(w.changes)
        w.transport.inject(Notification("NotifyFullStatus", SID_B, params, received_b))
        await w.wait_for(lambda xs: len(xs) >= start + 2)
        b_changes = w.changes[start:]
        assert [(c.device_id, c.capability) for c in b_changes] == [(DEV_B, "switch"), (DEV_B, "power_meter")]
        assert b_changes[0].state == {"on": False} and b_changes[1].state == {"watts": 0.0, "energy_total_wh": 17.0}
        assert all(c.ts == max(a_time, *(x.ts for x in w.changes[:start])) for c in b_changes), "the last emitted"
        assert [c.ts for c in w.changes] == sorted(c.ts for c in w.changes)
    run(scenario, n_plugs=2)


# --- status, stop, two connectors --------------------------------------------------------------------------------

def test_status():
    async def main():
        w = World()
        st = w.conn.status()
        assert (st.up, st.connected_devices, st.last_event_at, st.detail) == (False, 0, None, "not started")
        async with w:
            st = w.conn.status()
            assert (st.up, st.connected_devices, st.detail) == (True, 0, None)
            await w.connect()
            st = w.conn.status()
            assert st.connected_devices == 1 and st.last_event_at is not None and st.last_event_at.tzinfo is not None
            w.transport.broker_connected = False
            st = w.conn.status()
            assert (st.up, st.connected_devices, st.detail) == (False, 0, "mqtt broker not connected")
            w.transport.broker_connected = True
        assert w.conn.status().detail == "stopped" and not w.conn.status().up
    asyncio.run(main())


def test_stop_ends_changes_and_can_be_repeated():
    async def main():
        w = World()
        async with w:
            await w.connect()
        assert w._task.done()
        await w.conn.stop()                                 # twice: nothing happens
        assert all(t.done() for t in asyncio.all_tasks() if t.get_name().startswith("shelly-"))
    asyncio.run(main())


def test_two_connectors_in_one_process_do_not_see_each_other():
    async def main():
        async with World() as one, World() as two:
            await one.connect()
            await two.connect()
            count = len(two.changes)
            one.plugs[SID_A].press_button()
            await one.wait_for(lambda xs: any(c.capability == "switch" and c.state == {"on": True} for c in xs))
            await two.settle()
            assert len(two.changes) == count and not two.plugs[SID_A].on
    asyncio.run(main())


# --- make_connector ----------------------------------------------------------------------------------------------

def config(tmp_path, env=None, catalog_text=CATALOG_YAML):
    from engine.connector.interface import ConnectorConfig
    path = tmp_path / "catalog.yaml"
    if catalog_text is not None:
        path.write_text(catalog_text, encoding="utf-8")
    return ConnectorConfig(apartment_id="apt-prova-01", data_dir=tmp_path, catalog_path=path,
                           env=dict(FAKE_MQTT_ENV if env is None else env))


def test_make_connector_builds_without_connecting(tmp_path):
    conn = make_connector(config(tmp_path))
    assert isinstance(conn, ShellyConnector) and isinstance(conn._transport, MqttTransport)
    assert conn._transport._task is None and not conn._transport.broker_connected
    assert not conn.status().up and [d.device_id for d in conn.devices()] == ["dev-presa-prova"]
    assert FAKE_MQTT_ENV["SHELLY_MQTT_PASSWORD"] not in repr(conn._transport)


def test_make_connector_errors_are_clear(tmp_path):
    with pytest.raises(CatalogError, match="catalog file not found"):
        make_connector(config(tmp_path, catalog_text=None))
    env = {k: v for k, v in FAKE_MQTT_ENV.items() if k != "SHELLY_MQTT_HOST"}
    with pytest.raises(MqttConfigError, match="SHELLY_MQTT_HOST is required"):
        make_connector(config(tmp_path, env=env))
    with pytest.raises(CatalogError) as info:
        make_connector(config(tmp_path, catalog_text=CATALOG_YAML.replace("type: plug", "type: tostapane")))
    assert "shelly.type" in str(info.value) and "tostapane" not in str(info.value)


# --- Shelly 1 Gen4 and EM Mini Gen4 ------------------------------------------------------------------------------

SID_S1, SID_EM = "shelly1g4-000000000002", "shellyemminig4-000000000003"
DEV_S1, DEV_EM = "dev-rele", "dev-misura"


class G4World(World):
    """A Shelly 1 Gen4 (as switch or as boiler) and an EM Mini Gen4, offline until the test connects them. Each fake
    has its own clock, now + shift[shelly_id], so a test can place their notifications in time."""

    def __init__(self, s1_capability="switch", **kwargs):
        self.shift = {SID_S1: timedelta(0), SID_EM: timedelta(0)}
        self.s1 = FakeS1G4(SID_S1, clock=lambda: datetime.now(UTC) + self.shift[SID_S1])
        self.em = FakeMiniEMG4(SID_EM, energy_wh=500.0, clock=lambda: datetime.now(UTC) + self.shift[SID_EM])
        for fake in (self.s1, self.em):
            fake.online = False
        s1_values = {"setpoint_min": 7, "setpoint_max": 23} if s1_capability == "heating" else {}
        cat = parse_catalog({"rooms": [{"room_id": "camera", "name": "Camera"}], "devices": [
            {"device_id": DEV_S1, "label": "Relè", "room_id": "camera", "capabilities": {s1_capability: s1_values},
             "shelly": {"id": SID_S1, "type": "relay"}},
            {"device_id": DEV_EM, "label": "Misuratore", "room_id": "camera", "capabilities": {"power_meter": {}},
             "shelly": {"id": SID_EM, "type": "energy_meter"}}]}, load_thresholds())
        self.transport = FakeTransport(self.s1, self.em)
        self.conn = ShellyConnector(cat, self.transport, **kwargs)
        self.changes: list[StateChange] = []
        self._task = None

    async def connect_g4(self, sid, capability):
        device_id = DEV_S1 if sid == SID_S1 else DEV_EM
        start = len(self.changes)
        self.transport.set_online(sid, True)
        await self.wait_for(lambda xs: any(c.device_id == device_id and c.capability == capability
                                           for c in xs[start:]))
        return self.changes[start:]


def run_g4(scenario, **world):
    async def main():
        async with G4World(**world) as w:
            return await asyncio.wait_for(scenario(w), 20)
    return asyncio.run(main())


def test_shelly_1_online_snapshot_and_confirmed_command():
    async def scenario(w):
        new = await w.connect_g4(SID_S1, "switch")
        assert kinds(new) == [("online", True), ("state", "switch")] and new[1].state == {"on": False}
        assert [m for s, m, _ in w.transport.calls if s == SID_S1] == ["Shelly.GetDeviceInfo", "Shelly.GetStatus"]
        assert w.info(DEV_S1).capabilities == {"switch": {"on": False}}
        start = len(w.changes)
        w.s1.minute()                                      # switch:0.counts only: no StateChange
        await w.settle()
        assert w.changes[start:] == []
        progress = []
        result = await w.conn.execute(cmd(True, device_id=DEV_S1), progress.append)
        assert (result.outcome, result.state, progress) == ("confirmed", {"on": True}, ["sent", "verifying"])
        assert [m for s, m, _ in w.transport.calls if s == SID_S1][-2:] == ["Switch.Set", "Switch.GetStatus"]
        await w.wait_for(lambda xs: [(c.capability, c.state) for c in xs[start:]] == [("switch", {"on": True})])
        assert w.s1.on and w.info(DEV_S1).capabilities == {"switch": {"on": True}}
    run_g4(scenario)


def test_shelly_1_as_the_boiler_reports_and_switches_its_relay():
    async def scenario(w):
        new = await w.connect_g4(SID_S1, "heating")
        assert kinds(new) == [("online", True), ("state", "heating")] and new[1].state == {"on": False}
        assert w.info(DEV_S1).capabilities == {"heating": {"setpoint_min": 7, "setpoint_max": 23, "on": False}}
        result = await w.conn.execute(cmd(True, device_id=DEV_S1, capability="heating"), lambda s: None)
        assert (result.outcome, result.state) == ("confirmed", {"on": True})
        await w.wait_for(lambda xs: xs[-1].capability == "heating" and xs[-1].state == {"on": True})
        assert not any(c.capability == "switch" for c in w.changes)    # the catalog says heating: never switch
        result = await w.conn.execute(cmd(True, device_id=DEV_S1, capability="switch", n=2), lambda s: None)
        assert (result.outcome, result.reason) == ("failed", "internal_error")
    run_g4(scenario, s1_capability="heating")


def test_shelly_1_reboot_full_status_is_a_snapshot():
    async def scenario(w):
        await w.connect_g4(SID_S1, "switch")
        await w.conn.execute(cmd(True, device_id=DEV_S1), lambda s: None)
        await w.wait_for(lambda xs: xs[-1].capability == "switch" and xs[-1].state == {"on": True})
        start = len(w.changes)
        w.s1.reboot()
        await w.wait_for(lambda xs: kinds(xs[start:]) == [("state", "switch")])
        assert w.changes[-1].state == {"on": True}
    run_g4(scenario)


def test_em_mini_online_without_full_status_gets_its_snapshot_from_get_status():
    sent = []

    async def scenario(w):
        w.em.subscribe(sent.append)                        # everything the meter sends by itself
        new = await w.connect_g4(SID_EM, "power_meter")
        assert kinds(new) == [("online", True), ("state", "power_meter")]
        assert new[1].state == {"watts": 0.0, "energy_total_wh": 500.0}
        w.em.set_load(40.0)
        w.transport.set_online(SID_EM, False)              # a restart: offline, then back without NotifyFullStatus
        await w.wait_for(lambda xs: xs[-1].kind == "online" and xs[-1].online is False)
        new = await w.connect_g4(SID_EM, "power_meter")
        assert kinds(new) == [("online", True), ("state", "power_meter")]
        assert new[1].state == {"watts": 40.0, "energy_total_wh": 500.0}
        assert [m for s, m, _ in w.transport.calls if s == SID_EM] == ["Shelly.GetDeviceInfo", "Shelly.GetStatus"] * 2
        assert sent == [], "the EM Mini sent nothing by itself: the snapshot came from Shelly.GetStatus"
    run_g4(scenario)


def test_em_mini_notifications_become_power_meter_changes():
    async def scenario(w):
        await w.connect_g4(SID_EM, "power_meter")
        start = len(w.changes)
        w.em.set_load(850.0)
        w.em.report_power()                                 # em1:0
        await w.wait_for(lambda xs: len(xs) > start)
        w.em.add_energy(12.5)
        w.em.report_energy()                                # em1data:0, then the NotifyEvent "data": ignored
        await w.wait_for(lambda xs: len(xs) > start + 1)
        await w.settle()
        assert [(c.capability, c.state) for c in w.changes[start:]] == [
            ("power_meter", {"watts": 850.0, "energy_total_wh": 500.0}),
            ("power_meter", {"watts": 850.0, "energy_total_wh": 512.5})]
        assert w.info(DEV_EM).capabilities == {"power_meter": {"watts": 850.0, "energy_total_wh": 512.5}}
        result = await w.conn.execute(cmd(True, device_id=DEV_EM, capability="power_meter"), lambda s: None)
        assert (result.outcome, result.reason) == ("failed", "internal_error")
        assert not any(m.startswith("Switch.") for _, m, _ in w.transport.calls)
    run_g4(scenario)


def test_ts_order_with_the_em_mini_delay():
    """em1:0's ts is ~13.5 s before its arrival (translate.py, MiniEMG4): not compensated. Behind a later change of
    another device it takes that change's ts (the stream never goes back); alone it keeps its own, 13.5 s early."""
    async def scenario(w):
        await w.connect_g4(SID_S1, "switch")
        await w.connect_g4(SID_EM, "power_meter")
        w.shift[SID_S1] = timedelta(seconds=30)
        w.s1.press_button()                                 # the relay at now + 30 s
        await w.wait_for(lambda xs: xs[-1].capability == "switch" and xs[-1].state == {"on": True})
        relay_ts = w.changes[-1].ts
        w.shift[SID_EM] = timedelta(seconds=31)            # the meter 1 s later, its ts 13.5 s earlier
        w.em.set_load(850.0)
        w.em.report_power()
        await w.wait_for(lambda xs: xs[-1].capability == "power_meter" and xs[-1].state["watts"] == 850.0)
        assert w.changes[-1].ts == relay_ts                 # not now + 17.5 s: the last emitted
        w.shift[SID_EM] = timedelta(seconds=60)            # alone: the device's ts, 13.5 s before the reception
        w.em.set_load(0.0)
        received = datetime.now(UTC) + timedelta(seconds=60)
        w.em.report_power()
        await w.wait_for(lambda xs: xs[-1].capability == "power_meter" and xs[-1].state["watts"] == 0.0)
        early = (received - w.changes[-1].ts).total_seconds()
        assert 13.0 < early < 14.5, early
        assert [c.ts for c in w.changes] == sorted(c.ts for c in w.changes)
    run_g4(scenario)


# --- BLU sensors through a bridge (Shelly 1 Gen4) ----------------------------------------------------------------

DEV_BRIDGE, SID_BRIDGE = "dev-ponte", "shelly1g4-000000000002"
DEV_HT, DEV_MOTION, DEV_DOOR = "dev-ambiente", "dev-movimento", "dev-finestra"
ADDR_HT, ADDR_MOTION, ADDR_DOOR = "02:00:00:00:a1:01", "02:00:00:00:a1:02", "02:00:00:00:a1:03"
ADDR_STRANGER = "02:00:00:00:a1:09"                  # paired with the bridge, not in the catalog
BLU_DEVICES = {DEV_HT: (ADDR_HT, "blu_ht", {"temperature": {}, "humidity": {}}),
               DEV_MOTION: (ADDR_MOTION, "blu_motion", {"motion": {}}),
               DEV_DOOR: (ADDR_DOOR, "blu_door_window", {"contact": {}})}


class BluWorld(World):
    """A Shelly 1 Gen4 bridge (a switch, offline until the test connects it) and the catalog's BLU sensors. The bridge
    has a long threshold of its own, so moving the clock tests the sensors' thresholds, not the bridge's. The
    connector and the bridge share one clock, now + shift."""

    def __init__(self, sensors=(DEV_HT, DEV_MOTION, DEV_DOOR), uppercase_addr=False, **kwargs):
        self.shift = timedelta(0)

        def clock():
            return datetime.now(UTC) + self.shift
        self.bridge = FakeS1G4(SID_BRIDGE, clock=clock)
        self.bridge.online = False
        self.fakes = {ADDR_HT: FakeBluHT(ADDR_HT), ADDR_MOTION: FakeBluMotion(ADDR_MOTION),
                      ADDR_DOOR: FakeBluDoorWindow(ADDR_DOOR), ADDR_STRANGER: FakeBluHT(ADDR_STRANGER)}
        devices = [{"device_id": DEV_BRIDGE, "label": "Ponte", "room_id": "camera", "capabilities": {"switch": {}},
                    "shelly": {"id": SID_BRIDGE, "type": "relay", "offline_after_s": 100_000}}]
        for device_id in sensors:
            addr, kind, caps = BLU_DEVICES[device_id]
            devices.append({"device_id": device_id, "label": device_id, "room_id": "camera", "capabilities": caps,
                            "shelly": {"addr": addr.upper() if uppercase_addr else addr, "bridge": SID_BRIDGE,
                                       "type": kind}})
        cat = parse_catalog({"rooms": [{"room_id": "camera", "name": "Camera"}], "devices": devices},
                            load_thresholds())
        self.transport = FakeTransport(self.bridge)
        self.conn = ShellyConnector(cat, self.transport, clock=clock, **{"silence_check_s": 0.05, **kwargs})
        self.changes: list[StateChange] = []
        self._task = None

    def pair(self, *addrs):
        for addr in addrs:
            self.bridge.pair(self.fakes[addr])

    async def connect_bridge(self):
        start = len(self.changes)
        self.transport.set_online(SID_BRIDGE, True)
        await self.wait_for(lambda xs: any(c.device_id == DEV_BRIDGE and c.capability == "switch" for c in xs[start:]))
        await self.settle(0.1)                               # GetComponents, every page
        return self.changes[start:]

    def blu(self, start=0):
        """The changes of the sensors, as (device_id, kind, capability or online, state)."""
        return [(c.device_id, c.kind, c.capability if c.kind == "state" else c.online, c.state)
                for c in self.changes[start:] if c.device_id in BLU_DEVICES]

    def get_components_offsets(self):
        return [p["offset"] for _, m, p in self.transport.calls if m == "Shelly.GetComponents"]


def run_blu(scenario, **world):
    async def main():
        async with BluWorld(**world) as w:
            return await asyncio.wait_for(scenario(w), 20)
    return asyncio.run(main())


def all_packets(w):
    w.bridge.blu_packet(ADDR_HT, {69: 21.5, 46: 48}, battery=93)
    w.bridge.blu_packet(ADDR_MOTION, {33: False, 100: 1}, battery=100)
    w.bridge.blu_packet(ADDR_DOOR, {45: True, 63: 12.0, 100: 1}, battery=88)


def test_blu_snapshot_from_get_components_on_two_pages():
    """13 components, 10 a page: the Door/Window's open sensor is on the second page and it still appears."""
    async def scenario(w):
        w.pair(ADDR_HT, ADDR_MOTION, ADDR_DOOR)
        all_packets(w)                                      # before the bridge connects: only in its components
        await w.connect_bridge()
        assert [m for _, m, _ in w.transport.calls] == ["Shelly.GetDeviceInfo", "Shelly.GetStatus",
                                                        "Shelly.GetComponents", "Shelly.GetComponents"]
        assert w.get_components_offsets() == [0, 10]
        assert all(p["dynamic_only"] is True for _, m, p in w.transport.calls if m == "Shelly.GetComponents")
        assert w.bridge.blu_keys(ADDR_DOOR)[2] == "bthomesensor:207"     # the 11th component: page 2
        assert w.blu() == [
            (DEV_HT, "online", True, None),
            (DEV_HT, "state", "temperature", {"celsius": 21.5}), (DEV_HT, "state", "humidity", {"percent": 48.0}),
            (DEV_MOTION, "online", True, None), (DEV_MOTION, "state", "motion", {"detected": False}),
            (DEV_DOOR, "online", True, None), (DEV_DOOR, "state", "contact", {"open": True})]
        door = w.info(DEV_DOOR)
        assert door.online and door.capabilities == {"contact": {"open": True}} and door.battery_percent == 88.0
        assert w.info(DEV_HT).battery_percent == 93.0 and w.info(DEV_BRIDGE).battery_percent is None
        assert w.info(DEV_HT).last_seen is not None
        assert w.conn.status().connected_devices == 4
    run_blu(scenario)


def test_blu_component_numbers_differ_between_pairings_same_result(warnings):
    async def snapshot(stranger_first):
        async with BluWorld() as w:
            if stranger_first:                              # another sensor takes the first numbers, other order
                w.pair(ADDR_STRANGER, ADDR_DOOR, ADDR_MOTION, ADDR_HT)
            else:
                w.pair(ADDR_HT, ADDR_MOTION, ADDR_DOOR)
            all_packets(w)
            await w.connect_bridge()
            return (w.bridge.blu_keys(ADDR_HT), sorted(w.blu(), key=lambda x: (x[0], str(x[2]))),
                    [w.info(d).capabilities for d in BLU_DEVICES], [w.info(d).online for d in BLU_DEVICES])

    first = asyncio.run(snapshot(False))
    second = asyncio.run(snapshot(True))
    assert first[0] != second[0]                            # other numbers...
    assert first[1:] == second[1:]                          # ...same changes, same devices
    assert all(first[3])
    assert [f for m, f in warnings if m == "unknown blu sensor ignored"] == [
        {"device_id": DEV_BRIDGE, "addr": ADDR_STRANGER}]


def test_blu_component_added_and_removed_update_the_map(warnings):
    async def scenario(w):
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 50})
        await w.connect_bridge()
        assert not w.info(DEV_MOTION).online
        assert [f["device_id"] for m, f in warnings if m == "blu sensor not paired with its bridge"] == [
            DEV_MOTION, DEV_DOOR]
        start = len(w.changes)
        w.pair(ADDR_MOTION)                                 # 4 component_added: the map is read again
        await w.settle()
        assert w.get_components_offsets() == [0] * 5        # at the connection, then once per event
        assert w.blu(start) == []                           # paired, no packet yet: nothing made up
        w.bridge.blu_packet(ADDR_MOTION, {33: True, 100: 2}, battery=100)
        await w.wait_for(lambda xs: (DEV_MOTION, "state", "motion", {"detected": True}) in w.blu(start))
        assert w.blu(start) == [(DEV_MOTION, "online", True, None),
                                (DEV_MOTION, "state", "motion", {"detected": True})]
        start = len(w.changes)
        w.bridge.unpair(ADDR_MOTION)                        # component_removed: offline, warned once
        await w.wait_for(lambda xs: w.blu(start) == [(DEV_MOTION, "online", False, None)])
        await w.settle()
        assert [f["device_id"] for m, f in warnings if m == "blu sensor not paired with its bridge"] == [
            DEV_MOTION, DEV_DOOR, DEV_MOTION]
        start = len(w.changes)
        w.pair(ADDR_MOTION)                                 # paired again: new numbers
        w.bridge.blu_packet(ADDR_MOTION, {33: False}, battery=100)
        await w.wait_for(lambda xs: (DEV_MOTION, "state", "motion", {"detected": False}) in w.blu(start))
        assert w.bridge.blu_keys(ADDR_MOTION)[0] == "bthomedevice:202"
        w.bridge.blu_packet(ADDR_HT, {69: 20.5})            # the H&T is still mapped through all of it
        await w.wait_for(lambda xs: (DEV_HT, "state", "temperature", {"celsius": 20.5}) in w.blu(start))
    run_blu(scenario)


def test_blu_motion_at_rest_stays_online_then_goes_offline_beyond_its_threshold(warnings):
    async def scenario(w):
        w.pair(ADDR_MOTION)
        w.bridge.blu_packet(ADDR_MOTION, {33: False}, battery=100)
        await w.connect_bridge()
        start = len(w.changes)
        w.bridge.blu_packet(ADDR_MOTION, {33: True})
        w.shift = timedelta(seconds=60)
        w.bridge.blu_packet(ADDR_MOTION, {33: False})
        await w.wait_for(lambda xs: len(w.blu(start)) == 2)
        assert w.blu(start) == [(DEV_MOTION, "state", "motion", {"detected": True}),
                                (DEV_MOTION, "state", "motion", {"detected": False})]
        w.shift = timedelta(seconds=60 + 900)               # at rest: one packet, only the bthomedevice notified
        w.bridge.blu_packet(ADDR_MOTION, {33: False})
        w.shift = timedelta(seconds=60 + 900 + 40)
        w.bridge.blu_device_report(ADDR_MOTION)
        await w.settle(0.2)
        assert w.blu(start)[2:] == [] and w.info(DEV_MOTION).online
        w.shift = timedelta(seconds=60 + 900 + 2715)        # within the 2720 s of blu_motion (ts in whole seconds)
        await w.settle(0.2)
        assert w.info(DEV_MOTION).online
        w.shift = timedelta(seconds=60 + 900 + 2725)        # beyond it
        await w.wait_for(lambda xs: w.blu(start)[2:] == [(DEV_MOTION, "online", False, None)])
        assert ("device silent beyond threshold", DEV_MOTION) in [(m, f.get("device_id")) for m, f in warnings]
        assert w.info(DEV_BRIDGE).online                    # the bridge is not the one silent
        w.bridge.blu_packet(ADDR_MOTION, {33: True})        # a new packet: online again, with its snapshot
        await w.wait_for(lambda xs: len(w.blu(start)) == 5)
        assert w.blu(start)[3:] == [(DEV_MOTION, "online", True, None),
                                    (DEV_MOTION, "state", "motion", {"detected": True})]
    run_blu(scenario, sensors=(DEV_MOTION,))


def test_blu_motion_rest_packets_alone_keep_it_online():
    """The bthomedevice notification is the only sign of a Motion at rest: it renews the last packet."""
    async def scenario(w):
        w.pair(ADDR_MOTION)
        w.bridge.blu_packet(ADDR_MOTION, {33: False}, battery=100)
        await w.connect_bridge()
        for n in range(1, 5):                               # an hour at rest, a packet every 900 s
            w.shift = timedelta(seconds=900 * n)
            w.bridge.blu_packet(ADDR_MOTION, {33: False})
            w.bridge.blu_device_report(ADDR_MOTION)
            await w.settle(0.1)
            assert w.info(DEV_MOTION).online, n
        assert [c for c in w.blu() if c[1] == "online"] == [(DEV_MOTION, "online", True, None)]
    run_blu(scenario, sensors=(DEV_MOTION,))


def test_blu_sensors_go_offline_with_their_bridge_and_come_back_with_a_snapshot():
    async def scenario(w):
        w.pair(ADDR_HT, ADDR_MOTION, ADDR_DOOR)
        all_packets(w)
        await w.connect_bridge()
        start = len(w.changes)
        w.transport.set_online(SID_BRIDGE, False)
        await w.wait_for(lambda xs: len(w.blu(start)) == 3)
        assert (w.changes[start].device_id, w.changes[start].online) == (DEV_BRIDGE, False)   # the bridge first
        assert w.blu(start) == [(d, "online", False, None) for d in BLU_DEVICES]
        assert not any(w.info(d).online for d in BLU_DEVICES)
        w.bridge.blu_packet(ADDR_DOOR, {45: False})          # meanwhile the window closed
        start = len(w.changes)
        await w.connect_bridge()
        assert w.blu(start) == [
            (DEV_HT, "online", True, None),
            (DEV_HT, "state", "temperature", {"celsius": 21.5}), (DEV_HT, "state", "humidity", {"percent": 48.0}),
            (DEV_MOTION, "online", True, None), (DEV_MOTION, "state", "motion", {"detected": False}),
            (DEV_DOOR, "online", True, None), (DEV_DOOR, "state", "contact", {"open": False})]
        assert w.get_components_offsets() == [0, 10, 0, 10]
    run_blu(scenario)


def test_blu_contact_four_changes_in_a_few_seconds_all_in_order_rotation_gives_nothing():
    async def scenario(w):
        w.pair(ADDR_DOOR)
        w.bridge.blu_packet(ADDR_DOOR, {45: False, 63: 0.0, 100: 1}, battery=100)
        await w.connect_bridge()
        start = len(w.changes)
        for n, (open_, rotation) in enumerate([(True, 30.3), (False, 0.0), (True, 75.3), (False, 0.0)]):
            w.shift = timedelta(seconds=4 * n + 1)
            w.bridge.blu_packet(ADDR_DOOR, {45: open_})
            w.bridge.blu_packet(ADDR_DOOR, {63: rotation})   # the tilt, while it moves
        w.bridge.blu_packet(ADDR_DOOR, {63: 52.4, 100: 0})
        await w.wait_for(lambda xs: len(w.blu(start)) >= 4)
        await w.settle()
        assert w.blu(start) == [(DEV_DOOR, "state", "contact", {"open": v}) for v in (True, False, True, False)]
        ts = [c.ts for c in w.changes[start:]]
        assert ts == sorted(ts) and len(set(ts)) == 4       # each dated by its own packet
    run_blu(scenario, sensors=(DEV_DOOR,))


def test_blu_null_values_make_up_no_state():
    async def scenario(w):
        w.pair(ADDR_HT, ADDR_MOTION)
        w.bridge.blu_packet(ADDR_HT, {69: 22.0})            # a packet with the temperature only: humidity null
        await w.connect_bridge()
        assert w.blu() == [(DEV_HT, "online", True, None), (DEV_HT, "state", "temperature", {"celsius": 22.0})]
        assert w.info(DEV_HT).capabilities == {"temperature": {"celsius": 22.0}, "humidity": {}}
        assert not w.info(DEV_MOTION).online                # never a packet: offline, nothing made up
        assert w.info(DEV_MOTION).capabilities == {"motion": {}} and w.info(DEV_MOTION).battery_percent is None
    run_blu(scenario, sensors=(DEV_HT, DEV_MOTION))


def test_blu_sensor_not_in_the_catalog_is_ignored_with_one_warning(warnings):
    async def scenario(w):
        w.pair(ADDR_STRANGER, ADDR_HT)
        w.bridge.blu_packet(ADDR_STRANGER, {69: 30.0, 46: 20})
        w.bridge.blu_packet(ADDR_HT, {69: 21.0, 46: 40})
        await w.connect_bridge()
        for n in range(3):
            w.shift = timedelta(seconds=60 * (n + 1))
            w.bridge.blu_packet(ADDR_STRANGER, {69: 30.0 + n + 1})
            w.bridge.blu_device_report(ADDR_STRANGER)
        w.bridge.pair(FakeBluMotion("02:00:00:00:a1:0a"))    # another one: the map is read again
        await w.settle(0.2)
        assert {c[0] for c in w.blu()} == {DEV_HT}
        assert [f for m, f in warnings if m == "unknown blu sensor ignored"] == [
            {"device_id": DEV_BRIDGE, "addr": ADDR_STRANGER}, {"device_id": DEV_BRIDGE, "addr": "02:00:00:00:a1:0a"}]
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_catalog_mac_in_upper_case_matches_the_bridge():
    async def scenario(w):
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0, 46: 40})
        await w.connect_bridge()
        assert w.info(DEV_HT).online
    run_blu(scenario, sensors=(DEV_HT,), uppercase_addr=True)


def test_blu_battery_low_warns_once(warnings):
    async def scenario(w):
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0, 46: 40}, battery=20)
        await w.connect_bridge()
        for level in (15, 14, 13):
            w.bridge.blu_packet(ADDR_HT, {69: 21.0}, battery=level)
            w.bridge.blu_device_report(ADDR_HT)
        await w.settle()
        assert w.info(DEV_HT).battery_percent == 13.0
        assert [f for m, f in warnings if m == "battery low"] == [{"device_id": DEV_HT, "percent": 15.0}]
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_sensors_take_no_command_and_their_bridge_still_does():
    async def scenario(w):
        w.pair(ADDR_DOOR)
        w.bridge.blu_packet(ADDR_DOOR, {45: True})
        await w.connect_bridge()
        result = await w.conn.execute(cmd(True, device_id=DEV_DOOR, capability="contact"), lambda s: None)
        assert (result.outcome, result.reason) == ("failed", "internal_error")
        result = await w.conn.execute(cmd(True, device_id=DEV_BRIDGE), lambda s: None)
        assert (result.outcome, result.state) == ("confirmed", {"on": True})
    run_blu(scenario, sensors=(DEV_DOOR,))


def test_blu_components_read_failing_is_warned_once_and_tried_again(warnings):
    async def scenario(w):
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0, 46: 40})
        w.bridge.fail_next("Shelly.GetComponents")
        await w.connect_bridge()
        await w.wait_for(lambda xs: (DEV_HT, "online", True, None) in w.blu())
        assert [m for m, _ in warnings].count("blu components read failed") == 1
    run_blu(scenario, sensors=(DEV_HT,))


def test_a_bridge_without_blu_sensors_in_the_catalog_is_not_asked_its_components():
    async def scenario(w):
        w.pair(ADDR_STRANGER)
        w.bridge.blu_packet(ADDR_STRANGER, {69: 30.0})
        await w.connect_bridge()
        w.bridge.blu_packet(ADDR_STRANGER, {69: 31.0})
        w.bridge.pair(FakeBluMotion("02:00:00:00:a1:0a"))
        await w.settle()
        assert w.get_components_offsets() == []
        assert [c.device_id for c in w.changes] == [DEV_BRIDGE, DEV_BRIDGE]     # online and its switch
    run_blu(scenario, sensors=())


REAL_PAGES = json.loads((Path(__file__).with_name("fixtures") / "blu_get_components_pages.json")
                        .read_text(encoding="utf-8"))
REAL_AT = datetime.fromtimestamp(1794397100, UTC)       # 36 s after the newest packet of the real pages


def real_pages_world(w, pages):
    """The bridge answers GetComponents with these pages, and the clock is the time of the real answers."""
    w.shift = REAL_AT - datetime.now(UTC)
    w.bridge._get_components = lambda params: copy.deepcopy(pages[params.get("offset", 0) // 10])


def test_blu_snapshot_from_the_real_get_components():
    async def scenario(w):
        real_pages_world(w, REAL_PAGES["pages"])
        await w.connect_bridge()
        assert w.get_components_offsets() == [0, 10]
        assert w.blu() == [
            (DEV_HT, "online", True, None),
            (DEV_HT, "state", "temperature", {"celsius": 21.4}), (DEV_HT, "state", "humidity", {"percent": 53.0}),
            (DEV_MOTION, "online", True, None), (DEV_MOTION, "state", "motion", {"detected": False}),
            (DEV_DOOR, "online", True, None), (DEV_DOOR, "state", "contact", {"open": False})]
        assert w.info(DEV_HT).last_seen == datetime.fromtimestamp(1794397064, UTC)
        assert w.info(DEV_MOTION).last_seen == datetime.fromtimestamp(1794396871, UTC)
        assert {d: w.info(d).battery_percent for d in BLU_DEVICES} == {d: 100.0 for d in BLU_DEVICES}
    run_blu(scenario)


def test_blu_last_updated_ts_0_is_never_heard():
    """The real Motion right after its pairing: bthomedevice all null, bthomesensor value null and last_updated_ts 0.
    0 is not a packet of 1 January 1970: no last packet, offline, no state, no battery."""
    async def scenario(w):
        pages = copy.deepcopy(REAL_PAGES["pages"])
        never = REAL_PAGES["never_heard"]
        for component in (c for page in pages for c in page["components"]):
            if component["config"]["addr"] == ADDR_MOTION:
                status = never["bthomedevice"] if component["key"].startswith("bthomedevice") else never["bthomesensor"]
                component["status"] = {**status, "id": component["status"]["id"]}
        real_pages_world(w, pages)
        await w.connect_bridge()
        assert [c[0] for c in w.blu()] == [DEV_HT, DEV_HT, DEV_HT, DEV_DOOR, DEV_DOOR]     # no Motion at all
        motion = w.info(DEV_MOTION)
        assert (motion.online, motion.last_seen, motion.battery_percent) == (False, None, None)
        assert motion.capabilities == {"motion": {}}
        await w.settle(0.2)                                  # silence checks: still nothing about it
        assert not any(c[0] == DEV_MOTION for c in w.blu())
    run_blu(scenario)


def test_blu_fake_pairing_gives_0_and_the_connector_waits_for_the_first_packet():
    """The same through the fake bridge: paired during the run, its bthomesensor at last_updated_ts 0."""
    async def scenario(w):
        await w.connect_bridge()
        w.pair(ADDR_MOTION)
        await w.settle()
        page = w.bridge.handle("Shelly.GetComponents", {"dynamic_only": True})["components"]
        assert {c["status"]["last_updated_ts"] for c in page if c["key"].startswith("bthomesensor")} == {0}
        assert w.blu() == [] and w.info(DEV_MOTION).last_seen is None
        w.bridge.blu_packet(ADDR_MOTION, {33: True}, battery=100)
        await w.wait_for(lambda xs: w.blu() == [(DEV_MOTION, "online", True, None),
                                               (DEV_MOTION, "state", "motion", {"detected": True})])
    run_blu(scenario, sensors=(DEV_MOTION,))


GET_COMPONENTS_DELAY = timedelta(seconds=2)             # a page of the bench's Shelly 1 took up to 2.3 s


def slow_get_components(w, untrusted_ts_addr=None):
    """Every GetComponents page takes 2 s on the shared clock; returns the clock at the end of each page. With
    untrusted_ts_addr, that sensor's bthomesensors answer with a value and a last_updated_ts 1000 s in the FUTURE
    (beyond MAX_CLOCK_SKEW_S; one in the past is kept, however far): the connector must fall back on its own time."""
    ends = []
    real_call = w.transport.call

    async def call(shelly_id, method, params, timeout_s):
        if method != "Shelly.GetComponents":
            return await real_call(shelly_id, method, params, timeout_s)
        page = await real_call(shelly_id, method, params, timeout_s)
        await asyncio.sleep(0.01)
        w.shift += GET_COMPONENTS_DELAY
        for c in page["components"]:
            if c["config"]["addr"] == untrusted_ts_addr and c["key"].startswith("bthomesensor"):
                c["status"].update(value=c["status"]["value"] if c["status"]["value"] is not None else False,
                                   last_updated_ts=int((datetime.now(UTC) + w.shift).timestamp()) + 1000)
        ends.append(datetime.now(UTC) + w.shift)
        return page
    w.transport.call = call
    return ends


def assert_ts_never_go_back(changes):
    assert [c.ts for c in changes] == sorted(c.ts for c in changes)
    for device_id in {c.device_id for c in changes}:
        ts = [c.ts for c in changes if c.device_id == device_id]
        assert ts == sorted(ts), device_id


def test_blu_snapshot_fallback_time_is_after_the_slow_get_components():
    """The bridge comes back and GetComponents is slow (2 pages, 2 s each): the time taken when a component has no
    valid last_updated_ts of its own is the one AFTER the last page, not the one before the first. A valid
    last_updated_ts still dates its packet."""
    async def scenario(w):
        w.pair(ADDR_HT, ADDR_MOTION, ADDR_DOOR)
        all_packets(w)
        door_packet = datetime.fromtimestamp(int((datetime.now(UTC) + w.shift).timestamp()), UTC)
        ends = slow_get_components(w, untrusted_ts_addr=ADDR_HT)
        before = datetime.now(UTC) + w.shift
        await w.connect_bridge()
        assert len(ends) == 2 and ends[-1] - before >= 2 * GET_COMPONENTS_DELAY
        ht = [c for c in w.changes if c.device_id == DEV_HT]
        assert [(c.kind, c.capability) for c in ht] == [("online", None), ("state", "temperature"),
                                                        ("state", "humidity")]
        for c in ht:                                    # online, and both readings without a valid ts of their own
            assert ends[-1] <= c.ts < ends[-1] + timedelta(seconds=1), (c, ends)
        assert w.info(DEV_HT).last_seen == ht[0].ts
        assert w.info(DEV_DOOR).last_seen == door_packet   # its own last_updated_ts, not the fallback
        assert_ts_never_go_back(w.changes)
    run_blu(scenario)


def test_blu_component_added_fallback_time_is_after_the_slow_get_components():
    """The same on the read after a component_added (snapshot=False): a sensor that becomes reachable is dated
    after the pages were read, not when the event arrived."""
    async def scenario(w):
        await w.connect_bridge()
        ends = slow_get_components(w, untrusted_ts_addr=ADDR_MOTION)
        paired_at = datetime.now(UTC) + w.shift
        start = len(w.changes)
        w.pair(ADDR_MOTION)                             # component_added: the map is read again
        await w.wait_for(lambda xs: any(c.device_id == DEV_MOTION and c.kind == "state" for c in xs[start:]))
        await w.settle()
        motion = [c for c in w.changes[start:] if c.device_id == DEV_MOTION]
        assert [(c.kind, c.capability, c.online, c.state) for c in motion] == [
            ("online", None, True, None), ("state", "motion", None, {"detected": False})]
        assert motion[0].ts - paired_at >= GET_COMPONENTS_DELAY
        for c in motion:
            assert ends[0] <= c.ts < ends[0] + timedelta(seconds=1), (c, ends)
        assert_ts_never_go_back(w.changes)
    run_blu(scenario, sensors=(DEV_MOTION,))


# --- the age of a BLU sensor is its last packet, as the bridge dates it (translate.bthome_ts) ------------------------

def last_packet(w, addr):
    """The sensor's last packet as the fake bridge dates it (its bthomedevice's last_updated_ts)."""
    page = w.bridge.handle("Shelly.GetComponents", {"dynamic_only": True})["components"]
    key = w.bridge.blu_keys(addr)[0]
    return datetime.fromtimestamp(next(c for c in page if c["key"] == key)["status"]["last_updated_ts"], UTC)


def test_blu_bridge_back_with_a_sensor_silent_beyond_its_threshold_keeps_it_offline():
    """The bridge comes back and the H&T's last packet is 400 s old: beyond its 300 s, and beyond MAX_CLOCK_SKEW_S.
    That packet is not «now»: the H&T stays offline and sends nothing, not its old values."""
    async def scenario(w):
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0, 46: 40}, battery=90)
        packet = last_packet(w, ADDR_HT)
        w.shift = timedelta(seconds=400)
        await w.connect_bridge()
        await w.settle(0.2)                                  # silence checks too
        assert w.blu() == []
        ht = w.info(DEV_HT)
        assert not ht.online and ht.last_seen == packet and ht.capabilities == {"temperature": {}, "humidity": {}}
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_bridge_back_with_a_packet_within_the_threshold_but_older_than_the_skew():
    """The contact's last packet is 600 s old: older than MAX_CLOCK_SKEW_S (300 s), within its 920 s. Online with
    its snapshot, its age counted from the real packet; the ts of the stream still never goes back."""
    async def scenario(w):
        w.pair(ADDR_DOOR)
        w.bridge.blu_packet(ADDR_DOOR, {45: True}, battery=90)
        packet = last_packet(w, ADDR_DOOR)
        w.shift = timedelta(seconds=600)
        await w.connect_bridge()
        assert w.blu() == [(DEV_DOOR, "online", True, None), (DEV_DOOR, "state", "contact", {"open": True})]
        assert w.info(DEV_DOOR).online and w.info(DEV_DOOR).last_seen == packet
        assert_ts_never_go_back(w.changes)
        w.shift = timedelta(seconds=600 + 310)               # 910 s after its packet: within 920
        await w.settle(0.2)
        assert w.info(DEV_DOOR).online
        w.shift = timedelta(seconds=600 + 330)               # 930 s after it: offline, counted from the real packet
        await w.wait_for(lambda xs: w.blu()[-1] == (DEV_DOOR, "online", False, None))
    run_blu(scenario, sensors=(DEV_DOOR,))


# --- the map of a bridge does not outlive its connection -------------------------------------------------------------

def test_blu_map_is_forgotten_while_the_bridge_is_offline():
    """While the bridge is offline its sensors are paired again, and the numbers now name other measures: the old
    H&T temperature (bthomesensor:202) is now the Door/Window's rotation. Back online, GetComponents fails once: a
    notification with the old numbers gives nothing (no old map); after the retry the new numbers work."""
    async def scenario(w):
        w.pair(ADDR_HT, ADDR_DOOR)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0, 46: 40})
        w.bridge.blu_packet(ADDR_DOOR, {45: True})
        await w.connect_bridge()
        old_temperature = w.bridge.blu_keys(ADDR_HT)[3]                  # objects 1, 46, 69: the temperature
        assert old_temperature == "bthomesensor:202"
        w.transport.set_online(SID_BRIDGE, False)
        await w.wait_for(lambda xs: (DEV_DOOR, "online", False, None) in w.blu())
        w.bridge.unpair(ADDR_HT)
        w.bridge.unpair(ADDR_DOOR)
        w.bridge.restart_numbering()
        w.pair(ADDR_DOOR, ADDR_HT)
        assert w.bridge.blu_keys(ADDR_DOOR)[3] == old_temperature        # objects 1, 45, 63, 100: the rotation
        w.bridge.fail_next("Shelly.GetComponents")
        start = len(w.changes)
        w.transport.set_online(SID_BRIDGE, True)
        now = datetime.now(UTC) + w.shift                   # right after the connection, before any silence check
        w.transport.inject(Notification("NotifyStatus", SID_BRIDGE, {
            "ts": now.timestamp(), old_temperature: {"last_updated_ts": int(now.timestamp()), "value": 25.0}}, now))
        await w.wait_for(lambda xs: len(w.get_components_offsets()) >= 3)   # connection, failure, retry
        await w.settle()
        w.bridge.blu_packet(ADDR_HT, {69: 22.0})
        w.bridge.blu_packet(ADDR_DOOR, {45: False, 63: 25.0})
        await w.wait_for(lambda xs: (DEV_DOOR, "state", "contact", {"open": False}) in w.blu(start))
        await w.wait_for(lambda xs: (DEV_HT, "state", "temperature", {"celsius": 22.0}) in w.blu(start))
        assert not any(c[3] == {"celsius": 25.0} for c in w.blu(start)), w.blu(start)
        assert w.info(DEV_HT).capabilities["temperature"] == {"celsius": 22.0}
    run_blu(scenario, sensors=(DEV_HT, DEV_DOOR))


# --- the battery, from both sources --------------------------------------------------------------------------------

def test_blu_battery_from_both_sources_the_last_one_counts(warnings):
    """bthomedevice.battery and the obj_id 1 bthomesensor arrive in turn: the last that arrived counts. A bthomedevice
    report without battery leaves the level as it is. «battery low» once, again only after a new battery."""
    async def scenario(w):
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0, 46: 40}, battery=80)
        await w.connect_bridge()
        assert w.info(DEV_HT).battery_percent == 80.0
        device_key, battery_key = w.bridge.blu_keys(ADDR_HT)[:2]          # bthomedevice, obj_id 1

        async def arrives(key, change, expected):
            now = datetime.now(UTC) + w.shift
            change = {"last_updated_ts": int(now.timestamp()), **change}
            w.transport.inject(Notification("NotifyStatus", SID_BRIDGE, {"ts": now.timestamp(), key: change}, now))
            await w.settle(0.05)
            assert w.info(DEV_HT).battery_percent == expected, (key, change)

        await arrives(battery_key, {"value": 70}, 70.0)
        await arrives(device_key, {"battery": 60, "rssi": -60}, 60.0)
        await arrives(battery_key, {"value": 50}, 50.0)
        await arrives(device_key, {"packet_id": 9, "rssi": -61}, 50.0)   # no battery: not the older 60
        await arrives(device_key, {"battery": 14, "rssi": -60}, 14.0)    # low: warned
        await arrives(battery_key, {"value": 12}, 12.0)                  # still low: not again
        await arrives(battery_key, {"value": 100}, 100.0)                # a new battery
        await arrives(device_key, {"battery": 10, "rssi": -60}, 10.0)    # low again: warned again
        assert [f for m, f in warnings if m == "battery low"] == [{"device_id": DEV_HT, "percent": 14.0},
                                                                  {"device_id": DEV_HT, "percent": 10.0}]
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_battery_of_the_snapshot_is_the_newest_packets():
    """At the snapshot both sources are read at once: the component with the newest packet gives the level."""
    async def scenario(w):
        page = copy.deepcopy(REAL_PAGES["pages"])
        for component in (c for p in page for c in p["components"]):
            if component["config"]["addr"] != ADDR_HT:
                continue
            if component["key"].startswith("bthomedevice"):
                component["status"].update(battery=40, last_updated_ts=1794397000)    # older
            elif component["config"]["obj_id"] == 1:
                component["status"].update(value=35, last_updated_ts=1794397064)      # newer
        real_pages_world(w, page)
        await w.connect_bridge()
        assert w.info(DEV_HT).battery_percent == 35.0
    run_blu(scenario)


# --- a sensor its bridge cannot decode (errors: ["parse_failed"]) -------------------------------------------------

PARSE_FAILED = json.loads((Path(__file__).with_name("fixtures") / "blu_parse_failed.json").read_text(encoding="utf-8"))
PARSE_FAILED_AT = datetime.fromtimestamp(1794414510, UTC)  # 10 s after the H&T's packet of the real page


def errors_warnings(warnings):
    return [f for m, f in warnings if m == "blu sensor errors on its bridge"]


def test_blu_sensors_in_error_in_the_snapshot_stay_offline_with_one_warning(warnings):
    """The real answer of the EM Mini: the Motion and the Door/Window in parse_failed, packets 526 and 813 s old
    (within their thresholds), no bthomesensor; the H&T healthy. The H&T is online with its snapshot; the other two
    stay offline, warned once each with the bridge's error. The notifications of the capture change nothing."""
    async def scenario(w):
        w.shift = PARSE_FAILED_AT - datetime.now(UTC)
        w.bridge._get_components = lambda params: copy.deepcopy(PARSE_FAILED["page"])
        await w.connect_bridge()
        assert w.blu() == [(DEV_HT, "online", True, None), (DEV_HT, "state", "temperature", {"celsius": 20.4}),
                           (DEV_HT, "state", "humidity", {"percent": 57.0})]
        for device_id in (DEV_MOTION, DEV_DOOR):
            info = w.info(device_id)
            assert (info.online, info.last_seen, info.battery_percent) == (False, None, None), device_id
        assert errors_warnings(warnings) == [
            {"device_id": DEV_MOTION, "bridge_device_id": DEV_BRIDGE, "errors": "parse_failed"},
            {"device_id": DEV_DOOR, "bridge_device_id": DEV_BRIDGE, "errors": "parse_failed"}]
        count = len(w.changes)
        for n in PARSE_FAILED["notifications"]:
            w.transport.inject(Notification(n["method"], SID_BRIDGE, n["params"], datetime.now(UTC) + w.shift))
        await w.settle(0.2)
        assert len(w.changes) == count and len(errors_warnings(warnings)) == 2
        assert not w.info(DEV_MOTION).online and not w.info(DEV_DOOR).online
    run_blu(scenario)


def test_blu_sensor_entering_error_goes_offline_at_its_threshold_and_comes_back_when_it_is_gone(warnings):
    """A healthy Motion enters parse_failed: its packets go on reaching the bridge, none counts. Offline at its
    threshold from the last good packet, warned once; the error gone, the next packet brings it online with its
    snapshot; the error back, warned again."""
    async def scenario(w):
        w.pair(ADDR_MOTION)
        w.bridge.blu_packet(ADDR_MOTION, {33: False}, battery=100)
        good = last_packet(w, ADDR_MOTION)
        await w.connect_bridge()
        start = len(w.changes)
        w.bridge.blu_set_errors(ADDR_MOTION, ["parse_failed"])
        for n in range(1, 4):                               # a packet every 900 s, the bridge reporting each
            w.shift = timedelta(seconds=900 * n)
            w.bridge.blu_packet(ADDR_MOTION, {33: True})
            w.bridge.blu_device_report(ADDR_MOTION)
            await w.settle(0.1)
        assert last_packet(w, ADDR_MOTION) > good           # the bridge's last_updated_ts moved...
        assert w.info(DEV_MOTION).last_seen == good         # ...the connector's last packet did not
        assert w.info(DEV_MOTION).online and w.blu(start) == []      # 2700 s: within its 2720 s
        assert errors_warnings(warnings) == [
            {"device_id": DEV_MOTION, "bridge_device_id": DEV_BRIDGE, "errors": "parse_failed"}]
        w.shift = timedelta(seconds=2725)
        await w.wait_for(lambda xs: w.blu(start) == [(DEV_MOTION, "online", False, None)])
        assert ("device silent beyond threshold", DEV_MOTION) in [(m, f.get("device_id")) for m, f in warnings]
        w.bridge.blu_set_errors(ADDR_MOTION, [])            # decoded again
        w.shift = timedelta(seconds=2800)
        w.bridge.blu_packet(ADDR_MOTION, {33: True})
        await w.wait_for(lambda xs: len(w.blu(start)) == 3)
        assert w.blu(start)[1:] == [(DEV_MOTION, "online", True, None),
                                    (DEV_MOTION, "state", "motion", {"detected": True})]
        await w.settle()
        assert w.info(DEV_MOTION).online and len(errors_warnings(warnings)) == 1
        w.bridge.blu_set_errors(ADDR_MOTION, ["parse_failed"])       # and back again: a new warning
        w.shift = timedelta(seconds=2900)
        w.bridge.blu_packet(ADDR_MOTION, {33: False})
        await w.wait_for(lambda xs: len(errors_warnings(warnings)) == 2)
        assert w.blu(start)[3:] == []                       # no state from the packet in error
    run_blu(scenario, sensors=(DEV_MOTION,))
