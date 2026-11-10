"""Il rapporto del rodaggio (D-210): una settimana di produzione a confronto con quella prima. Sola lettura: solo
`gcloud logging read` e `gcloud monitoring alerts list`, nessuna scrittura, nessun token a mano (D-212).

    CLOUDSDK_CORE_ACCOUNT=<account proprietario> GCP_PROJECT_ID=<progetto> python scripts/monitoring/rodaggio.py
    ... python scripts/monitoring/rodaggio.py --dal 2026-11-09 --al 2026-11-16      # date locali, «al» escluso

Senza date: l'ultima settimana intera, da lunedì a lunedì (ora di Roma). Il periodo di confronto è quello di uguale
durata subito prima. Cosa stampa, per i due periodi:
1. disponibilità del server di produzione: le richieste del controllo di raggiungibilità domotica-bff-healthz (ogni
   60 s da 3 regioni) nei registri di Cloud Run; un minuto è «fermo» se il controllo esisteva e nessuna richiesta ha
   avuto 200. I minuti in cui il controllo non esisteva perché cancellato da una persona (lo spegnimento voluto di
   D-195: VM ferma, controllo cancellato, poi ricreato da setup.sh) sono «spento per scelta» e non contano: lo dice il
   registro di audit delle attività amministrative (Create/DeleteUptimeCheckConfig), sempre attivo, 400 giorni;
2. riavvii: «engine started» dei motori, «broker started_at=» del controllo del broker (valori diversi = avvii), e
   i minuti di VM ferma per scelta (instances.stop / start nello stesso registro di audit);
3. allarmi scattati: gli incidenti di Cloud Monitoring (gcloud monitoring alerts list), per politica, con i minuti aperti;
4. certificato del broker: righe «broker cert new / renew failed / revoked» e l'ultimo «cert_days»;
5. righe di errore del server (level error o severity ERROR) e dei motori (level error), raggruppate per messaggio;
6. memoria e disco della VM dalla riga «vm mem_used_pct=… disk_used_pct=…» del controllo ogni 5 minuti (media,
   massimo, ultimo valore); avvii di istanza di Cloud Run per motivo e risposte 429 e 5xx;
7. uscite della VM senza NAT (dal 10 novembre): le righe «egress ok|failed server= registry= acme=» del controllo, una
   l'ora: giorni coperti, prove riuscite e fallite, quale uscita è fallita. Cloud Logging è provato dalle righe stesse.
Un dato che non c'è ancora (per esempio la riga della VM prima dell'installazione del broker, B1/B4) è detto così.
`gcloud` si chiama attraverso bash: su Windows il suo .cmd passerebbe i filtri a cmd.exe, che storpia >= e virgolette.
"""
import argparse
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROME = ZoneInfo("Europe/Rome")
SERVICE = "domotica-bff"
UPTIME_AGENT = "GoogleStackdriverMonitoring-UptimeChecks"
CHECK_NAME = "domotica-bff-healthz"
AUDIT = 'log_id("cloudaudit.googleapis.com/activity")'
# how far back the admin activity log is read: 400 days (all Google keeps) made Cloud Logging answer 500; with no
# event in the window the check counts as existing and the VM as running, the normal case
AUDIT_DAYS = 90
RUN = f'resource.type="cloud_run_revision" AND resource.labels.service_name="{SERVICE}"'
SYSLOG = 'resource.type="gce_instance" AND log_id("syslog")'
NOT_YET = "dato non ancora disponibile"
NO_CHECKS = "spento per scelta tutto il periodo"


class Fermo(Exception):
    pass


def gcloud(args: list[str]) -> str:
    """One read-only gcloud call; its standard output. The project comes from GCP_PROJECT_ID, the account from
    CLOUDSDK_CORE_ACCOUNT (or gcloud's own default)."""
    project = os.environ.get("GCP_PROJECT_ID", "")
    if not project:
        raise Fermo("Manca GCP_PROJECT_ID: scrivi GCP_PROJECT_ID=<progetto> prima del comando.")
    full = [*args, f"--project={project}", "--quiet"]
    bash = shutil.which("bash")
    cmd = [bash, "-c", 'gcloud "$@"', "gcloud", *full] if bash else ["gcloud", *full]
    # no MSYS_NO_PATHCONV: Git Bash's gcloud wrapper needs its own path converted (E-11); no argument here starts with /
    done = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode:
        raise Fermo(f"gcloud {' '.join(args[:3])} non riuscito: {done.stderr.strip()[-400:]}")
    return done.stdout


def utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def logs(flt: str, start: datetime, end: datetime, fields: str = "") -> list[dict]:
    """The entries of a filter in [start, end), as JSON (only the fields asked, when given)."""
    full = f'({flt}) AND timestamp>="{utc(start)}" AND timestamp<"{utc(end)}"'
    fmt = f"json({fields})" if fields else "json"
    return json.loads(gcloud(["logging", "read", full, f"--format={fmt}", "--order=asc"]) or "[]")


def ts(entry: dict) -> datetime:
    return datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00"))


def dig(entry: dict, path: str):
    for key in path.split("."):
        entry = entry.get(key) if isinstance(entry, dict) else None
    return entry


# ---- the six parts ------------------------------------------------------------------------------------------------
def windows_off(events: list[tuple[datetime, bool, str]], end: datetime) -> list[tuple[datetime, datetime, str]]:
    """[(from, to, who)] while something was off, from (moment, on?, who) events in time order. Before the first event
    the state is the opposite of it (a first «create» means it did not exist before); still off at the end: to = end."""
    out, off_from, who = [], None, ""
    if events and events[0][1]:
        off_from, who = datetime.min.replace(tzinfo=timezone.utc), "non ancora creato"
    for moment, on, by in events:
        if on and off_from is not None:
            out.append((off_from, moment, who))
            off_from = None
        elif not on and off_from is None:
            off_from, who = moment, by
    if off_from is not None:
        out.append((off_from, end, who))
    return out


def audit(methods: str, end: datetime, fields: str) -> list[dict]:
    return logs(f"{AUDIT} AND ({methods})", end - timedelta(days=AUDIT_DAYS), end, fields)


def check_off(end: datetime) -> list[tuple[datetime, datetime, str]]:
    """When the uptime check did not exist, and who deleted it (admin activity audit log)."""
    events = []
    for e in audit('protoPayload.methodName:"UptimeCheckConfig"', end,
                   "timestamp,protoPayload.methodName,protoPayload.resourceName,"
                   "protoPayload.request.uptimeCheckConfig.displayName,protoPayload.authenticationInfo.principalEmail"):
        method = dig(e, "protoPayload.methodName") or ""
        ours = (dig(e, "protoPayload.request.uptimeCheckConfig.displayName") == CHECK_NAME if method.endswith("Create" + "UptimeCheckConfig")
                else f"/uptimeCheckConfigs/{CHECK_NAME}-" in (dig(e, "protoPayload.resourceName") or ""))
        if ours and not method.endswith("UpdateUptimeCheckConfig"):
            events.append((ts(e), not method.endswith("DeleteUptimeCheckConfig"),
                           dig(e, "protoPayload.authenticationInfo.principalEmail") or "?"))
    return windows_off(sorted(events), end)


def vm_off(end: datetime) -> list[tuple[datetime, datetime, str]]:
    """When the VM was stopped by someone (instances.stop / start, the entry that closes each operation)."""
    events = []
    for e in audit('protoPayload.methodName="v1.compute.instances.stop" OR protoPayload.methodName="v1.compute.instances.start"',
                   end, "timestamp,protoPayload.methodName,protoPayload.authenticationInfo.principalEmail,operation"):
        if dig(e, "operation.last") or not dig(e, "operation"):
            events.append((ts(e), dig(e, "protoPayload.methodName").endswith(".start"),
                           dig(e, "protoPayload.authenticationInfo.principalEmail") or "?"))
    return windows_off(sorted(events), end)


