"""Offline thresholds per device type (connector.md §2.6): after how many seconds of silence a device is offline.

A powered relay keeps a live connection and 120 s of silence means it is gone; a battery BLU sensor only sends a
Bluetooth beacon every 60 s (H&T, Door/Window) or every 900 s (Motion, normal mode), relayed by a bridging relay, so
one threshold for everything is either wrong for the relays or wrong for the Motion. The defaults per type live in
offline_thresholds.toml next to this module; an apartment can point SHELLY_OFFLINE_THRESHOLDS_PATH at its own copy.

Every device in the catalog must have a `shelly.type`, one of DEVICE_TYPES: a device without it is refused, never
given a guessed threshold. Precedence for a device, highest first:
  1. `shelly.offline_after_s` in the device's catalog entry (the single-device override);
  2. the value of its `shelly.type` in the thresholds file.
SHELLY_OFFLINE_AFTER_S (connector.md §5) is still read and checked, so a wrong value is still caught at start, but
with a type on every device it no longer decides any threshold (fallback_s).

Pure Python, no I/O beyond reading the file once; errors name the field, never its value (connector.md §2.7), and
never chain the original exception: what reaches the engine's log is our message alone.
A threshold must be a finite number of seconds greater than zero: nan or inf would leave a device online forever.
is_offline(silence_s, threshold_s) is the rule of §2.6, «silence beyond offline_after_s»: strictly beyond.
"""
import math
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

CONTRACT_DEFAULT_S = 120.0
ENV_DEFAULT = "SHELLY_OFFLINE_AFTER_S"
ENV_PATH = "SHELLY_OFFLINE_THRESHOLDS_PATH"
DEFAULT_PATH = Path(__file__).with_name("offline_thresholds.toml")

# the device types the catalog may name in `shelly.type`; the file must give a value for each
DEVICE_TYPES = ("relay", "plug", "energy_meter", "ir_blaster", "blu_ht", "blu_door_window", "blu_motion")


class OfflineThresholdsError(ValueError):
    """The thresholds file or a catalog entry is wrong; the message names the place, not the value."""


def _seconds(value, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OfflineThresholdsError(f"{where}: offline threshold must be a number of seconds")
    try:
        seconds = float(value)
    except OverflowError:                       # an integer too large for a float
        seconds = math.inf
    if not math.isfinite(seconds):              # nan, inf, -inf: the device would never go offline
        raise OfflineThresholdsError(f"{where}: offline threshold must be a finite number of seconds")
    if seconds <= 0:
        raise OfflineThresholdsError(f"{where}: offline threshold must be greater than zero")
    return seconds


def is_offline(silence_s: float, threshold_s: float) -> bool:
    """connector.md §2.6: a device is offline when its silence goes beyond its threshold, strictly; a silence equal to
    the threshold is still online."""
    return silence_s > threshold_s


@dataclass(frozen=True)
class OfflineThresholds:
    by_type: Mapping[str, float]
    # SHELLY_OFFLINE_AFTER_S or 120: checked at start, not applied to any device (every device has a type)
    fallback_s: float = CONTRACT_DEFAULT_S
    source: Path | None = field(default=None, compare=False)

    def for_device(self, shelly: Mapping | None, device_id: str | None = None) -> float:
        """The threshold for one catalog entry's `shelly:` section (connector.md §5)."""
        where = f"catalog device {device_id}" if device_id else "catalog device"
        if shelly is None:
            shelly = {}
        if not isinstance(shelly, Mapping):
            raise OfflineThresholdsError(f"{where}: the shelly section must be a mapping")
        kind = shelly.get("type")
        if kind is None:
            raise OfflineThresholdsError(f"{where}: shelly.type is missing")
        if not isinstance(kind, str) or kind not in self.by_type:
            raise OfflineThresholdsError(f"{where}: shelly.type is not one of the known device types")
        if "offline_after_s" in shelly:
            return _seconds(shelly["offline_after_s"], f"{where}: shelly.offline_after_s")
        return self.by_type[kind]


def load_thresholds(env: Mapping[str, str] | None = None, path: Path | None = None) -> OfflineThresholds:
    """Reads the per-type defaults (from `path`, else SHELLY_OFFLINE_THRESHOLDS_PATH, else the file in this package)
    and checks SHELLY_OFFLINE_AFTER_S (kept in fallback_s, applied to no device). Called once, from make_connector."""
    env = env or {}
    from_env = path is None and bool(env.get(ENV_PATH))
    source = path or (Path(env[ENV_PATH]) if from_env else DEFAULT_PATH)
    # which setting pointed at the file, never the path itself
    origin = f" ({ENV_PATH})" if from_env else ""
    if source.is_dir():
        raise OfflineThresholdsError(f"offline thresholds path is a folder, not a file{origin}")
    try:
        with source.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        raise OfflineThresholdsError(f"offline thresholds file not found{origin}") from None
    except UnicodeDecodeError:
        raise OfflineThresholdsError(f"offline thresholds file is not valid UTF-8{origin}") from None
    except tomllib.TOMLDecodeError:
        raise OfflineThresholdsError(f"offline thresholds file is not valid TOML{origin}") from None
    except OSError:
        raise OfflineThresholdsError(f"offline thresholds file cannot be read{origin}") from None

    types = data.get("types")
    if not isinstance(types, dict):
        raise OfflineThresholdsError("offline thresholds file: missing [types] table")
    by_type: dict[str, float] = {}
    for kind, value in types.items():
        if kind not in DEVICE_TYPES:
            raise OfflineThresholdsError(f"offline thresholds file: unknown device type in [types]: {kind}")
        by_type[kind] = _seconds(value, f"offline thresholds file: types.{kind}")
    missing = [kind for kind in DEVICE_TYPES if kind not in by_type]
    if missing:
        raise OfflineThresholdsError(f"offline thresholds file: [types] lacks {', '.join(missing)}")

    fallback = CONTRACT_DEFAULT_S
    if env.get(ENV_DEFAULT):
        try:
            fallback = _seconds(float(env[ENV_DEFAULT]), ENV_DEFAULT)
        except ValueError as exc:
            if isinstance(exc, OfflineThresholdsError):
                raise
            raise OfflineThresholdsError(f"{ENV_DEFAULT}: offline threshold must be a number of seconds") from None
    return OfflineThresholds(by_type=by_type, fallback_s=fallback, source=source)
