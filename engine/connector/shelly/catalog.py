"""The apartment's catalog for the Shelly connector (connector.md §5): read once by make_connector, checked whole.

The format (YAML, one file per apartment, /data/<apartment_id>/catalog.yaml by default):

    rooms:
      - {room_id: camera, name: Camera}
    devices:
      - device_id: dev-presa-camera          # stable, the id the app sees
        label: Presa stufetta                # Italian; the manager can rename it in the app (the engine keeps that)
        room_id: camera
        capabilities: {switch: {}, power_meter: {}}   # the catalog's values where the contract wants them
                                                      # (climate/heating: setpoint_min, setpoint_max, confirmation)
        links: {}                            # optional: confirmation_device_id, sensor_device_id (connector.md §2.2)
        shelly:
          id: shellyplugmg3-000000000001     # the shelly_id, the topic level after <apartment_id>/
          type: plug                         # required, one of offline.DEVICE_TYPES
          channel: 0                         # optional, 0 by default
          offline_after_s: 120               # optional, overrides the threshold of the type

A Shelly BLU sensor (battery, Bluetooth) has no shelly_id of its own: a powered Shelly of the catalog receives its
packets and is its bridge (translate.py, «Shelly BLU sensors»). Its shelly section names the sensor and the bridge:

        shelly:
          addr: 02:00:00:00:00:01            # the sensor's Bluetooth MAC, any case (compared in lower case)
          bridge: shelly1g4-000000000002     # the shelly.id of the bridge, a device of this catalog
          type: blu_ht                       # blu_ht, blu_motion or blu_door_window (translate.BLU_MODELS)
          offline_after_s: 200               # optional, as above

No id and no channel: the sensor is not a topic of the broker and has one channel. One bridge per sensor; a MAC
appears once in the catalog. The capabilities are what the sensor measures: blu_ht temperature and/or humidity,
blu_motion motion, blu_door_window contact. A section with addr or bridge is a BLU sensor, one without is a Shelly.

What is checked, all at start: the structure; room and device ids unique; every room_id exists; capabilities among the
eight of interface.CAPABILITIES; links only with the keys of interface.LINKS, to devices of the catalog that have the
right capability; shelly ids unique and one MQTT topic level each; the offline threshold of every device
(offline.OfflineThresholds.for_device); a Shelly model (translate.PROFILES) that serves the device's type and
capabilities. Unknown keys are refused, so a typo or a secret pasted by mistake never passes silently: the catalog
holds no secrets.

Errors (CatalogError) name the device and the field, never the value found (connector.md §2.7): the engine copies the
message into its log. They never chain the original exception either.

yaml is imported only by load_catalog: parse_catalog works on a mapping, so the package and the tests' harness import
without PyYAML.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from engine.connector.interface import CAPABILITIES, LINKS, Room

from .offline import OfflineThresholds, OfflineThresholdsError
from .translate import (BluModel, ModelProfile, blu_model_for, normalize_mac, profile_for_catalog, supported_blu,
                        supported_models)

ROOM_KEYS = {"room_id", "name"}
DEVICE_KEYS = {"device_id", "label", "room_id", "capabilities", "links", "shelly"}
SHELLY_KEYS = {"id", "type", "channel", "offline_after_s"}
BLU_SHELLY_KEYS = {"addr", "bridge", "type", "offline_after_s"}


class CatalogError(ValueError):
    """The catalog is missing or wrong. The message names the place (device, field), never the value."""


@dataclass(frozen=True)
class BluSensor:
    addr: str                               # the sensor's MAC, lower case
    bridge: str                             # the shelly_id of the bridge, a device of the catalog
    model: BluModel = field(repr=False)


@dataclass(frozen=True)
class CatalogDevice:
    device_id: str
    label: str
    room_id: str
    capabilities: Mapping[str, Mapping]     # capability -> the catalog's values ({} when it has none)
    links: Mapping[str, str]
    shelly_id: str | None                   # None for a BLU sensor (blu)
    device_type: str
    channel: int
    offline_after_s: float
    profile: ModelProfile | None = field(repr=False)    # None for a BLU sensor (blu)
    blu: BluSensor | None = None            # a BLU sensor: its MAC and its bridge


@dataclass(frozen=True)
class Catalog:
    rooms: tuple[Room, ...]
    devices: tuple[CatalogDevice, ...]

    def by_shelly_id(self) -> dict[str, CatalogDevice]:
        """The Shelly devices (the BLU sensors have no shelly_id)."""
        return {d.shelly_id: d for d in self.devices if d.shelly_id is not None}

    def by_device_id(self) -> dict[str, CatalogDevice]:
        return {d.device_id: d for d in self.devices}


# --- reading -----------------------------------------------------------------------------------------------------

def load_catalog(path: Path, thresholds: OfflineThresholds) -> Catalog:
    """Reads and checks the catalog file. The messages never carry the path's content; the path itself is the
    engine's setting (CATALOG_PATH), not repeated either."""
    import yaml      # here only (PyYAML): see the module's docstring

    path = Path(path)
    if path.is_dir():
        raise CatalogError("catalog path is a folder, not a file")
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise CatalogError("catalog file not found") from None
    except UnicodeDecodeError:
        raise CatalogError("catalog file is not valid UTF-8") from None
    except OSError:
        raise CatalogError("catalog file cannot be read") from None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark is not None else ""
        raise CatalogError(f"catalog file is not valid YAML{where}") from None
    return parse_catalog(data, thresholds)


