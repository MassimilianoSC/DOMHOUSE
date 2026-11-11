"""The Shelly connector (connector.md §2.7, §3): Youssouf's perimeter.

make_connector(config) is the engine's entry point (CONNECTOR=shelly): it reads the offline thresholds
(offline.load_thresholds, SHELLY_OFFLINE_THRESHOLDS_PATH / SHELLY_OFFLINE_AFTER_S), the catalog at config.catalog_path
(catalog.py) and the MQTT settings (SHELLY_MQTT_*, transport/mqtt.py), and builds the ShellyConnector. It opens no
connection: the transport starts in ShellyConnector.start(). Every error it raises names the setting, the device and
the field, never a value, so the engine can log it as it is ("connector setup failed").
"""
from engine.connector.interface import ConnectorConfig

from .catalog import load_catalog
from .connector import ShellyConnector
from .offline import load_thresholds


def make_connector(config: ConnectorConfig) -> ShellyConnector:
    from .transport.mqtt import MqttTransport     # aiomqtt itself is imported only when the transport connects

    thresholds = load_thresholds(config.env)
    catalog = load_catalog(config.catalog_path, thresholds)
    transport = MqttTransport.from_config(config)
    return ShellyConnector(catalog, transport)
