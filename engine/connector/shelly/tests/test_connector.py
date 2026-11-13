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
from engine.connector.shelly.transport.base import Notification, RpcError
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
    """GetStatus fails at the connection and at every retry: online without a snapshot, warned once. A
    NotifyFullStatus fills the state, and after it GetStatus is not tried again, however many silence checks come
    (0.05 s apart here)."""
    async def scenario(w):
        for _ in range(1000):
            w.plugs[SID_A].fail_next("Shelly.GetStatus")
        w.transport.set_online(SID_A, True)
        await w.wait_for(lambda xs: any(m == "device snapshot failed" for m, _ in warnings))
        assert w.info().online and kinds(w.mine()) == [("online", True)]
        await w.settle(0.2)
        assert [m for _, m, _ in w.transport.calls].count("Shelly.GetStatus") >= 3     # tried again, failing
        w.plugs[SID_A].reboot()                     # the next full status fills the state
        await w.wait_for(lambda xs: {c.capability for c in xs if c.kind == "state"} == {"switch", "power_meter"})
        await w.settle(0.1)                         # a check queued before the full status may still have tried
        tried = [m for _, m, _ in w.transport.calls].count("Shelly.GetStatus")
        await w.settle(0.4)                         # several silence checks: no more GetStatus
        assert [m for _, m, _ in w.transport.calls].count("Shelly.GetStatus") == tried
        assert [m for m, _ in warnings].count("device snapshot failed") == 1 and w.info().online
    run(scenario, silence_check_s=0.05)


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


def test_cancelled_command_the_state_is_what_the_device_reports():
    """The engine cancels a command half way (past its deadline), while the answer of Switch.Set is on its way. As over
    MQTT, the request had already reached the plug and the relay switched: nothing is called back and nothing made
    up, the state is what the plug reports (its NotifyStatus). The plug stays online and takes the next command."""
    async def scenario(w):
        await w.connect()
        w.transport.latency_s = 0.2
        task = asyncio.get_running_loop().create_task(w.conn.execute(cmd(True), lambda s: None))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await w.wait_for(lambda xs: any(c.capability == "switch" and c.state == {"on": True} for c in xs))
        await w.settle(0.3)
        assert w.plugs[SID_A].on and w.info().online
        assert w.info().capabilities["switch"] == {"on": True}
        assert [c.state for c in w.mine() if c.capability == "switch"] == [{"on": False}, {"on": True}]
        result = await w.conn.execute(cmd(False, n=2), lambda s: None)
        assert (result.outcome, result.state) == ("confirmed", {"on": False})
        await w.wait_for(lambda xs: w.info().capabilities["switch"] == {"on": False})
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


def test_a_device_clock_ahead_never_dates_the_others_later():
    """Plug A's clock is 240 s ahead, within MAX_CLOCK_SKEW_S: its change is dated at its reception, not 240 s later,
    so plug B's change right after, with the right clock, keeps its own time (at midnight a consumption would
    otherwise fall in the wrong day). The stream still never goes back."""
    async def scenario(w):
        await w.connect(SID_A)
        await w.connect(SID_B)
        w.plugs[SID_A].clock_skew = timedelta(seconds=240)
        start = len(w.changes)
        before_a = datetime.now(UTC)
        w.plugs[SID_A].press_button()
        await w.wait_for(lambda xs: any(c.device_id == DEV_A and c.capability == "switch" for c in xs[start:]))
        a = next(c for c in w.changes[start:] if c.device_id == DEV_A and c.capability == "switch")
        assert before_a <= a.ts <= datetime.now(UTC), a.ts                  # its reception, not now + 240 s
        before_b = datetime.now(UTC)
        w.plugs[SID_B].press_button()
        await w.wait_for(lambda xs: any(c.device_id == DEV_B and c.capability == "switch" for c in xs[start:]))
        b = next(c for c in w.changes[start:] if c.device_id == DEV_B and c.capability == "switch")
        assert before_b - timedelta(seconds=0.05) <= b.ts <= datetime.now(UTC), b.ts   # its own time (ts in 1/100 s)
        assert [c.ts for c in w.changes] == sorted(c.ts for c in w.changes)
    run(scenario, n_plugs=2)


def test_a_full_status_with_its_clock_ahead_is_dated_at_its_reception():
    """A NotifyFullStatus whose ts is 200 s ahead of its reception, within MAX_CLOCK_SKEW_S: trusted, but the states
    of the snapshot come out at the reception, never later, as for NotifyStatus."""
    async def scenario(w):
        await w.connect(SID_A)
        received = max(datetime.now(UTC), w.changes[-1].ts) + timedelta(seconds=1)
        params = {"ts": round((received + timedelta(seconds=200)).timestamp(), 2), **w.plugs[SID_A].full_status()}
        assert notification_ts(params, received) > received                # the device's clock is trusted...
        start = len(w.changes)
        w.transport.inject(Notification("NotifyFullStatus", SID_A, params, received))
        await w.wait_for(lambda xs: len(xs) >= start + 2)
        assert [(c.capability, c.ts) for c in w.changes[start:]] == [("switch", received), ("power_meter", received)]
    run(scenario)


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
SID_EM_BRIDGE = "shellyemminig4-000000000003"        # BluWorld(bridge="em_mini")
DEV_HT, DEV_MOTION, DEV_DOOR = "dev-ambiente", "dev-movimento", "dev-finestra"
ADDR_HT, ADDR_MOTION, ADDR_DOOR = "02:00:00:00:a1:01", "02:00:00:00:a1:02", "02:00:00:00:a1:03"
ADDR_STRANGER = "02:00:00:00:a1:09"                  # paired with the bridge, not in the catalog
BLU_DEVICES = {DEV_HT: (ADDR_HT, "blu_ht", {"temperature": {}, "humidity": {}}),
               DEV_MOTION: (ADDR_MOTION, "blu_motion", {"motion": {}}),
               DEV_DOOR: (ADDR_DOOR, "blu_door_window", {"contact": {}})}


