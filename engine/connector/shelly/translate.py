"""Contract capabilities <-> Shelly RPC and notifications (connector.md §2.3-§2.6, §3): pure functions, no I/O.

Everything model-specific is a row of PROFILES, keyed by the `app` field of Shelly.GetDeviceInfo: where each
device-reported field of a capability lives in the device's status, and which RPC brings a commandable capability to
its target. Adding a model means adding a row, not new code.

What this module reports is only what connector.md §2.3 calls «dispositivo»: switch.on, heating.on (the boiler's
relay, §2.3: never the «riscaldamento abilitato» the app sees, which is the engine's), power_meter.watts and the raw
cumulative counter power_meter.energy_total_wh (Wh, as the device counts it, also when it restarts from zero after a
reboot: the engine recognises the drop). The fields of one capability may live in different components of the status
(the EM Mini's watts in em1:0, its counter in em1data:0): every FieldSource names its own. kwh_today and the hourly
consumption are the engine's, never computed here. Numbers come out as float; a field of the wrong type leaves its
capability out rather than guessing.
"""
import copy
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from engine.connector.interface import CommandResult

from .transport.base import RpcError, TransportOffline, TransportTimeout

MAX_CLOCK_SKEW_S = 300.0   # a device clock further than this from our reception time is not trusted (§2.2)


class UnknownModel(ValueError):
    """The device's app has no row in PROFILES. The message never repeats the value (connector.md §2.7)."""


@dataclass(frozen=True)
class FieldSource:
    component: str                    # key template in the status, "{ch}" is the channel: "switch:{ch}"
    path: tuple[str, ...]             # inside the component: ("aenergy", "total")
    kind: Literal["bool", "float"]


@dataclass(frozen=True)
class CommandSpec:
    method: str                       # the RPC that sets the state: "Switch.Set"
    read_back: str                    # the RPC that reads it back: "Switch.GetStatus"
    target_field: str                 # the field of ConnectorCommand.target: "on"
    param: str                        # the RPC parameter it becomes: "on"
    read_back_field: str              # where the reached value is in the read back: "output"


@dataclass(frozen=True)
class ModelProfile:
    app: str
    device_type: str                                         # the catalog's shelly.type it serves (offline.DEVICE_TYPES)
    label: str                                               # for the messages: "Shelly Plug M Gen3"
    capabilities: Mapping[str, Mapping[str, FieldSource]]   # capability -> field -> where it lives
    commands: Mapping[str, CommandSpec]                      # commandable capability -> how to command it
    # groups of capabilities of which the catalog lists at most one: the Shelly 1's relay is a switch OR a boiler
    exclusive: tuple[frozenset[str], ...] = ()

    def covers(self, device_type: str, capabilities) -> bool:
        """This model can be the device the catalog describes: same type, every capability listed has a row, and at
        most one of each exclusive group."""
        listed = set(capabilities)
        return (device_type == self.device_type and listed <= set(self.capabilities)
                and all(len(listed & group) <= 1 for group in self.exclusive))

    def offer(self) -> str:
        """For the messages: "power_meter, switch"; an exclusive group reads "heating or switch"."""
        grouped = set().union(*self.exclusive) if self.exclusive else set()
        parts = [c for c in self.capabilities if c not in grouped]
        parts += [" or ".join(sorted(group)) for group in self.exclusive]
        return ", ".join(sorted(parts))


_SWITCH_COMMAND = CommandSpec(method="Switch.Set", read_back="Switch.GetStatus", target_field="on", param="on",
                              read_back_field="output")

