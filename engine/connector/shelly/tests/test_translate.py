"""Capabilities <-> Shelly RPC and notifications (engine/connector/shelly/translate.py, connector.md §2.3-§2.6).

The samples are the Plug M Gen3 on the bench (firmware 1.8.99, 10 November 2026) with invented ids (connector.md §5);
the Shelly 1 Gen4 and the EM Mini Gen4 come from tests/fixtures/g4_relay_emmini_mqtt_capture.jsonl (session C); the
BLU sensors from tests/fixtures/blu_bridge_mqtt_capture.jsonl (session D) and blu_get_components_pages.json.
Run: python -m pytest engine/connector/shelly/tests -q
"""
import asyncio
import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from engine.connector.shelly.translate import (BLU_MODELS, BTHOME_IGNORED, PROFILES, UnknownModel, apply_notify_status,
                                               blu_reading, bthome_components, bthome_ts, capabilities_from_status,
                                               capabilities_touched, command_call, component_event_targets,
                                               confirmed_result, error_result, merge_partial, normalize_mac,
                                               notification_ts, profile_for, read_back_call, supported_models)
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


# --- Shelly 1 Gen4 and EM Mini Gen4, from the bench capture (session C, 10 November 2026) -------------------------

G4_CAPTURE = Path(__file__).with_name("fixtures") / "g4_relay_emmini_mqtt_capture.jsonl"
S1 = profile_for("S1G4")
EM = profile_for("MiniEMG4")


def g4_messages(prefix: str) -> list[tuple[datetime, dict]]:
    """(received_at, the JSON message) of one device of the capture, by the start of its shelly_id."""
    out = []
    for line in G4_CAPTURE.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if not record["topic"].split("/")[1].startswith(prefix) or record["topic"].endswith("/online"):
            continue
        received = datetime.strptime(record["received_at"], "%Y-%m-%dT%H:%M:%S%z").astimezone(UTC)
        out.append((received, json.loads(record["payload"])))
    return out


def g4_result(prefix: str, method: str) -> dict:
    """The answer to the first RPC of that method sent to that device."""
    messages = [m for _, m in g4_messages(prefix)]
    rpc_id = next(m["id"] for m in messages if m.get("method") == method and "result" not in m)
    return next(m["result"] for m in messages if m.get("id") == rpc_id and "result" in m)


def g4_status_notifications(prefix: str) -> list[tuple[datetime, dict]]:
    return [(r, m["params"]) for r, m in g4_messages(prefix) if m.get("method") == "NotifyStatus"]


def test_the_two_gen4_rows_are_found_by_their_app():
    assert (S1.device_type, S1.label) == ("relay", "Shelly 1 Gen4")
    assert (EM.device_type, EM.label) == ("energy_meter", "Shelly EM Mini Gen4")
    assert g4_result("shelly1g4", "Shelly.GetDeviceInfo")["app"] == "S1G4"
    assert g4_result("shellyemminig4", "Shelly.GetDeviceInfo")["app"] == "MiniEMG4"


def test_s1g4_full_status_from_the_capture():
    status = g4_result("shelly1g4", "Shelly.GetStatus")
    assert capabilities_from_status(S1, status) == {"switch": {"on": False}, "heating": {"on": False}}


def test_s1g4_is_a_switch_or_a_boiler_never_both_and_never_a_meter():
    assert S1.covers("relay", {"switch": {}}) and S1.covers("relay", {"heating": {"setpoint_min": 7}})
    assert not S1.covers("relay", {"switch": {}, "heating": {}})
    assert not S1.covers("relay", {"switch": {}, "power_meter": {}})
    assert not S1.covers("plug", {"switch": {}})
    assert PLUG.covers("plug", {"switch": {}, "power_meter": {}})          # the Plug as before


def test_s1g4_partial_with_output_touches_its_relay():
    output = [p for _, p in g4_status_notifications("shelly1g4") if "output" in p.get("switch:0", {})]
    assert [p["switch:0"]["output"] for p in output] == [True, False, True, False, True, False]
    status = g4_result("shelly1g4", "Shelly.GetStatus")
    status, changed = apply_notify_status(S1, status, output[0])
    assert changed == {"switch": {"on": True}, "heating": {"on": True}}
    assert status["switch:0"]["source"] == "MQTT"


