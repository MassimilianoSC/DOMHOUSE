"""Tests of gravi.py (review D-4; answer 1245 = a for the accepted list). Run in the CI job «difetti-noti» before the
check itself: python -m pytest .github/audit -q"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
import gravi  # noqa: E402

TODAY = dt.date(2026, 11, 22)


def yarn_line(ghsa: str, severity: str, module: str = "lib", path: str = "a>lib") -> str:
    return json.dumps({"type": "auditAdvisory", "data": {"resolution": {"path": path}, "advisory": {
        "github_advisory_id": ghsa, "severity": severity, "module_name": module, "vulnerable_versions": "<2", "patched_versions": ">=2", "cves": []}}})


SUMMARY = json.dumps({"type": "auditSummary", "data": {"vulnerabilities": {}}})


def pip_report(*vulns, skipped=()):
    deps = [{"name": "uvicorn", "version": "0.25.0", "vulns": list(vulns)}]
    deps += [{"name": n, "skip_reason": r} for n, r in skipped]
    return {"dependencies": deps}


def osv(severities: dict):
    """A fake OSV: the record of each id with its severity; an id not listed has no record (404)."""
    return lambda url: ({"database_specific": {"severity": severities[url.rsplit("/", 1)[1]]}} if url.rsplit("/", 1)[1] in severities else None)


# ---- yarn
def test_yarn_one_line_per_advisory_even_with_many_paths():
    found = gravi.yarn_findings([yarn_line("GHSA-1", "high", path="a>lib"), yarn_line("GHSA-1", "high", path="b>lib"), SUMMARY])
    assert [f["id"] for f in found] == ["GHSA-1"]


def test_yarn_without_summary_is_no_answer():
    with pytest.raises(gravi.NoAnswer):
        gravi.yarn_findings([yarn_line("GHSA-1", "high"), '{"type":"warning"}'])


# ---- pip and OSV
def test_pip_without_the_list_is_no_answer():
    with pytest.raises(gravi.NoAnswer):
        gravi.pip_findings({})


def test_pip_severity_from_the_github_alias():
    found, _ = gravi.pip_findings(pip_report({"id": "PYSEC-1", "aliases": ["CVE-1", "GHSA-2"], "fix_versions": ["0.30.0"]}), fetch=osv({"GHSA-2": "HIGH"}))
    assert found[0]["severity"] == "high"


def test_pip_severity_from_another_alias_when_no_github_one():
    found, _ = gravi.pip_findings(pip_report({"id": "PYSEC-1", "aliases": ["CVE-9"], "fix_versions": []}), fetch=osv({"CVE-9": "CRITICAL"}))
    assert found[0]["severity"] == "critical"


def test_osv_without_severity_is_unclassified_and_green(capsys):
    found, _ = gravi.pip_findings(pip_report({"id": "PYSEC-1", "aliases": [], "fix_versions": []}), fetch=osv({}))
    assert found[0]["severity"] is None
    assert gravi.report(found, today=TODAY) == 0
    assert "non classificato" in capsys.readouterr().out


def test_osv_not_answering_is_no_answer_never_green():
    def down(url):
        raise gravi.NoAnswer("OSV non risponde")
    with pytest.raises(gravi.NoAnswer):
        gravi.pip_findings(pip_report({"id": "PYSEC-1", "aliases": ["GHSA-2"], "fix_versions": []}), fetch=down)


def test_fetch_404_is_no_record_other_errors_are_no_answer(monkeypatch):
    import urllib.error

    def raising(code):
        def urlopen(url, timeout):
            raise urllib.error.HTTPError(url, code, "x", {}, None)
        return urlopen
    monkeypatch.setattr(gravi.urllib.request, "urlopen", raising(404))
    assert gravi._fetch_json("https://api.osv.dev/v1/vulns/X") is None
    monkeypatch.setattr(gravi.urllib.request, "urlopen", raising(429))
    with pytest.raises(gravi.NoAnswer):
        gravi._fetch_json("https://api.osv.dev/v1/vulns/X")
    def offline(url, timeout):
        raise urllib.error.URLError("no network")
    monkeypatch.setattr(gravi.urllib.request, "urlopen", offline)
    with pytest.raises(gravi.NoAnswer):
        gravi._fetch_json("https://api.osv.dev/v1/vulns/X")


def test_skipped_libraries_are_printed_and_counted(capsys):
    found, skipped = gravi.pip_findings(pip_report(skipped=[("misteriosa", "Dependency not found on PyPI")]), fetch=osv({}))
    assert gravi.report(found, skipped, today=TODAY) == 0
    out = capsys.readouterr().out
    assert "non controllata" in out and "misteriosa" in out and "Librerie non controllate: 1" in out


# ---- red only for high or critical
@pytest.mark.parametrize("severity, code", [("critical", 1), ("high", 1), ("moderate", 0), ("low", 0)])
def test_red_only_for_high_or_critical(severity, code):
    assert gravi.report(gravi.yarn_findings([yarn_line("GHSA-1", severity), SUMMARY]), today=TODAY) == code


# ---- accepted advisories (answer 1245 = a)
def accepted(**over):
    entry = {"id": "GHSA-1", "libreria": "lib", "inserito": dt.date(2026, 11, 20), "scadenza": dt.date(2026, 12, 15), "motivo": "Solo nel server di sviluppo"}
    entry.update(over)
    return gravi.load_accepted({"accettati": [entry]}, TODAY)


def test_accepted_and_not_expired_is_printed_and_green(capsys):
    found = gravi.yarn_findings([yarn_line("GHSA-1", "critical"), SUMMARY])
    assert gravi.report(found, accepted=accepted(), today=TODAY) == 0
    out = capsys.readouterr().out
    assert "accettato fino al 15/12/2026, motivo: Solo nel server di sviluppo" in out


def test_accepted_on_its_last_day_still_counts_as_accepted():
    found = gravi.yarn_findings([yarn_line("GHSA-1", "high"), SUMMARY])
    assert gravi.report(found, accepted=accepted(scadenza=TODAY), today=TODAY) == 0


def test_expired_counts_again_by_itself(capsys):
    found = gravi.yarn_findings([yarn_line("GHSA-1", "high"), SUMMARY])
    entry = accepted(inserito=dt.date(2026, 11, 1), scadenza=dt.date(2026, 11, 21))
    assert gravi.report(found, accepted=entry, today=TODAY) == 1
    assert "accettazione scaduta il 21/11/2026" in capsys.readouterr().out


def test_accepted_only_for_its_library():
    found = gravi.yarn_findings([yarn_line("GHSA-1", "high", module="altra"), SUMMARY])
    assert gravi.report(found, accepted=accepted(), today=TODAY) == 1


def test_accepted_through_an_alias_of_pip():
    found, _ = gravi.pip_findings(pip_report({"id": "PYSEC-1", "aliases": ["GHSA-1"], "fix_versions": []}), fetch=osv({"PYSEC-1": "HIGH"}))
    assert gravi.report(found, accepted=accepted(libreria="uvicorn"), today=TODAY) == 0


def test_more_than_30_days_is_a_wrong_entry():
    with pytest.raises(gravi.BadAccepted, match="30 giorni"):
        accepted(inserito=dt.date(2026, 11, 20), scadenza=dt.date(2026, 12, 21))


def test_exactly_30_days_is_allowed():
    assert accepted(inserito=dt.date(2026, 11, 20), scadenza=dt.date(2026, 12, 20))


def test_without_a_reason_is_a_wrong_entry():
    with pytest.raises(gravi.BadAccepted, match="motivo"):
        accepted(motivo="  ")


@pytest.mark.parametrize("over, words", [({"scadenza": "presto"}, "non è una data"), ({"inserito": dt.date(2026, 12, 1), "scadenza": dt.date(2026, 12, 2)}, "futuro"), ({"id": ""}, "manca id")])
def test_other_wrong_entries(over, words):
    with pytest.raises(gravi.BadAccepted, match=words):
        accepted(**over)


def test_main_wrong_list_is_red_and_says_so(tmp_path, capsys):
    bad = tmp_path / "accettati.yml"
    bad.write_text(yaml.safe_dump({"accettati": [{"id": "GHSA-1", "libreria": "lib", "inserito": "2026-11-20", "scadenza": "2026-12-15"}]}), encoding="utf-8")
    yarn = tmp_path / "yarn.json"
    yarn.write_text(SUMMARY + "\n", encoding="utf-8")
    assert gravi.main(["--yarn", str(yarn), "--accettati", str(bad)], today=TODAY) == 1
    assert "da correggere" in capsys.readouterr().out


def test_main_the_repository_list_is_valid_and_empty(tmp_path):
    yarn_file = tmp_path / "yarn.json"
    yarn_file.write_text(SUMMARY + "\n", encoding="utf-8")
    assert gravi.main(["--yarn", str(yarn_file), "--accettati", str(Path(__file__).parent / "accettati.yml")], today=TODAY) == 0
    assert gravi.load_accepted(yaml.safe_load((Path(__file__).parent / "accettati.yml").read_text(encoding="utf-8")), TODAY) == []
