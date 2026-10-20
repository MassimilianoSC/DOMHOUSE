"""The connector interface (per-youssouf/connector.md, §2). Ours: a change here is agreed with o1, and an incompatible
one raises CONNECTOR_API_VERSION together with tests/test_interface.py.

The engine decides (rules, limits, modes, the boiler's thermostat, "confirmation: power"); the connector only reports
the devices and brings them to the state the engine asks for. All of it asyncio; datetimes are timezone-aware, UTC.
"""
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

CONNECTOR_API_VERSION = "1"

# the eight capabilities of contract/openapi.yaml, components.schemas.Capabilities
CAPABILITIES = ("switch", "power_meter", "climate", "heating", "temperature", "humidity", "contact", "motion")
COMMANDABLE = ("switch", "climate", "heating")          # components.schemas.Command
LINKS = {"confirmation_device_id": ("climate", "power_meter"),   # link key -> (capability of the device, of the target)
         "sensor_device_id": ("heating", "temperature")}


@dataclass(frozen=True)
class Room:
    room_id: str
    name: str


@dataclass(frozen=True)
class DeviceInfo:
    device_id: str
    label: str
    room_id: str
    online: bool
    last_seen: datetime | None
    capabilities: dict[str, dict]
    # never part of GET /devices: which power meter confirms a split, which sensor regulates a boiler (§2.2)
    links: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectorCommand:
    command_id: str
    correlation_id: str
    device_id: str
    capability: str          # one of COMMANDABLE
    target: dict             # the COMPLETE state to reach, not the contract's action (§2.4)
    deadline: datetime       # the result must come before this moment


@dataclass(frozen=True)
class CommandResult:
    outcome: Literal["confirmed", "delivered", "failed"]
    reason: Literal["device_offline", "device_rejected", "internal_error"] | None = None
    state: dict | None = None      # with "confirmed": the state the device reported
    detail: str | None = None      # for the logs, short English; never secrets


@dataclass(frozen=True)
class StateChange:
    device_id: str
    kind: Literal["state", "online"]
    ts: datetime
    capability: str | None = None   # kind="state"
    state: dict | None = None       # kind="state": the capability's device-reported fields
    online: bool | None = None      # kind="online"


@dataclass(frozen=True)
class ConnectorConfig:
    """What make_connector(config) receives, once, at the engine's start (§2.7): never the engine's API key nor its
    other settings. env holds only the connector's own environment variables, those named <NAME>_* for CONNECTOR=<name>
    (e.g. SHELLY_OFFLINE_AFTER_S for shelly), with their full names."""
    apartment_id: str
    data_dir: Path           # the apartment's data (DATA_DIR, by default /data/<apartment_id>)
    catalog_path: Path       # the devices' catalog (CATALOG_PATH, by default <data_dir>/catalog.yaml)
    env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ConnectorStatus:
    up: bool
    connected_devices: int
    last_event_at: datetime | None
    detail: str | None = None


class Connector(Protocol):
    api_version: str

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def rooms(self) -> list[Room]: ...
    def devices(self) -> list[DeviceInfo]: ...
    async def execute(self, cmd: ConnectorCommand, on_progress: Callable[[str], None]) -> CommandResult: ...
    def changes(self) -> AsyncIterator[StateChange]: ...
    def status(self) -> ConnectorStatus: ...
