"""Capabilities <-> Shelly RPC and notifications (engine/connector/shelly/translate.py, connector.md §2.3-§2.6).

The samples are the Plug M Gen3 on the bench (firmware 1.8.99, 10 November 2026) with invented ids (connector.md §5).
Run: python -m pytest engine/connector/shelly/tests -q
"""
import asyncio
import copy
from datetime import UTC, datetime, timedelta

import pytest

from engine.connector.shelly.translate import (PROFILES, UnknownModel, apply_notify_status, capabilities_from_status,
                                               capabilities_touched, command_call, confirmed_result, error_result,
                                               merge_partial, notification_ts, profile_for, read_back_call)
from engine.connector.shelly.transport.base import RpcError, TransportOffline, TransportTimeout

PLUG = profile_for("PlugMG3")
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)

SWITCH_STATUS = {"id": 0, "source": "button", "output": True, "apower": 12.2, "voltage": 224.1, "freq": 50.1,
                 "current": 0.106, "aenergy": {"total": 0.0, "by_minute": [0.0, 0.0, 0.0], "minute_ts": 1794303660},
                 "ret_aenergy": {"total": 0.0, "by_minute": [0.0, 0.0, 0.0], "minute_ts": 1794303660},
                 "temperature": {"tC": 46.7, "tF": 116.1}}
FULL = {"switch:0": SWITCH_STATUS, "sys": {"mac": "000000000001", "uptime": 42}, "wifi": {"rssi": -60}}


def all_values(result: dict):
    for fields in result.values():
        yield from fields.items()


# --- the table -------------------------------------------------------------------------------------------------

def test_profile_is_found_by_app():
    assert profile_for("PlugMG3") is PROFILES["PlugMG3"]


def test_unknown_app_names_no_value():
    with pytest.raises(UnknownModel) as info:
        profile_for("SomeOtherApp")
    assert "SomeOtherApp" not in str(info.value)


# --- full status ---------------------------------------------------------------------------------------------------

def test_full_status_of_the_bench_plug():
    assert capabilities_from_status(PLUG, FULL) == {"switch": {"on": True},
                                                    "power_meter": {"watts": 12.2, "energy_total_wh": 0.0}}


def test_numbers_are_float_and_kwh_today_never_appears():
    status = copy.deepcopy(FULL)
    status["switch:0"]["apower"] = 13             # an int in the JSON
    status["switch:0"]["aenergy"]["total"] = 5
    result = capabilities_from_status(PLUG, status)
    assert type(result["power_meter"]["watts"]) is float
    assert type(result["power_meter"]["energy_total_wh"]) is float
    assert all(name != "kwh_today" for name, _ in all_values(result))


def test_components_outside_the_profile_and_extra_fields_are_ignored():
    result = capabilities_from_status(PLUG, FULL)
    assert set(result) == {"switch", "power_meter"}
    assert set(result["power_meter"]) == {"watts", "energy_total_wh"}


def test_wrong_types_leave_the_capability_out():
    status = copy.deepcopy(FULL)
    status["switch:0"]["output"] = "on"
    status["switch:0"]["apower"] = True           # a bool is not a number
    assert capabilities_from_status(PLUG, status) == {}


def test_missing_component_gives_nothing():
    assert capabilities_from_status(PLUG, {"sys": {}}) == {}


def test_counter_restarting_from_zero_is_reported_as_it_is():
    before = copy.deepcopy(FULL)
    before["switch:0"]["aenergy"]["total"] = 1834.5
    after = copy.deepcopy(FULL)                   # after a reboot: 0.0
    assert capabilities_from_status(PLUG, before)["power_meter"]["energy_total_wh"] == 1834.5
    assert capabilities_from_status(PLUG, after)["power_meter"]["energy_total_wh"] == 0.0


# --- partial notifications -----------------------------------------------------------------------------------------

def test_partial_with_output_only_touches_switch():
    status, changed = apply_notify_status(PLUG, FULL, {"ts": 1794303700.1, "switch:0": {"output": False}})
    assert changed == {"switch": {"on": False}}
    assert status["switch:0"]["output"] is False
    assert "ts" not in status


def test_partial_with_power_only_fills_the_counter_from_the_last_state():
    _, changed = apply_notify_status(PLUG, FULL, {"switch:0": {"apower": 0.0}})
    assert changed == {"power_meter": {"watts": 0.0, "energy_total_wh": 0.0}}


def test_partial_with_nested_counter_is_merged_recursively():
    status, changed = apply_notify_status(PLUG, FULL, {"switch:0": {"aenergy": {"total": 3.2}}})
    assert changed == {"power_meter": {"watts": 12.2, "energy_total_wh": 3.2}}
    assert status["switch:0"]["aenergy"]["minute_ts"] == 1794303660      # the rest of aenergy is kept


