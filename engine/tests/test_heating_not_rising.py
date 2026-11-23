"""Item 15, E2 (answer 1232 = a; a6, 23 November 2026): «la temperatura non risale». A boiler whose relay is on while
its room stays under the frost protection's threshold for no_rise_minutes (a parameter of «Antigelo», first value 120,
30–480) gets one informational decision heating_not_rising per episode; the BFF turns it into a push. The episode ends
when the room reaches the threshold again or the relay goes off; without a usable sensor there is no alert (D-164's
decisions say it). In every mode; with «Antigelo» switched off too (answer 1260 = a).

Run: python -m pytest engine/tests -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
BOILER, SENSOR = "dev-caldaia", "dev-ambiente-soggiorno"
MINUTE = 0.01
WAIT = 30                                                  # no_rise_minutes in these tests: 0.3 s


@pytest.fixture(autouse=True)
def fast_minutes(monkeypatch):
    monkeypatch.setenv("MOCK_TIME_SCALE", str(MINUTE))


def temperature(e, celsius):
    e.test_state({"device_id": SENSOR, "capability": "temperature", "state": {"celsius": celsius}}, ACTOR, CORR)


def alerts(e):
    return [d for d in e.decisions if d["action"] == "heating_not_rising"]


async def regulate_and_wait(e):
    e.regulate()
    await asyncio.gather(*list(e.tasks), return_exceptions=True)


async def past_the_wait():
    await asyncio.sleep(WAIT * MINUTE + 0.08)


async def started():
    """apt-prova-01: comfort, boiler enabled at 21 °C, relay on; the alert waits WAIT minutes."""
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    e.ensure_started()
    e.update_rules({"rules": [{"rule_id": "frost_protection", "params": {"no_rise_minutes": WAIT}}]}, ACTOR, CORR)
    await asyncio.sleep(0.1)
    assert e.relay[BOILER] is True
    return e


def test_the_parameter_its_first_value_and_its_limits():
    e = core.ApartmentEngine("apt-prova-01", SimulatedConnector(), seed=False)
    rule = e.rule("frost_protection")
    assert rule["params"]["no_rise_minutes"] == 120 and rule["limits"]["no_rise_minutes"] == {"min": 30, "max": 480}
    with pytest.raises(core.MockError) as exc:
        e.update_rules({"rules": [{"rule_id": "frost_protection", "params": {"no_rise_minutes": 20}}]}, ACTOR, CORR)
    assert exc.value.error == "param_out_of_range"


def test_one_alert_per_episode_after_the_minutes_and_a_new_episode_after_the_room_warmed_up():
    async def main():
        e = await started()
        temperature(e, 6.0)
        await regulate_and_wait(e)
        assert alerts(e) == []                                         # not before the minutes
        await past_the_wait()
        await regulate_and_wait(e)
        await regulate_and_wait(e)
        assert len(alerts(e)) == 1
        a = alerts(e)[0]
        assert (a["actor"], a["target"], a["outcome"], a["new_value"]) == (
            "system", {"type": "device", "device_id": BOILER}, "informational", "6 °C")
        assert a["reasoning"] == "Caldaia: accesa da 30 minuti, ma la temperatura resta sotto l'antigelo (8 °C). Controlla la caldaia."
        temperature(e, 8.0)                                            # at the threshold: the episode ends
        await regulate_and_wait(e)
        temperature(e, 6.5)
        await regulate_and_wait(e)
        assert len(alerts(e)) == 1                                     # a new episode waits its minutes again
        await past_the_wait()
        await regulate_and_wait(e)
        assert len(alerts(e)) == 2
    asyncio.run(main())


def test_a_room_that_warms_up_in_time_gives_no_alert():
    async def main():
        e = await started()
        temperature(e, 6.0)
        await regulate_and_wait(e)
        await asyncio.sleep(WAIT * MINUTE / 2)
        temperature(e, 9.0)
        await regulate_and_wait(e)
        await past_the_wait()
        temperature(e, 7.5)                                            # under again: counted from now
        await regulate_and_wait(e)
        assert alerts(e) == []
    asyncio.run(main())


def test_no_alert_with_the_relay_off_or_without_a_sensor():
    async def main():
        e = await started()
        cmd = e.create_command(BOILER, {"capability": "heating", "action": "set_heating", "params": {"on": False}},
                               ACTOR, CORR)
        while e.commands[cmd["command_id"]]["status"] not in core.FINAL:
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.2)
        await regulate_and_wait(e)
        assert e.relay[BOILER] is False
        temperature(e, 6.0)                                            # comfort: nothing asks the boiler to heat
        await regulate_and_wait(e)
        await past_the_wait()
        await regulate_and_wait(e)
        assert alerts(e) == []

        e = await started()
        temperature(e, 6.0)
        await regulate_and_wait(e)
        e.test_state({"device_id": SENSOR, "online": False}, ACTOR, CORR)
        await past_the_wait()
        await regulate_and_wait(e)
        assert alerts(e) == []
    asyncio.run(main())


def test_1260_also_with_the_frost_rule_switched_off():
    async def main():
        e = await started()
        e.update_rules({"rules": [{"rule_id": "frost_protection", "enabled": False}]}, ACTOR, CORR)
        temperature(e, 6.0)
        await regulate_and_wait(e)
        await past_the_wait()
        await regulate_and_wait(e)
        assert len(alerts(e)) == 1
    asyncio.run(main())
