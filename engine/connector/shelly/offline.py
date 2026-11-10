"""Offline thresholds per device type (connector.md §2.6): after how many seconds of silence a device is offline.

A powered relay keeps a live connection and 120 s of silence means it is gone; a battery BLU sensor only sends a
Bluetooth beacon every 60 s (H&T, Door/Window) or every 900 s (Motion, normal mode), relayed by a bridging relay, so
one threshold for everything is either wrong for the relays or wrong for the Motion. The defaults per type live in
offline_thresholds.toml next to this module; an apartment can point SHELLY_OFFLINE_THRESHOLDS_PATH at its own copy.

Precedence for a device, highest first:
  1. `shelly.offline_after_s` in the device's catalog entry (the single-device override);
  2. the value of its `shelly.type` in the thresholds file;
  3. SHELLY_OFFLINE_AFTER_S (the process-wide value of §5);
  4. 120 s, the contract's default.

Pure Python, no I/O beyond reading the file once; errors name the field, never its value (connector.md §2.7).
"""
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
    if value <= 0:
        raise OfflineThresholdsError(f"{where}: offline threshold must be greater than zero")
    return float(value)


@dataclass(frozen=True)
class OfflineThresholds:
    by_type: Mapping[str, float]
    fallback_s: float = CONTRACT_DEFAULT_S     # for a device without a type: SHELLY_OFFLINE_AFTER_S or 120
    source: Path | None = field(default=None, compare=False)

    def for_device(self, shelly: Mapping | None, device_id: str | None = None) -> float:
        """The threshold for one catalog entry's `shelly:` section (connector.md §5)."""
        where = f"catalog device {device_id}" if device_id else "catalog device"
        shelly = shelly or {}
        if "offline_after_s" in shelly:
            return _seconds(shelly["offline_after_s"], f"{where}: shelly.offline_after_s")
        kind = shelly.get("type")
        if kind is None:
            return self.fallback_s
        if not isinstance(kind, str) or kind not in self.by_type:
            raise OfflineThresholdsError(f"{where}: shelly.type is not one of the known device types")
        return self.by_type[kind]


def load_thresholds(env: Mapping[str, str] | None = None, path: Path | None = None) -> OfflineThresholds:
    """Reads the per-type defaults (from `path`, else SHELLY_OFFLINE_THRESHOLDS_PATH, else the file in this package)
    and the process-wide fallback from SHELLY_OFFLINE_AFTER_S. Called once, from make_connector."""
    env = env or {}
    source = path or (Path(env[ENV_PATH]) if env.get(ENV_PATH) else DEFAULT_PATH)
    try:
        with source.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        raise OfflineThresholdsError("offline thresholds file not found") from None
    except tomllib.TOMLDecodeError:
        raise OfflineThresholdsError("offline thresholds file is not valid TOML") from None

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