def test_s1g4_counts_input_and_the_rest_change_nothing():
    status = g4_result("shelly1g4", "Shelly.GetStatus")
    others = [p for _, p in g4_status_notifications("shelly1g4") if "output" not in p.get("switch:0", {})]
    assert any(set(p) == {"ts", "switch:0"} and set(p["switch:0"]) == {"counts"} for p in others)   # every minute
    for params in others + [{"input:0": {"state": True}}]:
        status, changed = apply_notify_status(S1, status, params)
        assert changed == {}, params


def test_s1g4_command_is_switch_set_for_switch_and_heating():
    for capability in ("switch", "heating"):
        assert command_call(S1, capability, {"on": True}) == ("Switch.Set", {"id": 0, "on": True})
        assert read_back_call(S1, capability) == ("Switch.GetStatus", {"id": 0})
    read_back = g4_result("shelly1g4", "Switch.GetStatus")         # output false in the capture
    assert confirmed_result(S1, "heating", {"on": False}, read_back).state == {"on": False}
    assert confirmed_result(S1, "switch", {"on": True}, read_back).reason == "device_rejected"


def test_em_mini_full_status_from_the_capture():
    status = g4_result("shellyemminig4", "Shelly.GetStatus")
    assert capabilities_from_status(EM, status) == {"power_meter": {"watts": 0.0, "energy_total_wh": 0.0}}
    loaded = copy.deepcopy(status)
    loaded["em1:0"]["act_power"], loaded["em1data:0"]["total_act_energy"] = 850, 1234.5
    result = capabilities_from_status(EM, loaded)
    assert result == {"power_meter": {"watts": 850.0, "energy_total_wh": 1234.5}}
    assert type(result["power_meter"]["watts"]) is float


def test_em_mini_each_component_completes_the_other():
    status = copy.deepcopy(g4_result("shellyemminig4", "Shelly.GetStatus"))
    status["em1data:0"]["total_act_energy"] = 500.0
    status, changed = apply_notify_status(EM, status, {"em1:0": {"act_power": 850.0, "voltage": 224.0}})
    assert changed == {"power_meter": {"watts": 850.0, "energy_total_wh": 500.0}}
    status, changed = apply_notify_status(EM, status, {"em1data:0": {"total_act_energy": 512.5}})
    assert changed == {"power_meter": {"watts": 850.0, "energy_total_wh": 512.5}}


def test_em_mini_notifications_of_the_capture():
    status = g4_result("shellyemminig4", "Shelly.GetStatus")
    touched = 0
    for _, params in g4_status_notifications("shellyemminig4"):
        status, changed = apply_notify_status(EM, status, params)
        if "em1:0" in params or "em1data:0" in params:
            assert changed == {"power_meter": {"watts": 0.0, "energy_total_wh": 0.0}}, params
            touched += 1
        else:
            assert changed == {}, params            # mqtt, sys: nothing
    assert touched > 50


def test_em_mini_voltage_current_freq_calibration_are_ignored():
    status = g4_result("shellyemminig4", "Shelly.GetStatus")
    _, changed = apply_notify_status(EM, status, {"em1:0": {"voltage": 230.0, "current": 1.2, "freq": 49.9,
                                                            "calibration": "user"}})
    assert changed == {}
    assert capabilities_touched(EM, {"em1data:0": {"total_act_ret_energy": 3.0}}) == set()


def test_em_mini_has_no_command():
    assert EM.commands == {}
    for capability in ("power_meter", "switch"):
        with pytest.raises(ValueError, match="not commandable"):
            command_call(EM, capability, {"on": True})


