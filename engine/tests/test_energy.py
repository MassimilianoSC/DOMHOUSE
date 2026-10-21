"""Consumption from the power meters' telemetry (P-60 step 6, D-130): GET /energy adds up the hourly Wh the engine
saved, hours without readings count 0, a reading after a gap is spread evenly over the hours of the gap (also across
the local midnight, for kwh_today), avoided_hvac_hours is null.

Europe/Rome in 2026: CEST -> CET on Sunday 25 October (03:00 -> 02:00), so that day has 25 hours.

Run: python -m pytest engine/tests -q
"""
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from engine import core
from engine.connector.interface import StateChange
from engine.connector.simulated import SimulatedConnector
from engine.store import SqliteStore

ROME = ZoneInfo("Europe/Rome")
METERS = ["dev-misura-clima", "dev-caldaia", "dev-presa-camera"]     # the simulated catalog's, in its order (D-139: the split's meter apart)


def at(monkeypatch, moment: datetime):
    monkeypatch.setattr(core, "utcnow", lambda: moment.astimezone(UTC))


class NoCounterAtLoad(SimulatedConnector):
    """The simulated catalog without the meters' counters in devices(): only the test's readings count."""

    def devices(self):
        out = super().devices()
        for d in out:
            d.capabilities.get("power_meter", {}).pop("energy_total_wh", None)
        return out


def engine(store=None):
    return core.ApartmentEngine("apt-prova-01", NoCounterAtLoad(), seed=False, store=store)


def reading(e, device_id: str, ts: datetime, total_wh: float):
    e._apply_change(StateChange(device_id, "state", ts, capability="power_meter",
                                state={"watts": 100, "energy_total_wh": total_wh}))


def report(e, frm: datetime, to: datetime, bucket: str) -> dict:
    return e.energy({"from": core.iso(frm), "to": core.iso(to), "bucket": bucket})


def test_hours_from_the_telemetry_and_zero_where_nothing_was_read(monkeypatch):
    at(monkeypatch, datetime(2026, 10, 20, 12, 30, tzinfo=UTC))
    e = engine()
    e.store.add_telemetry("dev-presa-camera", "2026-10-20T08:00Z", 250)
    e.store.add_telemetry("dev-caldaia", "2026-10-20T08:00Z", 50)
    e.store.add_telemetry("dev-caldaia", "2026-10-20T11:00Z", 1234)
    e.store.add_telemetry("dev-tolto", "2026-10-20T10:00Z", 10)          # a meter no longer in the catalog
    e.store.add_telemetry("dev-presa-camera", "2026-10-20T07:00Z", 999)  # before `from`: not counted
    r = report(e, datetime(2026, 10, 20, 8, tzinfo=UTC), datetime(2026, 10, 21, tzinfo=UTC), "hour")
    # up to now (12:30): 08..12, the current hour included; later hours are not in the series
    assert [s["ts"] for s in r["series"]] == [f"2026-10-20T{h:02d}:00:00.000Z" for h in range(8, 13)]
    assert [s["kwh"] for s in r["series"]] == [0.3, 0.0, 0.01, 1.234, 0.0]
    assert r["total_kwh"] == 1.544 and r["avoided_hvac_hours"] is None
    assert [(d["device_id"], d["kwh"]) for d in r["by_device"]] == [
        ("dev-misura-clima", 0.0), ("dev-caldaia", 1.284), ("dev-presa-camera", 0.25), ("dev-tolto", 0.01)]
    assert r["by_device"][-1]["label"] == "dev-tolto"


def test_an_hour_that_starts_before_to_counts_entirely(monkeypatch):
    at(monkeypatch, datetime(2026, 10, 20, 23, tzinfo=UTC))
    e = engine()
    e.store.add_telemetry("dev-presa-camera", "2026-10-20T09:00Z", 400)
    r = report(e, datetime(2026, 10, 20, 8, 45, tzinfo=UTC), datetime(2026, 10, 20, 9, 15, tzinfo=UTC), "hour")
    assert [(s["ts"], s["kwh"]) for s in r["series"]] == [("2026-10-20T08:00:00.000Z", 0.0),
                                                         ("2026-10-20T09:00:00.000Z", 0.4)]


