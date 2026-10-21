"""The weekly summary for the managers (P-60 step 11, D-133 point 2, D-150): the past week, Monday to Sunday in the
apartment's time zone, ready on Monday at 08:00. Everything is read through the contract (/energy, /decisions,
/approvals, /devices) and the bookings the BFF keeps; this module only computes, bff/summary_job.py runs and stores.

The four items:
- consumption, at equal occupancy (D-150): kWh per occupied night of the week against the median of the occupied
  nights of the 4 weeks before, and the same for the vacant nights; total and per device. Anomalous when at least
  ANOMALY_RATIO (+30 %) over the median AND the week's excess (difference per night x nights of that kind) is at least
  ANOMALY_MIN_KWH (+5 kWh). No nights of that kind in the 4 weeks before: «confronto non disponibile», never an alarm.
  Before 5 weeks of real data (energy_since, step 6): «dati insufficienti».
  A "night" is the local day of the evening: day D is occupied when a booking (not cancelled) has check-in day <= D <
  check-out day.
- devices offline now for more than OFFLINE_HOURS (24), and the «offline_alert» episodes of the week;
- approvals of the week that expired without an answer;
- windows that switched the climate off at least WINDOW_TIMES (3) times in the week (one episode = one correlation).
Fixed sentences, written by the code (D-150 point 5: Gemini's prose comes when a real apartment has 4 weeks of real data).
"""
import re
import statistics
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ANOMALY_RATIO = 1.30
ANOMALY_MIN_KWH = 5.0
OFFLINE_HOURS = 24
WINDOW_TIMES = 3
WEEKS_BEFORE = 4
READY_AT = time(8, 0)                 # Monday, the apartment's local time


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def last_week(now: datetime, tz: ZoneInfo) -> tuple[date, bool]:
    """(Monday of the week that ended, whether its summary is due: Monday 08:00 local has passed)."""
    local = now.astimezone(tz)
    this_monday = local.date() - timedelta(days=local.weekday())
    due = local >= datetime.combine(this_monday, READY_AT, tzinfo=tz)
    return this_monday - timedelta(days=7), due


def week_id(monday: date) -> str:
    year, week, _ = monday.isocalendar()
    return f"{year}-W{week:02d}"


def occupied_days(bookings: list, tz: ZoneInfo) -> set[date]:
    """The local days whose night is occupied (check-in day <= day < check-out day), cancelled bookings left out."""
    days: set[date] = set()
    for b in bookings:
        if b.status == "cancelled":
            continue
        first, last = parse(b.checkin_at).astimezone(tz).date(), parse(b.checkout_at).astimezone(tz).date()
        d = first
        while d < last:
            days.add(d)
            d += timedelta(days=1)
    return days


@dataclass
class Night:
    day: date
    kwh: float
    devices: dict[str, float] = field(default_factory=dict)     # device_id -> kWh of that day


def compare(week: list[float], before: list[float]) -> dict:
    """The week's kWh per night against the median of the nights before: status normal | anomalous | not_comparable."""
    if not week:
        return {"nights": 0, "kwh_per_night": None, "median_before": None, "status": "no_nights"}
    per_night = sum(week) / len(week)
    out = {"nights": len(week), "kwh_per_night": round(per_night, 2), "median_before": None, "status": "not_comparable"}
    if not before:
        return out
    median = statistics.median(before)
    out["median_before"] = round(median, 2)
    excess = (per_night - median) * len(week)
    out["status"] = ("anomalous" if per_night >= median * ANOMALY_RATIO and excess >= ANOMALY_MIN_KWH else "normal")
    return out


def energy_part(nights_week: list[Night], nights_before: list[Night], occupied: set[date],
                labels: dict[str, str]) -> dict:
    def split(nights, pick):
        occ = [pick(n) for n in nights if n.day in occupied and pick(n) is not None]
        vac = [pick(n) for n in nights if n.day not in occupied and pick(n) is not None]
        return occ, vac

    occ_w, vac_w = split(nights_week, lambda n: n.kwh)
    occ_b, vac_b = split(nights_before, lambda n: n.kwh)
    devices = []
    for device_id in sorted({d for n in nights_week + nights_before for d in n.devices}):
        o_w, v_w = split(nights_week, lambda n, d=device_id: n.devices.get(d))
        o_b, v_b = split(nights_before, lambda n, d=device_id: n.devices.get(d))
        devices.append({"device_id": device_id, "label": labels.get(device_id, device_id),
                        "occupied": compare(o_w, o_b), "vacant": compare(v_w, v_b)})
    return {"available": True, "occupied": compare(occ_w, occ_b), "vacant": compare(vac_w, vac_b), "devices": devices}


