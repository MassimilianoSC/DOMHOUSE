"""P7a-1 (P-83 review of PR #7, gravity 2), the engine's part: a boiler's relay whose state the connector could not read
(Shelly.GetStatus failed when the device connected: no "on" in its snapshot) was taken as open, so with the thermostat
wanting it open no command was ever sent, while the real relay could be closed: heating unregulated without a time
limit. Now a relay of unknown state is «unknown», and the first regulation commands it to what the thermostat wants,
whichever way. (The connector's part, trying GetStatus again, is Youssouf's.)

Run: python -m pytest engine/tests -q
"""
import asyncio
import dataclasses

import pytest

from engine import core
from engine.connector import simulated
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
BOILER, SENSOR = "dev-caldaia", "dev-ambiente-soggiorno"
MINUTE = 0.2


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))
    for name in ("SENT_AFTER_S", "VERIFYING_AFTER_S", "OUTCOME_AFTER_S"):
        monkeypatch.setattr(simulated, name, 0)               # the simulated device answers at once


def snapshot_failed(relay_closed: bool) -> SimulatedConnector:
    """The real relay is closed (or open), but the connector's snapshot of the boiler has no "on"."""
    conn = SimulatedConnector()
    conn._devices[BOILER].capabilities["heating"]["on"] = relay_closed
    listed = conn.devices

    def devices():
        out = []
        for d in listed():
            if d.device_id == BOILER:
                heating = {k: v for k, v in d.capabilities["heating"].items() if k != "on"}
                d = dataclasses.replace(d, capabilities={**d.capabilities, "heating": heating})
            out.append(d)
        return out
    conn.devices = devices
    return conn


def stop(e) -> None:
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


def test_an_unknown_relay_is_commanded_open_when_the_room_is_warm():
    async def main():
        conn = snapshot_failed(relay_closed=True)
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
        assert BOILER not in e.relay                                        # unknown, not «open»
        e.ensure_started()
        e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": 26}}, ACTOR, CORR)
        await asyncio.sleep(10 * MINUTE)                                    # two seconds: regulations
        assert e.relay.get(BOILER) is False
        assert conn._devices[BOILER].capabilities["heating"]["on"] is False  # the real relay was opened
        stop(e)
    asyncio.run(main())


def test_a_known_relay_as_before_is_not_commanded_again():
    async def main():
        conn = SimulatedConnector()
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
        assert BOILER in e.relay
        e.ensure_started()
        e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": 26}}, ACTOR, CORR)
        switched = []
        real = e._switch_relay

        async def counted(*a, **k):
            switched.append(a[1])
            return await real(*a, **k)
        e._switch_relay = counted
        await asyncio.sleep(10 * MINUTE)
        assert switched == [] or switched == [False] and e.relay.get(BOILER) is False
        stop(e)
    asyncio.run(main())
