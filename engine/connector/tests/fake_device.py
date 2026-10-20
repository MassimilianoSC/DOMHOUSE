"""The fake device of the SimulatedConnector (ours; the model for engine/connector/shelly/tests/).

test_interface.py drives every connector through a harness: the connector under test plus the two things a test must
do to the "world" behind it, which a real connector cannot do by itself (a device goes away, a sensor changes).
A connector's harness lives in engine/connector/<name>/tests/harness.py and exposes make_harness() (see HARNESSES in
test_interface.py); the simulated one is here. If the connector needs more than the engine's configuration to be
built by make_connector(config) (the Shelly one needs its catalog), the harness also exposes connector_env(data_dir)
-> dict of environment variables, e.g. {"CATALOG_PATH": <a catalog it writes in data_dir>}; the simulated needs none.
"""
from engine.connector.simulated import SimulatedConnector


class SimulatedHarness:
    name = "simulated"

    def __init__(self):
        self.connector = SimulatedConnector(variant=0)

    def set_online(self, device_id: str, online: bool) -> None:
        self.connector.set_online(device_id, online)

    def set_state(self, device_id: str, capability: str, state: dict) -> None:
        self.connector.set_state(device_id, capability, state)

    async def close(self) -> None:
        await self.connector.stop()


def make_harness() -> SimulatedHarness:
    return SimulatedHarness()