PROFILES: Mapping[str, ModelProfile] = {
    # Shelly Plug M Gen3 (S3PL-30110EU): one relay with metering, everything in the switch:0 component
    "PlugMG3": ModelProfile(
        app="PlugMG3",
        device_type="plug",
        label="Shelly Plug M Gen3",
        capabilities={
            "switch": {"on": FieldSource("switch:{ch}", ("output",), "bool")},
            "power_meter": {"watts": FieldSource("switch:{ch}", ("apower",), "float"),
                            "energy_total_wh": FieldSource("switch:{ch}", ("aenergy", "total"), "float")},
        },
        commands={"switch": _SWITCH_COMMAND},
    ),
    # Shelly 1 Gen4 (S4SW-001X16EU, firmware 2.0.3, bench of 10 November 2026): one relay, NO metering (its switch:0
    # has output, source, counts and temperature, never apower/aenergy). The relay is either a switch or the
    # boiler's thermostat contact (heating, connector.md §2.3-§2.4): the device reports only "on" = the relay, the
    # engine sends {"on": bool}, the same Switch.Set and read back as a switch. setpoint_min/max come from the
    # catalog; links.sensor_device_id is optional (without it the engine logs «boiler without sensor» and the relay
    # follows only a person's command, unregulated). The catalog lists switch OR heating, never both.
    # Ignored: input:0, and the NotifyStatus a minute with only switch:0.counts (no field of any capability).
    "S1G4": ModelProfile(
        app="S1G4",
        device_type="relay",
        label="Shelly 1 Gen4",
        capabilities={
            "switch": {"on": FieldSource("switch:{ch}", ("output",), "bool")},
            "heating": {"on": FieldSource("switch:{ch}", ("output",), "bool")},
        },
        commands={"switch": _SWITCH_COMMAND, "heating": _SWITCH_COMMAND},
        exclusive=(frozenset({"switch", "heating"}),),
    ),
    # Shelly EM Mini Gen4 (S4EM-001PXCEU16, firmware 1.7.0, bench of 10 November 2026): a meter only, no command.
    # watts <- em1:{ch}.act_power (W); energy_total_wh <- em1data:{ch}.total_act_energy, in Wh («Total active energy,
    # Wh», Shelly API docs, EM1Data.GetStatus, read on 11 November 2026). Two components for one capability: a
    # NotifyStatus with em1:0 alone takes the counter from the last known status, and the other way round.
    # Ignored: em1:0's voltage, current, freq and calibration; the NotifyEvent "data" of em1data:0 (the minute's
    # records saved to flash); total_act_ret_energy. On its return online it sends NO NotifyFullStatus (the Shelly 1
    # and the Plug do): the snapshot is the connector's Shelly.GetStatus.
    # Timing, for the «confirmation: power» of a split (connector-v2.md §2.5: a change of watts in changes() within
    # 2 s). AT REST (the bench capture, steady load) em1:0 comes every ~14.4 s and its ts is ~13.5 s before
    # its arrival (the device's other notifications are not). When the power CHANGES the device notifies at once,
    # out of that cycle, then about every second: measured on 11 November with a real load (~40 W) switched by a
    # relay, the first change of watts reached the engine 50 ms after the relay's change. §2.5 is met. Nothing is
    # compensated here: StateChange.ts is the device's ts, as for any notification.
    "MiniEMG4": ModelProfile(
        app="MiniEMG4",
        device_type="energy_meter",
        label="Shelly EM Mini Gen4",
        capabilities={
            "power_meter": {"watts": FieldSource("em1:{ch}", ("act_power",), "float"),
                            "energy_total_wh": FieldSource("em1data:{ch}", ("total_act_energy",), "float")},
        },
        commands={},
    ),
}


def profile_for(app: str) -> ModelProfile:
    try:
        return PROFILES[app]
    except (KeyError, TypeError):
        raise UnknownModel("unsupported Shelly app") from None


def profile_for_catalog(device_type: str, capabilities) -> ModelProfile | None:
    """The profile that can serve a catalog entry (its shelly.type and its capabilities), or None: checked at start,
    so a device no model supports is refused before anything connects. With several candidates the first row wins;
    Shelly.GetDeviceInfo then tells which model is really there (ShellyConnector checks it with covers())."""
    return next((p for p in PROFILES.values() if p.covers(device_type, capabilities)), None)


def supported_models() -> str:
    """For the catalog's error message: "Shelly Plug M Gen3 (type plug: power_meter, switch); Shelly 1 Gen4 (type
    relay: heating or switch); ..."."""
    return "; ".join(f"{p.label} (type {p.device_type}: {p.offer()})" for p in PROFILES.values())


# --- status -> capabilities --------------------------------------------------------------------------------------

