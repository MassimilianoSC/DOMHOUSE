"""A fake MQTT broker and client for the tests of transport/mqtt.py: no network, no aiomqtt.

FakeBroker keeps the retained messages, delivers what is published to the clients whose subscriptions match (MQTT
wildcards + and #), and plays the devices: device_publish() sends what a Shelly would send, and an RPC published on
<prefix>/<shelly_id>/rpc is answered by `responder` (by default from the bench capture, see capture_responder).
FakeMqttClient has the shape of aiomqtt.Client that MqttTransport uses: an async context manager with subscribe,
publish and a `messages` iterator that raises FakeMqttError when the broker drops the connection.
"""
import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

CAPTURE = Path(__file__).with_name("fixtures") / "plugmg3_mqtt_capture.jsonl"
_DROP = object()


class FakeMqttError(Exception):
    """Stands for aiomqtt.MqttError."""


@dataclass(frozen=True)
class FakeMessage:
    topic: str
    payload: bytes
    retain: bool = False


def load_capture(session: str | None = None) -> list[dict]:
    lines = [json.loads(line) for line in CAPTURE.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [line for line in lines if session is None or line["session"] == session]


def topic_matches(pattern: str, topic: str) -> bool:
    p, t = pattern.split("/"), topic.split("/")
    for i, level in enumerate(p):
        if level == "#":
            return True
        if i >= len(t) or (level != "+" and level != t[i]):
            return False
    return len(p) == len(t)


def capture_answers(session: str | None = "A") -> list[tuple[str, dict | None, dict]]:
    """(method, params, answer) for each RPC of the capture that got an answer. A request is a line on
    <prefix>/<shelly_id>/rpc; its answer is the next line of the same session with the same id on an answer topic."""
    lines = load_capture(session)
    answers = []
    for i, line in enumerate(lines):
        parts = line["topic"].split("/")
        if len(parts) != 3 or parts[2] != "rpc":
            continue
        request = json.loads(line["payload"])
        for later in lines[i + 1:]:
            if later["session"] != line["session"] or not later["topic"].endswith("connector/rpc"):
                continue
            answer = json.loads(later["payload"])
            if answer.get("id") == request["id"]:
                answers.append((request["method"], request.get("params"), answer))
                break
    return answers


def capture_responder(session: str | None = "A") -> Callable[[str, dict], dict | None]:
    """Answers a request with the capture's answer to the same method and params, carrying the request's id.

    The capture was taken when the requests still used src = "dev/connector", so its answers sit on
    "dev/connector/rpc". The broker below publishes each answer on "<src of the request>/rpc", i.e. on
    "<prefix>/<shelly_id>/connector/rpc": the topic is rewritten, the answer's body is the captured one."""
    answers = capture_answers(session)

    def respond(shelly_id: str, request: dict) -> dict | None:
        for method, params, answer in answers:
            if method == request.get("method") and params == request.get("params"):
                return answer | {"id": request["id"], "src": shelly_id, "dst": request.get("src")}
        return None
    return respond


class FakeMqttClient:
    def __init__(self, broker: "FakeBroker", client_id: str):
        self.broker = broker
        self.client_id = client_id
        self.subscriptions: list[tuple[str, int]] = []
        self.is_connected = False
        self._queue: asyncio.Queue = asyncio.Queue()

    async def __aenter__(self) -> "FakeMqttClient":
        if self.broker.refuse_connects > 0:
            self.broker.refuse_connects -= 1
            raise FakeMqttError("connection refused")
        self.is_connected = True
        self.broker.clients.append(self)
        return self

    async def __aexit__(self, *exc) -> None:
        self.is_connected = False
        if self in self.broker.clients:
            self.broker.clients.remove(self)

    async def subscribe(self, topic: str, qos: int = 0) -> None:
        self.subscriptions.append((topic, qos))
        for retained_topic, payload in self.broker.retained.items():   # as a broker does at subscription
            if topic_matches(topic, retained_topic):
                self._queue.put_nowait(FakeMessage(retained_topic, payload, retain=True))

    async def publish(self, topic: str, payload: str, qos: int = 0) -> None:
        if not self.is_connected:
            raise FakeMqttError("not connected")
        self.broker.client_published(topic, payload, qos)

    @property
    def messages(self):
        return self._messages()

    async def _messages(self):
        while True:
            item = await self._queue.get()
            if item is _DROP:
                raise FakeMqttError("Disconnected during message iteration")
            yield item

    def deliver(self, topic: str, payload: bytes, retain: bool = False) -> None:
        if any(topic_matches(pattern, topic) for pattern, _ in self.subscriptions):
            self._queue.put_nowait(FakeMessage(topic, payload, retain))

    def drop(self) -> None:
        self._queue.put_nowait(_DROP)


class FakeBroker:
    def __init__(self, responder: Callable[[str, dict], dict | None] | None = None):
        self.responder = responder if responder is not None else capture_responder("A")
        self.retained: dict[str, bytes] = {}
        self.clients: list[FakeMqttClient] = []
        self.published: list[tuple[str, str, int]] = []        # what the clients published: (topic, payload, qos)
        self.connects: list[tuple[object, str]] = []           # (settings, client_id) of every attempt
        self.refuse_connects = 0                               # the next N connection attempts fail

    def factory(self, settings, client_id: str) -> FakeMqttClient:
        self.connects.append((settings, client_id))
        return FakeMqttClient(self, client_id)

    def device_publish(self, topic: str, payload: str | bytes, retain: bool = False) -> None:
        data = payload.encode("utf-8") if isinstance(payload, str) else payload
        if retain:
            self.retained[topic] = data
        for client in list(self.clients):
            client.deliver(topic, data, retain)

    def set_online(self, prefix: str, shelly_id: str, online: bool) -> None:
        self.device_publish(f"{prefix}/{shelly_id}/online", "true" if online else "false", retain=True)

    def client_published(self, topic: str, payload: str, qos: int) -> None:
        self.published.append((topic, payload, qos))
        parts = topic.split("/")
        if len(parts) != 3 or parts[2] != "rpc":
            return
        request = json.loads(payload)
        answer = self.responder(parts[1], request)
        if answer is not None:
            self.device_publish(f"{request['src']}/rpc", json.dumps(answer))

    def drop(self) -> None:
        """The connection to every client drops (broker restarted, network gone)."""
        for client in list(self.clients):
            client.drop()

    def requests(self) -> list[dict]:
        return [json.loads(payload) for topic, payload, _ in self.published if topic.endswith("/rpc")]