class BluWorld(World):
    """A Shelly 1 Gen4 bridge (a switch, offline until the test connects it) and the catalog's BLU sensors. The bridge
    has a long threshold of its own, so moving the clock tests the sensors' thresholds, not the bridge's. The
    connector and the bridge share one clock, now + shift. bridge="em_mini": the bridge is an EM Mini Gen4 (a meter,
    power_meter), with its own shelly_id."""

    def __init__(self, sensors=(DEV_HT, DEV_MOTION, DEV_DOOR), uppercase_addr=False, bridge="relay", **kwargs):
        self.shift = timedelta(0)

        def clock():
            return datetime.now(UTC) + self.shift
        if bridge == "em_mini":
            self.bridge = FakeMiniEMG4(SID_EM_BRIDGE, clock=clock)
            self.bridge_capability, bridge_type = "power_meter", "energy_meter"
        else:
            self.bridge = FakeS1G4(SID_BRIDGE, clock=clock)
            self.bridge_capability, bridge_type = "switch", "relay"
        self.bridge.online = False
        self.fakes = {ADDR_HT: FakeBluHT(ADDR_HT), ADDR_MOTION: FakeBluMotion(ADDR_MOTION),
                      ADDR_DOOR: FakeBluDoorWindow(ADDR_DOOR), ADDR_STRANGER: FakeBluHT(ADDR_STRANGER)}
        devices = [{"device_id": DEV_BRIDGE, "label": "Ponte", "room_id": "camera",
                    "capabilities": {self.bridge_capability: {}},
                    "shelly": {"id": self.bridge.shelly_id, "type": bridge_type, "offline_after_s": 100_000}}]
        for device_id in sensors:
            addr, kind, caps = BLU_DEVICES[device_id]
            devices.append({"device_id": device_id, "label": device_id, "room_id": "camera", "capabilities": caps,
                            "shelly": {"addr": addr.upper() if uppercase_addr else addr,
                                       "bridge": self.bridge.shelly_id, "type": kind}})
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
        self.transport.set_online(self.bridge.shelly_id, True)
        await self.wait_for(lambda xs: any(c.device_id == DEV_BRIDGE and c.capability == self.bridge_capability
                                           for c in xs[start:]))
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


# --- the bridge's clock: last_updated_ts is read with it ------------------------------------------------------------

def clock_warnings(warnings):
    return [f for m, f in warnings if m == "bridge clock off"]


async def ht_every_minute(w, minutes, skews=None, offline_until=0, first=1):
    """The H&T sends a packet a minute (a new temperature each time, so its bthomesensor is notified); skews, when
    given, sets the bridge's clock before each packet. After each one: the H&T is still online and its temperature
    comes out dated on OUR clock; up to the minute offline_until, instead, it is offline and its temperature does not
    come out. first: the minute of the first packet."""
    for n in range(first, first + minutes):
        if skews is not None:
            w.bridge.clock_skew = timedelta(seconds=skews[n - first])
        w.shift = timedelta(seconds=60 * n)
        received = datetime.now(UTC) + w.shift
        w.bridge.blu_packet(ADDR_HT, {69: 20.0 + n})
        if n <= offline_until:
            await w.settle(0.15)
            assert not w.info(DEV_HT).online, n
            assert (DEV_HT, "state", "temperature", {"celsius": 20.0 + n}) not in w.blu(), n
            continue
        await w.wait_for(lambda xs: (DEV_HT, "state", "temperature", {"celsius": 20.0 + n}) in w.blu())
        await w.settle(0.15)                                 # silence checks
        assert w.info(DEV_HT).online, n
        ts = [c.ts for c in w.changes if c.device_id == DEV_HT and c.kind == "state"][-1]
        assert abs((ts - received).total_seconds()) < 2, (n, ts, received)