def _read(status: Mapping, source: FieldSource, channel: int):
    node = status.get(source.component.format(ch=channel))
    for key in source.path:
        if not isinstance(node, Mapping) or key not in node:
            return None
        node = node[key]
    if source.kind == "bool":
        return node if isinstance(node, bool) else None
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        return None
    return float(node)


def _capability(profile: ModelProfile, capability: str, status: Mapping, channel: int) -> dict | None:
    values = {}
    for field_name, source in profile.capabilities[capability].items():
        value = _read(status, source, channel)
        if value is None:
            return None
        values[field_name] = value
    return values


def capabilities_from_status(profile: ModelProfile, status: Mapping, channel: int = 0) -> dict[str, dict]:
    """A full status (Shelly.GetStatus, or the params of NotifyFullStatus) -> the device fields of each capability,
    e.g. {"switch": {"on": True}, "power_meter": {"watts": 12.2, "energy_total_wh": 0.0}}. A capability appears only
    when all of its fields are there with the right type; components the profile does not name are ignored."""
    result = {}
    for capability in profile.capabilities:
        values = _capability(profile, capability, status, channel)
        if values is not None:
            result[capability] = values
    return result


def merge_partial(last_status: Mapping, partial: Mapping) -> dict:
    """The fields a NotifyStatus carries, merged recursively onto the last known status. Returns a new dict and leaves
    both arguments untouched; the top-level "ts" of the notification's params is not part of the status."""
    merged = copy.deepcopy(dict(last_status))

    def merge(into: dict, changes: Mapping) -> None:
        for key, value in changes.items():
            if isinstance(value, Mapping) and isinstance(into.get(key), dict):
                merge(into[key], value)
            else:
                into[key] = copy.deepcopy(value)

    merge(merged, {k: v for k, v in partial.items() if k != "ts"})
    return merged


def _present(partial: Mapping, source: FieldSource, channel: int) -> bool:
    node = partial.get(source.component.format(ch=channel))
    for key in source.path:
        if not isinstance(node, Mapping) or key not in node:
            return False
        node = node[key]
    return True


def capabilities_touched(profile: ModelProfile, partial: Mapping, channel: int = 0) -> set[str]:
    """The capabilities with at least one field in a partial notification."""
    return {capability for capability, fields in profile.capabilities.items()
            if any(_present(partial, source, channel) for source in fields.values())}


def apply_notify_status(profile: ModelProfile, last_status: Mapping, partial: Mapping,
                        channel: int = 0) -> tuple[dict, dict[str, dict]]:
    """A NotifyStatus (only the changed fields) on top of the last known status (connector.md §2.6) -> (the new full
    status, {each touched capability: all of its device fields}). A change of apower alone yields power_meter only,
    with energy_total_wh taken from the last known status."""
    status = merge_partial(last_status, partial)
    changed = {}
    for capability in capabilities_touched(profile, partial, channel):
        values = _capability(profile, capability, status, channel)
        if values is not None:
            changed[capability] = values
    return status, changed


def bthome_ts(last_updated_ts, received_at: datetime, max_skew_s: float = MAX_CLOCK_SKEW_S,
              bridge_offset_s: float | None = None) -> datetime | None:
    """When a BLU packet arrived at its bridge, on OUR clock: last_updated_ts (Unix seconds), or None when the
    component has received no packet yet (null or 0).

    NOT the rule of notification_ts. last_updated_ts is the time the bridge received the packet, written by the
    bridge's clock: a value in the PAST is kept as it is, however far (a sensor silent for hours really was silent for
    hours, and its age against the threshold is counted from there).
      - bridge_offset_s known (the bridge's clock minus ours, ShellyConnector keeps it per bridge): the packet's time
        is last_updated_ts - bridge_offset_s, never later than received_at. So a bridge 400 s behind does not make
        a sensor that sends every minute look 400 s old.
      - unknown (None): our clock is the bridge's; only a value in the FUTURE beyond max_skew_s is not trusted and
        becomes our reception time."""
    if isinstance(last_updated_ts, bool) or not isinstance(last_updated_ts, (int, float)) or last_updated_ts <= 0:
        return None
    try:
        packet_at = datetime.fromtimestamp(last_updated_ts - (bridge_offset_s or 0.0), UTC)
    except (OverflowError, OSError, ValueError):
        return received_at
    if bridge_offset_s is not None:
        return min(packet_at, received_at)
    if (packet_at - received_at).total_seconds() > max_skew_s:
        return received_at
    return packet_at


