"""transport/mqtt.py on a fake MQTT broker fed by the bench capture (tests/fixtures/plugmg3_mqtt_capture.jsonl).

Note on the capture: it was taken when the RPC requests still used src = "dev/connector", so its answers arrive on
"dev/connector/rpc". The transport now uses src = "<prefix>/<shelly_id>/connector" and listens on
"<prefix>/+/connector/rpc"; FakeBroker (fake_mqtt.py) publishes each captured answer on "<src of the request>/rpc",
i.e. it rewrites the answer's topic and keeps the captured body.

Every test runs on asyncio.Runner(loop_factory=asyncio.SelectorEventLoop), as aiomqtt needs on Windows; no
pytest-asyncio. Run: python -m pytest engine/connector/shelly/tests -q
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import pytest

from engine import log
from engine.connector.interface import ConnectorConfig
from engine.connector.shelly.translate import MAX_CLOCK_SKEW_S, notification_ts
from engine.connector.shelly.transport.base import (ConnectionEvent, Notification, RpcError, TransportOffline,
                                                    TransportTimeout)
from engine.connector.shelly.transport.mqtt import (MqttConfigError, MqttSettings, MqttTransport, settings_from_env)

from .fake_mqtt import FakeBroker, capture_answers, capture_responder, load_capture

APT = "dev"                                  # the prefix of the lab broker, as in the capture
SID = "shellyplugmg3-a1b2c3d4e5f6"           # the capture's id (invented when it was anonymised)
SID2 = "shellyplugmg3-000000000002"
PASSWORD = "pw-never-shown-7f3a"
SETTINGS = MqttSettings(host="broker.test", port=1883, username="connector-dev", password=PASSWORD)
ENV = {"SHELLY_MQTT_HOST": "broker.test", "SHELLY_MQTT_USERNAME": "connector-dev", "SHELLY_MQTT_PASSWORD": PASSWORD}


def run(scenario):
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        return runner.run(scenario())


class Sleeps:
    """The transport's sleep: records the waits; with a gate, holds the reconnection until the test opens it."""

    def __init__(self):
        self.delays: list[float] = []
        self.gate: asyncio.Event | None = None

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)
        if self.gate is not None:
            await self.gate.wait()
        await asyncio.sleep(0)


class Clock:
    def __init__(self, now: datetime | None = None):
        self.now = now or datetime.fromisoformat("2026-11-10T11:00:00+00:00")

    def __call__(self) -> datetime:
        return self.now


async def settle() -> None:
    for _ in range(20):
        await asyncio.sleep(0)


async def drain(transport: MqttTransport) -> list:
    """What the stream holds now, without waiting for more."""
    items = []
    stream = transport.notifications()
    while True:
        try:
            items.append(await asyncio.wait_for(stream.__anext__(), timeout=0.05))
        except (asyncio.TimeoutError, StopAsyncIteration):
            return items


async def started(broker: FakeBroker, *, sleep=None, clock=None) -> MqttTransport:
    transport = MqttTransport(APT, SETTINGS, client_factory=broker.factory, sleep=sleep or Sleeps(),
                              clock=clock or Clock())
    await transport.start()
    return transport


def answer_topic(shelly_id: str) -> str:
    return f"{APT}/{shelly_id}/connector/rpc"