@pytest.mark.parametrize("skew_s", [-400, 400])
def test_blu_bridge_clock_off_the_age_is_counted_on_the_bridge_clock(warnings, skew_s):
    """The bridge's clock is steadily 400 s behind (or ahead of) ours, beyond MAX_CLOCK_SKEW_S; the H&T sends every
    minute. The offset of the connection's GetStatus is a candidate, confirmed by the H&T's packet CLOCK_CONFIRM_S
    (5 minutes) later: from then on last_updated_ts is read on the bridge's clock, the H&T is online, its values come
    out dated on our clock, and the bridge is warned once, at the confirmation. Before it our clock is used: 400 s
    behind, the H&T's packets look 400 s old and it is offline (the price wanted); 400 s ahead, they are in the
    future beyond the skew and dated at their reception, so it is online from the start."""
    assert connector_module.CLOCK_CONFIRM_S == 300

    async def scenario(w):
        w.bridge.clock_skew = timedelta(seconds=skew_s)
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        if skew_s < 0:
            assert w.blu() == [] and not w.info(DEV_HT).online
        else:
            assert w.blu() == [(DEV_HT, "online", True, None), (DEV_HT, "state", "temperature", {"celsius": 20.0}),
                               (DEV_HT, "state", "humidity", {"percent": 40.0})]
        assert bridge_offset(w) is None and clock_warnings(warnings) == []
        await ht_every_minute(w, 4, offline_until=4 if skew_s < 0 else 0)      # 60 ... 240 s: not confirmed
        assert bridge_offset(w) is None and clock_warnings(warnings) == []
        await ht_every_minute(w, 3, first=5)                # 300 s: confirmed; 360, 420 s
        assert abs(bridge_offset(w) - skew_s) <= 1
        assert [c for c in w.blu() if c[1] == "online"] == [(DEV_HT, "online", True, None)]
        warned = clock_warnings(warnings)
        assert len(warned) == 1 and warned[0]["device_id"] == DEV_BRIDGE
        assert abs(warned[0]["offset_s"] - skew_s) <= 1             # sys.unixtime is in whole seconds
        assert_ts_never_go_back(w.changes)
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_bridge_clock_corrected_midway_never_adopts_the_offset_off(warnings):
    """The bridge's clock is 400 s behind at the connection, then right, then 400 s behind again, then right: never
    off for CLOCK_CONFIRM_S, so the -400 s offset is never adopted and "bridge clock off" never warned. Step by step:
      - connection (-400 s, a candidate; our clock): the H&T's packet looks 400 s old, offline;
      - minute 1 (-400 s, 60 s after the first: not confirmed): still offline, nothing;
      - minute 2 (0 s: adopted at once, the candidate dropped): online with its snapshot, dated at its reception;
      - minute 3 (0 s): its temperature, dated at its reception;
      - minutes 4 and 5 (-400 s: a candidate again, the 0 s offset still used): the packets look 400 s old, so they do
        not renew its last packet; it stays online on the packet of minute 3 (silent 120 s at minute 5, within its
        300 s), and their temperatures come out dated 400 s before their reception, brought to the last ts emitted
        (the stream never goes back);
      - minute 6 (0 s: the candidate dropped): its temperature, dated at its reception."""
    async def scenario(w):
        w.bridge.clock_skew = timedelta(seconds=-400)
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        assert w.blu() == [] and not w.info(DEV_HT).online
        for n, skew in enumerate([-400, 0, 0, -400, -400, 0], start=1):
            w.bridge.clock_skew = timedelta(seconds=skew)
            w.shift = timedelta(seconds=60 * n)
            received = datetime.now(UTC) + w.shift
            start = len(w.changes)
            w.bridge.blu_packet(ADDR_HT, {69: 20.0 + n})
            temperature = (DEV_HT, "state", "temperature", {"celsius": 20.0 + n})
            if n == 1:
                await w.settle(0.15)
                assert w.blu(start) == [] and not w.info(DEV_HT).online
                continue
            await w.wait_for(lambda xs: temperature in w.blu(start))
            await w.settle(0.15)                             # silence checks
            assert w.info(DEV_HT).online, n
            if n == 2:
                assert w.blu(start) == [(DEV_HT, "online", True, None), temperature,
                                        (DEV_HT, "state", "humidity", {"percent": 40.0})]
            else:
                assert w.blu(start) == [temperature], n
            ts = [c.ts for c in w.changes[start:] if c.device_id == DEV_HT and c.capability == "temperature"][0]
            late = (received - ts).total_seconds()
            if skew:
                assert ts == w.changes[start - 1].ts and late > 50, (n, late)    # the last ts emitted
            else:
                assert abs(late) < 2, (n, late)
        assert [c for c in w.blu() if c[1] == "online"] == [(DEV_HT, "online", True, None)]
        assert clock_warnings(warnings) == []
        assert_ts_never_go_back(w.changes)
    run_blu(scenario, sensors=(DEV_HT,))


# --- a sensor whose error goes away without "errors": [] -----------------------------------------------------------

def test_blu_error_gone_without_an_empty_errors_is_read_at_the_next_read_due(warnings):
    """How the bridge says that an error is gone was never seen: here it never notifies "errors": [], the error only
    disappears from GetComponents. The Motion is in error and offline (its last good packet beyond 2720 s), the H&T on
    the same bridge healthy; the interval of the reads for errors is 60 s here. While the error lasts GetComponents is
    read again at most once per interval, not at every check; the error is warned once, and the H&T sends nothing
    again. The error gone, a packet at rest (no bthomesensor notified) and the bthomedevice report without "errors":
    the Motion stays offline until the next read due, then it is online with its snapshot, and the reads stop."""
    async def scenario(w):
        w.bridge.announce_errors_gone = False
        w.pair(ADDR_HT, ADDR_MOTION)
        w.bridge.blu_packet(ADDR_MOTION, {33: False}, battery=100)          # the last good packet, at 0 s
        w.bridge.blu_set_errors(ADDR_MOTION, ["parse_failed"])
        w.shift = timedelta(seconds=2000)
        w.bridge.blu_packet(ADDR_MOTION, {33: False})                       # in error: only its bthomedevice moves
        w.shift = timedelta(seconds=2800)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0, 46: 40}, battery=90)
        await w.connect_bridge()                                            # the read of the connection, at 2800 s
        assert w.blu() == [(DEV_HT, "online", True, None), (DEV_HT, "state", "temperature", {"celsius": 21.0}),
                           (DEV_HT, "state", "humidity", {"percent": 40.0})]
        assert not w.info(DEV_MOTION).online
        assert len(w.get_components_offsets()) == 1                         # 8 components: one page a read
        await w.settle(0.2)                                                 # checks within the interval: no read
        assert len(w.get_components_offsets()) == 1
        w.shift = timedelta(seconds=2870)                                   # 70 s after it: one read, still in error
        await w.settle(0.2)
        assert len(w.get_components_offsets()) == 2
        assert len(w.blu()) == 3                    # the read in error sends nothing again for the H&T
        assert len(errors_warnings(warnings)) == 1
        w.bridge.blu_set_errors(ADDR_MOTION, [])
        w.shift = timedelta(seconds=2880)
        w.bridge.blu_packet(ADDR_MOTION, {33: False})                       # at rest: no bthomesensor notified
        w.bridge.blu_device_report(ADDR_MOTION)                             # without "errors"
        start = len(w.changes)
        await w.settle(0.2)
        assert w.blu(start) == [] and not w.info(DEV_MOTION).online         # healed, but not read yet
        assert len(w.get_components_offsets()) == 2
        w.shift = timedelta(seconds=2940)                                   # 70 s after the last read: the read due
        await w.wait_for(lambda xs: len(w.blu(start)) == 2)
        assert w.blu(start) == [(DEV_MOTION, "online", True, None),
                                (DEV_MOTION, "state", "motion", {"detected": False})]
        assert len(w.get_components_offsets()) == 3
        w.shift = timedelta(seconds=3010)                                   # 70 s later again
        await w.settle(0.2)
        assert len(w.get_components_offsets()) == 3                         # healed: no more reads
        assert w.info(DEV_MOTION).online and len(errors_warnings(warnings)) == 1
    run_blu(scenario, sensors=(DEV_HT, DEV_MOTION), errors_reread_s=60)


