"""A8 (Autonomia, 16 November 2026): the «off» threshold of an infrared split confirmed by its meter. Before, it was
CONFIRM_OFF_WATTS, a setting changed only on the VM; an outdoor unit that keeps a heater on in winter stays above 15 W
when off. Now it is the parameter off_watts of the rule setpoint_limits (5-100 W, first value CONFIRM_OFF_WATTS),
changed from the app, valid ALSO with the rule off (a measure of the split, not a limit). One place reads it,
off_watts(split_id), that the catalog may later replace per device (§7.1). The absolute «on» seen through the meter is
the larger of CONFIRM_ON_WATTS and off_watts + 5: with off_watts above 20 a split switched off by its remote would
otherwise never be seen off.

Run: python -m pytest engine/tests/test_off_watts.py -q
"""
import asyncio

import pytest

from engine import core
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ACTOR, CORR = "prova@hqe.it", "2f0a6a4e-7a5d-4b0b-9a5e-3b1f1a2c9d10"
SPLIT, METER = "dev-clima-soggiorno", "dev-misura-clima"


def engine(**kw) -> core.ApartmentEngine:
    return core.ApartmentEngine("apt-prova-01", SimulatedConnector(variant=1), seed=False, **kw)


def set_off_watts(e, value, enabled=None):
    patch = {"rule_id": "setpoint_limits", "params": {"off_watts": value}}
    if enabled is not None:
        patch["enabled"] = enabled
    return e.update_rules({"rules": [patch]}, ACTOR, CORR)


def believed_on(e):
    e.devices[SPLIT]["capabilities"]["climate"]["on"] = True


def test_the_parameter_its_limits_and_its_first_value_from_the_setting():
    rule = engine().rule("setpoint_limits")
    assert rule["params"]["off_watts"] == 15 and rule["limits"]["off_watts"] == {"min": 5, "max": 100}
    assert engine(settings={"CONFIRM_OFF_WATTS": 30.0}).rule("setpoint_limits")["params"]["off_watts"] == 30
    assert engine(settings={"CONFIRM_OFF_WATTS": 2.0}).rule("setpoint_limits")["params"]["off_watts"] == 5   # bounded


def test_the_app_changes_it_within_its_limits():
    e = engine()
    set_off_watts(e, 40)
    assert e.rule("setpoint_limits")["params"]["off_watts"] == 40 and e.off_watts(SPLIT) == 40
    with pytest.raises(core.MockError) as refused:
        set_off_watts(e, 101)
    assert refused.value.error == "param_out_of_range"


def test_a_split_switched_off_by_its_remote_is_seen_under_the_new_threshold():
    e = engine()
    believed_on(e)
    e._power_seen(METER, {"watts": 35})                   # the outdoor unit's heater, split off
    assert SPLIT not in e.remote_low                       # 15 W: not seen off
    set_off_watts(e, 40)
    e._power_seen(METER, {"watts": 35})
    assert SPLIT in e.remote_low                           # 40 W: seen off, after REMOTE_OFF_MINUTES
    e.remote_low[SPLIT] -= 10_000
    e._remote_off_check()
    assert e.devices[SPLIT]["capabilities"]["climate"]["on"] is False
    assert "consumo sotto 40 W" in e.decisions[-1]["reasoning"]


def test_it_holds_also_with_the_rule_off():
    e = engine()
    set_off_watts(e, 40, enabled=False)
    believed_on(e)
    e._power_seen(METER, {"watts": 35})
    assert e.off_watts(SPLIT) == 40 and SPLIT in e.remote_low


def test_the_absolute_on_is_above_the_off_threshold():
    e = engine()
    set_off_watts(e, 40)
    assert e.devices[SPLIT]["capabilities"]["climate"]["on"] is False
    e._power_seen(METER, {"watts": 42})                    # above CONFIRM_ON_WATTS (20), under 40 + 5: not on
    assert e.devices[SPLIT]["capabilities"]["climate"]["on"] is False
    e._power_seen(METER, {"watts": 50})
    assert e.devices[SPLIT]["capabilities"]["climate"]["on"] is True


def test_a_switch_off_is_confirmed_under_the_new_threshold():
    async def main():
        e = engine()
        set_off_watts(e, 40)
        waiter = e._watch_power((e.devices[METER], "off", 870.0))
        e._power_seen(METER, {"watts": 35})
        return waiter.done() and waiter.result()
    assert asyncio.run(main()) is True


def test_a_rule_saved_before_gets_it_from_the_setting(tmp_path):
    db = tmp_path / "engine.db"
    first = core.ApartmentEngine("apt-prova-01", SimulatedConnector(variant=1), seed=False, store=SqliteStore(db))
    rule = first.rule("setpoint_limits")
    rule["params"].pop("off_watts")
    rule["limits"].pop("off_watts")
    first._save_apartment()                                 # an engine before A8 saved this
    first.store.close()
    again = core.ApartmentEngine("apt-prova-01", SimulatedConnector(variant=1), seed=False, store=SqliteStore(db),
                                 settings={"CONFIRM_OFF_WATTS": 25.0})
    assert again.rule("setpoint_limits")["params"]["off_watts"] == 25
    assert again.rule("setpoint_limits")["limits"]["off_watts"] == {"min": 5, "max": 100}
    again.store.close()
