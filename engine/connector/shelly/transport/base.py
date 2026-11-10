"""The transport behind the Shelly connector (connector.md §3): how RPCs and notifications travel, kept in one module.

Whether the devices reach us over an outbound WebSocket, MQTT or the Shelly cloud is decided elsewhere (PR #1). The
rest of the connector only sees this Protocol, so swapping the transport changes one module and one setting, and the
connector's tests run on tests/fake_transport.py.

One deliberate difference from the Protocol printed in connector.md §3: notifications() also carries ConnectionEvent,
in the same stream as the Notification items. The connector must emit, for one device and in this order, offline,
online, then a full snapshot (§2.6); a separate signal for the connection could overtake or lag the notifications of
the same device, a single stream cannot. connected() stays, for status() and for a quick check before a command.
"""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, Union

NotificationMethod = Literal["NotifyStatus", "NotifyFullStatus", "NotifyEvent"]
NOTIFICATION_METHODS = ("NotifyStatus", "NotifyFullStatus", "NotifyEvent")


def _require_utc(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")


@dataclass(frozen=True)
class Notification:
    """A JSON-RPC notification a Shelly device sent: NotifyStatus carries only the fields that changed,
    NotifyFullStatus the whole status, NotifyEvent an event (button pressed, ...)."""
    method: NotificationMethod
    shelly_id: str
    params: dict
    received_at: datetime          # when it reached us, aware, UTC

    def __post_init__(self):
        if self.method not in NOTIFICATION_METHODS:
            raise ValueError("method must be NotifyStatus, NotifyFullStatus or NotifyEvent")
        _require_utc(self.received_at, "received_at")


@dataclass(frozen=True)
class ConnectionEvent:
    """A device's connection opened (connected=True) or closed (connected=False), in the same stream as its
    notifications, so the order offline, online, snapshot holds for each device (connector.md §2.6)."""
    shelly_id: str
    connected: bool
    received_at: datetime          # aware, UTC

    def __post_init__(self):
        _require_utc(self.received_at, "received_at")


TransportEvent = Union[Notification, ConnectionEvent]


class TransportError(Exception):
    """Base of the errors call() raises; never raised by itself."""


class TransportOffline(TransportError):
    """The device is not connected, or its connection dropped while the RPC was in flight."""


class TransportTimeout(TransportError):
    """No answer within timeout_s."""


class RpcError(TransportError):
    """The device answered the RPC with an error. str() carries the code only: the device's message may repeat the
    values we sent, and the logs must never carry them (connector.md §5)."""

    def __init__(self, code: int, message: str):
        super().__init__(code, message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"rpc error {self.code}"


class Transport(Protocol):
    @property
    def broker_connected(self) -> bool:
        """The transport itself is up (for MQTT: connected to the broker). ShellyConnector.status().up copies it."""
        ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...

    async def call(self, shelly_id: str, method: str, params: dict | None, timeout_s: float) -> dict:
        """One RPC. Raises TransportOffline, TransportTimeout or RpcError(code, message)."""
        ...

    def notifications(self) -> AsyncIterator[TransportEvent]:
        """Notification and ConnectionEvent items, in the order they happened for each device; one consumer."""
        ...

    def connected(self) -> set[str]: ...
