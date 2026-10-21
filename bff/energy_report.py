"""P-52 (D-92): the consumption report as a real Excel file, for a month or for a stay.

Data come from the contract's GET /energy, unchanged: always the HOURLY series, asked in pieces of at most CHUNK (the
contract allows 31 days per request, and a month of 31 days with the end of summer time lasts 31 days and one hour),
then added up here in the apartment's time zone. The amount is kWh × the price per kWh set by the organisation's admin
(the apartment's own price first). No guest data: of a stay only its id, the number of guests and the times.
D-130: the engine counts 0 for an hour without readings; the report says from when consumption is measured
(energy_since, bff/energy_since.py) and leaves the earlier hours, days and totals EMPTY, not 0.
"""
import asyncio
import io
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import xlsxwriter

from . import instances

CHUNK = timedelta(days=15)
MAX_SPAN = timedelta(days=366)
MAX_PARALLEL = 3   # lot 11 (P-57): a year-long stay is ~25 pieces; the engine never gets more than this at once
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class EnergyUnavailable(Exception):
    """The instance does not offer /energy (501)."""


@dataclass
class Usage:
    hours: dict[datetime, float] = field(default_factory=dict)     # UTC hour -> kWh
    devices: dict[str, list] = field(default_factory=dict)          # device_id -> [label, kWh]

    @property
    def total(self) -> float:
        return sum(self.hours.values())


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def pieces(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    out, cur = [], start
    while cur < end:
        nxt = min(cur + CHUNK, end)
        out.append((cur, nxt))
        cur = nxt
    return out


async def collect(apt, actor: str, start: datetime, end: datetime) -> Usage:
    """Hourly kWh and the per-device totals between start and end (UTC), from the instance."""
    gate = asyncio.Semaphore(MAX_PARALLEL)

    async def one(frm: datetime, to: datetime):
        async with gate:
            resp = await instances.call(apt, "GET", "/energy", actor=actor,
                                        params={"from": iso(frm), "to": iso(to), "bucket": "hour"})
        if resp.status_code == 501:
            raise EnergyUnavailable()
        resp.raise_for_status()
        return resp.json()

    usage = Usage()
    for body in await asyncio.gather(*(one(a, b) for a, b in pieces(start, end))):
        for point in body.get("series") or []:
            hour = parse(point["ts"])
            usage.hours[hour] = usage.hours.get(hour, 0.0) + float(point.get("kwh") or 0)
        for d in body.get("by_device") or []:
            entry = usage.devices.setdefault(d["device_id"], [d.get("label") or d["device_id"], 0.0])
            entry[1] += float(d.get("kwh") or 0)
    return usage


@dataclass
class Report:
    organisation: str
    apartment: str
    apartment_id: str
    timezone: str
    start: datetime
    end: datetime
    in_progress: bool
    price: float | None
    title: str                                   # "Rendiconto mensile" / "Rendiconto del soggiorno"
    period: str                                  # e.g. "ottobre 2026" or the stay's local times
    stay: dict | None = None                     # {booking_id, guests, status}
    energy_since: str | None = None              # D-130: first hour with measured consumption; None = none yet


MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre",
          "novembre", "dicembre"]


def month_label(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]} {year}"


def local_text(dt: datetime, tz: ZoneInfo) -> str:
    return dt.astimezone(tz).strftime("%d/%m/%Y %H:%M")


