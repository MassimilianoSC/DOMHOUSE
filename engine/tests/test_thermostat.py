"""The boiler's thermostat (P-60 step 5b, R1 R2, D-126 D-128): heating.on is the intention the app sees, the relay is
the engine's. Hysteresis 0.5 °C, at least 5 "minutes" between two switches, the frost protection in an empty
apartment also with the heating disabled (one decision per switch), sensor problems as decisions. Minutes run fast:
MOCK_TIME_SCALE = real seconds per simulated minute.

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.config import DEFAULT_SETTINGS
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
BOILER, SENSOR = "dev-caldaia", "dev-ambiente-soggiorno"
MINUTE = 0.02


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


class Recorder(SimulatedConnector):
    """The simulated connector, recording what the boiler is asked."""

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.boiler_targets = []

    async def execute(self, cmd, on_progress):
        if cmd.device_id == BOILER:
            self.boiler_targets.append(dict(cmd.target))
        return await super().execute(cmd, on_progress)


def temperature(e, celsius):
    e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": celsius}}, ACTOR, CORR)


async def regulate_and_wait(e):
    e.regulate()
    await asyncio.gather(*list(e.tasks), return_exceptions=True)


async def wait_min_switch():
    await asyncio.sleep(DEFAULT_SETTINGS["THERMOSTAT_MIN_SWITCH_MINUTES"] * MINUTE + 0.05)


def test_comfort_regulation_with_hysteresis_and_minimum_time():
    async def main():
        conn = Recorder()
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False)     # boiler enabled at 21 °C, relay on
        e.ensure_started()
        assert e.devices[BOILER]["capabilities"]["heating"]["on"] is True and e.relay[BOILER] is True
        temperature(e, 21.6)                                           # above 21 + 0.5: off
        await regulate_and_wait(e)
        assert e.relay[BOILER] is False and conn.boiler_targets[-1] == {"on": False}
        assert e.devices[BOILER]["capabilities"]["heating"]["on"] is True          # the app still sees "enabled"
        temperature(e, 20.8)                                           # below 21, but too soon after the last switch
        await regulate_and_wait(e)
        assert e.relay[BOILER] is False
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.relay[BOILER] is True
        temperature(e, 21.3)                                           # inside the band: unchanged
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.relay[BOILER] is True
        # R2: in comfort the switches are not decisions
        assert not [d for d in e.decisions if d["action"].startswith("frost_") or d["action"] == "thermostat_sensor"]
    asyncio.run(main())


def test_frost_protection_in_an_empty_apartment_also_when_disabled():
    async def main():
        e = core.ApartmentEngine("apt-bologna-01", Recorder(variant=1), seed=False)   # empty, boiler disabled
        e.ensure_started()
        assert e.mode == "empty" and e.devices[BOILER]["capabilities"]["heating"]["on"] is False
        frost = e.rule("frost_protection")["params"]["celsius"]
        temperature(e, frost - 0.5)
        await regulate_and_wait(e)
        assert e.relay[BOILER] is True
        on = [d for d in e.decisions if d["action"] == "frost_heating_on"]
        assert len(on) == 1 and on[0]["actor"] == "rule:frost_protection" and "Antigelo" in on[0]["reasoning"]
        temperature(e, frost + 0.6)
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.relay[BOILER] is False and [d for d in e.decisions if d["action"] == "frost_heating_off"]
        assert e.devices[BOILER]["capabilities"]["heating"]["on"] is False          # the intention is untouched
    asyncio.run(main())


def test_a_command_applies_the_intention_and_the_relay_follows_the_room():
    async def main():
        conn = Recorder()
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False)
        e.ensure_started()
        temperature(e, 23.0)                                           # a warm room
        cmd = e.create_command(BOILER, {"capability": "heating", "action": "set_heating",
                                        "params": {"on": True, "setpoint": 20}}, ACTOR, CORR)
        end = asyncio.get_running_loop().time() + 10
        while e.commands[cmd["command_id"]]["status"] not in core.FINAL:
            assert asyncio.get_running_loop().time() < end
            await asyncio.sleep(0.02)
        assert e.commands[cmd["command_id"]]["status"] == "acked"
        heating = e.devices[BOILER]["capabilities"]["heating"]
        assert heating["on"] is True and heating["setpoint"] == 20                  # what the app asked
        assert conn.boiler_targets[-1] == {"on": False} and e.relay[BOILER] is False  # the room is warm: relay off
    asyncio.run(main())


def test_sensor_problems_are_decisions_and_the_relay_follows_the_intention():
    async def main():
        e = core.ApartmentEngine("apt-prova-01", Recorder(), seed=False)
        e.ensure_started()
        temperature(e, 23.0)
        await regulate_and_wait(e)
        assert e.relay[BOILER] is False
        e.test_state({"device_id": SENSOR, "online": False}, ACTOR, CORR)
        await wait_min_switch()
        await regulate_and_wait(e)
        issues = [d for d in e.decisions if d["action"] == "thermostat_sensor"]
        assert len(issues) == 1 and "non disponibile" in issues[0]["reasoning"]
        assert e.relay[BOILER] is True                                 # no reading: follows "enabled"
        await regulate_and_wait(e)
        assert len([d for d in e.decisions if d["action"] == "thermostat_sensor"]) == 1   # once per problem
        e.test_state({"device_id": SENSOR, "online": True}, ACTOR, CORR)
        await regulate_and_wait(e)
        back = [d for d in e.decisions if d["action"] == "thermostat_sensor"]
        assert len(back) == 2 and "ripresa" in back[-1]["reasoning"]
    asyncio.run(main())


def test_the_intention_survives_a_restart(tmp_path):
    from engine.store import SqliteStore
    db = tmp_path / "engine.db"
    conn = Recorder()

    async def first_life():
        e = core.ApartmentEngine("apt-prova-01", conn, seed=False, store=SqliteStore(db))
        e.ensure_started()
        temperature(e, 23.0)
        await regulate_and_wait(e)
        assert e.relay[BOILER] is False
        for task in [e.loop_task, e.consumer_task]:
            task.cancel()
        e.store.close()
    asyncio.run(first_life())
    second = core.ApartmentEngine("apt-prova-01", conn, seed=False, store=SqliteStore(db))
    assert second.devices[BOILER]["capabilities"]["heating"]["on"] is True and second.relay[BOILER] is False
    second.store.close()


# -------- D-164: a boiler without a usable sensor never heats by itself --------
def _no_sensor_decisions(e):
    return [d for d in e.decisions if d["action"] in ("thermostat_sensor", "frost_inactive")]


def test_without_a_sensor_a_modes_intention_keeps_the_relay_off_a_persons_is_followed():
    async def main():
        e = core.ApartmentEngine("apt-prova-01", Recorder(), seed=False)
        e.ensure_started()
        e.test_state({"device_id": SENSOR, "online": False}, ACTOR, CORR)
        e.set_mode("comfort", ACTOR, CORR, "prova")                    # a mode: the boiler must not heat unregulated
        await asyncio.sleep(0.3)
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.devices[BOILER]["capabilities"]["heating"]["on"] is True and e.relay[BOILER] is False
        issues = _no_sensor_decisions(e)
        assert [d["action"] for d in issues] == ["thermostat_sensor"]
        assert issues[0]["reasoning"].startswith("Caldaia: sensore di temperatura mancante, regolazione automatica disattivata")
        await regulate_and_wait(e)
        assert len(_no_sensor_decisions(e)) == 1                       # once per episode
        cmd = e.create_command(BOILER, {"capability": "heating", "action": "set_heating",
                                        "params": {"on": True, "setpoint": 22}}, ACTOR, CORR)   # a person's command
        while e.commands[cmd["command_id"]]["status"] not in core.FINAL:
            await asyncio.sleep(0.02)
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.relay[BOILER] is True and "segue il comando manuale" in _no_sensor_decisions(e)[-1]["reasoning"]
    asyncio.run(main())


def test_without_a_sensor_in_casa_vuota_the_frost_protection_says_it_cannot_act():
    async def main():
        e = core.ApartmentEngine("apt-prova-01", Recorder(), seed=False)
        e.ensure_started()
        e.set_mode("empty", ACTOR, CORR, "prova")
        await asyncio.sleep(0.3)
        e.test_state({"device_id": SENSOR, "online": False}, ACTOR, CORR)
        await wait_min_switch()
        await regulate_and_wait(e)
        frost = [d for d in e.decisions if d["action"] == "frost_inactive"]
        assert len(frost) == 1 and e.relay[BOILER] is False
        assert frost[0]["reasoning"].startswith("Caldaia: sensore di temperatura mancante, antigelo non attivo")
        await regulate_and_wait(e)
        assert len([d for d in e.decisions if d["action"] == "frost_inactive"]) == 1
        e.test_state({"device_id": SENSOR, "online": True}, ACTOR, CORR)
        temperature(e, 5.0)                                            # the sensor answers: the frost protection acts
        await wait_min_switch()
        await regulate_and_wait(e)
        assert e.relay[BOILER] is True and "regolazione ripresa" in _no_sensor_decisions(e)[-1]["reasoning"]
    asyncio.run(main())
