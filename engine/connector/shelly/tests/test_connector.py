"""ShellyConnector on FakeTransport (connector.md §2, §3): connection and snapshot, partial notifications, commands,
silence, unknown devices, the order of ts, status, stop, make_connector; then the Shelly 1 Gen4 and the EM Mini Gen4.
No pytest-asyncio: asyncio.run per test.
"""
import asyncio
import json
from datetime import UTC, datetime, timedelta

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
from .fake_device import FakeMiniEMG4, FakePlugMG3, FakeS1G4
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
    async def scenario(w):
        w.plugs[SID_A].fail_next("Shelly.GetStatus")
        w.transport.set_online(SID_A, True)
        await w.wait_for(lambda xs: any(m == "device snapshot failed" for m, _ in warnings))
        assert w.info().online and kinds(w.mine()) == [("online", True)]
        w.plugs[SID_A].reboot()                     # the next full status fills the state
        await w.wait_for(lambda xs: {c.capability for c in xs if c.kind == "state"} == {"switch", "power_meter"})
    run(scenario)


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