def test_blu_sensor_in_error_then_silent_reads_the_map_at_most_every_5_minutes():
    """A Motion in parse_failed that then goes silent (a flat battery): its errors stay in the map for good. With the
    default ERRORS_REREAD_INTERVAL_S (5 minutes) the map is read again at most once per interval from the last read,
    however many silence checks: here about 20 minutes in steps of 130 s, several checks a step, and 3 reads after
    the connection's (at 390, 780 and 1170 s)."""
    assert connector_module.ERRORS_REREAD_INTERVAL_S == 300

    async def scenario(w):
        w.pair(ADDR_MOTION)
        w.bridge.blu_packet(ADDR_MOTION, {33: False}, battery=100)
        w.bridge.blu_set_errors(ADDR_MOTION, ["parse_failed"])
        w.bridge.blu_packet(ADDR_MOTION, {33: True})                        # in error: only its bthomedevice moves
        await w.connect_bridge()
        assert len(w.get_components_offsets()) == 1
        checks = []
        check = w.conn._check_blu_silence

        def counted(bridge, now):
            checks.append(now)
            check(bridge, now)
        w.conn._check_blu_silence = counted
        for n in range(1, 10):                                              # 130 ... 1170 s
            w.shift = timedelta(seconds=130 * n)
            await w.settle(0.15)
        assert len(checks) >= 18, len(checks)
        assert len(w.get_components_offsets()) == 1 + 3
    run_blu(scenario, sensors=(DEV_MOTION,))


def test_blu_failed_read_for_errors_keeps_the_map_and_sends_no_snapshot_again(warnings):
    """The Motion in error, the H&T healthy on the same bridge; the interval of the reads for errors is 60 s here.
    Two reads for errors fail in a row, the third succeeds: the map of before is kept (a new H&T value in between comes
    out), each read is tried again only when the next interval is due, never at every check, and never with the
    snapshot: the H&T does not send online or its states again. "blu components read failed" is warned once."""
    async def scenario(w):
        w.pair(ADDR_HT, ADDR_MOTION)
        w.bridge.blu_packet(ADDR_MOTION, {33: False}, battery=100)
        w.bridge.blu_set_errors(ADDR_MOTION, ["parse_failed"])
        w.bridge.blu_packet(ADDR_MOTION, {33: True})                        # in error: only its bthomedevice moves
        w.bridge.blu_packet(ADDR_HT, {69: 21.0, 46: 40}, battery=90)
        await w.connect_bridge()
        start = len(w.changes)
        assert len(w.get_components_offsets()) == 1
        w.bridge.fail_next("Shelly.GetComponents")
        w.bridge.fail_next("Shelly.GetComponents")
        w.shift = timedelta(seconds=70)                                     # due: the read fails
        await w.settle(0.2)
        assert len(w.get_components_offsets()) == 2                         # not tried again at every check
        w.shift = timedelta(seconds=100)
        w.bridge.blu_packet(ADDR_HT, {69: 22.0})                            # the map of before still works
        await w.wait_for(lambda xs: (DEV_HT, "state", "temperature", {"celsius": 22.0}) in w.blu(start))
        await w.settle(0.2)
        assert len(w.get_components_offsets()) == 2
        w.shift = timedelta(seconds=140)                                    # due again: fails again
        await w.settle(0.2)
        assert len(w.get_components_offsets()) == 3
        w.shift = timedelta(seconds=210)                                    # due again: succeeds
        await w.settle(0.2)
        assert len(w.get_components_offsets()) == 4
        w.shift = timedelta(seconds=240)
        await w.settle(0.2)
        assert len(w.get_components_offsets()) == 4
        assert w.blu(start) == [(DEV_HT, "state", "temperature", {"celsius": 22.0})]
        assert [m for m, _ in warnings].count("blu components read failed") == 1
        assert len(errors_warnings(warnings)) == 1
    run_blu(scenario, sensors=(DEV_HT, DEV_MOTION), errors_reread_s=60)


# --- the bridge's offset: forgotten with the connection, taken only from reliable sources -------------------------

def bridge_offset(w):
    return w.conn._devices[DEV_BRIDGE].clock_offset_s