def test_days_from_local_midnight_with_the_25_hour_day(monkeypatch):
    at(monkeypatch, datetime(2026, 11, 1, tzinfo=UTC))
    e = engine()
    e.store.add_telemetry("dev-presa-camera", "2026-10-24T21:00Z", 100)  # 23:00 on the 24th (CEST)
    e.store.add_telemetry("dev-presa-camera", "2026-10-24T22:00Z", 200)  # 00:00 on the 25th (CEST)
    e.store.add_telemetry("dev-presa-camera", "2026-10-25T22:00Z", 300)  # 23:00 on the 25th (CET): its 25th hour
    e.store.add_telemetry("dev-presa-camera", "2026-10-25T23:00Z", 400)  # 00:00 on the 26th (CET)
    r = report(e, datetime(2026, 10, 24, tzinfo=ROME), datetime(2026, 10, 27, tzinfo=ROME), "day")
    assert [(s["ts"], s["kwh"]) for s in r["series"]] == [
        ("2026-10-23T22:00:00.000Z", 0.1), ("2026-10-24T22:00:00.000Z", 0.5), ("2026-10-25T23:00:00.000Z", 0.4)]


def test_a_gap_is_spread_over_its_hours_also_across_midnight(monkeypatch):
    e = engine()
    before = datetime(2026, 10, 20, 22, 30, tzinfo=ROME)                 # 20:30 UTC
    after = datetime(2026, 10, 21, 1, 30, tzinfo=ROME)                   # 23:30 UTC, three hours later
    reading(e, "dev-presa-camera", before, 1000)
    reading(e, "dev-presa-camera", after, 1600)                          # 600 Wh in three hours: 200 Wh an hour
    rows = {h: round(wh, 6) for _, h, wh in e.store.telemetry("dev-presa-camera")}
    assert rows == {"2026-10-20T20:00Z": 100, "2026-10-20T21:00Z": 200, "2026-10-20T22:00Z": 200,
                    "2026-10-20T23:00Z": 100}
    # today (the 21st, local) is only what came after the local midnight (22:00 UTC): 300 Wh
    assert e.devices["dev-presa-camera"]["capabilities"]["power_meter"]["kwh_today"] == 0.3
    at(monkeypatch, datetime(2026, 10, 22, tzinfo=UTC))
    r = report(e, datetime(2026, 10, 20, tzinfo=ROME), datetime(2026, 10, 22, tzinfo=ROME), "day")
    assert [s["kwh"] for s in r["series"]] == [0.3, 0.3]


def test_a_counter_back_to_zero_counts_from_zero_and_readings_out_of_order_stay_in_their_hour():
    e = engine()
    t = datetime(2026, 10, 20, 10, 10, tzinfo=UTC)
    reading(e, "dev-presa-camera", t, 5000)
    reading(e, "dev-presa-camera", t + timedelta(minutes=20), 80)       # restarted: 80 Wh since the restart
    reading(e, "dev-presa-camera", t + timedelta(minutes=10), 100)      # late: 20 Wh, in its own hour
    assert sum(wh for _, _, wh in e.store.telemetry("dev-presa-camera")) == pytest.approx(100)
    assert {h for _, h, _ in e.store.telemetry("dev-presa-camera")} == {"2026-10-20T10:00Z"}


def test_the_same_report_after_a_restart_on_sqlite(tmp_path, monkeypatch):
    at(monkeypatch, datetime(2026, 10, 21, 6, tzinfo=UTC))
    db = tmp_path / "engine.db"
    first = engine(SqliteStore(db))
    reading(first, "dev-caldaia", datetime(2026, 10, 21, 1, 0, tzinfo=UTC), 10_000)
    reading(first, "dev-caldaia", datetime(2026, 10, 21, 3, 0, tzinfo=UTC), 10_400)
    frm, to = datetime(2026, 10, 21, tzinfo=UTC), datetime(2026, 10, 21, 6, tzinfo=UTC)
    before = report(first, frm, to, "hour")
    first.store.close()
    second = engine(SqliteStore(db))
    assert report(second, frm, to, "hour") == before
    assert [s["kwh"] for s in before["series"]] == [0.0, 0.2, 0.2, 0.0, 0.0, 0.0]
    second.store.close()


# -------- the simulated power meters (step 6b): a cumulative counter that grows with the watts --------
class Clock:
    """One clock for the engine and the simulated connector."""

    def __init__(self, monkeypatch, start: datetime):
        self.now = start
        from engine.connector import simulated
        monkeypatch.setattr(core, "utcnow", lambda: self.now)
        monkeypatch.setattr(simulated, "utcnow", lambda: self.now)

    def advance(self, **kw):
        self.now += timedelta(**kw)