def notification_ts(params: Mapping, received_at: datetime, max_skew_s: float = MAX_CLOCK_SKEW_S) -> datetime:
    """When a change happened (StateChange.ts, connector.md §2.2): the device's "ts" (Unix seconds) when present and
    within max_skew_s of our reception time, otherwise the reception time."""
    ts = params.get("ts")
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return received_at
    try:
        device_time = datetime.fromtimestamp(ts, UTC)
    except (OverflowError, OSError, ValueError):
        return received_at
    if abs((device_time - received_at).total_seconds()) > max_skew_s:
        return received_at
    return device_time


# --- Shelly BLU sensors, through a bridge ------------------------------------------------------------------------
#
# A BLU sensor (Bluetooth, battery) never talks to us: a powered Shelly of the catalog, its bridge, receives its
# packets and exposes it as dynamic components (bench of 11 November 2026, Shelly 1 Gen4 firmware 2.0.3; the Plug M
# Gen3 and the EM Mini Gen4 do the same):
#   - bthomedevice:<n>  config.addr = the sensor's MAC; status: battery, packet_id, rssi, last_updated_ts;
#   - bthomesensor:<n>  one per measure; config: addr, obj_id (the BTHome object), idx; status: value, last_updated_ts.
# <n> is chosen by the bridge at every pairing and is NOT stable: a measure is addr + obj_id, never the number.
# Shelly.GetStatus does not carry them ("bthome": {} only); Shelly.GetComponents {"dynamic_only": true} does, 10 per
# page. The NotifyStatus of the bridge carry bthomesensor:<n> {value, last_updated_ts} (only when the value changes)
# or bthomedevice:<n> {packet_id, rssi, last_updated_ts[, battery]} (at most once a minute, the last packet already
# received): no addr, no obj_id, so the connector keeps the map number -> (addr, obj_id) read with GetComponents.
# Before the first packet (real answer, tests/fixtures/blu_get_components_pages.json, never_heard): the bthomedevice
# has rssi, battery, packet_id and last_updated_ts null; a bthomesensor has value null and last_updated_ts 0, not
# null. bthome_ts reads both null and 0 as «never heard»: 0 is no packet of 1 January 1970.
# A sensor the bridge cannot decode (bench of 11 November 2026, afternoon: Motion and Door/Window on the EM Mini Gen4 firmware
# 1.7.0, tests/fixtures/blu_parse_failed.json): its bthomedevice carries "errors": ["parse_failed"] and still moves
# last_updated_ts, while it has no bthomesensor at all. "errors" is in a NotifyStatus only when it changes (the
# bthomedevice report a minute later repeats last_updated_ts and rssi without it, while GetComponents still shows it):
# BthomeComponent.updated keeps it until a notification says otherwise. Only the bthomedevice was seen with errors;
# BthomeComponent.errors reads it on any bthome component.

BTHOME_DEVICE, BTHOME_SENSOR = "bthomedevice", "bthomesensor"
# BTHome objects that are not a field of the contract: battery (a level, never a StateChange: ShellyConnector takes it
# from both bthomedevice.battery and this obj_id 1 bthomesensor, the last that arrived counts, battery.py), rotation
# in degrees (Door/Window), illuminance level 0-2 (Motion, Door/Window). Never a StateChange, never a warning.
BTHOME_IGNORED = frozenset({1, 63, 100})


@dataclass(frozen=True)
class BluModel:
    device_type: str                                         # the catalog's shelly.type (offline.DEVICE_TYPES)
    label: str                                               # for the messages
    model_id: int                                            # shelly_mfdata.model_id of the discovery, for reference
    objects: Mapping[int, tuple[str, str, Literal["bool", "float"]]]   # obj_id -> (capability, field, kind)

    def capabilities(self) -> set[str]:
        return {capability for capability, _, _ in self.objects.values()}

    def covers(self, capabilities) -> bool:
        """The catalog may list any non-empty part of what the sensor measures: an H&T may be temperature only."""
        listed = set(capabilities)
        return bool(listed) and listed <= self.capabilities()

    def obj_id_of(self, capability: str) -> int | None:
        return next((obj for obj, (cap, _, _) in self.objects.items() if cap == capability), None)