def test_blu_bridge_offset_is_forgotten_when_the_bridge_goes_offline(warnings):
    """The bridge's clock is 400 s behind, its offset confirmed by the H&T's packet 5 minutes after the connection; it
    goes offline and comes back restarted with its clock right, and its Shelly.GetStatus fails. The H&T's last packet
    is 400 s old on the right clock: beyond its 300 s. The offset of before (-400 s) would make that packet «now»: it
    was forgotten with the connection, our clock is used, and the H&T stays offline, also once a time of the bridge
    comes (the GetStatus tried again at the silence check)."""
    async def scenario(w):
        w.bridge.clock_skew = timedelta(seconds=-400)
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        w.shift = timedelta(seconds=300)
        w.bridge.blu_packet(ADDR_HT, {69: 20.5})            # confirms the -400 s of the connection
        await w.wait_for(lambda xs: w.info(DEV_HT).online)
        assert abs(bridge_offset(w) + 400) <= 1
        w.transport.set_online(SID_BRIDGE, False)
        await w.wait_for(lambda xs: w.blu()[-1] == (DEV_HT, "online", False, None))
        w.bridge.clock_skew = timedelta(0)                  # restarted, its clock right
        w.bridge.blu_packet(ADDR_HT, {69: 21.0})            # offline for us: only in its components
        w.shift = timedelta(seconds=700)
        w.bridge.fail_next("Shelly.GetStatus")
        start, reads = len(w.changes), len(w.get_components_offsets())
        w.transport.set_online(SID_BRIDGE, True)
        await w.wait_for(lambda xs: len(w.get_components_offsets()) > reads)
        await w.settle(0.05)
        assert bridge_offset(w) is None or abs(bridge_offset(w)) < 2, bridge_offset(w)
        assert w.blu(start) == [] and not w.info(DEV_HT).online
        # the GetStatus tried again at the silence check: the bridge's snapshot, and its right time
        await w.wait_for(lambda xs: any(c.device_id == DEV_BRIDGE and c.kind == "state" for c in xs[start:]))
        await w.settle(0.2)
        assert abs(bridge_offset(w)) < 2
        assert w.blu(start) == [] and not w.info(DEV_HT).online
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_bridge_clock_off_is_warned_again_after_the_bridge_was_offline(warnings):
    """The "bridge clock off" warning goes with the offset when the bridge goes offline: back with its clock still
    400 s behind, it is warned again when that offset is confirmed again (5 minutes after the new connection; at the
    connection it is only a candidate, no warning)."""
    async def scenario(w):
        w.bridge.clock_skew = timedelta(seconds=-400)
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        assert clock_warnings(warnings) == []
        w.shift = timedelta(seconds=300)
        w.bridge.blu_packet(ADDR_HT, {69: 20.5})            # confirmed
        await w.wait_for(lambda xs: w.info(DEV_HT).online)
        assert len(clock_warnings(warnings)) == 1
        w.transport.set_online(SID_BRIDGE, False)
        await w.wait_for(lambda xs: w.blu()[-1] == (DEV_HT, "online", False, None))
        assert bridge_offset(w) is None
        await w.connect_bridge()
        assert len(clock_warnings(warnings)) == 1 and bridge_offset(w) is None      # a candidate again
        w.shift = timedelta(seconds=600)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0})            # confirmed again
        await w.wait_for(lambda xs: len(clock_warnings(warnings)) == 2)
        assert abs(bridge_offset(w) + 400) <= 1
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_em_mini_power_reports_do_not_move_the_bridge_offset():
    """An EM Mini Gen4 as the bridge, its clock right: its em1:0 comes with a ts 13.5 s behind (bench), between one
    BLU packet and the next. Only the bthome notifications and GetStatus give the offset: it never swings."""
    async def scenario(w):
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        offsets = [bridge_offset(w)]
        for n in range(1, 4):
            w.shift = timedelta(seconds=20 * n)
            start = len(w.changes)
            w.bridge.set_load(100.0 * n)
            w.bridge.report_power()                         # em1:0, its ts 13.5 s behind
            await w.wait_for(lambda xs: any(c.device_id == DEV_BRIDGE and c.kind == "state" for c in xs[start:]))
            offsets.append(bridge_offset(w))
            w.bridge.blu_packet(ADDR_HT, {69: 20.0 + n})
            await w.wait_for(lambda xs: (DEV_HT, "state", "temperature", {"celsius": 20.0 + n}) in w.blu())
            offsets.append(bridge_offset(w))
        assert all(abs(o) < connector_module.CLOCK_OFFSET_IGNORED_S for o in offsets), offsets
    run_blu(scenario, sensors=(DEV_HT,), bridge="em_mini")