def test_partial_outside_the_capabilities_changes_nothing():
    _, changed = apply_notify_status(PLUG, FULL, {"switch:0": {"temperature": {"tC": 50.0}}, "wifi": {"rssi": -70}})
    assert changed == {}


def test_merge_partial_leaves_its_arguments_untouched():
    last = copy.deepcopy(FULL)
    partial = {"switch:0": {"aenergy": {"total": 9.0}}}
    snapshot_last, snapshot_partial = copy.deepcopy(last), copy.deepcopy(partial)
    merged = merge_partial(last, partial)
    assert last == snapshot_last and partial == snapshot_partial
    merged["switch:0"]["aenergy"]["by_minute"].append(1.0)
    assert last["switch:0"]["aenergy"]["by_minute"] == [0.0, 0.0, 0.0]


def test_capabilities_touched():
    assert capabilities_touched(PLUG, {"switch:0": {"output": True, "apower": 5}}) == {"switch", "power_meter"}
    assert capabilities_touched(PLUG, {"switch:0": {"source": "rpc"}}) == set()


# --- time ----------------------------------------------------------------------------------------------------------

def test_device_time_is_used_when_close_to_reception():
    device = NOW - timedelta(seconds=2)
    assert notification_ts({"ts": device.timestamp()}, NOW) == device


def test_reception_time_when_the_device_clock_is_off_or_missing():
    assert notification_ts({"ts": (NOW - timedelta(seconds=301)).timestamp()}, NOW) == NOW
    assert notification_ts({"ts": (NOW + timedelta(hours=3)).timestamp()}, NOW) == NOW
    assert notification_ts({}, NOW) == NOW
    assert notification_ts({"ts": "yesterday"}, NOW) == NOW
    assert notification_ts({"ts": True}, NOW) == NOW


# --- commands ------------------------------------------------------------------------------------------------------

def test_switch_command_becomes_switch_set():
    assert command_call(PLUG, "switch", {"on": True}) == ("Switch.Set", {"id": 0, "on": True})
    assert command_call(PLUG, "switch", {"on": False}) == ("Switch.Set", {"id": 0, "on": False})


def test_read_back_is_switch_get_status():
    assert read_back_call(PLUG, "switch") == ("Switch.GetStatus", {"id": 0})


def test_capability_not_commandable_or_bad_target():
    with pytest.raises(ValueError, match="climate"):
        command_call(PLUG, "climate", {"on": True})
    with pytest.raises(ValueError, match="target.on"):
        command_call(PLUG, "switch", {})
    with pytest.raises(ValueError, match="target.on"):
        command_call(PLUG, "switch", {"on": "yes"})


def test_read_back_that_reached_the_target_is_confirmed():
    off = SWITCH_STATUS | {"output": False}
    assert confirmed_result(PLUG, "switch", {"on": False}, off).outcome == "confirmed"
    assert confirmed_result(PLUG, "switch", {"on": False}, off).state == {"on": False}
    assert confirmed_result(PLUG, "switch", {"on": True}, SWITCH_STATUS).state == {"on": True}


def test_read_back_that_missed_the_target_is_rejected():
    result = confirmed_result(PLUG, "switch", {"on": True}, SWITCH_STATUS | {"output": False})
    assert (result.outcome, result.reason, result.detail) == ("failed", "device_rejected",
                                                              "output did not reach target")
    assert result.state is None


def test_read_back_without_output_is_an_internal_error():
    result = confirmed_result(PLUG, "switch", {"on": True}, {"id": 0})
    assert (result.outcome, result.reason) == ("failed", "internal_error")


# --- errors --------------------------------------------------------------------------------------------------------

def test_errors_map_to_the_three_reasons():
    cases = {RpcError(-103, "Argument 'on', value 42 not valid"): ("device_rejected", "rpc error -103"),
             TransportOffline(): ("device_offline", "device offline"),
             TransportTimeout(): ("internal_error", "transport timeout"),
             RuntimeError("boom with a secret"): ("internal_error", "RuntimeError")}
    for exc, (reason, detail) in cases.items():
        result = error_result(exc)
        assert (result.outcome, result.reason, result.detail) == ("failed", reason, detail), exc
        assert result.state is None


def test_detail_never_carries_what_the_device_said():
    assert "42" not in error_result(RpcError(-103, "Argument 'on', value 42 not valid")).detail
    assert "secret" not in error_result(RuntimeError("boom with a secret")).detail


def test_prefix_tells_where_it_failed():
    assert error_result(TransportOffline(), prefix="read back failed: ").detail == "read back failed: device offline"


def test_cancellation_is_never_turned_into_an_outcome():
    with pytest.raises(TypeError):
        error_result(asyncio.CancelledError())    # a BaseException: it must reach the engine