def minutes_in(windows, start: datetime, stop: datetime) -> set[int]:
    """The minutes of [start, stop) that fall in one of the windows."""
    out = set()
    for a, b, _ in windows:
        first = max(int((a - start).total_seconds() // 60), 0) if a > start else 0
        last = min(int(-(-(b - start).total_seconds() // 60)), int((stop - start).total_seconds() // 60))
        out.update(range(first, max(last, first)))
    return out


def availability(start: datetime, end: datetime, now: datetime) -> dict:
    stop = min(end, now)
    entries = logs(f'{RUN} AND log_id("run.googleapis.com/requests") AND httpRequest.userAgent:"{UPTIME_AGENT}"',
                   start, stop, "timestamp,httpRequest.status")
    minutes = max(int((stop - start).total_seconds() // 60), 0)
    windows = [w for w in check_off(stop) if w[1] > start and w[0] < stop]
    off = minutes_in(windows, start, stop)
    ok = {int((ts(e) - start).total_seconds() // 60) for e in entries if dig(e, "httpRequest.status") == 200}
    down = sorted(m for m in range(minutes) if m not in ok and m not in off)
    measured = minutes - len(off)
    # a period with the check deleted throughout is said as such, never as 0 % (D-212)
    return {"minutes": minutes, "off": len(off), "off_by": sorted({w[2] for w in windows}),
            "down": len(down) if measured else None, "checks": len(entries),
            "failed": sum(1 for e in entries if dig(e, "httpRequest.status") != 200),
            "pct": round(100 * (measured - len(down)) / measured, 3) if measured else None,
            "longest": longest_run(down) if measured else None}


def longest_run(minutes: list[int]) -> int:
    best = run = 0
    for i, m in enumerate(minutes):
        run = run + 1 if i and m == minutes[i - 1] + 1 else 1
        best = max(best, run)
    return best


def restarts(start: datetime, end: datetime) -> dict:
    engines = Counter(dig(e, "jsonPayload.apartment_id") or "?" for e in logs(
        'log_id("domhouse_engine") AND jsonPayload.msg="engine started"', start, end, "timestamp,jsonPayload.apartment_id"))
    seen = [re.search(r"broker started_at=(\S+)", dig(e, "jsonPayload.message") or "") for e in logs(
        f'{SYSLOG} AND jsonPayload.message:"broker started_at="', start, end, "timestamp,jsonPayload.message")]
    starts = {m.group(1) for m in seen if m}
    broker = None if not seen else sum(1 for s in starts if start <= parse_any(s) < end)
    windows = [w for w in vm_off(end) if w[1] > start and w[0] < end]
    return {"engines": dict(engines), "broker": broker, "vm_off": len(minutes_in(windows, start, end))}


def parse_any(text: str) -> datetime:
    text = re.sub(r"(\.\d{6})\d+", r"\1", text.replace("Z", "+00:00"))       # docker writes nanoseconds
    return datetime.fromisoformat(text)


def incidents(start: datetime, end: datetime, now: datetime) -> dict:
    alerts = json.loads(gcloud(["monitoring", "alerts", "list", "--format=json"]) or "[]")
    out: dict[str, dict] = {}
    for a in alerts:
        opened = parse_any(a["openTime"])
        closed = parse_any(a["closeTime"]) if a.get("closeTime") else now
        if opened >= end or closed < start:
            continue
        name = dig(a, "policy.displayName") or "?"
        part = out.setdefault(name, {"count": 0, "minutes": 0})
        part["count"] += 1 if opened >= start else 0
        part["minutes"] += int((min(closed, end) - max(opened, start)).total_seconds() // 60)
    return out


def certificate(start: datetime, end: datetime) -> dict:
    lines = [dig(e, "jsonPayload.message") or "" for e in logs(
        f'{SYSLOG} AND jsonPayload.message:"domhouse-check" AND jsonPayload.message:"broker "', start, end,
        "timestamp,jsonPayload.message")]
    days = [int(m.group(1)) for m in (re.search(r"broker ok cert_days=(\d+)", x) for x in lines) if m]
    return {"new": sum("broker cert new" in x for x in lines), "failed": sum("broker cert renew failed" in x for x in lines),
            "revoked": sum("broker cert revoked" in x for x in lines), "days_last": days[-1] if days else None,
            "seen": bool(lines)}


def errors(start: datetime, end: datetime) -> dict:
    server = Counter()
    for e in logs(f'{RUN} AND (jsonPayload.level="error" OR severity>=ERROR)', start, end,
                  "timestamp,jsonPayload.msg,jsonPayload.error,textPayload"):
        text = dig(e, "jsonPayload.msg") or (dig(e, "textPayload") or "?").strip().splitlines()[0]
        server[text[:120]] += 1
    engines = Counter()
    for e in logs('log_id("domhouse_engine") AND jsonPayload.level="error"', start, end,
                  "timestamp,jsonPayload.msg,jsonPayload.apartment_id"):
        engines[f'{dig(e, "jsonPayload.apartment_id") or "?"}: {(dig(e, "jsonPayload.msg") or "?")[:110]}'] += 1
    return {"server": dict(server.most_common()), "engines": dict(engines.most_common())}


def vm_and_run(start: datetime, end: datetime) -> dict:
    mem, disk = [], []
    for e in logs(f'{SYSLOG} AND jsonPayload.message:"vm mem_used_pct="', start, end, "timestamp,jsonPayload.message"):
        m = re.search(r"vm mem_used_pct=(\d+) disk_used_pct=(\d+)", dig(e, "jsonPayload.message") or "")
        if m:
            mem.append(int(m.group(1)))
            disk.append(int(m.group(2)))
    reasons = Counter()
    for e in logs(f'{RUN} AND log_id("run.googleapis.com/varlog/system") AND textPayload:"Starting new instance"',
                  start, end, "timestamp,textPayload"):
        m = re.search(r"Reason: (\w+)", dig(e, "textPayload") or "")
        reasons[m.group(1) if m else "?"] += 1
    statuses = Counter(dig(e, "httpRequest.status") for e in logs(
        f'{RUN} AND log_id("run.googleapis.com/requests") AND (httpRequest.status>=500 OR httpRequest.status=429)',
        start, end, "timestamp,httpRequest.status"))
    return {"mem": summary(mem), "disk": summary(disk), "instances": dict(reasons),
            "statuses": {str(k): v for k, v in sorted(statuses.items())}}


def egress(start: datetime, end: datetime) -> dict:
    """The hourly tries of the VM's ways out (engine-vm.sh check-all, D-212)."""
    entries = logs(f'{SYSLOG} AND jsonPayload.message:"egress "', start, end, "timestamp,jsonPayload.message")
    ok = failed = 0
    days, broken = set(), Counter()
    for e in entries:
        m = re.search(r"egress (ok|failed) server=(\S+) registry=(\S+) acme=(\S+)", dig(e, "jsonPayload.message") or "")
        if not m:
            continue
        days.add(ts(e).astimezone(ROME).date())
        if m.group(1) == "ok":
            ok += 1
            continue
        failed += 1
        for name, code, good in (("server", m.group(2), ("200", "nessuno")), ("registry", m.group(3), ("200", "401")),
                                 ("acme", m.group(4), ("200",))):
            if code not in good:
                broken[name] += 1
    period_days = (end.astimezone(ROME).date() - start.astimezone(ROME).date()).days
    return {"ok": ok, "failed": failed, "days": len(days), "period_days": period_days, "broken": dict(broken)}


def summary(values: list[int]) -> dict | None:
    if not values:
        return None
    return {"mean": round(statistics.mean(values), 1), "max": max(values), "last": values[-1], "n": len(values)}


def collect(start: datetime, end: datetime, now: datetime) -> dict:
    return {"from": start, "to": end, "availability": availability(start, end, now), "restarts": restarts(start, end),
            "incidents": incidents(start, end, now), "certificate": certificate(start, end),
            "errors": errors(start, end), "vm": vm_and_run(start, end), "egress": egress(start, end)}


# ---- printing -----------------------------------------------------------------------------------------------------
def when(d: dict) -> str:
    last = (d["to"] - timedelta(seconds=1)).astimezone(ROME)
    return f'{d["from"].astimezone(ROME):%d/%m} – {last:%d/%m}'


def pair(label: str, a, b) -> str:
    return f"   {label:<38} {str(a):<26} {b}"


def counted(items: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in items.items()) or "nessuno"


def stat(s: dict | None) -> str:
    return f'media {s["mean"]} %, massimo {s["max"]} %, ultimo {s["last"]} %' if s else NOT_YET


def render(week: dict, before: dict) -> str:
    out = [f"Rapporto del rodaggio: settimana {when(week)}, a confronto con {when(before)}", "",
           pair("", "questa settimana", "settimana prima")]
    av = [w["availability"] for w in (week, before)]
    out += ["1. Disponibilità del server di produzione",
            pair("disponibile", *[f'{a["pct"]} %' if a["pct"] is not None else NO_CHECKS for a in av]),
            pair("spento per scelta, non contato", *[f'{a["off"]} min' + (f' ({", ".join(a["off_by"])})' if a["off"] else "")
                                                      for a in av]),
            pair("minuti di fermo (il più lungo)", *[f'{a["down"]} ({a["longest"]})' if a["down"] is not None else "-"
                                                      for a in av]),
            pair("controlli / non riusciti", *[f'{a["checks"]} / {a["failed"]}' for a in av]), ""]
    rs = [w["restarts"] for w in (week, before)]
    out += ["2. Riavvii",
            pair("motori (engine started)", *[counted(r["engines"]) for r in rs]),
            pair("broker", *[r["broker"] if r["broker"] is not None else NOT_YET for r in rs]),
            pair("VM ferma per scelta", *[f'{r["vm_off"]} min' for r in rs]), ""]
    out.append("3. Allarmi scattati (incidenti, minuti aperti)")
    names = sorted(set(week["incidents"]) | set(before["incidents"]))
    for name in names:
        a, b = (w["incidents"].get(name, {"count": 0, "minutes": 0}) for w in (week, before))
        out.append(pair(name[:38], f'{a["count"]} ({a["minutes"]} min)', f'{b["count"]} ({b["minutes"]} min)'))
    if not names:
        out.append(pair("nessuno", "", ""))
    cs = [w["certificate"] for w in (week, before)]
    out += ["", "4. Certificato del broker",
            pair("rinnovi / falliti / revoche", *[f'{c["new"]} / {c["failed"]} / {c["revoked"]}' if c["seen"] else NOT_YET
                                                   for c in cs]),
            pair("giorni alla scadenza (ultimo)", *[c["days_last"] if c["days_last"] is not None else NOT_YET for c in cs]),
            "", "5. Righe di errore, per messaggio"]
    for who, key in (("server", "server"), ("motori", "engines")):
        a, b = week["errors"][key], before["errors"][key]
        out.append(f"   {who}: {sum(a.values())} questa settimana, {sum(b.values())} la settimana prima")
        for msg in list(dict.fromkeys([*a, *b]))[:15]:
            out.append(pair(f"  {msg}"[:38], a.get(msg, 0), b.get(msg, 0)))
    vs = [w["vm"] for w in (week, before)]
    out += ["", "6. VM e Cloud Run",
            pair("memoria della VM", *[stat(v["mem"]) for v in vs]),
            pair("disco della VM", *[stat(v["disk"]) for v in vs]),
            pair("avvii di istanza (motivo)", *[counted(v["instances"]) for v in vs]),
            pair("risposte 429 e 5xx", *[counted(v["statuses"]) for v in vs])]
    es = [w["egress"] for w in (week, before)]
    out += ["", "7. Uscite della VM senza NAT (server, Artifact Registry, Let's Encrypt; Cloud Logging dalle righe stesse)",
            pair("giorni coperti", *[f'{x["days"]} su {x["period_days"]}' if x["ok"] + x["failed"] else NOT_YET for x in es]),
            pair("prove riuscite / fallite", *[f'{x["ok"]} / {x["failed"]}' if x["ok"] + x["failed"] else NOT_YET for x in es]),
            pair("uscite fallite", *[counted(x["broken"]) for x in es])]
    return "\n".join(out)


def period(args, today: date) -> tuple[datetime, datetime]:
    if args.dal and args.al:
        first, last = date.fromisoformat(args.dal), date.fromisoformat(args.al)
    else:
        last = today - timedelta(days=today.weekday())           # this week's Monday: the last full week ends there
        first = last - timedelta(days=7)
    if last <= first:
        raise Fermo("«al» deve venire dopo «dal».")
    return datetime(first.year, first.month, first.day, tzinfo=ROME), datetime(last.year, last.month, last.day, tzinfo=ROME)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Rapporto settimanale del rodaggio (D-210), sola lettura.")
    parser.add_argument("--dal", help="primo giorno, AAAA-MM-GG (ora di Roma)")
    parser.add_argument("--al", help="giorno dopo l'ultimo, AAAA-MM-GG")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    try:
        start, end = period(args, now.astimezone(ROME).date())
        length = end - start
        week = collect(start, end, now)
        before = collect(start - length, start, now)
    except Fermo as stop:
        print(f"FERMO: {stop}", file=sys.stderr)
        return 1
    print(render(week, before))
    return 0


if __name__ == "__main__":
    sys.exit(main())
