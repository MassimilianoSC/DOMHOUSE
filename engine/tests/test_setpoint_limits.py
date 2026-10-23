"""«Limiti del setpoint» (lot 31, D-174, D-183 points 124-125): the engine keeps each device's limits from the catalog,
the boundary in every case; the switch on = the manager's limits inside the device's, for climate and boiler; off =
the device's; a manual command out of them is refused, an automatic one brought inside with a note; an empty
intersection = the device's limits with one decision per episode; the frost protection only the device's limits.

Run: python -m pytest engine/tests -q
"""
import asyncio
import dataclasses

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
CLIMA, CALDAIA = "dev-clima-soggiorno", "dev-caldaia"


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", "0.02")


class NarrowBoiler(SimulatedConnector):
    """A catalog whose boiler goes only from 5 to 12 °C: no overlap with the manager's 16-24."""

    def devices(self):
        out = []
        for d in super().devices():
            if d.device_id == CALDAIA:
                d = dataclasses.replace(d, capabilities={**d.capabilities, "heating": {
                    **d.capabilities["heating"], "setpoint_min": 5, "setpoint_max": 12}})
            out.append(d)
        return out


def engine(connector=None, store=None):
    return core.ApartmentEngine("apt-prova-01", connector or SimulatedConnector(), seed=False, store=store,
                                settings={"COMPRESSOR_WAIT_SECONDS": 0})


def limits(e, device_id, cap):
    state = e.devices[device_id]["capabilities"][cap]
    return state["setpoint_min"], state["setpoint_max"]


def rules(e, enabled=None, **params):
    patch = {"rule_id": "setpoint_limits", **({"params": params} if params else {})}
    if enabled is not None:
        patch["enabled"] = enabled
    e.update_rules({"rules": [patch]}, ACTOR, CORR)


def set_point(e, device_id, cap, sp):
    action = "set_climate" if cap == "climate" else "set_heating"
    return e.validate_command(e.devices[device_id], {"capability": cap, "action": action, "params": {"setpoint": sp}})


def ignored(e):
    return [d for d in e.decisions if d["action"] == "setpoint_limits_ignored"]


def test_switch_on_the_managers_limits_inside_the_devices_for_climate_and_boiler():
    e = engine()                                                  # catalog: climate 16-24, boiler 7-23
    assert e.device_limits(CALDAIA, "heating") == (7, 23) and e.device_limits(CLIMA, "climate") == (16, 24)
    assert limits(e, CLIMA, "climate") == (16, 24) and limits(e, CALDAIA, "heating") == (16, 23)
    rules(e, min=18, max=22)
    assert limits(e, CLIMA, "climate") == (18, 22) and limits(e, CALDAIA, "heating") == (18, 22)
    sent = {ev["data"]["capability"] for ev in e.events if ev["event"] == "device.state"
            and ev["data"]["device_id"] in (CLIMA, CALDAIA)}
    assert sent == {"climate", "heating"}                         # the app sees the new limits at once
    rules(e, min=10, max=28)                                      # wider than the device: the catalog is the boundary
    assert limits(e, CLIMA, "climate") == (16, 24) and limits(e, CALDAIA, "heating") == (10, 23)


def test_switch_off_the_devices_limits():
    e = engine()
    rules(e, min=18, max=22)
    rules(e, enabled=False)
    assert limits(e, CLIMA, "climate") == (16, 24) and limits(e, CALDAIA, "heating") == (7, 23)
    assert set_point(e, CALDAIA, "heating", 10)[2] == {"setpoint": 10}       # accepted: inside the device's
    rules(e, enabled=True)
    assert limits(e, CALDAIA, "heating") == (18, 22)


def test_manual_out_of_limits_refused_automatic_brought_inside_with_a_note():
    e = engine()
    with pytest.raises(core.MockError) as exc:
        set_point(e, CALDAIA, "heating", 10)
    assert exc.value.status == 422 and exc.value.error == "setpoint_out_of_range" and exc.value.details == {
        "min": 16, "max": 23}
    body, note = e._within_limits(e.devices[CALDAIA], {"capability": "heating", "action": "set_heating",
                                                       "params": {"on": True, "setpoint": 10}})
    assert body["params"]["setpoint"] == 16 and note == "setpoint 10 °C riportato a 16 °C (limiti 16–23)"


def test_the_modes_temperatures_inside_the_effective_limits():
    e = engine()
    rules(e, min=20, max=24)                                      # eco 18 and comfort 21: eco is brought to 20
    by_device = {device_id: body for device_id, body in e.mode_commands("eco", CORR)}
    assert by_device[CALDAIA]["params"]["setpoint"] == 20
    by_device = {device_id: body for device_id, body in e.mode_commands("comfort", CORR)}
    assert by_device[CALDAIA]["params"]["setpoint"] == 21


def test_the_frost_protection_only_inside_the_devices_limits():
    async def main():
        e = engine()
        e.ensure_started()
        e.set_mode("empty", ACTOR, CORR, "Prova")
        end = asyncio.get_running_loop().time() + 10
        while any(c["status"] not in core.FINAL for c in e.commands.values()):
            assert asyncio.get_running_loop().time() < end, e.commands
            await asyncio.sleep(0.02)
        return e
    e = asyncio.run(main())
    heating = e.devices[CALDAIA]["capabilities"]["heating"]
    assert heating["setpoint"] == 8 and limits(e, CALDAIA, "heating") == (16, 23)     # 8 °C under the manager's 16
    assert CALDAIA in e.heating_by_mode
    rules(e, min=17)                                              # a change of the limits leaves the frost alone
    assert e.devices[CALDAIA]["capabilities"]["heating"]["setpoint"] == 8
    e.update_rules({"rules": [{"rule_id": "frost_protection", "params": {"celsius": 5}}]}, ACTOR, CORR)
    by_device = {device_id: body for device_id, body in e.mode_commands("empty", CORR)}
    assert by_device[CALDAIA]["params"]["setpoint"] == 7          # but always inside the device's (7-23)


def test_an_empty_intersection_the_devices_limits_and_one_decision_per_episode(tmp_path):
    db = tmp_path / "engine.db"
    e = engine(NarrowBoiler(), SqliteStore(db))
    assert limits(e, CALDAIA, "heating") == (5, 12) and limits(e, CLIMA, "climate") == (16, 24)
    [d] = ignored(e)
    assert d["actor"] == "rule:setpoint_limits" and d["outcome"] == "informational"
    assert d["target"] == {"type": "device", "device_id": CALDAIA}
    assert d["reasoning"] == ("Caldaia: i limiti del setpoint (16–24 °C) sono fuori da quelli del dispositivo "
                              "(5–12 °C): valgono quelli del dispositivo")
    rules(e, min=17)                                              # the same episode: no new decision
    assert len(ignored(e)) == 1
    e.store.close()
    e = engine(NarrowBoiler(), SqliteStore(db))                   # nor after a restart
    assert len(ignored(e)) == 1 and e.limits_conflicts == {f"{CALDAIA}:heating"}
    rules(e, enabled=False)                                       # the episode ends
    assert e.limits_conflicts == set() and limits(e, CALDAIA, "heating") == (5, 12)
    rules(e, enabled=True)                                        # a new episode: a new decision
    assert len(ignored(e)) == 2