def workbook(r: Report, usage: Usage, generated_at: datetime) -> bytes:
    tz = ZoneInfo(r.timezone)
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    bold = wb.add_format({"bold": True})
    title = wb.add_format({"bold": True, "font_size": 14})
    kwh = wb.add_format({"num_format": "0.00"})
    eur = wb.add_format({"num_format": "#,##0.00 €"})
    price_fmt = wb.add_format({"num_format": "0.0000 €"})
    head = wb.add_format({"bold": True, "bottom": 1})

    def amount(value: float):
        return round(value * r.price, 2) if r.price is not None else None

    since = parse(r.energy_since) if r.energy_since else None
    measured = {h: v for h, v in usage.hours.items() if since is not None and h >= since}   # D-130
    if since is None:
        available = "Nessun consumo misurato finora"
    elif since <= r.start:
        available = local_text(since, tz)
    else:
        available = local_text(since, tz) + (": ore precedenti vuote" if since < r.end else ": nessun dato nel periodo")

    # --- Riepilogo
    ws = wb.add_worksheet("Riepilogo")
    ws.set_column(0, 0, 26)
    ws.set_column(1, 1, 44)
    ws.write(0, 0, f"{r.title} dei consumi", title)
    rows = [("Organizzazione", r.organisation), ("Appartamento", f"{r.apartment} ({r.apartment_id})"),
            ("Periodo", r.period), ("Dal", local_text(r.start, tz)), ("Al", local_text(r.end, tz)),
            ("Fuso orario", r.timezone), ("Consumi disponibili dal", available)]
    if r.stay:
        rows += [("Prenotazione", r.stay["booking_id"]),
                 ("Ospiti", r.stay["guests"] if r.stay.get("guests") is not None else "non indicato"),
                 ("Stato del soggiorno", r.stay["status"])]
    rows.append(("Generato il", local_text(generated_at, tz)))
    line = 2
    for label, value in rows:
        ws.write(line, 0, label, bold)
        ws.write(line, 1, value)
        line += 1
    if r.in_progress:
        ws.write(line, 1, "Periodo in corso: i dati arrivano fino al momento della generazione")
        line += 1
    line += 1
    total = sum(measured.values())
    ws.write(line, 0, "Totale kWh", bold)
    if measured:
        ws.write_number(line, 1, round(total, 2), kwh)
    ws.write(line + 1, 0, "Prezzo €/kWh", bold)
    ws.write(line + 2, 0, "Importo", bold)
    if r.price is None:
        ws.write(line + 1, 1, "prezzo non impostato")
        ws.write(line + 2, 1, "")
    else:
        ws.write_number(line + 1, 1, r.price, price_fmt)
        if measured:
            ws.write_number(line + 2, 1, amount(total), eur)

    # --- Giornaliero (days in the apartment's time zone)
    days: dict[date, float | None] = {}             # None: a day with no measured hour, left empty
    for hour, value in usage.hours.items():
        d = hour.astimezone(tz).date()
        if hour in measured:
            days[d] = (days.get(d) or 0.0) + value
        else:
            days.setdefault(d, None)
    ws = wb.add_worksheet("Giornaliero")
    ws.set_column(0, 2, 16)
    for col, h in enumerate(("Giorno", "kWh", "Importo")):
        ws.write(0, col, h, head)
    for i, d in enumerate(sorted(days), start=1):
        ws.write(i, 0, d.strftime("%d/%m/%Y"))
        if days[d] is None:
            continue
        ws.write_number(i, 1, round(days[d], 2), kwh)
        if r.price is not None:
            ws.write_number(i, 2, amount(days[d]), eur)

    # --- Orario
    ws = wb.add_worksheet("Orario")
    ws.set_column(0, 1, 18)
    for col, h in enumerate(("Ora (locale)", "kWh")):
        ws.write(0, col, h, head)
    for i, hour in enumerate(sorted(usage.hours), start=1):
        ws.write(i, 0, local_text(hour, tz))
        if hour in measured:
            ws.write_number(i, 1, round(usage.hours[hour], 3), kwh)

    # --- Dispositivi
    ws = wb.add_worksheet("Dispositivi")
    ws.set_column(0, 0, 34)
    ws.set_column(1, 2, 14)
    for col, h in enumerate(("Dispositivo", "kWh", "Importo")):
        ws.write(0, col, h, head)
    for i, (label, value) in enumerate(sorted(usage.devices.values(), key=lambda d: -d[1]), start=1):
        ws.write(i, 0, label)
        if not measured:
            continue
        ws.write_number(i, 1, round(value, 2), kwh)
        if r.price is not None:
            ws.write_number(i, 2, amount(value), eur)

    wb.close()
    return buf.getvalue()