def test_blu_full_status_after_a_restart_does_not_move_the_bridge_offset(warnings):
    """The bench's Shelly 1 Gen4 sends its first NotifyFullStatus after a restart with its clock about 1750 s off
    (behind). Here the fake's clock is that far off for every message of those minutes (the sys events too), and its
    H&T is silent since 1740 s, offline. That offset would bring the H&T's last packet to «now»: it is not taken, and
    when the map is read again (a sensor paired meanwhile) the H&T stays offline."""
    async def scenario(w):
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        w.shift = timedelta(seconds=1740)
        await w.wait_for(lambda xs: w.blu()[-1] == (DEV_HT, "online", False, None))
        start = len(w.changes)
        w.bridge.clock_skew = timedelta(seconds=-1750)      # the first minutes after the restart
        w.bridge.reboot()                                   # NotifyFullStatus
        await w.wait_for(lambda xs: any(c.device_id == DEV_BRIDGE for c in xs[start:]))
        reads = len(w.get_components_offsets())
        w.bridge.pair(w.fakes[ADDR_STRANGER])               # component_added: the map is read again
        await w.wait_for(lambda xs: len(w.get_components_offsets()) > reads)
        await w.settle(0.2)
        assert w.blu(start) == [] and not w.info(DEV_HT).online
        assert abs(bridge_offset(w)) < connector_module.CLOCK_OFFSET_IGNORED_S
        assert clock_warnings(warnings) == []
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_bridge_offset_beyond_a_day_is_ignored_with_one_warning(warnings):
    """The bridge's clock is two days ahead: no clock. The offset is not adopted (none, our clock), warned once as
    implausible, never as "bridge clock off"; a last_updated_ts that far in the future is our reception time, so the
    H&T that sends every minute stays online, its values dated on our clock."""
    async def scenario(w):
        w.bridge.clock_skew = timedelta(days=2)
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        assert bridge_offset(w) is None and w.info(DEV_HT).online
        await ht_every_minute(w, 3)
        assert bridge_offset(w) is None
        implausible = [f for m, f in warnings if m == "bridge clock implausible"]
        assert len(implausible) == 1 and implausible[0]["device_id"] == DEV_BRIDGE
        assert abs(implausible[0]["offset_s"] - 2 * 86_400) <= 1
        assert clock_warnings(warnings) == []
    run_blu(scenario, sensors=(DEV_HT,))


@pytest.mark.parametrize("bridge_time", ["known", "unknown"])
def test_blu_packet_after_its_reception_is_dated_at_its_reception(bridge_time):
    """A BLU packet whose last_updated_ts, brought to our clock, would fall 100 s after its reception (within
    MAX_CLOCK_SKEW_S): its state comes out at the reception, never later. "known": the bridge's offset is known (its
    clock right; translate.bthome_ts keeps the packet at the reception). "unknown": the bridge has no time yet
    (sys.unixtime null) and the notification no ts, so no offset (the way out, _emit, keeps it at the reception)."""
    async def scenario(w):
        if bridge_time == "unknown":
            full_status = w.bridge.full_status

            def without_time():
                status = full_status()
                status["sys"]["unixtime"] = None
                return status
            w.bridge.full_status = without_time
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        assert (bridge_offset(w) is None) == (bridge_time == "unknown")
        received = max(datetime.now(UTC) + w.shift, w.changes[-1].ts) + timedelta(seconds=1)
        params = {w.bridge.blu_keys(ADDR_HT)[3]: {"last_updated_ts": int(received.timestamp()) + 100, "value": 23.0}}
        if bridge_time == "known":
            params["ts"] = round(received.timestamp(), 2)
        start = len(w.changes)
        w.transport.inject(Notification("NotifyStatus", SID_BRIDGE, params, received))
        await w.wait_for(lambda xs: len(xs) > start)
        assert [(c.device_id, c.capability, c.state, c.ts) for c in w.changes[start:]] == [
            (DEV_HT, "temperature", {"celsius": 23.0}, received)]
    run_blu(scenario, sensors=(DEV_HT,))


@pytest.mark.parametrize("unixtime", [None, "absent"])
def test_blu_bridge_without_its_time_yet_gives_no_offset(warnings, monkeypatch, unixtime):
    """A bridge that has no time yet: sys.unixtime null, or not there. No offset, no warning, no error; the H&T is
    read on our clock."""
    errors = []
    monkeypatch.setattr(connector_module.log, "error", lambda msg, **fields: errors.append((msg, fields)))

    async def scenario(w):
        full_status = w.bridge.full_status

        def without_time():
            status = full_status()
            if unixtime == "absent":
                del status["sys"]["unixtime"]
            else:
                status["sys"]["unixtime"] = None
            return status
        w.bridge.full_status = without_time
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        await w.settle(0.1)
        assert bridge_offset(w) is None and w.info(DEV_HT).online
        assert not [m for m, _ in warnings if m.startswith("bridge clock")] and errors == []
    run_blu(scenario, sensors=(DEV_HT,))


# --- an offset beyond the skew is a candidate until a later source confirms it --------------------------------------

def get_status_calls(w):
    return sum(1 for _, m, _ in w.transport.calls if m == "Shelly.GetStatus")


def clock_infos(monkeypatch):
    seen = []
    monkeypatch.setattr(connector_module.log, "info",
                        lambda msg, **fields: seen.append(fields) if msg == "bridge clock offset to be confirmed"
                        else None)
    return seen


def test_blu_clock_candidate_confirmed_by_a_bthome_notification(warnings, monkeypatch):
    """The bridge 400 s behind: the GetStatus of the connection gives a candidate (logged once, no warning, not used:
    the H&T looks 400 s old, offline). A bthome NotifyStatus giving the same offset CLOCK_CONFIRM_S later confirms it:
    adopted, "bridge clock off" warned once, and the H&T of that packet is online."""
    infos = clock_infos(monkeypatch)

    async def scenario(w):
        w.bridge.clock_skew = timedelta(seconds=-400)
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        assert bridge_offset(w) is None and not w.info(DEV_HT).online
        assert clock_warnings(warnings) == [] and len(infos) == 1 and abs(infos[0]["offset_s"] + 400) <= 1
        w.shift = timedelta(seconds=300)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0})
        await w.wait_for(lambda xs: w.info(DEV_HT).online)
        assert abs(bridge_offset(w) + 400) <= 1 and len(infos) == 1
        assert len(clock_warnings(warnings)) == 1
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_clock_candidate_confirmed_by_get_status_at_the_silence_check():
    """A Motion at rest: no BLU packet for minutes. The bridge 400 s behind gives a candidate at the connection; when
    it has waited CLOCK_CONFIRM_S, the next silence check reads Shelly.GetStatus again, once, and its sys.unixtime
    confirms it."""
    async def scenario(w):
        w.bridge.clock_skew = timedelta(seconds=-400)
        w.pair(ADDR_MOTION)
        w.bridge.blu_packet(ADDR_MOTION, {33: False}, battery=100)
        await w.connect_bridge()
        calls = get_status_calls(w)
        assert bridge_offset(w) is None and calls == 1
        w.shift = timedelta(seconds=290)
        await w.settle(0.2)
        assert bridge_offset(w) is None and get_status_calls(w) == calls
        w.shift = timedelta(seconds=310)
        await w.wait_for(lambda xs: bridge_offset(w) is not None)
        assert abs(bridge_offset(w) + 400) <= 1
        await w.settle(0.2)
        assert get_status_calls(w) == calls + 1
    run_blu(scenario, sensors=(DEV_MOTION,))


