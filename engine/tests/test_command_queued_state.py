"""D32 (P-83 review, gravity 3): a second command to the same split, created while the first held the device's lock,
computed its target from the state before the first: «fan high» sent while the split was being turned on became
{on: False, fan: high} and turned it off again («off → off» in the log); and its 10 s ran from its creation, so after
a long first command it timed out, though it was sent anyway. Now a command computes what it asks (and its old value
for the log) when it enters the lock, from the state the first command left, and its time starts there. Scenario of the
independent verification (V-B1a/prova_d32.py), inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
ACTOR2, CORR2 = "altro@hqe.it", "3f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d11"
CLIMA = "dev-clima-soggiorno"


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "0.02")


class Slow(SimulatedConnector):
    def __init__(self, *a, slow_s=2.0, **k):
        super().__init__(*a, **k)
        self.slow_id, self.slow_s, self.targets = None, slow_s, []

    async def execute(self, cmd, on_progress):
        self.targets.append((cmd.command_id, dict(cmd.target)))
        if cmd.command_id == self.slow_id:
            await asyncio.sleep(self.slow_s)
        return await super().execute(cmd, on_progress)


async def settle(e, timeout=30.0):
    end = asyncio.get_running_loop().time() + timeout
    while any(c["status"] not in core.FINAL for c in e.commands.values()):
        assert asyncio.get_running_loop().time() < end
        await asyncio.sleep(0.02)


async def queued(slow_s):
    conn = Slow(slow_s=slow_s)
    e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
    e.ensure_started()
    await settle(e)
    e.create_command(CLIMA, {"capability": "climate", "action": "turn_off"}, ACTOR, CORR)
    await settle(e)
    await asyncio.sleep(0.5)                                   # the compressor's pause is over
    a = e.create_command(CLIMA, {"capability": "climate", "action": "set_climate", "params": {"on": True}}, ACTOR, CORR)
    conn.slow_id = a["command_id"]
    await asyncio.sleep(0.2)                                   # A inside the lock, waiting for the slow device
    b = e.create_command(CLIMA, {"capability": "climate", "action": "set_climate", "params": {"fan": "high"}},
                         ACTOR2, CORR2)
    await settle(e)
    return e, conn, a, b


def test_the_second_command_starts_from_the_state_the_first_left():
    async def main():
        e, conn, a, b = await queued(2.0)
        climate = e.devices[CLIMA]["capabilities"]["climate"]
        assert climate["on"] is True and climate["fan"] == "high"
        sent_b = [t for cid, t in conn.targets if cid == b["command_id"]]
        assert sent_b and sent_b[0]["on"] is True
        assert e.commands[b["command_id"]]["status"] == "acked"
    asyncio.run(main())


def test_its_time_starts_when_it_gets_the_device():
    async def main():
        e, conn, a, b = await queued(9.0)                      # the first one takes almost all of its 10 s
        assert e.commands[b["command_id"]]["status"] == "acked"
        assert e.devices[CLIMA]["capabilities"]["climate"]["fan"] == "high"
    asyncio.run(main())