def test_the_simulated_counter_grows_with_the_watts_and_only_meters_drawing_power_report(monkeypatch):
    clock = Clock(monkeypatch, datetime(2026, 10, 20, 10, 0, tzinfo=UTC))
    conn = SimulatedConnector()                          # Rimini: split at 870 W, boiler at 95 W, socket at 0 W
    clock.advance(minutes=30)
    readings = {c.device_id: c.state for c in conn.read_meters(notify=False)}
    assert set(readings) == {"dev-misura-clima", "dev-caldaia"}
    assert readings["dev-misura-clima"] == {"watts": 870, "energy_total_wh": 812_400 + 435}
    assert readings["dev-caldaia"] == {"watts": 95, "energy_total_wh": 96_300 + 47.5}
    assert all("kwh_today" not in s for s in readings.values())


def test_a_command_counts_the_old_power_up_to_the_change(monkeypatch):
    import asyncio

    from engine.connector.interface import ConnectorCommand
    from engine.connector import simulated
    clock = Clock(monkeypatch, datetime(2026, 10, 20, 10, 0, tzinfo=UTC))
    monkeypatch.setattr(simulated, "SENT_AFTER_S", 0)
    monkeypatch.setattr(simulated, "VERIFYING_AFTER_S", 0)
    monkeypatch.setattr(simulated, "OUTCOME_AFTER_S", 0)
    conn = SimulatedConnector()
    clock.advance(hours=1)
    cmd = ConnectorCommand(command_id="c1", correlation_id="x", device_id="dev-presa-camera", capability="switch",
                           target={"on": True}, deadline=clock.now + timedelta(seconds=30))
    asyncio.run(conn.execute(cmd, lambda step: None))
    clock.advance(minutes=15)                            # 15 minutes at 1200 W: 300 Wh
    socket = {c.device_id: c.state for c in conn.read_meters(notify=False)}["dev-presa-camera"]
    assert socket == {"watts": 1200, "energy_total_wh": 41_700 + 300}


def test_simulated_readings_reach_the_telemetry_and_a_meter_back_online_brings_its_gap(monkeypatch):
    clock = Clock(monkeypatch, datetime(2026, 10, 20, 10, 0, tzinfo=UTC))
    conn = SimulatedConnector()
    e = core.ApartmentEngine("apt-prova-01", conn, seed=False)      # loads the counters: the first reading
    for _ in range(3):                                               # three readings, ten minutes apart
        clock.advance(minutes=10)
        for change in conn.read_meters(notify=False):
            e._apply_change(change)
    split = sum(wh for _, _, wh in e.store.telemetry("dev-misura-clima"))
    assert split == pytest.approx(870 / 2)                          # 30 minutes at 870 W
    assert e.devices["dev-misura-clima"]["capabilities"]["power_meter"]["kwh_today"] == 0.435
    # the boiler's meter goes away for two hours and comes back with the whole gap: spread over its hours
    for change in conn.set_online("dev-caldaia", False, notify=False):
        e._apply_change(change)
    clock.advance(hours=2)
    for change in conn.set_online("dev-caldaia", True, notify=False):
        e._apply_change(change)
    rows = {h: wh for _, h, wh in e.store.telemetry("dev-caldaia")}
    assert rows == pytest.approx({"2026-10-20T10:00Z": 95 * 0.5 + 95 * 0.5, "2026-10-20T11:00Z": 95.0,
                                  "2026-10-20T12:00Z": 95 * 0.5}, abs=0.01)   # the counter keeps 3 decimals


def test_a_meter_drawing_power_reads_through_changes_on_its_own():
    import asyncio

    async def main():
        conn = SimulatedConnector()
        conn.reading_every_s = 0.05
        got = []

        async def read():
            async for change in conn.changes():
                got.append(change)
                if len(got) >= 4:
                    return
        await asyncio.wait_for(read(), timeout=5)
        return got
    got = asyncio.run(main())
    assert {c.device_id for c in got} == {"dev-misura-clima", "dev-caldaia"}
    assert all(c.capability == "power_meter" and "energy_total_wh" in c.state for c in got)


