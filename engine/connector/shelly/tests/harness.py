"""The harness of the ShellyConnector for the common tests (engine/connector/tests/test_interface.py, connector.md §4).

make_harness() builds, inside the running event loop, a ShellyConnector on FakeTransport with one fake Plug M Gen3
(tests/fake_device.py), from the test catalog below. set_online and set_state act on the fake world, as the harness
of the simulated connector does (engine/connector/tests/fake_device.py); close() stops the connector.

One thing differs from the simulated harness, on purpose, and only here. The common tests look for an online device
right after start() (a_switch), while ShellyConnector.start(), as connector.md §2.1 asks, returns without waiting for
the devices: a real plug announces itself shortly after, with the broker's retained "online" message, then the
connector asks its model and its status. So the harness wraps start() of its connector instance: the real start(),
then a wait of at most START_WAIT_S (5 s) until every fake device is online with its snapshot. The connector itself
is unchanged; with the fakes the wait is two RPCs, about 0.3 s. If the devices do not come, the wait ends quietly and
the tests that need them fail on their own assertions.

FakeTransport answers every RPC after LATENCY_S, so a command lasts about 0.3 s, like the simulated one, and
test_cancelled_command_leaves_the_connector_usable can cancel it half way (after 0.1 s).

connector_env(data_dir) writes the same catalog to data_dir/catalog.yaml (the engine's default CATALOG_PATH) and gives
the SHELLY_MQTT_* variables make_connector needs, with fake values: make_connector never connects.

The common tests that need a temperature sensor, a battery sensor, a boiler or a split skip themselves: the Plug has
switch and power_meter only.
"""
import asyncio
from pathlib import Path

from engine.connector.shelly.catalog import parse_catalog
from engine.connector.shelly.connector import ShellyConnector
from engine.connector.shelly.offline import load_thresholds

from .fake_device import FakePlugMG3
from .fake_transport import FakeTransport

PLUG_DEVICE_ID = "dev-presa-prova"
PLUG_SHELLY_ID = "shellyplugmg3-000000000001"      # invented, as connector.md §5 asks
START_WAIT_S = 5.0
LATENCY_S = 0.15

CATALOG = {
    "rooms": [{"room_id": "camera", "name": "Camera"}],
    "devices": [{"device_id": PLUG_DEVICE_ID, "label": "Presa di prova", "room_id": "camera",
                 "capabilities": {"switch": {}, "power_meter": {}},
                 "shelly": {"id": PLUG_SHELLY_ID, "type": "plug", "channel": 0}}],
}
CATALOG_YAML = f"""\
# test catalog of engine/connector/shelly/tests/harness.py (invented ids)
rooms:
  - {{room_id: camera, name: Camera}}
devices:
  - device_id: {PLUG_DEVICE_ID}
    label: Presa di prova
    room_id: camera
    capabilities: {{switch: {{}}, power_meter: {{}}}}
    shelly: {{id: {PLUG_SHELLY_ID}, type: plug, channel: 0}}
"""
FAKE_MQTT_ENV = {"SHELLY_MQTT_HOST": "broker.invalid", "SHELLY_MQTT_USERNAME": "connector-prova",
                 "SHELLY_MQTT_PASSWORD": "password-finta-di-prova"}


class ShellyHarness:
    name = "shelly"

    def __init__(self):
        self.plugs = {PLUG_DEVICE_ID: FakePlugMG3(PLUG_SHELLY_ID, on=False, load_watts=12.2, energy_wh=41_700.0)}
        self.transport = FakeTransport(*self.plugs.values(), announce_on_start=True, latency_s=LATENCY_S)
        self.connector = ShellyConnector(parse_catalog(CATALOG, load_thresholds()), self.transport)
        real_start = self.connector.start

        async def start() -> None:          # see the module's docstring: the wait is the harness's, not the connector's
            await real_start()
            await self.wait_ready()
        self.connector.start = start

    async def wait_ready(self, timeout: float = START_WAIT_S) -> None:
        end = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < end:
            ready = {d.device_id for d in self.connector.devices()
                     if d.online and all(d.capabilities[c] for c in d.capabilities)}
            if ready >= {k for k, p in self.plugs.items() if p.online}:
                return
            await asyncio.sleep(0.02)

    def set_online(self, device_id: str, online: bool) -> None:
        self.transport.set_online(self.plugs[device_id].shelly_id, online)

    def set_state(self, device_id: str, capability: str, state: dict) -> None:
        """What a Plug can simulate: switch.on (the button), power_meter.watts (the load) and energy_total_wh (only
        upwards: the energy used meanwhile)."""
        plug = self.plugs[device_id]
        if capability == "switch" and set(state) <= {"on"}:
            if "on" in state and bool(state["on"]) != plug.on:
                plug.press_button()
            return
        if capability == "power_meter" and set(state) <= {"watts", "energy_total_wh"}:
            if "watts" in state:
                plug.set_load(float(state["watts"]))
            if "energy_total_wh" in state:
                current = plug.full_status()["switch:0"]["aenergy"]["total"]
                if float(state["energy_total_wh"]) < current:
                    raise ValueError("a Plug's energy counter only goes up (reboot() starts it from zero)")
                plug.add_energy(float(state["energy_total_wh"]) - current)
            return
        raise ValueError(f"a Plug M Gen3 cannot simulate {capability}")

    async def close(self) -> None:
        await self.connector.stop()


def make_harness() -> ShellyHarness:
    return ShellyHarness()


def connector_env(data_dir: Path) -> dict[str, str]:
    (Path(data_dir) / "catalog.yaml").write_text(CATALOG_YAML, encoding="utf-8")
    return dict(FAKE_MQTT_ENV)
