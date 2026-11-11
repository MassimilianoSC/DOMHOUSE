"""The fake Plug M Gen3 and the FakeTransport, together with translate.py (connector.md §2.6, §3).

Run: python -m pytest engine/connector/shelly/tests -q
"""
import asyncio
import json
from pathlib import Path

import pytest

from engine.connector.shelly.translate import (apply_notify_status, capabilities_from_status, command_call,
                                               confirmed_result, error_result, profile_for, read_back_call)
from engine.connector.shelly.transport.base import (ConnectionEvent, Notification, RpcError, TransportOffline,
                                                    TransportTimeout)

from .fake_device import FakeBluDoorWindow, FakeBluHT, FakeBluMotion, FakePlugMG3, FakeS1G4
from .fake_transport import FakeTransport

SID = "shellyplugmg3-000000000001"


async def drain(transport: FakeTransport) -> list:
    """What the stream holds now, without waiting for more."""
    items = []
    stream = transport.notifications()
    while True:
        try:
            items.append(await asyncio.wait_for(stream.__anext__(), timeout=0.05))
        except (asyncio.TimeoutError, StopAsyncIteration):
            return items


def run(scenario):
    async def main():
        device = FakePlugMG3(SID, on=False, load_watts=12.2)
        transport = FakeTransport(device)
        await transport.start()
        try:
            return await scenario(device, transport)
        finally:
            await transport.stop()
    return asyncio.run(main())


def test_whole_path_from_device_info_to_confirmed():
    async def scenario(device, transport):
        info = await transport.call(SID, "Shelly.GetDeviceInfo", None, 1)
        assert info["id"] == SID and info["gen"] == 3
        profile = profile_for(info["app"])
        status = await transport.call(SID, "Shelly.GetStatus", None, 1)
        assert capabilities_from_status(profile, status)["switch"] == {"on": False}
        method, params = command_call(profile, "switch", {"on": True})
        assert await transport.call(SID, method, params, 1) == {"was_on": False}     # the state BEFORE
        method, params = read_back_call(profile, "switch")
        read_back = await transport.call(SID, method, params, 1)
        assert confirmed_result(profile, "switch", {"on": True}, read_back).state == {"on": True}
    run(scenario)


def test_switch_on_sends_output_then_power_then_current_as_three_partials():
    # as in the capture: {"output": true, "source": "MQTT"}, then {"apower": ...}, then {"current": ...}
    async def scenario(device, transport):
        profile = profile_for("PlugMG3")
        status = await transport.call(SID, "Shelly.GetStatus", None, 1)
        await transport.call(SID, "Switch.Set", {"id": 0, "on": True}, 1)
        first, second, third = await drain(transport)
        assert first.method == second.method == third.method == "NotifyStatus"
        assert first.params["switch:0"] == {"output": True, "source": "MQTT"}
        assert second.params["switch:0"] == {"apower": 12.2}
        assert third.params["switch:0"] == {"current": 0.054}
        assert first.received_at.tzinfo is not None and "ts" in first.params
        status, changed = apply_notify_status(profile, status, first.params)
        assert changed == {"switch": {"on": True}}
        status, changed = apply_notify_status(profile, status, second.params)
        assert changed == {"power_meter": {"watts": 12.2, "energy_total_wh": 0.0}}
        status, changed = apply_notify_status(profile, status, third.params)
        assert changed == {}                                  # current is no capability's field
    run(scenario)


def test_switch_off_sends_one_partial_with_output_power_and_current():
    # as in the capture: {"apower": 0, "current": 0, "output": false, "source": "MQTT"} in one message
    async def scenario(device, transport):
        await transport.call(SID, "Switch.Set", {"id": 0, "on": True}, 1)
        await drain(transport)
        status = await transport.call(SID, "Shelly.GetStatus", None, 1)
        await transport.call(SID, "Switch.Set", {"id": 0, "on": False}, 1)
        (off,) = await drain(transport)
        assert off.params["switch:0"] == {"output": False, "source": "MQTT", "apower": 0, "current": 0}
        _, changed = apply_notify_status(profile_for("PlugMG3"), status, off.params)
        assert changed == {"switch": {"on": False}, "power_meter": {"watts": 0.0, "energy_total_wh": 0.0}}
    run(scenario)


def test_button_press_is_a_partial_with_its_source():
    async def scenario(device, transport):
        device.press_button()
        first, *_ = await drain(transport)
        assert first.params["switch:0"] == {"output": True, "source": "button"}
        device.press_button()
        (off,) = await drain(transport)
        assert off.params["switch:0"]["source"] == "button"
    run(scenario)


def test_load_and_energy_changes_are_partials():
    async def scenario(device, transport):
        device.press_button()
        await drain(transport)
        device.set_load(40.0)
        device.add_energy(1.5)
        power, current, energy = await drain(transport)
        assert power.params["switch:0"] == {"apower": 40.0}
        assert current.params["switch:0"] == {"current": 0.178}
        assert energy.params["switch:0"]["aenergy"]["total"] == 1.5
    run(scenario)


