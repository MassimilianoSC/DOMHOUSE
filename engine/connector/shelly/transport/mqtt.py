"""The MQTT transport of the Shelly connector (connector.md §3; D-196: MQTT with a broker of ours).

Topics, all under the apartment's prefix (ConnectorConfig.apartment_id), as measured on the bench (PR #1, 10 November
2026) with a Plug M Gen3 on Mosquitto:

  <apartment_id>/<shelly_id>/rpc                the device receives the RPC requests (we publish, QoS 1)
  <apartment_id>/<shelly_id>/events/rpc         NotifyStatus / NotifyFullStatus / NotifyEvent (we subscribe, QoS 1)
  <apartment_id>/<shelly_id>/online             "true" / "false", retained; "false" is the device's last will
  <apartment_id>/<shelly_id>/connector/rpc      the answers to our RPCs (we subscribe, QoS 1)

A request is {"id", "src", "method", "params"} with src = "<apartment_id>/<shelly_id>/connector": a Shelly answers on
"<src>/rpc", with the same id and either "result" or "error": {code, message}.

Why the answer topic is per device. The broker grants each device its own prefix only (<apartment_id>/<shelly_id>/#).
With src inside that prefix a device never needs to write outside it, and no device can publish an answer, true or
false, on the topic of another one. On top of that an answer counts only if it arrives on the topic of the device we
asked, its id is among the RPCs pending for that device, and the "src" of its payload is that device.
If the broker still refuses the device the write on its answer topic (a wrong ACL), the answer never arrives and the
device stays connected: on this side that is only a TransportTimeout, and nothing tells the two cases apart.

The device is identified by the TOPIC, the part the broker's permissions control; "src" in a payload is only the
shelly_id. When the two differ the message is dropped with a warning. Invalid JSON, an unknown method or a malformed
answer are dropped too; the logs name the device and the reason, never the payload.

Connection state. ConnectionEvent travels in the notifications() stream (base.py), and connected() reflects the last
"online" value of each device, the retained ones received at subscription included. The last will "false" reaches us
up to 1.5 x the device's 60 s keep-alive after it disappears, so about 90 s.
When the connection to the broker drops: the pending RPCs fail with TransportOffline, a ConnectionEvent(connected=False)
goes out for every device that was connected (connector.md §2.6: socket closed -> offline at once), then we reconnect
with a growing wait (RECONNECT_FIRST_S doubling up to RECONNECT_MAX_S). After the reconnection the retained "online"
messages come back by themselves; the full snapshot after a return is the connector's to ask, with Shelly.GetStatus.
start() never raises because the broker is out of reach: it waits for the first attempt and leaves the retries to the
background loop (connector.md §6: a transport problem never ends the process).

Time. received_at is our reception time, UTC. The device's "ts" stays untouched in params: right after a connection a
Shelly can send NotifyFullStatus with a clock hours off, and translate.notification_ts already chooses which to trust.

Configuration from ConnectorConfig.env, SHELLY_* only (connector.md §2.7, §5): see settings_from_env. Errors name the
variable, never its value; the password never appears in logs, exceptions or repr.

aiomqtt is imported only by aiomqtt_client, the default client factory: the tests pass a fake client and run without
the library. On Windows aiomqtt needs a selector event loop (asyncio.SelectorEventLoop); on Linux nothing changes.
"""
import asyncio
import contextlib
import itertools
import json
import secrets
import ssl
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from engine import log
from engine.connector.interface import ConnectorConfig

from .base import (NOTIFICATION_METHODS, ConnectionEvent, Notification, RpcError, TransportEvent, TransportOffline,
                   TransportTimeout)

ENV_HOST = "SHELLY_MQTT_HOST"
ENV_PORT = "SHELLY_MQTT_PORT"
ENV_USERNAME = "SHELLY_MQTT_USERNAME"
ENV_PASSWORD = "SHELLY_MQTT_PASSWORD"
ENV_TLS = "SHELLY_MQTT_TLS"
ENV_CA_FILE = "SHELLY_MQTT_CA_FILE"

QOS = 1                     # the devices publish with QoS 1
KEEPALIVE_S = 60
CONNECT_TIMEOUT_S = 10.0    # one connection attempt to the broker
START_WAIT_S = 15.0         # start() waits at most this for the first attempt to end
RECONNECT_FIRST_S = 1.0
RECONNECT_MAX_S = 30.0