BLU_MODELS: Mapping[str, BluModel] = {
    # Shelly BLU H&T (SBHT-203C): a packet every ~60 s, nothing sent early on a change
    "blu_ht": BluModel("blu_ht", "Shelly BLU H&T", 17,
                       {69: ("temperature", "celsius", "float"), 46: ("humidity", "percent", "float")}),
    # Shelly BLU Motion (SBMO-103Z): true at once, false ~60 s after the last movement, at rest a packet every ~900 s
    "blu_motion": BluModel("blu_motion", "Shelly BLU Motion", 19, {33: ("motion", "detected", "bool")}),
    # Shelly BLU Door/Window (SBDW-103C): open and closed at once, at rest a packet every ~300 s
    "blu_door_window": BluModel("blu_door_window", "Shelly BLU Door/Window", 20, {45: ("contact", "open", "bool")}),
}


def blu_model_for(device_type) -> BluModel | None:
    return BLU_MODELS.get(device_type) if isinstance(device_type, str) else None


def supported_blu() -> str:
    """For the catalog's error message: "Shelly BLU H&T (type blu_ht: humidity, temperature); ..."."""
    return "; ".join(f"{m.label} (type {m.device_type}: {', '.join(sorted(m.capabilities()))})"
                     for m in BLU_MODELS.values())


def normalize_mac(addr) -> str | None:
    """A Bluetooth MAC as "aa:bb:cc:dd:ee:ff" (lower case), or None. Accepts the ",p" / ",1" suffix of the ble
    component's lists; anything else is not a MAC."""
    if not isinstance(addr, str):
        return None
    mac = addr.split(",", 1)[0].strip().lower()
    parts = mac.split(":")
    if len(parts) != 6 or not all(len(p) == 2 and all(c in "0123456789abcdef" for c in p) for p in parts):
        return None
    return mac


@dataclass(frozen=True)
class BthomeComponent:
    """One bthomedevice/bthomesensor of a bridge, as GetComponents gave it and the notifications updated it."""
    key: str                          # "bthomesensor:207"
    addr: str                         # normalized MAC of the sensor
    obj_id: int | None                # None for the bthomedevice
    status: Mapping                   # the last known status: value / battery, last_updated_ts, ...

    @property
    def last_updated_ts(self):
        return self.status.get("last_updated_ts")

    @property
    def errors(self) -> tuple[str, ...]:
        """The bridge's errors for this component ("parse_failed": it cannot decode the sensor's packets), () when
        none. A component with errors carries no packet and no value the connector may use."""
        errors = self.status.get("errors")
        if not isinstance(errors, list):
            return ()
        return tuple(e if isinstance(e, str) else "unknown" for e in errors)

    def updated(self, change: Mapping) -> "BthomeComponent":
        return BthomeComponent(self.key, self.addr, self.obj_id, {**self.status, **copy.deepcopy(dict(change))})


def bthome_components(components) -> dict[str, BthomeComponent]:
    """The "components" of Shelly.GetComponents (any page) -> {key: BthomeComponent} for the bthome ones with a valid
    addr (and, for a sensor, an integer obj_id). Other dynamic components and malformed entries are left out."""
    found: dict[str, BthomeComponent] = {}
    if not isinstance(components, list):
        return found
    for entry in components:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("key"), str):
            continue
        key, config = entry["key"], entry.get("config")
        kind = key.split(":", 1)[0]
        if kind not in (BTHOME_DEVICE, BTHOME_SENSOR) or not isinstance(config, Mapping):
            continue
        addr = normalize_mac(config.get("addr"))
        if addr is None:
            continue
        obj_id = None
        if kind == BTHOME_SENSOR:
            obj_id = config.get("obj_id")
            if isinstance(obj_id, bool) or not isinstance(obj_id, int):
                continue
        status = entry.get("status")
        status = copy.deepcopy(dict(status)) if isinstance(status, Mapping) else {}
        found[key] = BthomeComponent(key, addr, obj_id, status)
    return found