def test_reboot_sends_a_full_status_with_the_counter_at_zero():
    async def scenario(device, transport):
        device.add_energy(100.0)
        await drain(transport)
        device.reboot()
        (full,) = await drain(transport)
        assert full.method == "NotifyFullStatus"
        profile = profile_for("PlugMG3")
        assert capabilities_from_status(profile, full.params)["power_meter"]["energy_total_wh"] == 0.0
    run(scenario)


def test_faults_become_the_three_outcomes():
    async def scenario(device, transport):
        device.fail_next("Switch.Set", -103, "Argument 'on', value 42 not valid")
        with pytest.raises(RpcError) as info:
            await transport.call(SID, "Switch.Set", {"id": 0, "on": True}, 1)
        assert error_result(info.value).reason == "device_rejected"

        device.hang_next("Switch.Set")
        with pytest.raises(TransportTimeout) as info:
            await transport.call(SID, "Switch.Set", {"id": 0, "on": True}, 0.05)
        assert error_result(info.value).reason == "internal_error"

        transport.set_online(SID, False)
        with pytest.raises(TransportOffline) as info:
            await transport.call(SID, "Switch.Set", {"id": 0, "on": True}, 1)
        assert error_result(info.value).reason == "device_offline"
        assert SID not in transport.connected()
    run(scenario)


def test_unknown_method_and_wrong_channel_are_rpc_errors():
    async def scenario(device, transport):
        with pytest.raises(RpcError) as info:
            await transport.call(SID, "Cover.Open", {"id": 0}, 1)
        assert info.value.code == -32601
        with pytest.raises(RpcError) as info:
            await transport.call(SID, "Switch.Set", {"id": 1, "on": True}, 1)
        assert info.value.code == -105
    run(scenario)


def test_connection_events_travel_in_order_with_the_notifications():
    async def scenario(device, transport):
        device.press_button()                     # on: output, then power, then current
        transport.set_online(SID, False)
        device.press_button()                     # while offline: nothing reaches us
        transport.set_online(SID, True)
        device.reboot()                           # the snapshot after the reconnection
        items = await drain(transport)
        kinds = [(type(i).__name__, getattr(i, "connected", None), getattr(i, "method", None)) for i in items]
        assert kinds == [("Notification", None, "NotifyStatus")] * 3 + [
                         ("ConnectionEvent", False, None), ("ConnectionEvent", True, None),
                         ("Notification", None, "NotifyFullStatus")]
        assert all(i.received_at.tzinfo is not None for i in items)
    run(scenario)


def test_set_online_twice_emits_one_event():
    async def scenario(device, transport):
        transport.set_online(SID, False)
        transport.set_online(SID, False)
        assert [type(i) for i in await drain(transport)] == [ConnectionEvent]
    run(scenario)


def test_unknown_device_is_offline():
    async def scenario(device, transport):
        with pytest.raises(TransportOffline):
            await transport.call("shellyplugmg3-00000000ffff", "Shelly.GetStatus", None, 1)
    run(scenario)


def test_stop_ends_the_stream():
    async def main():
        transport = FakeTransport(FakePlugMG3(SID))
        await transport.start()
        await transport.stop()
        assert [item async for item in transport.notifications()] == []
    asyncio.run(main())


def test_two_transports_do_not_see_each_other():
    async def main():
        a, b = FakePlugMG3(SID), FakePlugMG3("shellyplugmg3-000000000002")
        ta, tb = FakeTransport(a), FakeTransport(b)
        await ta.start()
        await tb.start()
        a.press_button()
        assert all(isinstance(i, Notification) and i.shelly_id == SID for i in await drain(ta))
        assert await drain(tb) == []
        assert tb.connected() == {"shellyplugmg3-000000000002"}
    asyncio.run(main())


# --- BLU sensors paired with a fake bridge ----------------------------------------------------------------------

def test_fake_bridge_pairs_numbers_and_pages_its_components():
    bridge = FakeS1G4()
    assert bridge.handle("Shelly.GetComponents", {"dynamic_only": True}) == {
        "components": [], "cfg_rev": 10, "offset": 0, "total": 0}       # nothing paired: an empty answer
    sent = []
    bridge.subscribe(sent.append)
    for sensor in (FakeBluHT("02:00:00:00:a1:01"), FakeBluMotion("02:00:00:00:a1:02"),
                   FakeBluDoorWindow("02:00:00:00:a1:03")):
        bridge.pair(sensor)
    targets = [n.params["events"][0]["target"] for n in sent]
    assert targets[:4] == ["bthomedevice:200", "bthomesensor:200", "bthomesensor:201", "bthomesensor:202"]
    assert len(targets) == 13 and all(n.params["events"][0]["event"] == "component_added" for n in sent)
    first = bridge.handle("Shelly.GetComponents", {"dynamic_only": True, "offset": 0})
    second = bridge.handle("Shelly.GetComponents", {"dynamic_only": True, "offset": 10})
    assert (len(first["components"]), first["total"], len(second["components"]), second["offset"]) == (10, 13, 3, 10)
    keys = [c["key"] for c in first["components"] + second["components"]]
    assert keys[:3] == ["bthomedevice:200", "bthomedevice:201", "bthomedevice:202"] and keys[-1] == "bthomesensor:209"
    door = second["components"][0]
    assert door["config"] == {"id": 207, "addr": "02:00:00:00:a1:03", "name": None, "obj_id": 45, "idx": 0,
                              "meta": None}
    assert door["status"] == {"id": 207, "value": None, "last_updated_ts": 0}         # no packet yet: 0, not null
    sent.clear()
    bridge.unpair("02:00:00:00:a1:02")
    assert [(n.params["events"][0]["event"], n.params["events"][0]["target"]) for n in sent] == [
        ("component_removed", "bthomesensor:203"), ("component_removed", "bthomesensor:204"),
        ("component_removed", "bthomesensor:205"), ("component_removed", "bthomedevice:201")]


