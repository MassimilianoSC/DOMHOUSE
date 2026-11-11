"""Contract capabilities <-> Shelly RPC and notifications (connector.md §2.3-§2.6, §3): pure functions, no I/O.

Everything model-specific is a row of PROFILES, keyed by the `app` field of Shelly.GetDeviceInfo: where each
device-reported field of a capability lives in the device's status, and which RPC brings a commandable capability to
its target. Adding a model means adding a row, not new code.

What this module reports is only what connector.md §2.3 calls «dispositivo»: switch.on, power_meter.watts and the raw
cumulative counter power_meter.energy_total_wh (Wh, as the device counts it, also when it restarts from zero after a
reboot: the engine recognises the drop). kwh_today and the hourly consumption are the engine's, never computed here.
Numbers come out as float; a field of the wrong type leaves its capability out rather than guessing.
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

    def covers(self, device_type: str, capabilities) -> bool:
        """This model can be the device the catalog describes: same type, and every capability listed has a row."""
        return device_type == self.device_type and set(capabilities) <= set(self.capabilities)


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
    # Next rows, not written yet (same shape):
    # - Shelly 1 Gen4: a relay; check with Shelly.GetStatus on the real device whether its switch:0 reports
    #   apower/aenergy before giving it a power_meter.
    # - Shelly EM Mini Gen4: a meter only, no command. Its component name (perhaps "pm1:{ch}") is NOT confirmed:
    #   verify it with Shelly.GetStatus on the real device before writing the row.
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
    """For the catalog's error message: "Shelly Plug M Gen3 (type plug: power_meter, switch)"."""
    return "; ".join(f"{p.label} (type {p.device_type}: {', '.join(sorted(p.capabilities))})"
                     for p in PROFILES.values())


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
