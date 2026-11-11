"""D16 (P-83 review, gravity 2): a mode change skipped a device offline (or every device with the connector down), and
when it came back nothing gave it the mode: the boiler kept the old intention (21 °C in «casa vuota», 8 °C after the
prearrival), the climate stayed on in eco and «casa vuota». Now the boiler's intention (the engine's own, connector-v2
§2.3-2.4) takes the mode's anyway and its relay follows when it is back; a climate's command of the mode waits and is
sent when the climate is reachable again, unless the mode changed or a person commanded it meanwhile; a decision says
what waits. Scenarios of the independent verification (V-D16/test_d16.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
BOILER, CLIMA, SENSOR = "dev-caldaia", "dev-clima-soggiorno", "dev-ambiente-soggiorno"
MINUTE = 0.02


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


class Rec(SimulatedConnector):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.targets = []

    async def execute(self, cmd, on_progress):
        self.targets.append((cmd.device_id, dict(cmd.target)))
        return await super().execute(cmd, on_progress)


def go(e, conn, device_id, online):
    """The real path: the connector's changes (online + full snapshot) applied by the engine."""
    for ch in conn.set_online(device_id, online, notify=False):
        e._apply_change(ch)


async def settle(e, rounds=3):
    for _ in range(rounds):
        e.regulate()
        await asyncio.gather(*list(e.tasks), return_exceptions=True)
        await asyncio.sleep(6 * MINUTE)


def heating(e) -> dict:
    return e.devices[BOILER]["capabilities"]["heating"]


def test_boiler_offline_when_the_apartment_is_emptied_gets_the_frost_threshold():
    async def main():
        conn = Rec()
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
        e.ensure_started()
        e.set_mode("comfort", ACTOR, CORR, "prep")
        await settle(e, 1)
        go(e, conn, BOILER, False)
        e.set_mode("empty", ACTOR, CORR, "Modalità impostata dall'app")
        assert any(d["action"] == "mode_device_pending" and d["target"].get("device_id") == BOILER for d in e.decisions)
        go(e, conn, BOILER, True)
        e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": 18.0}}, ACTOR, CORR)
        await settle(e)
        frost = e.rule("frost_protection")["params"]["celsius"]
        assert heating(e)["setpoint"] == frost and BOILER in e.heating_by_mode
        assert e.relay.get(BOILER) is False                           # 18 °C is above the frost threshold
    asyncio.run(main())


def test_boiler_offline_at_the_prearrival_gets_comfort():
    async def main():
        conn = Rec(variant=1)
        e = core.ApartmentEngine("apt-bologna-01", conn, seed=False)
        e.ensure_started()
        e.set_mode("empty", ACTOR, CORR, "prep")
        await settle(e, 1)
        go(e, conn, BOILER, False)
        e.set_mode("comfort", ACTOR, CORR, "arrivo")
        go(e, conn, BOILER, True)
        await settle(e)
        assert heating(e)["on"] and heating(e)["setpoint"] == e.rule("setpoint_limits")["params"]["comfort_celsius"]
    asyncio.run(main())


def test_climate_offline_when_the_apartment_is_emptied_is_turned_off_when_back():
    async def main():
        conn = Rec()
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
        e.ensure_started()
        assert e.devices[CLIMA]["capabilities"]["climate"]["on"] is True
        go(e, conn, CLIMA, False)
        e.set_mode("empty", ACTOR, CORR, "Modalità impostata dall'app")
        go(e, conn, CLIMA, True)
        conn.targets.clear()
        await settle(e)
        sent = [t[1] for t in conn.targets if t[0] == CLIMA]
        assert len(sent) == 1 and sent[0]["on"] is False                 # the waiting turn_off, once
        assert e.devices[CLIMA]["capabilities"]["climate"]["on"] is False
    asyncio.run(main())


def test_a_persons_command_meanwhile_wins_over_the_waiting_one():
    async def main():
        conn = Rec()
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
        e.ensure_started()
        go(e, conn, CLIMA, False)
        e.set_mode("empty", ACTOR, CORR, "Modalità impostata dall'app")
        go(e, conn, CLIMA, True)
        e.create_command(CLIMA, {"capability": "climate", "action": "set_climate",
                                 "params": {"on": True, "mode": "cool", "setpoint": 24}}, ACTOR, CORR)
        await settle(e)
        conn.targets.clear()
        await settle(e)
        assert not [t for t in conn.targets if t[0] == CLIMA]           # the waiting turn_off was dropped
        assert e.devices[CLIMA]["capabilities"]["climate"]["on"] is True
    asyncio.run(main())


def test_with_the_connector_down_the_mode_reaches_the_devices_when_it_is_back(monkeypatch):
    async def main():
        conn = Rec()
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
        e.ensure_started()
        e.set_mode("comfort", ACTOR, CORR, "prep")
        await settle(e, 1)
        monkeypatch.setenv("DOMOTICA_TEST_CONNECTOR_DOWN", "1")
        e.tick()
        assert not e.connector_was_up
        e.set_mode("empty", ACTOR, CORR, "Modalità impostata dall'app")
        monkeypatch.delenv("DOMOTICA_TEST_CONNECTOR_DOWN")
        e.tick()
        conn.targets.clear()
        await settle(e)
        assert heating(e)["setpoint"] == e.rule("frost_protection")["params"]["celsius"]
        assert e.devices[CLIMA]["capabilities"]["climate"]["on"] is False
    asyncio.run(main())


def test_control_toward_comfort_the_climate_was_already_taken_back():
    async def main():
        conn = Rec(variant=1)
        e = core.ApartmentEngine("apt-bologna-01", conn, seed=False)
        e.ensure_started()
        go(e, conn, CLIMA, False)
        e.set_mode("comfort", ACTOR, CORR, "arrivo")
        assert CLIMA in e.climate_by_mode
    asyncio.run(main())
