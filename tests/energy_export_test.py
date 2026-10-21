"""P-52 (D-92): the consumption report as an Excel file. In-process, dev auth, memory repository, the instance's
GET /energy replaced by a fake that answers the hourly series (1 kWh per hour, two meters). The .xlsx is read back
with zipfile + XML, no extra library."""
import asyncio
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from bff import instances
from bff.main import app
from bff.repository import BookingRecord, get_repository

APT, TID = "apt-bologna-01", "t-flatsharing-demo"
ADMIN, VIEWER_ONLY_RIMINI = "admin@demo.it", "proprietario@demo.it"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
DATA_FROM = datetime(2025, 1, 1, tzinfo=UTC)          # the fake engine measures from here (D-130)


def run(coro):
    return asyncio.run(coro)


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@pytest.fixture
def engine(monkeypatch):
    calls = []

    async def fake(apt, method, path, **kw):
        assert (method, path) == ("GET", "/energy")
        p = kw["params"]
        frm, to = parse(p["from"]), parse(p["to"])
        calls.append((frm, to, p["bucket"]))
        assert p["bucket"] in ("hour", "day") and to - frm <= timedelta(days=31)   # the contract's limit, always kept
        # 1 kWh an hour from DATA_FROM on, 0 before (an engine counts 0 for an hour without readings, D-130); by day
        # (energy_since's search) a day counts the hours from DATA_FROM
        step = timedelta(hours=1) if p["bucket"] == "hour" else timedelta(days=1)
        series, cur = [], frm.replace(minute=0, second=0, microsecond=0)      # whole hours, as the engine
        if p["bucket"] == "day":
            cur = cur.replace(hour=0)                                         # (the engine: local midnight)
        while cur < to:
            nxt = cur + step
            hours = max(0.0, (nxt - max(cur, DATA_FROM)).total_seconds() / 3600)
            series.append({"ts": cur.isoformat().replace("+00:00", "Z"), "kwh": hours})
            cur = nxt
        n = sum(s["kwh"] for s in series)
        body = {"from": p["from"], "to": p["to"], "bucket": p["bucket"], "total_kwh": n, "avoided_hvac_hours": None,
                "series": series, "by_device": [{"device_id": "m1", "label": "Clima", "kwh": n * 0.75},
                                                {"device_id": "m2", "label": "Caldaia", "kwh": n * 0.25}]}
        return httpx.Response(200, json=body, request=httpx.Request("GET", "http://x"))
    monkeypatch.setattr(instances, "call", fake)
    return calls


async def get(path, who=ADMIN, **params):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.get(path, params=params, headers={"X-Dev-User": who})


def sheets(content: bytes) -> dict[str, list[list]]:
    """Every sheet as rows of values (strings resolved, numbers as float)."""
    z = zipfile.ZipFile(io.BytesIO(content))
    shared = [si.findtext(".//m:t", default="", namespaces=NS) for si in
              ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS)] if "xl/sharedStrings.xml" in z.namelist() else []
    names = [s.get("name") for s in ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS)]
    out = {}
    for i, name in enumerate(names, start=1):
        rows = []
        for row in ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml")).iter(f"{{{NS['m']}}}row"):
            cells = []
            for c in row.findall("m:c", NS):
                v = c.findtext("m:v", namespaces=NS)
                cells.append(shared[int(v)] if c.get("t") == "s" else (float(v) if v is not None else None))
            rows.append(cells)
        out[name] = rows
    return out


def summary(book) -> dict:
    return {r[0]: (r[1] if len(r) > 1 else None) for r in book["Riepilogo"] if r and isinstance(r[0], str)}


def set_prices(tenant=None, apt=None):
    repo = get_repository()
    run(repo.update_tenant(TID, {"energy_price_eur_kwh": tenant}))
    a = run(repo.get_apartment(APT))
    a.energy_price_eur_kwh = apt
    run(repo.upsert_apartment(a))