WINDOW_RE = re.compile(r"(?:^|e )(.+?) apert[ao] da oltre")


def window_part(decisions: list[dict], labels: dict[str, str]) -> list[dict]:
    episodes: dict[str, set[str]] = {}
    for d in decisions:
        if d.get("actor") != "rule:window_open_off" or d.get("action") != "turn_off":
            continue
        m = WINDOW_RE.search(d.get("reasoning") or "")
        window = m.group(1) if m else "una finestra"
        episodes.setdefault(window, set()).add(d.get("correlation_id") or d.get("decision_id"))
    return sorted(({"window": w, "times": len(c)} for w, c in episodes.items() if len(c) >= WINDOW_TIMES),
                  key=lambda x: -x["times"])


def offline_part(devices: list[dict], decisions: list[dict], now: datetime) -> dict:
    labels = {d["device_id"]: d.get("label") or d["device_id"] for d in devices}
    still = [{"device_id": d["device_id"], "label": labels[d["device_id"]], "last_seen": d.get("last_seen")}
             for d in devices if not d.get("online")
             and (not d.get("last_seen") or now - parse(d["last_seen"]) > timedelta(hours=OFFLINE_HOURS))]
    episodes: dict[str, int] = {}
    for d in decisions:
        if d.get("action") == "offline_alert":
            device_id = (d.get("target") or {}).get("device_id") or "?"
            episodes[device_id] = episodes.get(device_id, 0) + 1
    return {"now": still, "episodes": [{"device_id": k, "label": labels.get(k, k), "times": v}
                                       for k, v in sorted(episodes.items())]}


def sentences(s: dict) -> list[str]:
    """The notable items, fixed sentences in Italian; empty = a week without news."""
    out = []
    e = s["energy"]
    kinds = (("occupied", "per notte con ospiti"), ("vacant", "per notte senza ospiti"))
    if e.get("available"):
        for key, words in kinds:
            c = e[key]
            if c["status"] == "anomalous":
                out.append(f"Consumi alti {words}: {c['kwh_per_night']:g} kWh contro una mediana di "
                           f"{c['median_before']:g} kWh nelle 4 settimane prima.")
        for dev in e["devices"]:
            for key, words in kinds:
                c = dev[key]
                if c["status"] == "anomalous":
                    out.append(f"{dev['label']}: consumi alti {words}, {c['kwh_per_night']:g} kWh contro "
                               f"{c['median_before']:g} kWh.")
    for d in s["offline"]["now"]:
        out.append(f"{d['label']} è offline da più di {OFFLINE_HOURS} ore.")
    for a in s["approvals_expired"]:
        out.append(f"Approvazione scaduta senza risposta: {a['description']}.")
    for w in s["windows"]:
        out.append(f"{w['window']} aperta {w['times']} volte con il clima spento dalla regola.")
    return out


def build(apartment_id: str, tz_name: str, monday: date, now: datetime, *, nights_week: list[Night],
          nights_before: list[Night], bookings: list, devices: list[dict], decisions: list[dict],
          approvals: list[dict], energy_since: str | None, labels: dict[str, str]) -> dict:
    tz = ZoneInfo(tz_name)
    start = datetime.combine(monday, time(0, 0), tzinfo=tz)
    end = start + timedelta(days=7)
    need_from = start - timedelta(weeks=WEEKS_BEFORE)
    if energy_since and parse(energy_since) <= need_from:
        energy = energy_part(nights_week, nights_before, occupied_days(bookings, tz), labels)
    else:
        energy = {"available": False, "since": energy_since,
                  "reason": "dati insufficienti: servono 5 settimane di consumi veri"
                            + (f", disponibili dal {parse(energy_since).astimezone(tz).strftime('%d/%m/%Y')}"
                               if energy_since else "")}
    in_week = [d for d in decisions if start <= parse(d["ts"]) < end]
    summary = {
        "apartment_id": apartment_id, "week": week_id(monday), "from": iso(start), "to": iso(end),
        "generated_at": iso(now), "energy": energy,
        "offline": offline_part(devices, in_week, now),
        "approvals_expired": [{"approval_id": a["approval_id"], "description": a["description"], "created_at": a["created_at"]}
                              for a in approvals if a.get("status") == "expired" and start <= parse(a["created_at"]) < end],
        "windows": window_part(in_week, labels),
    }
    summary["items"] = sentences(summary)
    summary["notable"] = bool(summary["items"])
    return summary