def test_fake_bridge_notifies_a_measure_only_when_it_changes():
    bridge = FakeS1G4()
    bridge.pair(FakeBluHT("02:00:00:00:a1:01"))
    sent = []
    bridge.subscribe(sent.append)
    bridge.blu_packet("02:00:00:00:a1:01", {69: 21.5, 46: 48}, battery=100)
    assert [sorted(k for k in n.params if k != "ts") for n in sent] == [
        ["bthomesensor:200"], ["bthomesensor:201"], ["bthomesensor:202"]]   # battery, humidity, temperature
    sent.clear()
    bridge.blu_packet("02:00:00:00:a1:01", {69: 21.5, 46: 49})
    assert [list(k for k in n.params if k != "ts") for n in sent] == [["bthomesensor:201"]]
    sent.clear()
    bridge.blu_device_report("02:00:00:00:a1:01")
    report = sent[0].params["bthomedevice:200"]
    assert set(report) == {"last_updated_ts", "packet_id", "rssi", "battery"} and report["packet_id"] == 2
    sent.clear()
    bridge.blu_device_report("02:00:00:00:a1:01")                        # battery unchanged: not repeated
    assert set(sent[0].params["bthomedevice:200"]) == {"last_updated_ts", "packet_id", "rssi"}


REAL_PAGES = Path(__file__).with_name("fixtures") / "blu_get_components_pages.json"


def shape(value):
    """Field names in order and the type of every leaf: what must match the real answers, values aside."""
    if isinstance(value, dict):
        return [(k, shape(v)) for k, v in value.items()]
    if isinstance(value, list):
        return [shape(v) for v in value]
    return type(value).__name__


def test_fake_bridge_answers_with_the_shape_of_the_real_get_components():
    """Same envelope, same components in the same order, same fields in the same order with the same types, as the
    real answers of the Shelly 1 Gen4 (fixture), once the fake's sensors sent the values the real ones had."""
    real = json.loads(REAL_PAGES.read_text(encoding="utf-8"))["pages"]
    bridge = FakeS1G4()
    sensors = {s.addr: s for s in (FakeBluHT("02:00:00:00:a1:01"), FakeBluMotion("02:00:00:00:a1:02"),
                                   FakeBluDoorWindow("02:00:00:00:a1:03"))}
    for sensor in sensors.values():
        bridge.pair(sensor)
    for component in (c for page in real for c in page["components"] if c["key"].startswith("bthomesensor")):
        battery = component["status"]["value"] if component["config"]["obj_id"] == 1 else None
        bridge.blu_packet(component["config"]["addr"], {component["config"]["obj_id"]: component["status"]["value"]},
                          battery=battery, rssi=-60)
    fake = [bridge.handle("Shelly.GetComponents", {"dynamic_only": True, "offset": page["offset"]}) for page in real]
    assert [c["key"] for p in fake for c in p["components"]] == [c["key"] for p in real for c in p["components"]]
    for fake_page, real_page in zip(fake, real):
        assert list(fake_page) == list(real_page)                      # components, cfg_rev, offset, total
        assert (fake_page["offset"], fake_page["total"]) == (real_page["offset"], real_page["total"])
        for f, r in zip(fake_page["components"], real_page["components"]):
            assert shape(f) == shape(r), f["key"]
            assert f["config"] == r["config"], f["key"]                # ids, MAC, obj_id, idx, meta: the same


def test_fake_sensor_never_heard_is_the_real_one():
    """Right after the pairing, before the first packet: the bthomedevice all null, the bthomesensor value null and
    last_updated_ts 0 (not null), exactly as the real Motion."""
    never = json.loads(REAL_PAGES.read_text(encoding="utf-8"))["never_heard"]
    bridge = FakeS1G4()
    bridge.pair(FakeBluHT("02:00:00:00:a1:01"))           # the real Motion was the second pairing: 201, 203-205
    bridge.pair(FakeBluMotion("02:00:00:00:a1:02"))
    components = {c["key"]: c for c in bridge.handle("Shelly.GetComponents", {"dynamic_only": True})["components"]}
    assert components["bthomedevice:201"]["status"] == never["bthomedevice"]
    assert components["bthomesensor:204"]["status"] == never["bthomesensor"]
    assert never["bthomesensor"]["last_updated_ts"] == 0 and never["bthomesensor"]["value"] is None
