"""The weekly summary's computation (P-60 step 11, D-133 point 2, D-150): the week due on Monday at 08:00 local, the
occupied nights from the bookings, consumption compared at equal occupancy (+30 % and +5 kWh, «non disponibile»
without nights of that kind), too little data, devices offline for more than a day, approvals expired, windows
recurring 3 times, the fixed sentences."""
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from bff import weekly_summary as ws

ROME = ZoneInfo("Europe/Rome")
MONDAY = date(2026, 10, 12)                                   # the week 12-18 October 2026
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=ROME)


def at(day: date, hour: int) -> str:
    return ws.iso(datetime(day.year, day.month, day.day, hour, tzinfo=ROME))


def booking(checkin: date, checkout: date, status="booked"):
    return SimpleNamespace(checkin_at=at(checkin, 15), checkout_at=at(checkout, 10), status=status)


def test_the_week_is_due_on_monday_at_eight_local():
    assert ws.last_week(datetime(2026, 10, 19, 7, 59, tzinfo=ROME), ROME) == (MONDAY, False)
    assert ws.last_week(datetime(2026, 10, 19, 8, 0, tzinfo=ROME), ROME) == (MONDAY, True)
    assert ws.last_week(datetime(2026, 10, 22, 12, 0, tzinfo=ROME), ROME) == (MONDAY, True)
    assert ws.week_id(MONDAY) == "2026-W42"


def test_occupied_nights_from_the_bookings():
    days = ws.occupied_days([booking(date(2026, 10, 12), date(2026, 10, 14)),
                             booking(date(2026, 10, 16), date(2026, 10, 18), status="cancelled")], ROME)
    assert days == {date(2026, 10, 12), date(2026, 10, 13)}   # Monday and Tuesday nights; the cancelled one ignored


def test_the_comparison_at_equal_occupancy():
    assert ws.compare([14, 14], [10, 10, 10, 10])["status"] == "anomalous"       # +40 %, +8 kWh in the week
    assert ws.compare([14], [10, 10, 10, 10])["status"] == "normal"              # +40 % but only +4 kWh
    assert ws.compare([12, 12, 12, 12, 12], [10] * 8)["status"] == "normal"      # +20 %
    assert ws.compare([14, 14], [])["status"] == "not_comparable"               # no nights of that kind before
    assert ws.compare([], [10])["status"] == "no_nights"


def nights(first: date, days: int, kwh, devices=None) -> list:
    return [ws.Night(first + timedelta(days=i), kwh(first + timedelta(days=i)),
                     devices(first + timedelta(days=i)) if devices else {}) for i in range(days)]


def build(**over):
    base = dict(nights_week=[], nights_before=[], bookings=[], devices=[], decisions=[], approvals=[],
                energy_since="2026-01-01T00:00:00.000Z", labels={"m1": "Misuratore clima"})
    base.update(over)
    return ws.build("apt-prova-01", "Europe/Rome", MONDAY, NOW.astimezone(UTC), **base)


def test_consumption_occupied_and_vacant_nights_separately_total_and_per_device():
    occupied = [booking(date(2026, 9, 14), date(2026, 9, 21)), booking(date(2026, 10, 12), date(2026, 10, 15))]
    def kwh(d):                                                 # 10 kWh with guests, 2 without; this week 16 with guests
        busy = any(b.checkin_at[:10] <= d.isoformat() < b.checkout_at[:10] for b in occupied)
        return (16 if d >= MONDAY else 10) if busy else 2
    s = build(nights_week=nights(MONDAY, 7, kwh, lambda d: {"m1": kwh(d) / 2}),
              nights_before=nights(MONDAY - timedelta(weeks=4), 28, kwh, lambda d: {"m1": kwh(d) / 2}),
              bookings=occupied)
    e = s["energy"]
    assert (e["occupied"]["nights"], e["occupied"]["kwh_per_night"], e["occupied"]["median_before"]) == (3, 16, 10)
    assert e["occupied"]["status"] == "anomalous" and e["vacant"]["status"] == "normal"
    assert e["devices"][0]["occupied"]["status"] == "anomalous"   # 8 vs 5 kWh per night, +9 kWh in the week
    assert "Consumi alti per notte con ospiti: 16 kWh contro una mediana di 10 kWh" in s["items"][0]
    assert any(i.startswith("Misuratore clima: consumi alti per notte con ospiti") for i in s["items"]) and s["notable"]


def test_never_vacant_before_is_not_comparable_and_too_little_data_says_so():
    always = [booking(date(2026, 9, 1), date(2026, 10, 12))]      # occupied every night of the 4 weeks before
    s = build(nights_week=nights(MONDAY, 7, lambda d: 30), nights_before=nights(MONDAY - timedelta(weeks=4), 28,
              lambda d: 10), bookings=always)
    assert s["energy"]["vacant"]["status"] == "not_comparable" and not s["notable"]   # never an alarm
    s = build(energy_since="2026-10-01T00:00:00.000Z")
    assert s["energy"]["available"] is False and "disponibili dal 01/10/2026" in s["energy"]["reason"]


def test_offline_approvals_and_windows():
    now = NOW.astimezone(UTC)
    devices = [{"device_id": "d1", "label": "Presa camera", "online": False, "last_seen": ws.iso(now - timedelta(hours=30))},
               {"device_id": "d2", "label": "Caldaia", "online": False, "last_seen": ws.iso(now - timedelta(hours=2))}]
    in_week = at(date(2026, 10, 14), 12)
    decisions = [{"ts": in_week, "actor": "rule:offline_alert", "action": "offline_alert", "target": {"device_id": "d1"}}]
    for i in range(3):                                        # three episodes, two decisions each (split and boiler)
        for target in ("clima", "caldaia"):
            decisions.append({"ts": in_week, "actor": "rule:window_open_off", "action": "turn_off", "correlation_id": f"c{i}",
                              "target": {"device_id": target},
                              "reasoning": "Finestra camera aperta da oltre 5 minuti"})
    decisions.append({"ts": in_week, "actor": "rule:window_open_off", "action": "turn_off", "correlation_id": "x",
                      "reasoning": "Finestra bagno aperta da oltre 5 minuti"})      # only once: not recurring
    approvals = [{"approval_id": "apr-1", "status": "expired", "description": "Spegnere la caldaia", "created_at": in_week},
                 {"approval_id": "apr-2", "status": "rejected", "description": "Altro", "created_at": in_week}]
    s = build(devices=devices, decisions=decisions, approvals=approvals)
    assert [d["device_id"] for d in s["offline"]["now"]] == ["d1"] and s["offline"]["episodes"][0]["times"] == 1
    assert [a["approval_id"] for a in s["approvals_expired"]] == ["apr-1"]
    assert s["windows"] == [{"window": "Finestra camera", "times": 3}]
    assert s["items"] == ["Presa camera è offline da più di 24 ore.",
                          "Approvazione scaduta senza risposta: Spegnere la caldaia.",
                          "Finestra camera aperta 3 volte con il clima spento dalla regola."]
    assert build()["notable"] is False and build()["items"] == []              # a week without news