# --- checking ----------------------------------------------------------------------------------------------------

def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unknown_keys(entry: Mapping, allowed: set[str], where: str) -> None:
    extra = [k for k in entry if k not in allowed]
    if extra:
        # the key names are the catalog's structure, not values; still, at most a few and only if they are short words
        shown = ", ".join(sorted(str(k) for k in extra if isinstance(k, str) and k.isidentifier() and len(k) <= 32)[:5])
        raise CatalogError(f"{where}: unknown key{'s' if len(extra) > 1 else ''}" + (f" ({shown})" if shown else ""))


def _rooms(data) -> tuple[Room, ...]:
    if not isinstance(data, list) or not data:
        raise CatalogError("catalog: rooms must be a non-empty list")
    rooms, seen = [], set()
    for n, entry in enumerate(data, 1):
        where = f"catalog room #{n}"
        if not isinstance(entry, Mapping):
            raise CatalogError(f"{where}: must be a mapping with room_id and name")
        room_id = entry.get("room_id")
        if not _text(room_id):
            raise CatalogError(f"{where}: room_id is missing or not a text")
        where = f"catalog room {room_id}"
        _unknown_keys(entry, ROOM_KEYS, where)
        if room_id in seen:
            raise CatalogError(f"{where}: room_id is repeated")
        if not _text(entry.get("name")):
            raise CatalogError(f"{where}: name is missing or not a text")
        seen.add(room_id)
        rooms.append(Room(room_id=room_id, name=entry["name"]))
    return tuple(rooms)


def _capabilities(raw, where: str) -> dict[str, dict]:
    if not isinstance(raw, Mapping) or not raw:
        raise CatalogError(f"{where}: capabilities must be a non-empty mapping")
    caps = {}
    for cap, values in raw.items():
        if cap not in CAPABILITIES:
            raise CatalogError(f"{where}: capabilities has a capability that is not one of the eight of the contract")
        if values is None:
            values = {}
        if not isinstance(values, Mapping):
            raise CatalogError(f"{where}: capabilities.{cap} must be a mapping")
        caps[cap] = dict(values)
    return caps


def _channel(shelly: Mapping, where: str) -> int:
    channel = shelly.get("channel", 0)
    if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 255:
        raise CatalogError(f"{where}: shelly.channel must be an integer between 0 and 255")
    return channel


def _shelly_id(shelly: Mapping, where: str) -> str:
    shelly_id = shelly.get("id")
    if not _text(shelly_id):
        raise CatalogError(f"{where}: shelly.id is missing or not a text")
    if shelly_id != shelly_id.strip() or any(c in shelly_id for c in "/+#") or not shelly_id.isprintable():
        raise CatalogError(f"{where}: shelly.id must be one MQTT topic level (no spaces, /, + or #)")
    return shelly_id


def _device(entry, n: int, rooms: set[str], thresholds: OfflineThresholds) -> CatalogDevice:
    if not isinstance(entry, Mapping):
        raise CatalogError(f"catalog device #{n}: must be a mapping")
    device_id = entry.get("device_id")
    if not _text(device_id):
        raise CatalogError(f"catalog device #{n}: device_id is missing or not a text")
    where = f"catalog device {device_id}"
    _unknown_keys(entry, DEVICE_KEYS, where)
    if not _text(entry.get("label")):
        raise CatalogError(f"{where}: label is missing or not a text")
    room_id = entry.get("room_id")
    if not _text(room_id):
        raise CatalogError(f"{where}: room_id is missing or not a text")
    if room_id not in rooms:
        raise CatalogError(f"{where}: room_id is not a room of the catalog")
    caps = _capabilities(entry.get("capabilities"), where)
    links = entry.get("links") or {}
    if not isinstance(links, Mapping):
        raise CatalogError(f"{where}: links must be a mapping")
    for key, target in links.items():
        if key not in LINKS:
            raise CatalogError(f"{where}: links has a key that is not confirmation_device_id or sensor_device_id")
        if not _text(target):
            raise CatalogError(f"{where}: links.{key} must be a device_id")
        if LINKS[key][0] not in caps:
            raise CatalogError(f"{where}: links.{key} needs the capability {LINKS[key][0]} on this device")
    shelly = entry.get("shelly")
    if not isinstance(shelly, Mapping):
        raise CatalogError(f"{where}: shelly section is missing or not a mapping")
    if "addr" in shelly or "bridge" in shelly:
        return _blu_device(entry, where, room_id, caps, links, shelly, thresholds)
    _unknown_keys(shelly, SHELLY_KEYS, f"{where}: shelly")
    shelly_id = _shelly_id(shelly, where)
    channel = _channel(shelly, where)
    try:
        threshold = thresholds.for_device(shelly, device_id)
    except OfflineThresholdsError as exc:
        raise CatalogError(str(exc)) from None
    profile = profile_for_catalog(shelly["type"], caps)
    if profile is None:
        raise CatalogError(f"{where}: shelly.type and capabilities are not supported by any Shelly model "
                           f"(supported today: {supported_models()})")
    return CatalogDevice(device_id=device_id, label=entry["label"], room_id=room_id, capabilities=caps,
                         links=dict(links), shelly_id=shelly_id, device_type=shelly["type"], channel=channel,
                         offline_after_s=threshold, profile=profile)