def test_month_with_the_end_of_summer_time(engine):
    set_prices(tenant=0.25)
    r = run(get(f"/app/apartments/{APT}/energy/export", month="2025-10"))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert 'filename="consumi-apt-bologna-01-2025-10.xlsx"' in r.headers["content-disposition"]
    book = sheets(r.content)
    assert list(book) == ["Riepilogo", "Giornaliero", "Orario", "Dispositivi"]
    hours = 31 * 24 + 1                                       # 26 October 2025 lasts 25 hours in Europe/Rome
    s = summary(book)
    assert s["Totale kWh"] == hours and s["Prezzo €/kWh"] == 0.25 and s["Importo"] == round(hours * 0.25, 2)
    assert s["Periodo"] == "ottobre 2025" and s["Dal"] == "01/10/2025 00:00" and s["Al"] == "01/11/2025 00:00"
    days = book["Giornaliero"][1:]
    assert len(days) == 31 and days[0][0] == "01/10/2025"
    assert {d[0]: d[1] for d in days}["26/10/2025"] == 25.0
    assert len(book["Orario"]) - 1 == hours
    assert [d[0] for d in book["Dispositivi"][1:]] == ["Clima", "Caldaia"]
    hourly = [c for c in engine if c[2] == "hour"]
    assert len(hourly) >= 3 and all(c[1] - c[0] <= timedelta(days=15) for c in hourly)   # asked in pieces


def test_stay_to_the_hour_with_the_apartment_price(engine):
    set_prices(tenant=0.25, apt=0.40)
    run(get_repository().upsert_booking(BookingRecord(apartment_id=APT, booking_id="RES-XLS-1", checkin_at="2025-11-03T14:00:00Z",
                                                      checkout_at="2025-11-05T09:00:00Z", guests=3, source="italianway")))
    r = run(get(f"/app/apartments/{APT}/energy/export", booking_id="RES-XLS-1"))
    assert r.status_code == 200 and "consumi-apt-bologna-01-RES-XLS-1.xlsx" in r.headers["content-disposition"]
    s = summary(sheets(r.content))
    assert s["Totale kWh"] == 43 and s["Prezzo €/kWh"] == 0.40 and s["Importo"] == 17.2   # 14:00 day 3 → 09:00 day 5
    assert s["Prenotazione"] == "RES-XLS-1" and s["Ospiti"] == 3 and s["Dal"] == "03/11/2025 15:00"   # local time
    assert "Stato del soggiorno" in s


def test_without_any_price_only_kwh(engine):
    set_prices()
    book = sheets(run(get(f"/app/apartments/{APT}/energy/export", month="2025-09")).content)
    assert summary(book)["Prezzo €/kWh"] == "prezzo non impostato"
    assert all(len(row) == 2 for row in book["Giornaliero"][1:])          # no amount column filled


def test_refusals(engine):
    path = f"/app/apartments/{APT}/energy/export"
    assert run(get(path)).json()["error"] == "bad_request"
    assert run(get(path, month="2025-10", booking_id="x")).json()["error"] == "bad_request"
    assert run(get(path, month="2025-13")).json()["error"] == "invalid_month"
    future = (datetime.now(UTC) + timedelta(days=62)).strftime("%Y-%m")
    assert run(get(path, month=future)).json()["error"] == "invalid_month"
    assert run(get(path, booking_id="inesistente")).status_code == 404
    run(get_repository().upsert_booking(BookingRecord(apartment_id=APT, booking_id="RES-XLS-X", checkin_at="2025-11-03T14:00:00Z",
                                                      checkout_at="2025-11-05T09:00:00Z", source="italianway", status="cancelled")))
    assert run(get(path, booking_id="RES-XLS-X")).status_code == 404
    r = run(get(path, VIEWER_ONLY_RIMINI, month="2025-10"))           # an apartment outside the viewer's list
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    assert run(get(f"/app/apartments/apt-altra-01/energy/export", month="2025-10")).status_code == 404   # other tenant


def test_engine_problems(monkeypatch):
    async def not_there(*a, **k):
        return httpx.Response(501, json={"error": "not_implemented"}, request=httpx.Request("GET", "http://x"))
    monkeypatch.setattr(instances, "call", not_there)
    assert run(get(f"/app/apartments/{APT}/energy/export", month="2025-10")).json()["error"] == "not_implemented"

    async def down(*a, **k):
        raise OSError("rete")
    monkeypatch.setattr(instances, "call", down)
    r = run(get(f"/app/apartments/{APT}/energy/export", month="2025-10"))
    assert r.status_code == 502 and r.json()["error"] == "instance_unreachable"