# one counter for the whole process: two transports of the same apartment in one process must not mix their answers
_request_ids = itertools.count(1)
_STOP = object()


def utcnow() -> datetime:
    return datetime.now(UTC)


# --- configuration -----------------------------------------------------------------------------------------------

class MqttConfigError(ValueError):
    """A SHELLY_MQTT_* variable is missing or wrong. The message names the variable, never its value."""


@dataclass(frozen=True)
class MqttSettings:
    host: str
    port: int
    username: str
    password: str = field(repr=False)
    tls: bool = False
    ca_file: Path | None = None


def _flag(raw: str | None, name: str) -> bool:
    value = (raw or "").strip().lower()
    if value in ("", "false", "0"):
        return False
    if value in ("true", "1"):
        return True
    raise MqttConfigError(f"{name} must be true or false")


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name) or ""
    if not value.strip():
        raise MqttConfigError(f"{name} is required")
    return value


def settings_from_env(env: Mapping[str, str]) -> MqttSettings:
    """SHELLY_MQTT_HOST, SHELLY_MQTT_USERNAME and SHELLY_MQTT_PASSWORD are required (the broker refuses anonymous
    clients). SHELLY_MQTT_TLS (true/false, default false: the connectors' listener is internal) and SHELLY_MQTT_PORT
    (default 1883, or 8883 with TLS) are optional, and so is SHELLY_MQTT_CA_FILE (with TLS only: a CA other than the
    system's, e.g. a lab certificate)."""
    host = _required(env, ENV_HOST).strip()
    tls = _flag(env.get(ENV_TLS), ENV_TLS)
    raw_port = (env.get(ENV_PORT) or "").strip()
    if raw_port:
        try:
            port = int(raw_port)
        except ValueError:
            raise MqttConfigError(f"{ENV_PORT} must be an integer between 1 and 65535") from None
        if not 1 <= port <= 65535:
            raise MqttConfigError(f"{ENV_PORT} must be an integer between 1 and 65535")
    else:
        port = 8883 if tls else 1883
    username = _required(env, ENV_USERNAME)
    password = _required(env, ENV_PASSWORD)
    ca_file = None
    raw_ca = (env.get(ENV_CA_FILE) or "").strip()
    if raw_ca:
        if not tls:
            raise MqttConfigError(f"{ENV_CA_FILE} needs {ENV_TLS}=true")
        ca_file = Path(raw_ca)
        if not ca_file.is_file():
            raise MqttConfigError(f"{ENV_CA_FILE} is not a readable file")
    return MqttSettings(host=host, port=port, username=username, password=password, tls=tls, ca_file=ca_file)


# --- the MQTT client ---------------------------------------------------------------------------------------------

class MqttClient(Protocol):
    """What the transport uses of aiomqtt.Client; the tests' fake client has the same shape. `messages` yields items
    with .topic (str() gives the topic) and .payload (bytes); it raises when the connection to the broker drops."""
    messages: Any

    async def subscribe(self, topic: str, qos: int = 0) -> Any: ...
    async def publish(self, topic: str, payload: str, qos: int = 0) -> Any: ...


ClientFactory = Callable[[MqttSettings, str], AbstractAsyncContextManager[MqttClient]]   # (settings, client_id)


def aiomqtt_client(settings: MqttSettings, client_id: str) -> AbstractAsyncContextManager[MqttClient]:
    """The default factory: a new aiomqtt.Client for each connection attempt. clean_session=True, because the queued
    messages of an old session would arrive after a fresh snapshot."""
    import aiomqtt      # here only: the tests and the engine's CI run without it

    tls_context = None
    if settings.tls:
        tls_context = ssl.create_default_context(cafile=str(settings.ca_file) if settings.ca_file else None)
    return aiomqtt.Client(settings.host, settings.port, username=settings.username, password=settings.password,
                          identifier=client_id, clean_session=True, keepalive=KEEPALIVE_S,
                          timeout=CONNECT_TIMEOUT_S, tls_context=tls_context)


# --- the transport -----------------------------------------------------------------------------------------------

@dataclass
class _Pending:
    shelly_id: str
    future: asyncio.Future


def _payload_text(payload: Any) -> str | None:
    if isinstance(payload, (bytes, bytearray)):
        try:
            return bytes(payload).decode("utf-8")
        except UnicodeDecodeError:
            return None
    return payload if isinstance(payload, str) else None


