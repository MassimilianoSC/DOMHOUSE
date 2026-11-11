"""One command over the transport: set, read back, one retry of the read back (engine/connector/shelly/command.py,
connector.md §2.5). Each test runs its own event loop, as test_interface.py does (no pytest-asyncio).

Run: python -m pytest engine/connector/shelly/tests -q
"""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from engine.connector.shelly.command import run_command
from engine.connector.shelly.translate import profile_for

from .fake_device import FakePlugMG3
from .fake_transport import FakeTransport

PLUG = profile_for("PlugMG3")
SID = "shellyplugmg3-000000000001"
FAST = 0.05      # an RPC timeout short enough to keep the tests quick


def go(device: FakePlugMG3, target: dict, *, deadline_s: float = 9.0, rpc_timeout_s: float = FAST):
    """Runs one switch command on the device; returns (result, progress, calls)."""
    async def main():
        transport = FakeTransport(device)
        await transport.start()
        progress: list[str] = []
        result = await run_command(transport, SID, PLUG, "switch", target,
                                   deadline=datetime.now(UTC) + timedelta(seconds=deadline_s),
                                   on_progress=progress.append, rpc_timeout_s=rpc_timeout_s)
        await transport.stop()
        return result, progress, [method for _, method, _ in transport.calls]
    return asyncio.run(main())


def test_switch_on_is_confirmed():
    device = FakePlugMG3(SID, on=False)
    result, progress, calls = go(device, {"on": True})
    assert (result.outcome, result.state) == ("confirmed", {"on": True})
    assert progress == ["sent", "verifying"]
    assert calls == ["Switch.Set", "Switch.GetStatus"]
    assert device.on is True


class _TimelineTransport(FakeTransport):
    """Writes each RPC into the same list on_progress writes to, to check what comes before what."""

    def __init__(self, timeline: list, *devices):
        super().__init__(*devices)
        self.timeline = timeline

    async def call(self, shelly_id, method, params, timeout_s):
        self.timeline.append(f"call {method}")
        return await super().call(shelly_id, method, params, timeout_s)


def test_sent_comes_before_the_rpc_and_verifying_before_the_read_back():
    async def main():
        timeline: list[str] = []
        transport = _TimelineTransport(timeline, FakePlugMG3(SID, on=False))
        await transport.start()
        result = await run_command(transport, SID, PLUG, "switch", {"on": True},
                                   deadline=datetime.now(UTC) + timedelta(seconds=9),
                                   on_progress=lambda step: timeline.append(step), rpc_timeout_s=FAST)
        timeline.append(result.outcome)
        return timeline
    assert asyncio.run(main()) == ["sent", "call Switch.Set", "verifying", "call Switch.GetStatus", "confirmed"]


def test_switch_off_is_confirmed():
    device = FakePlugMG3(SID, on=True)
    result, _, _ = go(device, {"on": False})
    assert (result.outcome, result.state) == ("confirmed", {"on": False})


def test_target_already_reached_is_still_confirmed():
    result, _, _ = go(FakePlugMG3(SID, on=True), {"on": True})
    assert (result.outcome, result.state) == ("confirmed", {"on": True})


def test_relay_that_refuses_is_rejected():
    device = FakePlugMG3(SID, on=False)
    device.protection_trips = True
    result, _, _ = go(device, {"on": True})
    assert (result.outcome, result.reason, result.detail) == ("failed", "device_rejected",
                                                              "output did not reach target")


# --- a device not connected: failed at once, no RPC, no "sent" ---------------------------------------------------

def test_device_not_connected_fails_at_once_without_sent():
    device = FakePlugMG3(SID)
    device.online = False
    result, progress, calls = go(device, {"on": True})
    assert (result.outcome, result.reason, result.detail) == ("failed", "device_offline", "device offline")
    assert progress == [] and calls == []


def test_device_unknown_to_the_transport_fails_at_once_without_sent():
    async def main():
        transport = FakeTransport(FakePlugMG3("shellyplugmg3-000000000002"))
        await transport.start()
        progress: list[str] = []
        result = await run_command(transport, SID, PLUG, "switch", {"on": True},
                                   deadline=datetime.now(UTC) + timedelta(seconds=9), on_progress=progress.append)
        return result, progress, transport.calls
    result, progress, calls = asyncio.run(main())
    assert (result.outcome, result.reason) == ("failed", "device_offline")
    assert progress == [] and calls == []


# --- errors on the set RPC after "sent": the command's own outcome, no prefix --------------------------------------