@pytest.fixture
def logs():
    records: list[logging.LogRecord] = []

    class Keep(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = logging.getLogger("engine")
    handler, old_level = Keep(), logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    yield records
    logger.removeHandler(handler)
    logger.setLevel(old_level)


def rendered(records) -> str:
    formatter = log.JsonFormatter()
    return "\n".join(formatter.format(r) for r in records)


# --- configuration -----------------------------------------------------------------------------------------------

def test_settings_from_env_and_their_defaults(tmp_path):
    s = settings_from_env(ENV)
    assert (s.host, s.port, s.username, s.password, s.tls, s.ca_file) == ("broker.test", 1883, "connector-dev",
                                                                         PASSWORD, False, None)
    assert settings_from_env(ENV | {"SHELLY_MQTT_TLS": "true"}).port == 8883
    assert settings_from_env(ENV | {"SHELLY_MQTT_TLS": "1", "SHELLY_MQTT_PORT": "18883"}).port == 18883
    ca = tmp_path / "ca.pem"
    ca.write_text("lab ca", encoding="utf-8")
    assert settings_from_env(ENV | {"SHELLY_MQTT_TLS": "true", "SHELLY_MQTT_CA_FILE": str(ca)}).ca_file == ca


@pytest.mark.parametrize("change, variable, bad_value", [
    ({"SHELLY_MQTT_HOST": ""}, "SHELLY_MQTT_HOST", None),
    ({"SHELLY_MQTT_PORT": "port-x9"}, "SHELLY_MQTT_PORT", "port-x9"),
    ({"SHELLY_MQTT_PORT": "70001"}, "SHELLY_MQTT_PORT", "70001"),
    ({"SHELLY_MQTT_TLS": "yes-x9"}, "SHELLY_MQTT_TLS", "yes-x9"),
    ({"SHELLY_MQTT_USERNAME": " "}, "SHELLY_MQTT_USERNAME", None),
    ({"SHELLY_MQTT_PASSWORD": ""}, "SHELLY_MQTT_PASSWORD", None),
    ({"SHELLY_MQTT_CA_FILE": "/etc/ca-x9.pem"}, "SHELLY_MQTT_CA_FILE", "ca-x9"),
    ({"SHELLY_MQTT_TLS": "true", "SHELLY_MQTT_CA_FILE": "/nowhere/ca-x9.pem"}, "SHELLY_MQTT_CA_FILE", "ca-x9"),
])
def test_config_errors_name_the_variable_never_the_value(change, variable, bad_value):
    env = {k: v for k, v in (ENV | change).items() if v}
    with pytest.raises(MqttConfigError) as info:
        settings_from_env(env)
    message = str(info.value)
    assert variable in message
    assert PASSWORD not in message
    if bad_value:
        assert bad_value not in message
    assert info.value.__cause__ is None                                   # no chained exception with the value
    assert info.value.__context__ is None or info.value.__suppress_context__


def test_password_never_in_repr_errors_or_logs(logs):
    config = ConnectorConfig(apartment_id=APT, data_dir=Path("."), catalog_path=Path("catalog.yaml"), env=ENV)
    transport = MqttTransport.from_config(config, client_factory=FakeBroker().factory)
    assert PASSWORD not in repr(settings_from_env(ENV))
    assert PASSWORD not in repr(transport) and "broker.test" in repr(transport)

    async def scenario():
        broker = FakeBroker()
        broker.refuse_connects = 1
        sleeps = Sleeps()
        sleeps.gate = asyncio.Event()
        t = await started(broker, sleep=sleeps)
        assert broker.connects[0][0].password == PASSWORD       # it does reach the client, and only the client
        await t.stop()
    run(scenario)
    assert "mqtt connect failed" in rendered(logs)
    assert PASSWORD not in rendered(logs)


def test_apartment_id_is_one_topic_level():
    for bad in ("", "dev/x", "dev+", "#"):
        with pytest.raises(ValueError):
            MqttTransport(bad, SETTINGS, client_factory=FakeBroker().factory)


# --- connection and subscriptions --------------------------------------------------------------------------------

def test_start_subscribes_to_the_three_topics_with_qos_1():
    async def scenario():
        broker = FakeBroker()
        t = await started(broker)
        (client,) = broker.clients
        assert client.subscriptions == [("dev/+/online", 1), ("dev/+/events/rpc", 1), ("dev/+/connector/rpc", 1)]
        assert t.broker_connected
        assert broker.connects[0][1].startswith("dev-connector-")
        await t.stop()
    run(scenario)


def test_start_does_not_raise_when_the_broker_is_out_of_reach(logs):
    async def scenario():
        broker = FakeBroker()
        broker.refuse_connects = 1
        sleeps = Sleeps()
        sleeps.gate = asyncio.Event()
        t = await started(broker, sleep=sleeps)
        assert not t.broker_connected and t.connected() == set()
        assert sleeps.delays == [1.0]
        sleeps.gate.set()
        await settle()
        assert t.broker_connected
        await t.stop()
    run(scenario)
    assert "mqtt connect failed" in rendered(logs)


def test_retained_online_counts_and_connected_follows_the_last_value():
    async def scenario():
        broker = FakeBroker()
        broker.set_online(APT, SID, True)                  # retained before we connect
        t = await started(broker)
        await settle()
        assert t.connected() == {SID}
        broker.set_online(APT, SID, False)
        items = await drain(t)
        assert [(type(i), i.shelly_id, i.connected) for i in items] == [(ConnectionEvent, SID, True),
                                                                       (ConnectionEvent, SID, False)]
        assert all(i.received_at.tzinfo is not None for i in items)
        assert t.connected() == set()
        await t.stop()
    run(scenario)


def test_capture_session_a_reaches_the_stream_in_order():
    async def scenario():
        broker = FakeBroker()
        t = await started(broker)
        lines = [line for line in load_capture("A") if line["topic"].endswith(("/online", "/events/rpc"))]
        for line in lines:
            broker.device_publish(line["topic"], line["payload"], retain=line["topic"].endswith("/online"))
        items = await drain(t)
        expected = [("online", line["payload"] == "true") if line["topic"].endswith("/online")
                    else ("event", json.loads(line["payload"])["method"]) for line in lines]
        got = [("online", i.connected) if isinstance(i, ConnectionEvent) else ("event", i.method) for i in items]
        assert got == expected
        assert {i.shelly_id for i in items} == {SID}
        assert items[1].params == json.loads(lines[1]["payload"])["params"]       # untouched, "ts" included
        assert ("event", "NotifyEvent") in got and got.count(("online", False)) == 2
        assert t.connected() == {SID}
        await t.stop()
    run(scenario)


def test_full_status_with_a_wrong_clock_keeps_its_ts_and_gets_our_received_at():
    async def scenario():
        clock = Clock()
        broker = FakeBroker()
        t = await started(broker, clock=clock)
        for line in load_capture("B"):
            if not line["topic"].endswith(("/online", "/events/rpc")):
                continue
            clock.now = datetime.strptime(line["received_at"], "%Y-%m-%dT%H:%M:%S%z")
            broker.device_publish(line["topic"], line["payload"], retain=line["topic"].endswith("/online"))
            await settle()
        items = await drain(t)
        (full,) = [i for i in items if isinstance(i, Notification) and i.method == "NotifyFullStatus"]
        assert full.received_at == datetime.fromisoformat("2026-11-10T11:14:36+00:00")
        assert full.params["ts"] == 1794302570.25                             # the device's clock, hours off
        assert (full.received_at.timestamp() - full.params["ts"]) > MAX_CLOCK_SKEW_S
        assert notification_ts(full.params, full.received_at) == full.received_at
        await t.stop()
    run(scenario)


# --- RPC ---------------------------------------------------------------------------------------------------------

def test_switch_set_round_trip_from_the_capture():
    async def scenario():
        broker = FakeBroker()
        t = await started(broker)
        broker.set_online(APT, SID, True)
        await settle()
        assert await t.call(SID, "Switch.Set", {"id": 0, "on": False}, 1) == {"was_on": True}
        assert await t.call(SID, "Switch.Set", {"id": 0, "on": True}, 1) == {"was_on": False}
        topic, payload, qos = broker.published[0]
        request = json.loads(payload)
        assert (topic, qos) == (f"dev/{SID}/rpc", 1)
        assert request["src"] == f"dev/{SID}/connector"
        assert (request["method"], request["params"]) == ("Switch.Set", {"id": 0, "on": False})
        assert isinstance(request["id"], int)
        await t.stop()
    run(scenario)


def test_shelly_get_status_from_the_capture():
    async def scenario():
        broker = FakeBroker()
        t = await started(broker)
        broker.set_online(APT, SID, True)
        await settle()
        status = await t.call(SID, "Shelly.GetStatus", None, 1)
        assert status["switch:0"]["output"] is True and status["switch:0"]["aenergy"]["total"] == 15.088
        assert "params" not in broker.requests()[-1]
        await t.stop()
    run(scenario)


def test_an_error_answer_is_an_rpc_error():
    def refuse(shelly_id, request):
        return {"id": request["id"], "src": shelly_id, "dst": request["src"],
                "error": {"code": -105, "message": "Argument 'id', value 1 not found!"}}

    async def scenario():
        broker = FakeBroker(responder=refuse)
        t = await started(broker)
        broker.set_online(APT, SID, True)
        await settle()
        with pytest.raises(RpcError) as info:
            await t.call(SID, "Switch.Set", {"id": 1, "on": True}, 1)
        assert (info.value.code, info.value.message) == (-105, "Argument 'id', value 1 not found!")
        assert str(info.value) == "rpc error -105"
        await t.stop()
    run(scenario)


def test_no_answer_is_a_timeout_and_the_late_answer_is_dropped(logs):
    # session B of the capture: a Shelly.GetStatus that never got its answer
    assert capture_answers("B") == []

    async def scenario():
        broker = FakeBroker(responder=capture_responder("B"))
        t = await started(broker)
        broker.set_online(APT, SID, True)
        await settle()
        with pytest.raises(TransportTimeout):
            await t.call(SID, "Shelly.GetStatus", None, 0.05)
        late = broker.requests()[-1]["id"]
        broker.device_publish(answer_topic(SID), json.dumps({"id": late, "src": SID, "result": {}}))
        await settle()
        assert [type(i) for i in await drain(t)] == [ConnectionEvent]
        assert t.connected() == {SID}
        await t.stop()
    run(scenario)
    assert "mqtt rpc answer dropped" in rendered(logs)


def test_only_the_asked_device_can_answer():
    async def scenario():
        broker = FakeBroker(responder=lambda shelly_id, request: None)
        t = await started(broker)
        broker.set_online(APT, SID, True)
        broker.set_online(APT, SID2, True)
        await settle()
        call = asyncio.create_task(t.call(SID, "Shelly.GetStatus", None, 1))
        await settle()
        rid = broker.requests()[-1]["id"]
        forged = {"forged": True}
        broker.device_publish(answer_topic(SID2), json.dumps({"id": rid, "src": SID2, "result": forged}))
        broker.device_publish(answer_topic(SID2), json.dumps({"id": rid, "src": SID, "result": forged}))
        broker.device_publish(answer_topic(SID), json.dumps({"id": rid, "src": SID2, "result": forged}))
        broker.device_publish(answer_topic(SID), json.dumps({"id": rid + 1000, "src": SID, "result": forged}))
        await settle()
        assert not call.done()
        broker.device_publish(answer_topic(SID), json.dumps({"id": rid, "src": SID, "result": {"ok": True}}))
        assert await call == {"ok": True}
        await t.stop()
    run(scenario)


def test_device_not_connected_is_offline_without_publishing():
    async def scenario():
        broker = FakeBroker()
        t = await started(broker)
        with pytest.raises(TransportOffline):
            await t.call(SID, "Switch.Set", {"id": 0, "on": True}, 1)
        broker.set_online(APT, SID, True)
        broker.set_online(APT, SID, False)
        await settle()
        with pytest.raises(TransportOffline):
            await t.call(SID, "Switch.Set", {"id": 0, "on": True}, 1)
        assert broker.published == []
        await t.stop()
    run(scenario)


def test_device_going_offline_fails_its_pending_rpc():
    async def scenario():
        broker = FakeBroker(responder=lambda shelly_id, request: None)
        t = await started(broker)
        broker.set_online(APT, SID, True)
        await settle()
        call = asyncio.create_task(t.call(SID, "Shelly.GetStatus", None, 5))
        await settle()
        broker.set_online(APT, SID, False)                  # the last will
        with pytest.raises(TransportOffline):
            await call
        await t.stop()
    run(scenario)


def test_request_ids_are_unique_across_transports():
    async def scenario():
        broker = FakeBroker()
        broker.set_online(APT, SID, True)
        a, b = await started(broker), await started(broker)
        await settle()
        assert await a.call(SID, "Switch.Set", {"id": 0, "on": False}, 1) == {"was_on": True}
        assert await b.call(SID, "Switch.Set", {"id": 0, "on": False}, 1) == {"was_on": True}
        ids = [r["id"] for r in broker.requests()]
        assert len(ids) == len(set(ids)) == 2
        await a.stop()
        await b.stop()
    run(scenario)


# --- broker drop -------------------------------------------------------------------------------------------------

def test_broker_drop_fails_pending_rpcs_marks_all_offline_and_reconnects():
    async def scenario():
        broker = FakeBroker(responder=lambda shelly_id, request: None)
        sleeps = Sleeps()
        t = await started(broker, sleep=sleeps)
        broker.set_online(APT, SID, True)
        broker.set_online(APT, SID2, True)
        await settle()
        assert len(await drain(t)) == 2
        call = asyncio.create_task(t.call(SID, "Shelly.GetStatus", None, 5))
        await settle()

        sleeps.gate = asyncio.Event()
        broker.drop()
        with pytest.raises(TransportOffline):
            await call
        await settle()
        offline = await drain(t)
        assert {(i.shelly_id, i.connected) for i in offline} == {(SID, False), (SID2, False)}
        assert len(offline) == 2 and not t.broker_connected and t.connected() == set()
        published = len(broker.published)
        with pytest.raises(TransportOffline):               # no broker: offline at once, nothing published
            await t.call(SID, "Shelly.GetStatus", None, 1)
        assert len(broker.published) == published

        broker.refuse_connects = 2
        sleeps.gate.set()
        await settle()
        back = await drain(t)
        assert {(i.shelly_id, i.connected) for i in back} == {(SID, True), (SID2, True)}   # the retained "true"
        assert len(back) == 2 and t.connected() == {SID, SID2}
        assert sleeps.delays == [1.0, 2.0, 4.0]
        assert len(broker.connects) == 4

        broker.drop()                                       # after a good connection the wait starts again
        await settle()
        assert sleeps.delays[-1] == 1.0
        await t.stop()
    run(scenario)


# --- dropped messages --------------------------------------------------------------------------------------------

MARKER = "content-marker-41"


def test_topic_and_src_that_differ_are_dropped(logs):
    async def scenario():
        broker = FakeBroker()
        t = await started(broker)
        broker.device_publish(f"{APT}/{SID}/events/rpc", json.dumps(
            {"src": SID2, "method": "NotifyStatus", "params": {"switch:0": {"output": True, "tag": MARKER}}}))
        await settle()
        assert await drain(t) == []
        await t.stop()
    run(scenario)
    assert "mqtt src does not match topic" in rendered(logs)
    assert MARKER not in rendered(logs)


def test_invalid_json_unknown_method_and_bad_online_are_dropped_without_their_content(logs):
    async def scenario():
        broker = FakeBroker()
        t = await started(broker)
        broker.device_publish(f"{APT}/{SID}/events/rpc", "{not json " + MARKER)
        broker.device_publish(f"{APT}/{SID}/events/rpc", b"\xff\xfe" + MARKER.encode())
        broker.device_publish(f"{APT}/{SID}/events/rpc", json.dumps(
            {"src": SID, "method": "Switch.Set", "params": {"tag": MARKER}}))
        broker.device_publish(f"{APT}/{SID}/events/rpc", json.dumps({"src": SID, "method": "NotifyStatus"}))
        broker.device_publish(f"{APT}/{SID}/online", "maybe-" + MARKER, retain=True)
        broker.device_publish(answer_topic(SID), "[" + MARKER)
        await settle()
        assert await drain(t) == []
        assert t.connected() == set() and t.broker_connected
        await t.stop()
    run(scenario)
    text = rendered(logs)
    for msg in ("mqtt payload not valid json", "mqtt notification method unknown", "mqtt notification without params",
                "mqtt online payload not valid"):
        assert msg in text
    assert MARKER not in text


def test_stop_fails_pending_rpcs_and_ends_the_stream():
    async def scenario():
        broker = FakeBroker(responder=lambda shelly_id, request: None)
        t = await started(broker)
        broker.set_online(APT, SID, True)
        await settle()
        call = asyncio.create_task(t.call(SID, "Shelly.GetStatus", None, 5))
        await settle()
        await t.stop()
        with pytest.raises(TransportOffline):
            await call
        items = [item async for item in t.notifications()]
        assert [(type(i), i.connected) for i in items] == [(ConnectionEvent, True)]     # no offline on stop
        assert t.connected() == set() and broker.clients == []
    run(scenario)
