"""The transport's types and errors (engine/connector/shelly/transport/base.py, connector.md §3).

Run: python -m pytest engine/connector/shelly/tests -q
"""
import dataclasses
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

import pytest

from engine.connector.shelly.transport import (ConnectionEvent, Notification, RpcError, TransportError,
                                               TransportOffline, TransportTimeout)

from .fake_transport import FakeTransport

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)


@runtime_checkable
class _TransportShape(Protocol):
    # the Protocol of transport/base.py, checkable at run time for this test only
    async def start(self): ...
    async def stop(self): ...
    async def call(self, shelly_id, method, params, timeout_s): ...
    def notifications(self): ...
    def connected(self): ...


def test_notification_is_frozen_and_wants_utc():
    n = Notification(method="NotifyStatus", shelly_id="shelly-test", params={}, received_at=NOW)
    with pytest.raises(dataclasses.FrozenInstanceError):
        n.shelly_id = "other"           # type: ignore[misc]
    with pytest.raises(ValueError):
        Notification(method="NotifyStatus", shelly_id="shelly-test", params={}, received_at=datetime(2026, 11, 10))


def test_notification_method_is_one_of_three():
    for method in ("NotifyStatus", "NotifyFullStatus", "NotifyEvent"):
        Notification(method=method, shelly_id="shelly-test", params={}, received_at=NOW)
    with pytest.raises(ValueError):
        Notification(method="Switch.Set", shelly_id="shelly-test", params={}, received_at=NOW)  # type: ignore[arg-type]


def test_connection_event_is_frozen_and_wants_utc():
    e = ConnectionEvent(shelly_id="shelly-test", connected=False, received_at=NOW)
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.connected = True              # type: ignore[misc]
    with pytest.raises(ValueError):
        ConnectionEvent(shelly_id="shelly-test", connected=True, received_at=datetime(2026, 11, 10))


def test_rpc_error_keeps_code_and_message_but_prints_the_code_only():
    exc = RpcError(-103, "Argument 'on', value 42 not valid")
    assert (exc.code, exc.message) == (-103, "Argument 'on', value 42 not valid")
    assert str(exc) == "rpc error -103"
    assert "42" not in str(exc)


def test_errors_share_one_base():
    for exc in (TransportOffline(), TransportTimeout(), RpcError(-1, "x")):
        assert isinstance(exc, TransportError)


def test_fake_transport_has_the_protocol_shape():
    assert isinstance(FakeTransport(), _TransportShape)