def blu_reading(model: BluModel, obj_id, value) -> tuple[str, dict] | None:
    """A bthomesensor value -> (capability, its device fields), e.g. (69, 21.5) -> ("temperature", {"celsius": 21.5}).
    None for the ignored objects (BTHOME_IGNORED), for objects this model does not have, for null (no packet yet) and
    for a value of the wrong type."""
    if obj_id in BTHOME_IGNORED or obj_id not in model.objects:
        return None
    capability, field_name, kind = model.objects[obj_id]
    if kind == "bool":
        return (capability, {field_name: value}) if isinstance(value, bool) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return capability, {field_name: float(value)}


def component_event_targets(params: Mapping) -> list[str]:
    """The bthome components a NotifyEvent of the bridge says were added or removed (sys component_added /
    component_removed, target "bthomedevice:<n>" or "bthomesensor:<n>")."""
    events = params.get("events") if isinstance(params, Mapping) else None
    targets = []
    for event in events if isinstance(events, list) else []:
        if (isinstance(event, Mapping) and event.get("component") == "sys"
                and event.get("event") in ("component_added", "component_removed")
                and isinstance(event.get("target"), str)
                and event["target"].split(":", 1)[0] in (BTHOME_DEVICE, BTHOME_SENSOR)):
            targets.append(event["target"])
    return targets


# --- commands ----------------------------------------------------------------------------------------------------

def _command_spec(profile: ModelProfile, capability: str) -> CommandSpec:
    try:
        return profile.commands[capability]
    except KeyError:
        raise ValueError(f"capability {capability} is not commandable on this Shelly model") from None


def command_call(profile: ModelProfile, capability: str, target: Mapping, channel: int = 0) -> tuple[str, dict]:
    """The RPC that brings the capability to its target state: ("Switch.Set", {"id": 0, "on": False})."""
    spec = _command_spec(profile, capability)
    value = target.get(spec.target_field)
    if not isinstance(value, bool):
        raise ValueError(f"target.{spec.target_field} must be a boolean")
    return spec.method, {"id": channel, spec.param: value}


def read_back_call(profile: ModelProfile, capability: str, channel: int = 0) -> tuple[str, dict]:
    """The RPC that reads back what the device reached: ("Switch.GetStatus", {"id": 0})."""
    return _command_spec(profile, capability).read_back, {"id": channel}


def confirmed_result(profile: ModelProfile, capability: str, target: Mapping, read_back: Mapping) -> CommandResult:
    """The outcome of a command from the read back that followed it. The set RPC's own answer (Switch.Set's "was_on",
    the state BEFORE the command) is for the logs only: what counts is the state read back. Reached -> confirmed with
    that state; not reached (e.g. the plug's overpower protection) -> failed/device_rejected."""
    spec = _command_spec(profile, capability)
    reached = read_back.get(spec.read_back_field)
    if not isinstance(reached, bool):
        return CommandResult(outcome="failed", reason="internal_error", detail="read back without the output state")
    if reached != target.get(spec.target_field):
        return CommandResult(outcome="failed", reason="device_rejected", detail="output did not reach target")
    return CommandResult(outcome="confirmed", state={spec.target_field: reached})


def error_result(exc: Exception, prefix: str = "") -> CommandResult:
    """A transport error -> the failed outcome of connector.md §2.5. detail is short English and never carries what
    the device said (an RPC error keeps its code only); prefix tells where it happened ("read back failed: ").
    Only Exception is handled: asyncio.CancelledError, a BaseException, must reach the engine and never becomes an
    outcome."""
    if not isinstance(exc, Exception):
        raise TypeError("error_result handles Exception only")
    if isinstance(exc, RpcError):
        reason, detail = "device_rejected", str(exc)
    elif isinstance(exc, TransportOffline):
        reason, detail = "device_offline", "device offline"
    elif isinstance(exc, TransportTimeout):
        reason, detail = "internal_error", "transport timeout"
    else:
        reason, detail = "internal_error", type(exc).__name__
    return CommandResult(outcome="failed", reason=reason, detail=prefix + detail)
