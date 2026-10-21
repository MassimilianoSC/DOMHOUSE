"""scripts/monitoring/engine-alerts.sh and its policies (P-60 step 10c, D-104, D-148): the five policy files are valid,
their filters and label extractors match the real lines of engine-vm.sh check-all (with or without the PID rsyslog may
add to the tag), and the script creates only what is missing (DRY_RUN creates nothing), with gcloud replaced by a
stand-in that records what it is asked."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FOLDER = ROOT / "scripts" / "monitoring" / "engine-alerts"
SCRIPT = ROOT / "scripts" / "monitoring" / "engine-alerts.sh"
HOST = "Oct 21 10:00:00 langbrain-dev "


def policies() -> dict[str, dict]:
    return {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(FOLDER.glob("*.json"))}


def regex_of(flt: str) -> str:
    """The RE2 expression of a Logging filter's =~"..." (string escapes undone)."""
    return re.search(r'=~"((?:[^"\\]|\\.)*)"', flt).group(1).replace("\\\\", "\\")


def test_five_policies_on_the_bff_channel():
    found = policies()
    assert set(found) == {"vm-muta.json", "motore-muto.json", "motore-errori.json", "backup-mancato.json", "disco-vm.json"}
    for name, p in found.items():
        assert p["displayName"].startswith("Motori: ") and p["notificationChannels"] == ["__CHANNEL__"], name
        assert p["severity"] in ("CRITICAL", "ERROR", "WARNING") and p["documentation"]["content"], name
    assert found["vm-muta.json"]["conditions"][0]["conditionAbsent"]["duration"] == "600s"
    assert found["motore-muto.json"]["alertStrategy"]["notificationRateLimit"]["period"] == "1800s"
    assert found["motore-errori.json"]["alertStrategy"]["notificationRateLimit"]["period"] == "1800s"
    assert found["backup-mancato.json"]["alertStrategy"]["notificationRateLimit"]["period"] == "43200s"
    threshold = found["disco-vm.json"]["conditions"][0]["conditionThreshold"]
    assert (threshold["thresholdValue"], threshold["comparison"], threshold["duration"]) == (80, "COMPARISON_GT", "600s")


@pytest.mark.parametrize("tag", ["domhouse-check: ", "domhouse-check[4242]: "])
def test_the_filters_match_the_watchs_real_lines(tag):
    found = policies()
    silent = found["motore-muto.json"]["conditions"][0]["conditionMatchedLog"]
    backup = found["backup-mancato.json"]["conditions"][0]["conditionMatchedLog"]
    for line in (f"{HOST}{tag}engine silent apt-rimini-01 (nessuna risposta, codice 000)",
                 f"{HOST}{tag}engine down dev (risponde 503: connector o database)"):
        assert re.search(regex_of(silent["filter"]), line), line
        apartment = re.search(re.search(r'"(.*)"', silent["labelExtractors"]["apartment"]).group(1).replace("\\\\", "\\"),
                              line).group(1)
        assert apartment in ("apt-rimini-01", "dev")
    assert not re.search(regex_of(silent["filter"]), f"{HOST}{tag}engine ok dev")
    line = f"{HOST}{tag}backup missing dev age_h=30"
    assert re.search(regex_of(backup["filter"]), line)
    assert re.search(re.search(r'"(.*)"', backup["labelExtractors"]["apartment"]).group(1), line).group(1) == "dev"
    summary = re.search(r"METRIC_FILTER='(.*)'", SCRIPT.read_text(encoding="utf-8")).group(1)
    assert re.search(regex_of(summary), f"{HOST}{tag}domhouse-check: 3 motori, 0 muti")
    errors = found["motore-errori.json"]["conditions"][0]["conditionMatchedLog"]
    assert 'log_id("domhouse_engine")' in errors["filter"] and 'jsonPayload.level="error"' in errors["filter"]


GCLOUD = r'''#!/usr/bin/env bash
echo "gcloud $*" >> "$STUB_DIR/calls.log"
case "$*" in
  *"channels list"*) echo "projects/progetto/notificationChannels/9514864875489091801" ;;
  *"metrics describe"*) [ -f "$STUB_DIR/metric-exists" ] && exit 0 || exit 1 ;;
  *"policies list"*) [ -f "$STUB_DIR/policies-exist" ] && echo "projects/progetto/alertPolicies/1" ;;
  *"policies create"*)
    for a in "$@"; do case "$a" in --policy-from-file=*) f="${a#--policy-from-file=}" ;; esac; done
    cat "$f" >> "$STUB_DIR/created.json"; echo >> "$STUB_DIR/created.json" ;;
esac
exit 0
'''


@pytest.fixture
def alerts(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_tests", ROOT / "scripts" / "run_tests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    bash = mod.git_bash()
    if not bash:
        pytest.skip("bash non disponibile")

    def posix(path: Path) -> str:
        s = path.as_posix()
        m = re.match(r"^([A-Za-z]):/(.*)$", s)
        return f"/{m.group(1).lower()}/{m.group(2)}" if m else s

    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "gcloud").write_text(GCLOUD, encoding="utf-8", newline="\n")
    (stubs / "python3").write_text(f'#!/usr/bin/env bash\nexec "{posix(Path(sys.executable))}" "$@"\n',
                                   encoding="utf-8", newline="\n")

    def run(dry=False):
        cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}"; '
               f'{"DRY_RUN=1 " if dry else ""}GCP_PROJECT_ID=progetto bash "{posix(SCRIPT)}"')
        out = subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=60)
        calls = (stubs / "calls.log").read_text(encoding="utf-8") if (stubs / "calls.log").exists() else ""
        created = (stubs / "created.json").read_text(encoding="utf-8") if (stubs / "created.json").exists() else ""
        for f in ("calls.log", "created.json"):
            (stubs / f).unlink(missing_ok=True)
        return out, calls, created

    run.stubs = stubs
    return run


def test_dry_run_creates_nothing_and_the_real_run_creates_what_is_missing(alerts):
    out, calls, created = alerts(dry=True)
    assert out.returncode == 0, out.stderr
    assert "create" not in calls and created == "" and out.stdout.count("(prova a secco) la creerei da") == 5
    out, calls, created = alerts()
    assert out.returncode == 0, out.stderr
    assert "logging metrics create domhouse_check_runs" in calls and calls.count("policies create") == 5
    assert "__CHANNEL__" not in created and created.count("notificationChannels/9514864875489091801") == 5
    (alerts.stubs / "metric-exists").write_text("", encoding="utf-8")
    (alerts.stubs / "policies-exist").write_text("", encoding="utf-8")
    out, calls, created = alerts()                                      # again: everything exists, nothing changes
    assert out.returncode == 0 and "create" not in calls and out.stdout.count("esiste già") == 6
