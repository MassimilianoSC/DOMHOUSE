"""The power confirmation of an infrared split (P-60 step 7, D-131, connector.md §2.5): the simulated split with
`confirmation: power` answers "delivered" as an infrared blaster would, and only its meter moves.

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import confirmation, core
from engine.config import ConfigError, load_config
from engine.connector import simulated
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
SPLIT = "dev-clima-soggiorno"


@pytest.fixture(autouse=True)
def quick(monkeypatch):
    """No transport delays; the meter is waited for half a second instead of up to the contract's 10 s."""
    for name in ("SENT_AFTER_S", "VERIFYING_AFTER_S", "OUTCOME_AFTER_S"):
        monkeypatch.setattr(simulated, name, 0)
    monkeypatch.setattr(confirmation, "CONFIRM_UNTIL_S", 0.5)


def run(engine, body, device_id=SPLIT):
    async def main():
        engine.ensure_started()
        cmd = engine.create_command(device_id, body, ACTOR, CORR)
        while engine.commands[cmd["command_id"]]["status"] not in core.FINAL:
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.05)
        return engine.commands[cmd["command_id"]]
    return asyncio.run(main())


def last_decision(engine) -> dict:
    return engine.decisions[-1]


def test_a_switch_off_confirmed_by_the_meter():
    conn = SimulatedConnector()                                   # Rimini: the split is on, 870 W
    e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
    cmd = run(e, {"capability": "climate", "action": "turn_off"})
    assert cmd["status"] == "acked"
    assert e.devices[SPLIT]["capabilities"]["climate"]["on"] is False
    assert e.devices[SPLIT]["capabilities"]["power_meter"]["watts"] == 0


def test_a_lost_frame_is_not_confirmed_and_the_split_stays_as_it_was():
    conn = SimulatedConnector()
    e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
    conn.lose_infrared(SPLIT)
    cmd = run(e, {"capability": "climate", "action": "turn_off"})
    assert (cmd["status"], cmd["reason"]) == ("timeout", "no_confirmation")
    assert e.devices[SPLIT]["capabilities"]["climate"]["on"] is True
    d = last_decision(e)
    assert d["outcome"] == "failed" and "Nessuna conferma dal misuratore «Climatizzatore soggiorno»" in d["reasoning"]


def test_a_change_with_the_split_on_is_not_verified():
    conn = SimulatedConnector()
    e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
    conn.lose_infrared(SPLIT)                                     # even a lost frame: nothing to verify, as decided
    cmd = run(e, {"capability": "climate", "action": "set_climate", "params": {"setpoint": 22}})
    assert cmd["status"] == "acked" and e.devices[SPLIT]["capabilities"]["climate"]["setpoint"] == 22


def test_a_meter_offline_accepts_the_command_with_a_decision():
    conn = SimulatedConnector()
    conn._devices[SPLIT].links = {"confirmation_device_id": "dev-presa-camera"}   # a meter of its own
    conn.set_online("dev-presa-camera", False, notify=False)
    e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
    assert e.devices["dev-presa-camera"]["online"] is False
    cmd = run(e, {"capability": "climate", "action": "turn_off"})
    assert cmd["status"] == "acked"
    d = next(d for d in reversed(e.decisions) if d["action"] == "command_unverified")
    assert d["outcome"] == "informational" and d["target"] == {"type": "device", "device_id": SPLIT}
    assert d["reasoning"] == ("Comando a climatizzatore soggiorno non verificato: il misuratore "
                              "«Presa stufetta camera» è offline")


def test_without_a_link_the_split_is_confirmation_none():
    conn = SimulatedConnector()
    conn._devices[SPLIT].links = {}
    e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
    conn.lose_infrared(SPLIT)
    assert run(e, {"capability": "climate", "action": "turn_off"})["status"] == "acked"


def test_the_apartments_thresholds():
    conn = SimulatedConnector(variant=1)                          # Bologna: the split is off, 0 W; on it draws 870 W
    e = core.ApartmentEngine("apt-prova-01", conn, seed=False, confirm_watts=(1000, 15))
    assert run(e, {"capability": "climate", "action": "set_climate", "params": {"on": True}})["status"] == "timeout"   # +870 W < 1000
    e = core.ApartmentEngine("apt-prova-02", SimulatedConnector(variant=1), seed=False)
    assert (e.confirm_on_watts, e.confirm_off_watts) == (20, 15)
    assert run(e, {"capability": "climate", "action": "set_climate", "params": {"on": True}})["status"] == "acked"


