"""D12 (P-83 review, gravity 2), the engine's part: a device already offline when the engine starts (a restart with a
plug unplugged meanwhile, or a device never connected) got no «offline» decision, no device.online event, and lost its
last_seen: the offline_alert watch started only on a change. Now, at the start, every device offline is watched as if
it had just gone offline (one offline_alert decision after the rule's minutes), a device.online false event is sent,
and last_seen comes back from the store when the connector does not know it yet. (The connector's part, a retained
«offline» from the broker for a device never seen online, is Youssouf's.) Scenario of the independent verification
(V-D12/prova_d12.py) on the simulated connector, inverted.

Run: python -m pytest engine/tests -q
"""
import asyncio
import dataclasses

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

PLUG = "dev-presa-camera"


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "0.05")       # the rule's 15 minutes are 0.75 s


def stop(e) -> None:
    for t in [e.loop_task, e.consumer_task, *e.tasks]:
        if t is not None:
            t.cancel()


async def run(db, offline_at_start: str | None):
    connector = SimulatedConnector()
    if offline_at_start:
        connector.set_online(offline_at_start, False, notify=False)
        listed = connector.devices

        def devices():                                  # as Shelly's connector at the start: never heard, no last_seen
            return [dataclasses.replace(d, last_seen=None) if d.device_id == offline_at_start else d for d in listed()]
        connector.devices = devices
    e = core.ApartmentEngine("apt-prova-01", connector, seed=False, store=SqliteStore(db))
    first = int(e.events[-1]["id"]) if e.events else 0
    e.ensure_started()
    await asyncio.sleep(2.0)
    stop(e)
    events = [x for x in e.events if int(x["id"]) > first and x["event"] == "device.online"]
    return e, events


def test_a_device_offline_at_the_restart_gets_its_alert_its_event_and_keeps_last_seen(tmp_path):
    async def main():
        db = tmp_path / "engine.db"
        first, _ = await run(db, None)
        plug = next(d for d in first.devices.values() if d["device_id"] == PLUG)
        assert plug["online"] and plug["last_seen"]
        again, events = await run(db, PLUG)
        plug2 = again.devices[PLUG]
        assert not plug2["online"]
        assert plug2["last_seen"] is not None                              # from the store, not lost
        assert [x["data"]["device_id"] for x in events if x["data"]["online"] is False] == [PLUG]
        alerts = [d for d in again.decisions if d["action"] == "offline_alert"]
        assert [d["target"]["device_id"] for d in alerts] == [PLUG]
    asyncio.run(main())


def test_with_every_device_online_nothing_is_said(tmp_path):
    async def main():
        db = tmp_path / "engine.db"
        await run(db, None)
        again, events = await run(db, None)
        assert events == [] and not [d for d in again.decisions if d["action"] == "offline_alert"]
    asyncio.run(main())
