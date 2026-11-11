"""The connector: the part of the engine that talks to the devices (engine/connector/connector-v2.md)."""
from .interface import (CONNECTOR_API_VERSION, CommandResult, Connector, ConnectorCommand, ConnectorConfig,
                        ConnectorStatus, DeviceInfo, Room, StateChange)

__all__ = ["CONNECTOR_API_VERSION", "CommandResult", "Connector", "ConnectorCommand", "ConnectorConfig",
           "ConnectorStatus", "DeviceInfo", "Room", "StateChange"]
