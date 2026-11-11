"""The run-in report (D-210, D-212): scripts/monitoring/rodaggio.py with gcloud replaced by canned answers. What is
checked: the period (last full week, Monday to Monday in Rome), availability by minute from the uptime checks, a
period without checks said as such and never as 0 %, incidents clipped to the period, restarts, certificate lines,
errors grouped by message, the VM's line, Cloud Run's instance starts and 429/5xx, and that only read-only gcloud
commands are called."""
import importlib.util
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("rodaggio", ROOT / "scripts" / "monitoring" / "rodaggio.py")
rodaggio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rodaggio)

START = datetime(2026, 11, 16, tzinfo=rodaggio.ROME)          # Monday 16 November, 00:00 in Rome = 15th 23:00 UTC
END = START + timedelta(hours=1)                              # one hour is enough for the arithmetic


def z(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def fake(monkeypatch, answers: dict[str, list], alerts=()):
    """gcloud answering by a word of the filter; every call recorded."""
    calls = []

    def gcloud(args):
        calls.append(args)
        if args[:3] == ["monitoring", "alerts", "list"]:
            return json.dumps(list(alerts))
        assert args[:2] == ["logging", "read"], args
        for key, entries in answers.items():
            if key in args[2]:
                return json.dumps(entries)
        return "[]"
    monkeypatch.setattr(rodaggio, "gcloud", gcloud)
    return calls


def check(minute: int, status=200, second=10):
    return {"timestamp": z(START + timedelta(minutes=minute, seconds=second)), "httpRequest": {"status": status}}


def test_the_default_period_is_the_last_full_week_monday_to_monday():
    first, last = rodaggio.period(SimpleNamespace(dal=None, al=None), date(2026, 11, 18))       # a Wednesday
    assert (first.date(), last.date()) == (date(2026, 11, 9), date(2026, 11, 16)) and first.tzinfo == rodaggio.ROME
    first, last = rodaggio.period(SimpleNamespace(dal="2026-11-09", al="2026-11-11"), date(2026, 11, 18))
    assert (first.date(), last.date()) == (date(2026, 11, 9), date(2026, 11, 11))
    with pytest.raises(rodaggio.Fermo):
        rodaggio.period(SimpleNamespace(dal="2026-11-11", al="2026-11-09"), date(2026, 11, 18))


def test_availability_by_minute_from_the_uptime_checks(monkeypatch):
    checks = [check(m) for m in range(60) if not 20 <= m < 25]          # five minutes with nothing: a stop
    checks += [check(m, status=503, second=40) for m in (30, 31)]        # a failure next to a success: still up
    checks += [check(40, status=503)]
    checks = [c for c in checks if c["timestamp"] != z(START + timedelta(minutes=40, seconds=10)) or
              c["httpRequest"]["status"] != 200]                       # minute 40: only the failure
    calls = fake(monkeypatch, {"UptimeChecks": checks})
    a = rodaggio.availability(START, END, END + timedelta(days=1))
    assert (a["minutes"], a["down"], a["longest"], a["failed"]) == (60, 6, 5, 3)
    assert a["pct"] == round(100 * 54 / 60, 3)
    assert 'timestamp>="2026-11-15T23:00:00Z"' in calls[0][2] and 'timestamp<"2026-11-16T00:00:00Z"' in calls[0][2]


def audit_check(minutes, method, by="m.scardovellicrac@gmail.com"):
    entry = {"timestamp": z(START + timedelta(minutes=minutes)), "protoPayload": {
        "methodName": f"google.monitoring.v3.UptimeCheckService.{method}UptimeCheckConfig",
        "authenticationInfo": {"principalEmail": by}}}
    if method == "Create":
        entry["protoPayload"]["request"] = {"uptimeCheckConfig": {"displayName": "domotica-bff-healthz"}}
        entry["protoPayload"]["resourceName"] = "projects/p"
    else:
        entry["protoPayload"]["resourceName"] = "projects/p/uptimeCheckConfigs/domotica-bff-healthz-abc"
    return entry


def test_minutes_with_the_check_deleted_by_a_person_are_switched_off_not_down(monkeypatch):
    """D-212: the shutdown of D-195 deleted the check and setup.sh made it again; those minutes are not a stop."""
    other = audit_check(-30, "Delete")
    other["protoPayload"]["resourceName"] = "projects/p/uptimeCheckConfigs/prova-allarme-xyz"     # another check
    fake(monkeypatch, {"UptimeCheckConfig": [audit_check(-60 * 24, "Delete"), other, audit_check(20, "Create")],
                       "UptimeChecks": [check(m) for m in range(20, 60) if m != 50]})
    a = rodaggio.availability(START, END, END + timedelta(days=1))
    assert (a["off"], a["down"], a["minutes"]) == (20, 1, 60) and a["off_by"] == ["m.scardovellicrac@gmail.com"]
    assert a["pct"] == round(100 * 39 / 40, 3)                      # one minute down out of the 40 the check existed


def test_a_period_with_the_check_deleted_throughout_is_not_zero_per_cent(monkeypatch):
    fake(monkeypatch, {"UptimeCheckConfig": [audit_check(-60, "Delete")]})
    a = rodaggio.availability(START, END, END)
    assert a["pct"] is None and a["down"] is None and a["off"] == 60 and a["checks"] == 0


def test_a_vm_stopped_by_someone_is_counted_apart(monkeypatch):
    op = lambda minutes, what: {"timestamp": z(START + timedelta(minutes=minutes)), "operation": {"last": True},
                                "protoPayload": {"methodName": f"v1.compute.instances.{what}",
                                                 "authenticationInfo": {"principalEmail": "m.scardovellicrac@gmail.com"}}}
    fake(monkeypatch, {"instances.stop": [op(10, "stop"), op(25, "start")]})
    assert rodaggio.restarts(START, END)["vm_off"] == 15


def test_incidents_counted_when_they_open_and_their_minutes_clipped_to_the_period(monkeypatch):
    alerts = [{"openTime": z(START - timedelta(minutes=10)), "closeTime": z(START + timedelta(minutes=5)),
               "policy": {"displayName": "Motori: VM muta"}},                      # opened before: minutes only
              {"openTime": z(START + timedelta(minutes=50)), "policy": {"displayName": "BFF non raggiungibile"}},
              {"openTime": z(START - timedelta(days=2)), "closeTime": z(START - timedelta(days=1)),
               "policy": {"displayName": "Motori: backup mancato"}}]               # outside the period
    fake(monkeypatch, {}, alerts)
    got = rodaggio.incidents(START, END, END + timedelta(minutes=30))
    assert got == {"Motori: VM muta": {"count": 0, "minutes": 5}, "BFF non raggiungibile": {"count": 1, "minutes": 10}}


def test_restarts_certificate_errors_vm_and_cloud_run(monkeypatch):
    syslog = lambda text, minute=1: {"timestamp": z(START + timedelta(minutes=minute)), "jsonPayload": {"message": text}}
    first_start = (START + timedelta(minutes=2)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.123456789Z")
    answers = {
        'msg="engine started"': [{"timestamp": z(START), "jsonPayload": {"apartment_id": "dev"}}] * 2,
        "broker started_at=": [syslog(f"domhouse-check: broker started_at={first_start}", m) for m in (5, 10)] +
                              [syslog("domhouse-check: broker started_at=2026-11-01T10:00:00.5Z", 0)],
        '"broker "': [syslog("domhouse-check: broker ok cert_days=40"), syslog("domhouse-check: broker cert new notAfter=x"),
                      syslog("domhouse-check: broker cert renew failed (mqtt.dh-lab.eu)"),
                      syslog("domhouse-check: broker ok cert_days=39", 30)],
        'jsonPayload.level="error" OR severity>=ERROR': [
            {"timestamp": z(START), "jsonPayload": {"msg": "push failed"}},
            {"timestamp": z(START), "jsonPayload": {"msg": "push failed"}},
            {"timestamp": z(START), "textPayload": "Traceback (most recent call last):\n  File x"}],
        'log_id("domhouse_engine") AND jsonPayload.level="error"': [
            {"timestamp": z(START), "jsonPayload": {"apartment_id": "dev", "msg": "connector lost"}}],
        "vm mem_used_pct=": [syslog("domhouse-check: vm mem_used_pct=30 disk_used_pct=16"),
                             syslog("bash[4242]: vm mem_used_pct=99 disk_used_pct=99"),    # the service's copy: left out
                             syslog("domhouse-check[77]: vm mem_used_pct=50 disk_used_pct=17", 5)],
        "Starting new instance": [{"timestamp": z(START), "textPayload": "Starting new instance. Reason: AUTOSCALING - x"}],
        "httpRequest.status>=500": [{"timestamp": z(START), "httpRequest": {"status": 429}},
                                    {"timestamp": z(START), "httpRequest": {"status": 503}}],
    }
    fake(monkeypatch, answers)
    assert rodaggio.restarts(START, END) == {"engines": {"dev": 2}, "broker": 1, "vm_off": 0}       # the old start is not this period's
    assert rodaggio.certificate(START, END) == {"new": 1, "failed": 1, "revoked": 0, "days_last": 39, "seen": True}
    e = rodaggio.errors(START, END)
    assert e == {"server": {"push failed": 2, "Traceback (most recent call last):": 1}, "engines": {"dev: connector lost": 1}}
    v = rodaggio.vm_and_run(START, END)
    assert v["mem"] == {"mean": 40, "max": 50, "last": 50, "n": 2} and v["disk"]["last"] == 17
    assert v["instances"] == {"AUTOSCALING": 1} and v["statuses"] == {"429": 1, "503": 1}


def test_the_ways_out_of_the_vm_days_covered_and_what_failed(monkeypatch):
    line = lambda text, hours: {"timestamp": z(START + timedelta(hours=hours)), "jsonPayload": {"message": text}}
    fake(monkeypatch, {"egress ": [line("domhouse-check: egress ok server=200 registry=401 acme=200", 0),
                                   line("bash[105352]: egress ok server=200 registry=401 acme=200", 0),   # the copy
                                   line("domhouse-check: egress failed server=200 registry=401 acme=000", 1),
                                   line("domhouse-check: egress failed server=503 registry=000 acme=200", 25),
                                   line("domhouse-check: egress ok server=200 registry=401 acme=200", 49)]})
    got = rodaggio.egress(START, START + timedelta(days=7))
    assert got == {"ok": 2, "failed": 2, "days": 3, "period_days": 7, "broken": {"acme": 1, "server": 1, "registry": 1}}


def test_the_report_compares_two_periods_and_says_what_is_missing(monkeypatch):
    calls = fake(monkeypatch, {"UptimeChecks": [check(m) for m in range(60)]})
    week = rodaggio.collect(START, END, END)
    before = rodaggio.collect(START - timedelta(hours=1), START, END)
    text = rodaggio.render(week, before)
    assert "disponibile                            100.0 %" in text
    assert text.count(rodaggio.NOT_YET) >= 6 and rodaggio.NO_CHECKS not in text
    assert re.search(r"spento per scelta, non contato +0 min +0 min", text), text
    assert "7. Uscite della VM senza NAT" in text
    assert {tuple(c[:2]) if c[0] == "logging" else tuple(c[:3]) for c in calls} == {("logging", "read"),
                                                                                    ("monitoring", "alerts", "list")}
