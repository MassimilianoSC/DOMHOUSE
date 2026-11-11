"""transport/mqtt.py on a real broker with a real Shelly: skipped unless SHELLY_MQTT_TEST_URL is set.

    SHELLY_MQTT_TEST_URL      mqtt://<user>:<password>@<host>:<port>  (mqtts:// for TLS); the connector's account
    SHELLY_MQTT_TEST_DEVICE   the shelly_id of the device on the bench, e.g. shellyplugmg3-<mac>
    SHELLY_MQTT_TEST_APARTMENT the topic prefix, default "dev" (the lab broker's)

The device must answer on <prefix>/<shelly_id>/connector/rpc, inside its own prefix: an ACL limited to
<prefix>/<shelly_id>/# is enough. Needs aiomqtt (pip install -r engine/requirements.txt).
Run: python -m pytest engine/connector/shelly/tests/test_transport_mqtt_live.py -q -rs
"""
import asyncio
import os
from urllib.parse import unquote, urlsplit

import pytest

from engine.connector.shelly.transport.base import ConnectionEvent
from engine.connector.shelly.transport.mqtt import MqttTransport, settings_from_env

URL = os.environ.get("SHELLY_MQTT_TEST_URL", "")
DEVICE = os.environ.get("SHELLY_MQTT_TEST_DEVICE", "")
APARTMENT = os.environ.get("SHELLY_MQTT_TEST_APARTMENT", "dev")

pytestmark = pytest.mark.skipif(not URL, reason="SHELLY_MQTT_TEST_URL not set")


def env_from_url(url: str) -> dict[str, str]:
    parts = urlsplit(url)
    if parts.scheme not in ("mqtt", "mqtts") or not parts.hostname:
        raise ValueError("SHELLY_MQTT_TEST_URL must look like mqtt://user:password@host:port")
    env = {"SHELLY_MQTT_HOST": parts.hostname,
           "SHELLY_MQTT_USERNAME": unquote(parts.username or ""),
           "SHELLY_MQTT_PASSWORD": unquote(parts.password or ""),
           "SHELLY_MQTT_TLS": "true" if parts.scheme == "mqtts" else "false"}
    if parts.port:
        env["SHELLY_MQTT_PORT"] = str(parts.port)
    return env


def test_live_connection_event_and_get_status():
    pytest.importorskip("aiomqtt")
    if not DEVICE:
        pytest.fail("SHELLY_MQTT_TEST_DEVICE not set")

    async def scenario():
        transport = MqttTransport(APARTMENT, settings_from_env(env_from_url(URL)))
        await transport.start()
        try:
            assert transport.broker_connected, "broker not reached (see the log line 'mqtt connect failed')"

            async def device_connected():
                async for item in transport.notifications():
                    if isinstance(item, ConnectionEvent) and item.shelly_id == DEVICE and item.connected:
                        return
            await asyncio.wait_for(device_connected(), timeout=15)
            assert DEVICE in transport.connected()

            status = await transport.call(DEVICE, "Shelly.GetStatus", None, 5)
            assert isinstance(status.get("switch:0", {}).get("output"), bool)
        finally:
            await transport.stop()

    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(scenario())