def test_every_role_downloads_on_the_apartments_it_sees(engine):
    for who in ("lettura@demo.it", "operatore@demo.it", ADMIN):
        assert run(get(f"/app/apartments/{APT}/energy/export", who, month="2025-10")).status_code == 200, who


def test_no_guest_data_in_the_file(engine):
    run(get_repository().upsert_booking(BookingRecord(apartment_id=APT, booking_id="RES-XLS-2", checkin_at="2025-11-10T14:00:00Z",
                                                      checkout_at="2025-11-11T09:00:00Z", guests=2, source="italianway")))
    book = sheets(run(get(f"/app/apartments/{APT}/energy/export", booking_id="RES-XLS-2")).content)
    text = repr(book)
    assert "RES-XLS-2" in text and not re.search(r"@|\+39|ospite", text, re.I)


# -------- prices: admin only, validated, in the log --------
async def patch(path, who, body):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.patch(path, json=body, headers={"X-Dev-User": who})


def test_prices_are_set_by_the_admin_and_logged():
    for bad in (-1, 10.5, 0.12345):
        r = run(patch("/app/admin/tenant", ADMIN, {"energy_price_eur_kwh": bad}))
        assert r.status_code == 422 and r.json()["error"] == "invalid_price", bad
    assert run(patch("/app/admin/tenant", "operatore@demo.it", {"energy_price_eur_kwh": 0.3})).status_code == 403
    set_prices()
    r = run(patch("/app/admin/tenant", ADMIN, {"energy_price_eur_kwh": 0.2512}))
    assert r.status_code == 200 and r.json()["energy_price_eur_kwh"] == 0.2512
    r = run(patch(f"/app/admin/apartments/{APT}", ADMIN, {"energy_price_eur_kwh": 0.3}))
    assert r.status_code == 200 and r.json()["energy_price_eur_kwh"] == 0.3
    r = run(patch(f"/app/admin/apartments/{APT}", ADMIN, {"name": r.json()["name"], "energy_price_eur_kwh": None}))
    assert r.json()["energy_price_eur_kwh"] is None
    entries = [e for e in run(get_repository().list_audit(TID, 20)) if e.action == "energy_price_changed"]
    assert [(e.target.type, e.details) for e in entries[:3]] == [
        ("apartment", {"from": 0.3, "to": None}), ("apartment", {"from": None, "to": 0.3}),
        ("tenant", {"from": None, "to": 0.2512})]


def test_at_most_three_pieces_at_a_time(monkeypatch):
    """Lot 11 (P-57): a long stay is many 15-day pieces; the engine never gets more than 3 requests at once."""
    from bff import energy_report

    state = {"now": 0, "max": 0, "calls": 0}

    async def slow(apt, method, path, **kw):
        state["now"] += 1
        state["calls"] += 1
        state["max"] = max(state["max"], state["now"])
        await asyncio.sleep(0.01)
        state["now"] -= 1
        body = {"series": [], "by_device": [], "total_kwh": 0}
        return httpx.Response(200, json=body, request=httpx.Request("GET", "http://x"))
    monkeypatch.setattr(instances, "call", slow)
    start = datetime(2025, 1, 1, tzinfo=UTC)
    run(energy_report.collect(None, "p-x@pseudo.hqe.it", start, start + timedelta(days=200)))
    assert state["calls"] == 14 and state["max"] == energy_report.MAX_PARALLEL == 3


# -------- D-130: from when consumption is measured (energy_since) --------
def set_since(value):
    from bff import energy_since
    energy_since._next_try.clear()
    a = run(get_repository().get_apartment(APT))
    a.energy_since = value
    run(get_repository().upsert_apartment(a))