def test_blu_clock_candidate_dropped_when_the_bridge_synchronises(warnings):
    """The bridge 400 s behind at the connection (a candidate), then synchronised: the H&T's next packet gives an
    offset within the skew, adopted at once, and the candidate is dropped. The -400 s is never adopted, never warned,
    and no GetStatus is read again for it."""
    async def scenario(w):
        w.bridge.clock_skew = timedelta(seconds=-400)
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        calls = get_status_calls(w)
        w.bridge.clock_skew = timedelta(0)
        w.shift = timedelta(seconds=60)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0})
        await w.wait_for(lambda xs: w.info(DEV_HT).online)
        assert abs(bridge_offset(w)) < connector_module.CLOCK_OFFSET_IGNORED_S
        w.shift = timedelta(seconds=400)
        await w.settle(0.2)
        assert get_status_calls(w) == calls and abs(bridge_offset(w)) < connector_module.CLOCK_OFFSET_IGNORED_S
        assert clock_warnings(warnings) == []
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_clock_candidate_not_confirmed_before_clock_confirm_s(warnings):
    """The same -400 s again 290 s after the candidate: too early, not adopted (the H&T stays offline, no warning);
    the wait counts from the first source, so at 300 s the H&T's packet confirms it."""
    async def scenario(w):
        w.bridge.clock_skew = timedelta(seconds=-400)
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        w.shift = timedelta(seconds=290)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0})
        await w.settle(0.2)
        assert bridge_offset(w) is None and not w.info(DEV_HT).online and clock_warnings(warnings) == []
        w.shift = timedelta(seconds=300)
        w.bridge.blu_packet(ADDR_HT, {69: 22.0})
        await w.wait_for(lambda xs: w.info(DEV_HT).online)
        assert abs(bridge_offset(w) + 400) <= 1 and len(clock_warnings(warnings)) == 1
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_clock_get_status_read_again_once_per_wait(warnings):
    """clock_confirm_s is 120 s here; a Motion at rest, no BLU packet. The candidate of the connection (-400 s) has
    waited: one GetStatus read again at the first check after 120 s, which fails, and not again at the next checks:
    120 s later. Its clock moved meanwhile (-500 s): a new candidate, the wait starts again, and the read 120 s later
    confirms the -500 s."""
    async def scenario(w):
        w.bridge.clock_skew = timedelta(seconds=-400)
        w.pair(ADDR_MOTION)
        w.bridge.blu_packet(ADDR_MOTION, {33: False}, battery=100)
        await w.connect_bridge()
        calls = get_status_calls(w)
        w.bridge.fail_next("Shelly.GetStatus")
        w.shift = timedelta(seconds=130)                     # due: read again, fails
        await w.wait_for(lambda xs: get_status_calls(w) == calls + 1)
        await w.settle(0.3)                                  # several checks
        assert get_status_calls(w) == calls + 1 and bridge_offset(w) is None
        w.shift = timedelta(seconds=200)
        await w.settle(0.2)
        assert get_status_calls(w) == calls + 1
        w.bridge.clock_skew = timedelta(seconds=-500)
        w.shift = timedelta(seconds=260)                     # 120 s after the failed read: -500 s, a new candidate
        await w.wait_for(lambda xs: get_status_calls(w) == calls + 2)
        await w.settle(0.3)
        assert get_status_calls(w) == calls + 2 and bridge_offset(w) is None
        w.shift = timedelta(seconds=390)                     # 130 s after the new candidate: confirmed
        await w.wait_for(lambda xs: bridge_offset(w) is not None)
        await w.settle(0.2)
        assert get_status_calls(w) == calls + 3 and abs(bridge_offset(w) + 500) <= 1
        warned = clock_warnings(warnings)
        assert len(warned) == 1 and abs(warned[0]["offset_s"] + 500) <= 1
    run_blu(scenario, sensors=(DEV_MOTION,), clock_confirm_s=120)


def test_blu_clock_candidate_is_forgotten_when_the_bridge_goes_offline():
    """A candidate (-400 s) at the connection; the bridge goes offline and back, its clock still 400 s behind: the
    candidate of the new connection waits from there, not from the first. 350 s after the first connection, 100 s
    after the second, the H&T's packet does not confirm it: the H&T stays offline."""
    async def scenario(w):
        w.bridge.clock_skew = timedelta(seconds=-400)
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        w.shift = timedelta(seconds=250)
        w.transport.set_online(SID_BRIDGE, False)
        await w.wait_for(lambda xs: not w.info(DEV_BRIDGE).online)
        await w.connect_bridge()
        w.shift = timedelta(seconds=350)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0})
        await w.settle(0.2)
        assert bridge_offset(w) is None and not w.info(DEV_HT).online
    run_blu(scenario, sensors=(DEV_HT,))


