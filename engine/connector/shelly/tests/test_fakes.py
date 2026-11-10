"""The fake Plug M Gen3 and the FakeTransport, together with translate.py (connector.md §2.6, §3).

Run: python -m pytest engine/connector/shelly/tests -q
"""
import asyncio

import pytest

from engine.connector.shelly.translate import (apply_notify_status, capabilities_from_status, command_call,
                                               confirmed_result, error_result, profile_for, read_back_call)
from engine.connector.shelly.transport.base import (ConnectionEvent, Notification, RpcError, TransportOffline,
                                                    TransportTimeout)

from .fake_device import FakePlugMG3
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


def test_switch_set_sends_output_then_power_as_two_partials():
    async def scenario(device, transport):
        profile = profile_for("PlugMG3")
        status = await transport.call(SID, "Shelly.GetStatus", None, 1)
        await transport.call(SID, "Switch.Set", {"id": 0, "on": True}, 1)
        first, second = await drain(transport)
        assert first.method == second.method == "NotifyStatus"
        assert first.params["switch:0"] == {"output": True, "source": "rpc"}
        assert second.params["switch:0"] == {"apower": 12.2}
        assert first.received_at.tzinfo is not None and "ts" in first.params
        status, changed = apply_notify_status(profile, status, first.params)
        assert changed == {"switch": {"on": True}}
        status, changed = apply_notify_status(profile, status, second.params)
        assert changed == {"power_meter": {"watts": 12.2, "energy_total_wh": 0.0}}
    run(scenario)


def test_button_press_is_a_partial_with_its_source():
    async def scenario(device, transport):
        device.press_button()
        first, _ = await drain(transport)
        assert first.params["switch:0"] == {"output": True, "source": "button"}
    run(scenario)


def test_load_and_energy_changes_are_partials():
    async def scenario(device, transport):
        device.press_button()
        await drain(transport)
        device.set_load(40.0)
        device.add_energy(1.5)
        power, energy = await drain(transport)
        assert power.params["switch:0"] == {"apower": 40.0}
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
        device.press_button()                     # on: output, then power
        transport.set_online(SID, False)
        device.press_button()                     # while offline: nothing reaches us
        transport.set_online(SID, True)
        device.reboot()                           # the snapshot after the reconnection
        items = await drain(transport)
        kinds = [(type(i).__name__, getattr(i, "connected", None), getattr(i, "method", None)) for i in items]
        assert kinds == [("Notification", None, "NotifyStatus"), ("Notification", None, "NotifyStatus"),
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