def test_rpc_error_on_set_is_rejected_with_the_code_only():
    device = FakePlugMG3(SID)
    device.fail_next("Switch.Set", -103, "Argument 'on', value secret-ish not valid")
    result, progress, calls = go(device, {"on": True})
    assert (result.outcome, result.reason, result.detail) == ("failed", "device_rejected", "rpc error -103")
    assert progress == ["sent"] and calls == ["Switch.Set"]


def test_connection_dropping_during_set_is_device_offline():
    device = FakePlugMG3(SID)
    device.drop_next("Switch.Set")
    result, progress, calls = go(device, {"on": True})
    assert (result.outcome, result.reason, result.detail) == ("failed", "device_offline", "device offline")
    assert progress == ["sent"] and calls == ["Switch.Set"]


def test_timeout_on_set_is_an_internal_error():
    device = FakePlugMG3(SID)
    device.hang_next("Switch.Set")
    result, progress, calls = go(device, {"on": True})
    assert (result.outcome, result.reason, result.detail) == ("failed", "internal_error", "transport timeout")
    assert progress == ["sent"] and calls == ["Switch.Set"]


def test_bad_target_is_refused_before_any_rpc():
    result, _, calls = go(FakePlugMG3(SID), {"on": "yes"})
    assert (result.outcome, result.reason) == ("failed", "internal_error")
    assert calls == []


# --- the read back and its one retry -----------------------------------------------------------------------------

@pytest.mark.parametrize("fault", ["hang_next", "drop_next"])
def test_read_back_is_retried_once_and_then_confirmed(fault):
    device = FakePlugMG3(SID, on=False)
    getattr(device, fault)("Switch.GetStatus")
    result, _, calls = go(device, {"on": True})
    assert (result.outcome, result.state) == ("confirmed", {"on": True})
    assert calls == ["Switch.Set", "Switch.GetStatus", "Switch.GetStatus"]


def test_read_back_timing_out_twice_says_read_back_failed():
    device = FakePlugMG3(SID, on=False)
    device.hang_next("Switch.GetStatus")
    device.hang_next("Switch.GetStatus")
    result, progress, calls = go(device, {"on": True})
    assert (result.outcome, result.reason, result.detail) == ("failed", "internal_error",
                                                              "read back failed: transport timeout")
    assert progress == ["sent", "verifying"]
    assert calls == ["Switch.Set", "Switch.GetStatus", "Switch.GetStatus"]      # never a third time


def test_read_back_offline_twice_is_device_offline():
    device = FakePlugMG3(SID, on=False)
    device.drop_next("Switch.GetStatus")
    device.drop_next("Switch.GetStatus")
    result, _, _ = go(device, {"on": True})
    assert (result.outcome, result.reason, result.detail) == ("failed", "device_offline",
                                                              "read back failed: device offline")


def test_rpc_error_on_read_back_is_not_retried():
    device = FakePlugMG3(SID, on=False)
    device.fail_next("Switch.GetStatus", -114, "busy")
    result, _, calls = go(device, {"on": True})
    assert (result.outcome, result.reason, result.detail) == ("failed", "device_rejected",
                                                              "read back failed: rpc error -114")
    assert calls == ["Switch.Set", "Switch.GetStatus"]


def test_no_retry_after_the_deadline():
    device = FakePlugMG3(SID, on=False)
    device.hang_next("Switch.GetStatus")
    # the first read back eats the time left: the retry would start after the deadline, so it never does
    result, _, calls = go(device, {"on": True}, deadline_s=0.15, rpc_timeout_s=1.0)
    assert result.detail == "read back failed: transport timeout"
    assert calls == ["Switch.Set", "Switch.GetStatus"]


def test_deadline_already_passed_sends_nothing():
    result, _, calls = go(FakePlugMG3(SID), {"on": True}, deadline_s=-1)
    assert (result.outcome, result.reason) == ("failed", "internal_error")
    assert calls == []


def test_cancellation_reaches_the_caller():
    async def main():
        device = FakePlugMG3(SID, on=False)
        device.hang_next("Switch.Set")
        transport = FakeTransport(device)
        await transport.start()
        task = asyncio.get_running_loop().create_task(
            run_command(transport, SID, PLUG, "switch", {"on": True},
                        deadline=datetime.now(UTC) + timedelta(seconds=9), on_progress=lambda s: None,
                        rpc_timeout_s=5.0))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # the transport is still usable afterwards
        result = await run_command(transport, SID, PLUG, "switch", {"on": True},
                                   deadline=datetime.now(UTC) + timedelta(seconds=9), on_progress=lambda s: None,
                                   rpc_timeout_s=FAST)
        assert result.outcome == "confirmed"
    asyncio.run(main())
