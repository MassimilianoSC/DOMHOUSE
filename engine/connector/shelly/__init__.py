"""The Shelly connector (connector.md §2.7, §3): Youssouf's perimeter.

The transport is decided: MQTT, with a broker of ours (D-196). make_connector(config) will come here together with the
ShellyConnector. For now the package holds the pieces that do not depend on the transport, starting with the offline
thresholds per device type (offline.py).
"""