def _blu_device(entry: Mapping, where: str, room_id: str, caps: dict, links: Mapping, shelly: Mapping,
                thresholds: OfflineThresholds) -> CatalogDevice:
    """A BLU sensor's entry (see the module's docstring); its bridge is checked against the whole catalog later."""
    _unknown_keys(shelly, BLU_SHELLY_KEYS, f"{where}: shelly")
    raw_addr = shelly.get("addr")
    addr = normalize_mac(raw_addr)
    if addr is None or "," in raw_addr:
        raise CatalogError(f"{where}: shelly.addr is missing or not a Bluetooth MAC (aa:bb:cc:dd:ee:ff)")
    if not _text(shelly.get("bridge")):
        raise CatalogError(f"{where}: shelly.bridge is missing or not a text")
    try:
        threshold = thresholds.for_device(shelly, entry["device_id"])
    except OfflineThresholdsError as exc:
        raise CatalogError(str(exc)) from None
    model = blu_model_for(shelly["type"])
    if model is None:
        raise CatalogError(f"{where}: shelly.type is not a BLU sensor type (supported today: {supported_blu()})")
    if not model.covers(caps):
        raise CatalogError(f"{where}: capabilities are not measured by this BLU sensor "
                           f"(supported today: {supported_blu()})")
    return CatalogDevice(device_id=entry["device_id"], label=entry["label"], room_id=room_id, capabilities=caps,
                         links=dict(links), shelly_id=None, device_type=shelly["type"], channel=0,
                         offline_after_s=threshold, profile=None,
                         blu=BluSensor(addr=addr, bridge=shelly["bridge"], model=model))


def parse_catalog(data, thresholds: OfflineThresholds) -> Catalog:
    """The checks of the module's docstring on an already-read catalog (a mapping)."""
    if not isinstance(data, Mapping):
        raise CatalogError("catalog: the file must be a mapping with rooms and devices")
    _unknown_keys(data, {"rooms", "devices"}, "catalog")
    rooms = _rooms(data.get("rooms"))
    raw_devices = data.get("devices")
    if not isinstance(raw_devices, list) or not raw_devices:
        raise CatalogError("catalog: devices must be a non-empty list")
    room_ids = {r.room_id for r in rooms}
    devices: list[CatalogDevice] = []
    device_ids: set[str] = set()
    shelly_ids: dict[str, str] = {}
    addrs: dict[str, str] = {}
    for n, entry in enumerate(raw_devices, 1):
        if isinstance(entry, Mapping) and _text(entry.get("device_id")) and entry["device_id"] in device_ids:
            raise CatalogError(f"catalog device {entry['device_id']}: device_id is repeated")
        device = _device(entry, n, room_ids, thresholds)
        if device.blu is not None:
            if device.blu.addr in addrs:
                raise CatalogError(f"catalog device {device.device_id}: shelly.addr is the same as device "
                                   f"{addrs[device.blu.addr]}")
            addrs[device.blu.addr] = device.device_id
            device_ids.add(device.device_id)
            devices.append(device)
            continue
        if device.shelly_id in shelly_ids:
            raise CatalogError(f"catalog device {device.device_id}: shelly.id is the same as device "
                               f"{shelly_ids[device.shelly_id]}")
        device_ids.add(device.device_id)
        shelly_ids[device.shelly_id] = device.device_id
        devices.append(device)
    for device in devices:
        if device.blu is not None and device.blu.bridge not in shelly_ids:
            raise CatalogError(f"catalog device {device.device_id}: shelly.bridge is not the shelly.id of a device "
                               f"of the catalog")
    by_id = {d.device_id: d for d in devices}
    for device in devices:
        for key, target in device.links.items():
            linked = by_id.get(target)
            if linked is None:
                raise CatalogError(f"catalog device {device.device_id}: links.{key} is not a device of the catalog")
            if linked is device:
                raise CatalogError(f"catalog device {device.device_id}: links.{key} points to the device itself")
            if LINKS[key][1] not in linked.capabilities:
                raise CatalogError(f"catalog device {device.device_id}: links.{key} points to a device without "
                                   f"{LINKS[key][1]}")
    return Catalog(rooms=rooms, devices=tuple(devices))