# -------- the demonstration apartments (step 6c): an invented profile before the engine started --------
def test_a_demonstration_shows_a_repeatable_profile_from_2026_per_meter(monkeypatch):
    Clock(monkeypatch, datetime(2026, 10, 20, 15, 30, tzinfo=UTC))
    a, b = core.ApartmentEngine("apt-rimini-01"), core.ApartmentEngine("apt-rimini-01")   # seeded, in memory
    march = report(a, datetime(2026, 3, 1, tzinfo=ROME), datetime(2026, 3, 31, tzinfo=ROME), "day")
    assert march == report(b, datetime(2026, 3, 1, tzinfo=ROME), datetime(2026, 3, 31, tzinfo=ROME), "day")
    assert all(s["kwh"] > 0 for s in march["series"]) and march["total_kwh"] > 0
    shares = [d["kwh"] / march["total_kwh"] for d in march["by_device"]]
    assert [d["device_id"] for d in march["by_device"]] == METERS and shares[0] > shares[1] > shares[2] > 0
    december = report(a, datetime(2025, 12, 1, tzinfo=ROME), datetime(2026, 1, 1, tzinfo=ROME), "day")
    assert december["total_kwh"] == 0                                # before the profile: nothing
    first = report(a, datetime(2025, 12, 31, 22, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC), "hour")
    assert [s["kwh"] > 0 for s in first["series"]] == [False, True]  # from 00:00 in Rome (23:00 UTC)


def test_the_profile_ends_at_the_hour_the_engine_started_and_kwh_today_agrees(monkeypatch):
    Clock(monkeypatch, datetime(2026, 10, 20, 15, 30, tzinfo=UTC))
    e = core.ApartmentEngine("apt-rimini-01")
    hours = report(e, datetime(2026, 10, 20, 13, tzinfo=UTC), datetime(2026, 10, 20, 16, tzinfo=UTC), "hour")
    assert [s["kwh"] > 0 for s in hours["series"]] == [True, True, False]   # 15:00 on: only what the meters read
    today = report(e, datetime(2026, 10, 20, tzinfo=ROME), datetime(2026, 10, 20, 15, 30, tzinfo=UTC), "day")
    kwh_today = sum(d["capabilities"]["power_meter"]["kwh_today"] for d in e.devices.values()
                    if "power_meter" in d["capabilities"])
    assert today["total_kwh"] == pytest.approx(kwh_today, abs=0.002) and kwh_today > 0   # the list and the cards agree


def test_a_restart_on_sqlite_keeps_the_profile_and_a_plain_engine_has_none(tmp_path, monkeypatch):
    clock = Clock(monkeypatch, datetime(2026, 10, 20, 15, 30, tzinfo=UTC))
    db = tmp_path / "engine.db"
    first = core.ApartmentEngine("apt-dev", SimulatedConnector(), seed=True, store=SqliteStore(db))
    window = (datetime(2026, 10, 20, 10, tzinfo=UTC), datetime(2026, 10, 20, 15, tzinfo=UTC))
    before = report(first, *window, "hour")
    first.store.close()
    clock.advance(days=2)                                            # restarted two days later: same profile end
    second = core.ApartmentEngine("apt-dev", SimulatedConnector(), seed=True, store=SqliteStore(db))
    assert second.restored and report(second, *window, "hour") == before and before["total_kwh"] > 0
    second.store.close()
    plain = core.ApartmentEngine("apt-prova-01", NoCounterAtLoad(), seed=False)
    assert report(plain, datetime(2026, 3, 1, tzinfo=ROME), datetime(2026, 3, 31, tzinfo=ROME), "day")["total_kwh"] == 0


def test_spread_pieces_add_up_exactly_also_with_microseconds():
    """Linux timestamps have microseconds: 500 Wh in one hour must be stored as 500, not 499.99999999999994 (the red of
    the lot 20 run in the Linux container)."""
    start = datetime(2026, 10, 21, 11, 16, 2, 497_000, tzinfo=UTC)       # the last reading, saved to the millisecond
    for us in (1, 8, 36):                     # wh * s / total gave 499.99999999999994 for these (measured on 21 Oct)
        assert core.spread(500.0, start, start + timedelta(microseconds=us)) == [("2026-10-21T11:00Z", 500.0)]
    end = start + timedelta(hours=2, minutes=13, microseconds=7)            # across three hours
    for wh in (500.0, 100.0, 0.1, 1234.5678):
        assert sum(w for _, w in core.spread(wh, start, end)) == wh