def test_the_thresholds_are_settings_of_the_engine():
    base = {"APARTMENT_ID": "apt-prova-01", "API_KEY": "k" * 16, "CONNECTOR": "simulated"}
    c = load_config(base)
    assert (c.confirm_on_watts, c.confirm_off_watts) == (20, 15)
    c = load_config({**base, "CONFIRM_ON_WATTS": "60", "CONFIRM_OFF_WATTS": "8.5"})
    assert (c.confirm_on_watts, c.confirm_off_watts) == (60, 8.5)
    assert "CONFIRM_ON_WATTS" not in c.for_connector().env
    for bad in ("zero", "0", "6000"):
        with pytest.raises(ConfigError, match="CONFIRM_OFF_WATTS must be a number between 1 and 5000"):
            load_config({**base, "CONFIRM_OFF_WATTS": bad})


# -------- the links checked at start (step 7b, connector.md §2.2) --------
def warnings(monkeypatch) -> list[tuple[str, dict]]:
    seen = []
    monkeypatch.setattr(core.logs, "warn", lambda msg, **fields: seen.append((msg, fields)))
    return seen


def test_the_simulated_catalog_has_good_links(monkeypatch):
    seen = warnings(monkeypatch)
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    assert seen == []
    assert e.links[SPLIT] == {"confirmation_device_id": SPLIT}
    assert e.links["dev-caldaia"] == {"sensor_device_id": "dev-ambiente-soggiorno"}


@pytest.mark.parametrize("links, reason", [
    ({SPLIT: {"confirmation_device_id": "dev-che-non-esiste"}}, "target not in the catalog"),
    ({SPLIT: {"confirmation_device_id": "dev-finestra-camera"}}, "target without power_meter"),
    ({SPLIT: {"confirmation_device_id": SPLIT, "colore": "rosso"}}, "unknown link key"),
    ({"dev-presa-camera": {"confirmation_device_id": "dev-presa-camera"}}, "link only for a device with climate"),
    ({"dev-caldaia": {"sensor_device_id": "dev-presa-camera"}}, "target without temperature"),
])
def test_a_wrong_link_is_left_out_with_a_log_line(monkeypatch, links, reason):
    conn = SimulatedConnector()
    for device_id, value in links.items():
        conn._devices[device_id].links = value
    seen = warnings(monkeypatch)
    core.ApartmentEngine("apt-prova-01", conn, seed=False)
    assert any(msg == "link ignored" and f["reason"] == reason for msg, f in seen), seen


def test_a_split_without_meter_is_none_and_a_boiler_without_sensor_is_not_regulated(monkeypatch):
    conn = SimulatedConnector()
    conn._devices[SPLIT].links = {"confirmation_device_id": "dev-finestra-camera"}    # wrong: no power_meter
    conn._devices["dev-caldaia"].links = {}
    seen = warnings(monkeypatch)
    e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
    msgs = [(m, f.get("device_id"), f.get("treated_as")) for m, f in seen]
    assert ("split without confirmation meter", SPLIT, "confirmation none") in msgs
    assert ("boiler without sensor", "dev-caldaia", "not regulated") in msgs
    assert e.links[SPLIT] == {} and e.confirmation_meter(SPLIT) is None
    conn.lose_infrared(SPLIT)                                     # none: a lost frame is not noticed
    assert run(e, {"capability": "climate", "action": "turn_off"})["status"] == "acked"


# -------- the connector down and back (step 7c, D-131) --------
class Switchable(SimulatedConnector):
    """A simulated connector whose status() can be put down and up."""
    up = True

    def status(self):
        import dataclasses
        return dataclasses.replace(super().status(), up=self.up)


def test_the_connector_down_and_back_is_an_event_a_decision_and_commands_wait():
    conn = Switchable()
    e = core.ApartmentEngine("apt-prova-01", conn, seed=False)

    async def main():
        e.tick()
        assert not [d for d in e.decisions if d["action"].startswith("connector_")]     # nothing changed
        conn.up = False
        e.tick()
        e.tick()                                                                          # once, not at every tick
        down = [d for d in e.decisions if d["action"] == "connector_down"]
        assert len(down) == 1 and down[0]["reasoning"].startswith("Collegamento ai dispositivi perso")
        health = [ev for ev in e.events if ev["event"] == "instance.health"]
        assert health[-1]["data"]["status"] == "down" and e.health()[0] == 503
        assert any(ev["event"] == "apartment.changed" for ev in e.events) and e.apartment()["online"] is False
        with pytest.raises(core.MockError) as refused:
            e.create_command("dev-presa-camera", {"capability": "switch", "action": "turn_on"}, ACTOR, CORR)
        assert refused.value.args[:2] == (409, "device_offline")
        assert "Collegamento ai dispositivi non disponibile" in refused.value.args[2]
        conn.up = True
        e.tick()
        assert e.decisions[-1]["action"] == "connector_up" and e.decisions[-1]["outcome"] == "informational"
        assert [ev for ev in e.events if ev["event"] == "instance.health"][-1]["data"]["status"] == "ok"
        assert e.create_command("dev-presa-camera", {"capability": "switch", "action": "turn_on"}, ACTOR, CORR)
    asyncio.run(main())