def test_the_first_reading_is_found_saved_and_written_in_the_report(engine):
    set_since(None)
    r = run(get(f"/app/apartments/{APT}/energy/export", month="2025-10"))
    assert r.status_code == 200, r.text
    assert run(get_repository().get_apartment(APT)).energy_since == "2025-01-01T00:00:00.000Z"
    assert summary(sheets(r.content))["Consumi disponibili dal"] == "01/01/2025 01:00"     # Rome, winter time
    days = [c for c in engine if c[2] == "day"]
    assert days and all(to - frm <= timedelta(days=31) for frm, to, _ in days)


def test_hours_before_the_first_reading_are_empty_not_zero(engine):
    set_since("2025-10-15T10:00:00.000Z")                    # 12:00 in Rome (summer time)
    r = run(get(f"/app/apartments/{APT}/energy/export", month="2025-10"))
    book = sheets(r.content)
    s = summary(book)
    measured = 31 * 24 + 1 - (14 * 24 + 12)                  # from 15/10 12:00 to the end of the month
    assert s["Consumi disponibili dal"] == "15/10/2025 12:00: ore precedenti vuote"
    assert s["Totale kWh"] == measured
    hours = {row[0]: row[1:] for row in book["Orario"][1:]}
    assert hours["15/10/2025 11:00"] == [] and hours["15/10/2025 12:00"] == [1.0]
    days = {row[0]: row[1:] for row in book["Giornaliero"][1:]}
    assert days["14/10/2025"] == [] and days["15/10/2025"][0] == 12.0 and days["16/10/2025"][0] == 24.0


def test_a_period_all_before_the_first_reading_and_no_reading_at_all(engine, monkeypatch):
    set_since("2025-12-01T00:00:00.000Z")
    s = summary(sheets(run(get(f"/app/apartments/{APT}/energy/export", month="2025-10")).content))
    assert s["Consumi disponibili dal"] == "01/12/2025 01:00: nessun dato nel periodo" and s["Totale kWh"] is None
    import sys
    monkeypatch.setattr(sys.modules[__name__], "DATA_FROM", datetime(2030, 1, 1, tzinfo=UTC))   # nothing measured
    set_since(None)
    book = sheets(run(get(f"/app/apartments/{APT}/energy/export", month="2025-10")).content)
    s = summary(book)
    assert s["Consumi disponibili dal"] == "Nessun consumo misurato finora" and s["Totale kWh"] is None
    assert all(len(row) == 1 for row in book["Orario"][1:]) and all(len(row) == 1 for row in book["Dispositivi"][1:])
    assert run(get_repository().get_apartment(APT)).energy_since is None


def test_the_search_stops_at_an_empty_window_refines_by_hour_and_waits_an_hour_to_retry(engine, monkeypatch):
    import sys

    from bff import energy_since
    monkeypatch.setattr(sys.modules[__name__], "DATA_FROM", datetime(2026, 9, 3, 5, tzinfo=UTC))
    set_since(None)
    apt = run(get_repository().get_apartment(APT))
    now = datetime(2026, 10, 21, 12, tzinfo=UTC)
    assert run(energy_since.search_and_save(apt, "actor", now)) == "2026-09-03T05:00:00.000Z"
    # two windows with consumption, the third empty: stop; then the first day by hour
    assert [c[2] for c in engine] == ["day", "day", "day", "hour"]
    engine.clear()
    set_since(None)
    monkeypatch.setattr(sys.modules[__name__], "DATA_FROM", datetime(2030, 1, 1, tzinfo=UTC))
    assert run(energy_since.search_and_save(apt, "actor", now)) is None and len(engine) == 1   # the latest window only
    assert run(energy_since.search_and_save(apt, "actor", now)) is None and len(engine) == 1   # not again within the hour


def test_the_date_only_moves_back(engine):
    from bff import energy_since
    set_since("2024-06-01T00:00:00.000Z")                    # older than what the engine shows now
    apt = run(get_repository().get_apartment(APT))
    assert run(energy_since.search_and_save(apt, "actor", datetime(2026, 10, 21, tzinfo=UTC))) == "2024-06-01T00:00:00.000Z"
    assert run(get_repository().get_apartment(APT)).energy_since == "2024-06-01T00:00:00.000Z"