# --- a pairing while the bridge is online: the old map is not used --------------------------------------------------

def test_blu_map_is_dropped_at_a_pairing_with_the_bridge_online():
    """The sensors are paired again while the bridge is online, with the numbers reused: the old H&T temperature
    (bthomesensor:202) is now the Door/Window's rotation. Every read of the map fails meanwhile: a notification with the
    old number gives nothing (no old map); once a read at the silence check succeeds, the new numbers work."""
    async def scenario(w):
        w.pair(ADDR_HT, ADDR_DOOR)
        w.bridge.blu_packet(ADDR_HT, {69: 21.0, 46: 40})
        w.bridge.blu_packet(ADDR_DOOR, {45: True})
        await w.connect_bridge()
        old_temperature = w.bridge.blu_keys(ADDR_HT)[3]
        assert old_temperature == "bthomesensor:202"
        failing = [True]
        real_get_components = w.bridge._get_components

        def get_components(params):
            if failing[0]:
                raise RpcError(-103, "fake bridge: busy")
            return real_get_components(params)
        w.bridge._get_components = get_components
        start = len(w.changes)
        w.bridge.unpair(ADDR_HT)
        w.bridge.unpair(ADDR_DOOR)
        w.bridge.restart_numbering()
        w.pair(ADDR_DOOR, ADDR_HT)
        assert w.bridge.blu_keys(ADDR_DOOR)[3] == old_temperature
        await w.wait_for(lambda xs: len(w.get_components_offsets()) >= 1 + 18)   # every event read, and failed
        now = datetime.now(UTC) + w.shift
        w.transport.inject(Notification("NotifyStatus", SID_BRIDGE, {
            "ts": now.timestamp(), old_temperature: {"last_updated_ts": int(now.timestamp()), "value": 85.0}}, now))
        await w.settle()
        assert not any(c[1] == "state" for c in w.blu(start)), w.blu(start)
        failing[0] = False                                  # the next silence check reads the new map
        await w.settle()
        w.bridge.blu_packet(ADDR_HT, {69: 22.0})
        w.bridge.blu_packet(ADDR_DOOR, {45: False, 63: 25.0})
        await w.wait_for(lambda xs: (DEV_DOOR, "state", "contact", {"open": False}) in w.blu(start))
        await w.wait_for(lambda xs: (DEV_HT, "state", "temperature", {"celsius": 22.0}) in w.blu(start))
        assert not any(c[3] in ({"celsius": 85.0}, {"celsius": 25.0}) for c in w.blu(start)), w.blu(start)
        assert w.info(DEV_HT).capabilities["temperature"] == {"celsius": 22.0}
    run_blu(scenario, sensors=(DEV_HT, DEV_DOOR))


def test_blu_restart_with_reconnection_and_its_clock_behind_keeps_a_dead_ht_offline(warnings):
    """The bridge restarts through a reconnection with its clock 1750 s behind (the bench's Shelly 1 Gen4 after a
    restart); its GetStatus at the connection reads that clock. The H&T, silent since 1740 s, is offline: its last
    packet, dated by the wrong offset, would look «now». It must stay offline."""
    async def scenario(w):
        w.pair(ADDR_HT)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        w.shift = timedelta(seconds=1740)
        await w.wait_for(lambda xs: w.blu()[-1] == (DEV_HT, "online", False, None))
        w.transport.set_online(SID_BRIDGE, False)
        await w.wait_for(lambda xs: not w.info(DEV_BRIDGE).online)
        w.bridge.clock_skew = timedelta(seconds=-1750)      # restarted, its clock not yet synchronised
        start, reads = len(w.changes), len(w.get_components_offsets())
        w.transport.set_online(SID_BRIDGE, True)            # GetStatus (sys.unixtime), then the map
        w.bridge.reboot()                                   # NotifyFullStatus
        await w.wait_for(lambda xs: len(w.get_components_offsets()) > reads)
        await w.settle(0.2)
        assert w.blu(start) == [] and not w.info(DEV_HT).online, (w.blu(start), bridge_offset(w))
    run_blu(scenario, sensors=(DEV_HT,))


def test_blu_restart_without_reconnection_a_stranger_packet_keeps_a_dead_ht_offline(warnings):
    """The bridge restarts before the broker notices, so no reconnection and no GetStatus; a packet of a sensor
    outside the catalog arrives with the wrong clock (1750 s behind), then the map is read again (a pairing). The H&T,
    silent since 1740 s, must stay offline."""
    async def scenario(w):
        w.pair(ADDR_HT, ADDR_STRANGER)
        w.bridge.blu_packet(ADDR_HT, {69: 20.0, 46: 40}, battery=90)
        await w.connect_bridge()
        w.shift = timedelta(seconds=1740)
        await w.wait_for(lambda xs: w.blu()[-1] == (DEV_HT, "online", False, None))
        start = len(w.changes)
        w.bridge.clock_skew = timedelta(seconds=-1750)      # restarted, its clock not yet synchronised
        w.bridge.reboot()                                   # NotifyFullStatus
        w.bridge.blu_packet(ADDR_STRANGER, {69: 19.0, 46: 50}, battery=80)
        await w.settle(0.2)
        reads = len(w.get_components_offsets())
        w.pair(ADDR_MOTION)                                 # component_added: the map is read again
        await w.wait_for(lambda xs: len(w.get_components_offsets()) > reads)
        await w.settle(0.2)
        assert w.blu(start) == [] and not w.info(DEV_HT).online, (w.blu(start), bridge_offset(w))
    run_blu(scenario, sensors=(DEV_HT,))