class MqttTransport:
    """The Transport Protocol of base.py over MQTT. client_factory, clock and sleep are for the tests."""

    def __init__(self, apartment_id: str, settings: MqttSettings, *, client_factory: ClientFactory | None = None,
                 clock: Callable[[], datetime] = utcnow,
                 sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep):
        if not isinstance(apartment_id, str) or not apartment_id or any(c in apartment_id for c in "/+#"):
            raise ValueError("apartment_id must be one MQTT topic level")
        self._apartment_id = apartment_id
        self._settings = settings
        self._factory: ClientFactory = client_factory or aiomqtt_client
        self._clock = clock
        self._sleep = sleep
        self._client_id = f"{apartment_id}-connector-{secrets.token_hex(4)}"
        self._client: MqttClient | None = None        # the live client; None while not connected to the broker
        self._online: dict[str, bool] = {}            # the last "online" value of each device seen
        self._pending: dict[int, _Pending] = {}
        self._queue: asyncio.Queue | None = None
        self._task: asyncio.Task | None = None
        self._first_attempt: asyncio.Event | None = None

    @classmethod
    def from_config(cls, config: ConnectorConfig, **kwargs) -> "MqttTransport":
        return cls(config.apartment_id, settings_from_env(config.env), **kwargs)

    def __repr__(self) -> str:
        s = self._settings
        return f"MqttTransport(apartment_id={self._apartment_id!r}, host={s.host!r}, port={s.port}, tls={s.tls})"

    # --- topics ---------------------------------------------------------------------------------------------------

    def _subscriptions(self) -> tuple[str, ...]:
        p = self._apartment_id
        return f"{p}/+/online", f"{p}/+/events/rpc", f"{p}/+/connector/rpc"

    def _route(self, topic: str) -> tuple[str | None, str | None]:
        """topic -> ("online" | "event" | "answer", shelly_id), or (None, None)."""
        parts = topic.split("/")
        if len(parts) < 3 or parts[0] != self._apartment_id or not parts[1]:
            return None, None
        tail = parts[2:]
        if tail == ["online"]:
            return "online", parts[1]
        if tail == ["events", "rpc"]:
            return "event", parts[1]
        if tail == ["connector", "rpc"]:
            return "answer", parts[1]
        return None, None

    # --- Protocol -------------------------------------------------------------------------------------------------

    @property
    def broker_connected(self) -> bool:
        return self._client is not None

    def connected(self) -> set[str]:
        return {sid for sid, online in self._online.items() if online}

    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("MqttTransport already started")
        self._queue = asyncio.Queue()
        self._first_attempt = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name=f"mqtt-transport-{self._apartment_id}")
        try:
            async with asyncio.timeout(START_WAIT_S):
                await self._first_attempt.wait()
        except TimeoutError:
            log.warn("mqtt first connection still pending", host=self._settings.host)

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._client = None
        self._online = {}
        self._fail_pending()
        if self._queue is not None:
            self._queue.put_nowait(_STOP)

    async def notifications(self) -> AsyncIterator[TransportEvent]:
        if self._queue is None:
            raise RuntimeError("MqttTransport.notifications() before start()")
        while True:
            item = await self._queue.get()
            if item is _STOP:
                return
            yield item

    async def call(self, shelly_id: str, method: str, params: dict | None, timeout_s: float) -> dict:
        client = self._client
        if client is None or not self._online.get(shelly_id):
            raise TransportOffline()
        request_id = next(_request_ids)
        request = {"id": request_id, "src": f"{self._apartment_id}/{shelly_id}/connector", "method": method}
        if params is not None:
            request["params"] = params
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = _Pending(shelly_id, future)
        try:
            async with asyncio.timeout(timeout_s):
                try:
                    await client.publish(f"{self._apartment_id}/{shelly_id}/rpc",
                                         json.dumps(request, separators=(",", ":")), qos=QOS)
                except Exception:
                    raise TransportOffline() from None
                return await future
        except TimeoutError:
            raise TransportTimeout() from None
        finally:
            self._pending.pop(request_id, None)

    # --- the connection loop --------------------------------------------------------------------------------------

    async def _run(self) -> None:
        delay = RECONNECT_FIRST_S
        while True:
            reached = False
            try:
                async with self._factory(self._settings, self._client_id) as client:
                    for topic in self._subscriptions():
                        await client.subscribe(topic, qos=QOS)
                    self._client, reached = client, True
                    delay = RECONNECT_FIRST_S
                    log.info("mqtt connected", host=self._settings.host, port=self._settings.port)
                    self._first_attempt.set()
                    async for message in client.messages:
                        self._dispatch(str(message.topic), message.payload)
                raise ConnectionError("message stream ended")
            except asyncio.CancelledError:
                raise
            except Exception as exc:          # what aiomqtt raises is MqttError, an Exception; never the password
                log.warn("mqtt connection lost" if reached else "mqtt connect failed",
                         host=self._settings.host, port=self._settings.port, error_type=type(exc).__name__)
            self._broker_lost()
            self._first_attempt.set()
            await self._sleep(delay)
            delay = min(delay * 2, RECONNECT_MAX_S)

    def _broker_lost(self) -> None:
        self._client = None
        self._fail_pending()
        now = self._clock()
        for shelly_id in sorted(self.connected()):
            self._online[shelly_id] = False
            self._put(ConnectionEvent(shelly_id=shelly_id, connected=False, received_at=now))

    def _fail_pending(self, shelly_id: str | None = None) -> None:
        for pending in list(self._pending.values()):
            if (shelly_id is None or pending.shelly_id == shelly_id) and not pending.future.done():
                pending.future.set_exception(TransportOffline())

    def _put(self, item: TransportEvent) -> None:
        if self._queue is not None:
            self._queue.put_nowait(item)

    # --- incoming messages ----------------------------------------------------------------------------------------

    def _dispatch(self, topic: str, payload: Any) -> None:
        try:
            self._handle(topic, payload)
        except Exception as exc:              # one bad message never drops the connection
            log.error("mqtt message handling failed", error_type=type(exc).__name__)

    def _handle(self, topic: str, payload: Any) -> None:
        received_at = self._clock()
        kind, shelly_id = self._route(topic)
        if kind is None:
            log.warn("mqtt message on unexpected topic dropped")
            return
        text = _payload_text(payload)
        if kind == "online":
            value = {"true": True, "false": False}.get((text or "").strip())
            if value is None:
                log.warn("mqtt online payload not valid", shelly_id=shelly_id)
                return
            self._set_online(shelly_id, value, received_at)
            return
        try:
            message = json.loads(text) if text is not None else None
        except ValueError:
            message = None
        if not isinstance(message, dict):
            log.warn("mqtt payload not valid json", shelly_id=shelly_id, topic_kind=kind)
            return
        if message.get("src") != shelly_id:
            log.warn("mqtt src does not match topic", shelly_id=shelly_id, topic_kind=kind)
            return
        if kind == "event":
            self._notification(shelly_id, message, received_at)
        else:
            self._answer(shelly_id, message)

    def _set_online(self, shelly_id: str, online: bool, received_at: datetime) -> None:
        if self._online.get(shelly_id) == online:
            return
        self._online[shelly_id] = online
        if not online:
            self._fail_pending(shelly_id)
        self._put(ConnectionEvent(shelly_id=shelly_id, connected=online, received_at=received_at))

    def _notification(self, shelly_id: str, message: dict, received_at: datetime) -> None:
        method, params = message.get("method"), message.get("params")
        if method not in NOTIFICATION_METHODS:
            log.warn("mqtt notification method unknown", shelly_id=shelly_id)
            return
        if not isinstance(params, dict):
            log.warn("mqtt notification without params", shelly_id=shelly_id)
            return
        self._put(Notification(method=method, shelly_id=shelly_id, params=params, received_at=received_at))

    def _answer(self, shelly_id: str, message: dict) -> None:
        request_id = message.get("id")
        valid_id = isinstance(request_id, int) and not isinstance(request_id, bool)
        pending = self._pending.get(request_id) if valid_id else None
        if pending is None or pending.shelly_id != shelly_id or pending.future.done():
            log.warn("mqtt rpc answer dropped", shelly_id=shelly_id, reason="unknown or late id")
            return
        if isinstance(message.get("error"), dict):
            error = message["error"]
            code = error.get("code")
            text = error.get("message")
            pending.future.set_exception(RpcError(code if isinstance(code, int) and not isinstance(code, bool) else -1,
                                                  text if isinstance(text, str) else ""))
        elif "result" in message and (message["result"] is None or isinstance(message["result"], dict)):
            pending.future.set_result(message["result"] or {})
        else:
            log.warn("mqtt rpc answer dropped", shelly_id=shelly_id, reason="neither result nor error")