def test_em1_ts_comes_about_13_s_earlier_than_the_rest():
    """The rhythm at rest written in the profile: em1:0's ts is ~13.5 s before its arrival, em1data:0's is not (the
    capture's clock is ~103 s behind the devices: only the difference between the two counts)."""
    em1, em1data = [], []
    for received, params in g4_status_notifications("shellyemminig4"):
        offset = params["ts"] - received.timestamp()
        if "em1:0" in params:
            em1.append(offset)
        elif "em1data:0" in params:
            em1data.append(offset)
    gap = sorted(em1data)[len(em1data) // 2] - sorted(em1)[len(em1) // 2]
    assert 12.5 < gap < 14.5, gap
    arrivals = [r.timestamp() for r, p in g4_status_notifications("shellyemminig4") if "em1:0" in p]
    steps = sorted(b - a for a, b in zip(arrivals, arrivals[1:]))
    assert 13 <= steps[len(steps) // 2] <= 16                      # one em1:0 every ~14.4 s


def test_supported_models_lists_the_three():
    assert supported_models() == ("Shelly Plug M Gen3 (type plug: power_meter, switch); "
                                  "Shelly 1 Gen4 (type relay: heating or switch); "
                                  "Shelly EM Mini Gen4 (type energy_meter: power_meter)")


# --- Shelly BLU sensors through a bridge, from the bench capture (session D, 11 November 2026) ------------------

BLU_CAPTURE = Path(__file__).with_name("fixtures") / "blu_bridge_mqtt_capture.jsonl"
BLU_PAGES = Path(__file__).with_name("fixtures") / "blu_get_components_pages.json"
ADDR_HT, ADDR_MOTION, ADDR_DOOR = "02:00:00:00:a1:01", "02:00:00:00:a1:02", "02:00:00:00:a1:03"
MODEL_OF = {ADDR_HT: BLU_MODELS["blu_ht"], ADDR_MOTION: BLU_MODELS["blu_motion"],
            ADDR_DOOR: BLU_MODELS["blu_door_window"]}


def blu_messages() -> list[tuple[datetime, dict]]:
    out = []
    for line in BLU_CAPTURE.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        if record["topic"].endswith("/online"):
            continue
        received = datetime.strptime(record["received_at"], "%Y-%m-%dT%H:%M:%S%z").astimezone(UTC)
        out.append((received, json.loads(record["payload"])))
    return out


def blu_map() -> dict:
    pages = json.loads(BLU_PAGES.read_text(encoding="utf-8"))["pages"]
    return bthome_components([c for page in pages for c in page["components"]])


def readings_from_the_capture() -> list[tuple[str, str, dict]]:
    """(addr, capability, fields) for every bthomesensor notification of the capture, through the map."""
    components, out = blu_map(), []
    for _, message in blu_messages():
        if message["method"] != "NotifyStatus":
            continue
        for key, change in message["params"].items():
            component = components.get(key)
            if component is None or component.obj_id is None or "value" not in change:
                continue
            reading = blu_reading(MODEL_OF[component.addr], component.obj_id, change["value"])
            if reading is not None:
                out.append((component.addr, *reading))
    return out


def test_the_two_pages_of_get_components_hold_the_three_sensors():
    pages = json.loads(BLU_PAGES.read_text(encoding="utf-8"))["pages"]
    assert [(p["offset"], len(p["components"]), p["total"]) for p in pages] == [(0, 10, 13), (10, 3, 13)]
    components = blu_map()
    assert len(components) == 13
    by_addr = {}
    for c in components.values():
        by_addr.setdefault(c.addr, set()).add(c.obj_id)
    assert by_addr == {ADDR_HT: {None, 1, 46, 69}, ADDR_MOTION: {None, 1, 33, 100}, ADDR_DOOR: {None, 1, 45, 63, 100}}
    # the Door/Window's open sensor is on the second page
    assert components["bthomesensor:207"].addr == ADDR_DOOR and components["bthomesensor:207"].obj_id == 45
    assert "bthomesensor:207" in {c["key"] for c in pages[1]["components"]}


def test_the_capture_gives_the_four_capabilities():
    readings = readings_from_the_capture()
    seen = {(addr, cap) for addr, cap, _ in readings}
    assert seen == {(ADDR_HT, "temperature"), (ADDR_HT, "humidity"), (ADDR_MOTION, "motion"), (ADDR_DOOR, "contact")}
    temps = [f["celsius"] for a, c, f in readings if c == "temperature"]
    assert temps[0] == 27.9 and all(isinstance(t, float) and 15 < t < 35 for t in temps)
    assert all(isinstance(f["percent"], float) and 0 <= f["percent"] <= 100 for _, c, f in readings if c == "humidity")


def test_motion_and_contact_are_booleans_in_the_order_of_the_capture():
    readings = readings_from_the_capture()
    motion = [f["detected"] for a, c, f in readings if c == "motion"]
    contact = [f["open"] for a, c, f in readings if c == "contact"]
    assert all(isinstance(v, bool) for v in motion + contact)
    assert motion[:4] == [False, True, False, True]
    # the window opened and closed, also 4 s apart (1794396993 open, 1794396997 closed, 1794397001 open)
    assert contact[:9] == [True, False, True, False, True, False, True, False, True]


def test_rotation_light_level_battery_and_unknown_objects_are_ignored():
    door, motion = BLU_MODELS["blu_door_window"], BLU_MODELS["blu_motion"]
    assert BTHOME_IGNORED == {1, 63, 100}
    assert blu_reading(door, 63, 36.5) is None                 # rotation, degrees
    assert blu_reading(door, 100, 1) is None                   # light level 0-2
    assert blu_reading(motion, 100, 2) is None
    assert blu_reading(motion, 1, 100) is None                 # battery: from bthomedevice
    assert blu_reading(motion, 0x2E, 50) is None               # humidity on a Motion: not its object
    assert blu_reading(door, 250, 1) is None                   # unknown
    # the capture's rotation and light notifications give nothing
    components = blu_map()
    ignored = [(k, ch) for _, m in blu_messages() if m["method"] == "NotifyStatus"
               for k, ch in m["params"].items() if k in components and components[k].obj_id in (63, 100)]
    assert len(ignored) > 10
    assert all(blu_reading(MODEL_OF[components[k].addr], components[k].obj_id, ch["value"]) is None
               for k, ch in ignored)


def test_wrong_types_and_null_give_no_reading():
    ht, door = BLU_MODELS["blu_ht"], BLU_MODELS["blu_door_window"]
    assert blu_reading(ht, 69, None) is None                    # no packet yet
    assert blu_reading(ht, 69, True) is None and blu_reading(ht, 69, "21.5") is None
    assert blu_reading(door, 45, 1) is None                     # not a boolean
    assert blu_reading(ht, 69, 21) == ("temperature", {"celsius": 21.0})


def test_component_events_of_the_capture():
    targets = [t for _, m in blu_messages() if m["method"] == "NotifyEvent"
               for t in component_event_targets(m["params"])]
    assert targets[:4] == ["bthomedevice:200", "bthomesensor:200", "bthomesensor:201", "bthomesensor:202"]
    assert "bthomesensor:209" in targets
    other = {"events": [{"component": "sys", "event": "component_added", "target": "boolean:200"},
                        {"component": "bthome", "event": "device_discovered"}]}
    assert component_event_targets(other) == []


def test_mac_and_last_updated_ts():
    assert normalize_mac("02:00:00:00:A1:01") == ADDR_HT
    assert normalize_mac("02:00:00:00:a1:01,p") == ADDR_HT        # as the ble component lists it
    assert normalize_mac("02:00:00:00:a1") is None and normalize_mac(None) is None
    assert normalize_mac("02:00:00:00:a1:zz") is None
    received = datetime.fromtimestamp(1794394038, UTC)
    assert bthome_ts(1794394038, received) == received
    assert bthome_ts(None, received) is None and bthome_ts(0, received) is None
    assert bthome_ts(1794394038 - 3600, received) == received     # beyond the trusted skew: our reception


def test_never_heard_components_of_the_real_answer_give_nothing():
    """bthomesensor value null and last_updated_ts 0, bthomedevice all null: no packet time, no reading."""
    never = json.loads(BLU_PAGES.read_text(encoding="utf-8"))["never_heard"]
    received = datetime.fromtimestamp(1794397100, UTC)
    components = bthome_components([
        {"key": "bthomedevice:201", "status": never["bthomedevice"],
         "config": {"id": 201, "addr": ADDR_MOTION, "name": None, "meta": {"ui": {"view": "regular"}}},
         "attrs": {"model_id": 19}},
        {"key": "bthomesensor:204", "status": never["bthomesensor"],
         "config": {"id": 204, "addr": ADDR_MOTION, "name": None, "obj_id": 33, "idx": 0, "meta": None}}])
    device, sensor = components["bthomedevice:201"], components["bthomesensor:204"]
    assert sensor.last_updated_ts == 0 and device.last_updated_ts is None
    assert bthome_ts(sensor.last_updated_ts, received) is None and bthome_ts(device.last_updated_ts, received) is None
    assert blu_reading(BLU_MODELS["blu_motion"], sensor.obj_id, sensor.status["value"]) is None
