"""The checks of scripts/run_tests.py itself: shell scripts runnable after a checkout (P-41) and the Firestore emulator
mandatory (P-42). A throwaway git repository in a temporary folder; nothing outside it is touched."""
import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _runner():
    spec = importlib.util.spec_from_file_location("run_tests", ROOT / "scripts" / "run_tests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    if not shutil.which("git"):
        pytest.skip("git non disponibile")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / "scripts" / "sub").mkdir(parents=True)
    return tmp_path


def test_scripts_with_lf_and_executable_bit_pass(repo):
    (repo / "scripts" / "deploy.sh").write_bytes(b"#!/usr/bin/env bash\necho ok\n")
    _git(repo, "add", "scripts/deploy.sh")
    _git(repo, "update-index", "--chmod=+x", "scripts/deploy.sh")
    c = _runner().check_shell_scripts(repo)
    assert (c["tests"], c["failures"], c["errors"]) == (1, 0, 0), c


def test_a_lost_executable_bit_or_crlf_is_red_also_in_subfolders(repo):
    (repo / "scripts" / "deploy.sh").write_bytes(b"#!/usr/bin/env bash\necho ok\n")
    (repo / "scripts" / "sub" / "setup.sh").write_bytes(b"#!/usr/bin/env bash\r\necho ok\r\n")
    _git(repo, "add", "scripts")
    _git(repo, "update-index", "--chmod=+x", "scripts/sub/setup.sh")   # deploy.sh stays 100644, as after 814cd67
    c = _runner().check_shell_scripts(repo)
    assert (c["tests"], c["failures"]) == (2, 2), c
    assert "scripts/deploy.sh: mode 100644 invece di 100755" in c["note"]
    assert "scripts/sub/setup.sh: fine riga i/crlf nel repository invece di i/lf" in c["note"]


def test_executable_in_the_index_but_100644_in_the_commit_is_red(repo):
    """b284268: a commit by path from Windows recorded 100644 while the index said 100755; the index alone was green."""
    who = ("-c", "user.name=prova", "-c", "user.email=prova@example.com")
    _git(repo, "config", "core.fileMode", "false")
    (repo / "scripts" / "ci-linux.sh").write_bytes(b"#!/usr/bin/env bash\necho ok\n")
    _git(repo, "add", "scripts/ci-linux.sh")
    _git(repo, *who, "commit", "-q", "-m", "senza bit")                      # HEAD: 100644
    _git(repo, "update-index", "--chmod=+x", "scripts/ci-linux.sh")         # index: 100755
    c = _runner().check_shell_scripts(repo)
    assert (c["tests"], c["failures"]) == (1, 1), c
    assert "scripts/ci-linux.sh: mode 100644 nel commit HEAD invece di 100755" in c["note"]
    _git(repo, *who, "commit", "-q", "-m", "bit")                           # the index as it is: 100755 in HEAD
    c = _runner().check_shell_scripts(repo)
    assert (c["tests"], c["failures"], c["errors"]) == (1, 0, 0), c


def test_no_script_at_all_is_an_error(repo):
    c = _runner().check_shell_scripts(repo)
    assert c["errors"] == 1 and "nessuno script" in c["note"]


def test_missing_emulator_is_red_and_says_how_to_fix_it(tmp_path, monkeypatch):
    rt = _runner()
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.setattr(rt, "FIRESTORE_JARS", tmp_path)                       # no JAR there
    proc, host, note = rt.start_firestore_emulator(tmp_path)
    assert proc is None and host is None
    assert "Firestore obbligatorio (P-42)" in note and "setup:emulators:firestore" in note
    (tmp_path / "cloud-firestore-emulator-v1.0.0.jar").write_bytes(b"")
    monkeypatch.setattr(rt.shutil, "which", lambda name: None)                 # JAR there, no java
    assert "JDK" in rt.start_firestore_emulator(tmp_path)[2]
    c = rt.with_firestore_verdict(rt.result(tests=8), None, note)
    assert (c["tests"], c["errors"], c["note"]) == (9, 1, note)                # a red, never a skip
    c = rt.with_firestore_verdict(rt.result(tests=32), "127.0.0.1:1", "Firestore: emulatore")
    assert (c["tests"], c["errors"]) == (32, 0)


# -------- lot 11 (P-57): a pytest filter is not a failure --------
def test_a_filter_that_matches_nothing_skips_the_suite(tmp_path):
    rt = _runner()
    suite = tmp_path / "uno_test.py"
    suite.write_text("def test_uno():\n    assert True\n", encoding="utf-8")
    c = rt.run_pytest(str(suite), tmp_path, ["-k", "nessuna_corrispondenza"], {**__import__("os").environ})
    assert c["suite_skipped"] is True and c["errors"] == 0 and "filtro" in c["note"]
    c = rt.run_pytest(str(suite), tmp_path, ["-k", "uno"], {**__import__("os").environ})
    assert (c["tests"], c["errors"], c["suite_skipped"]) == (1, 0, False)


def test_a_broken_suite_is_still_red(tmp_path):
    rt = _runner()
    suite = tmp_path / "rotto_test.py"
    suite.write_text("import modulo_che_non_esiste\n", encoding="utf-8")
    c = rt.run_pytest(str(suite), tmp_path, ["-k", "qualcosa"], {**__import__("os").environ})
    assert c["errors"] >= 1 and c["suite_skipped"] is False


def test_site_and_size_are_skipped_when_filtering_pytest():
    rt = _runner()
    assert rt.selected_suites([], ["-k", "webhook"]) == rt.HTTP_SUITES + rt.LOCAL_SUITES and rt.SCRIPT_SUITE not in \
        rt.selected_suites([], ["-k", "webhook"])
    assert rt.SITE_SUITE in rt.selected_suites(["sito"], ["-k", "x"])         # chosen explicitly: it runs
    everything = rt.selected_suites([], [])
    assert everything[0] == rt.SCRIPT_SUITE and everything[-3:] == [rt.SITE_SUITE, rt.E2E_SUITE, rt.SIZE_SUITE]


# -------- lot 11 (P-57): the log-based alert watches messages the BFF really writes --------
MONITORING = ROOT / "scripts" / "monitoring"


def _messages():
    return [m.strip() for m in (MONITORING / "log-alert-messages.txt").read_text(encoding="utf-8").splitlines() if m.strip()]


def test_every_watched_message_is_written_by_the_bff():
    import json
    import logging
    import re

    code = "".join(p.read_text(encoding="utf-8") for p in (ROOT / "bff").rglob("*.py"))
    written = set(re.findall(r'warn\(\s*"([^"]+)"', code))
    missing = [m for m in _messages() if m not in written]
    assert _messages() and missing == [], f"messaggi sorvegliati che il BFF non scrive più: {missing}"
    from bff.logs import JsonFormatter   # and they land in jsonPayload.msg, where the filter looks
    line = JsonFormatter().format(logging.LogRecord("bff", logging.WARNING, "x", 1, _messages()[0], None, None))
    assert json.loads(line)["msg"] == _messages()[0]


def test_setup_renders_a_valid_log_policy():
    import json
    import os

    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash non disponibile")
    env = {**os.environ, "RENDER_ONLY": "projects/prova/notificationChannels/7", "GCP_PROJECT_ID": "prova", "EMAIL": "a@b.it"}
    out = subprocess.run([bash, str(MONITORING / "setup.sh")], capture_output=True, text=True, encoding="utf-8", env=env, check=True)
    policy = json.loads(out.stdout)
    f = policy["conditions"][0]["conditionMatchedLog"]["filter"]
    assert 'resource.labels.service_name="domotica-bff"' in f and all(f'jsonPayload.msg="{m}"' in f for m in _messages())
    assert policy["notificationChannels"] == ["projects/prova/notificationChannels/7"]
    assert policy["alertStrategy"]["notificationRateLimit"]["period"] == "3600s"   # mandatory for log-based alerts


def test_setup_renders_the_alert_on_cloud_runs_429():
    """E-27: the filter that on the logs of 23 October finds the 111 refused requests of the two outages."""
    import json
    import os

    bash = shutil.which("bash")
    if not bash:
        pytest.skip("bash non disponibile")
    env = {**os.environ, "RENDER_ONLY_PLATFORM": "projects/prova/notificationChannels/7", "GCP_PROJECT_ID": "prova",
           "EMAIL": "a@b.it"}
    out = subprocess.run([bash, str(MONITORING / "setup.sh")], capture_output=True, text=True, encoding="utf-8", env=env, check=True)
    policy = json.loads(out.stdout)
    assert policy["conditions"][0]["conditionMatchedLog"]["filter"] == (
        'resource.type="cloud_run_revision" AND resource.labels.service_name="domotica-bff" AND httpRequest.status=429 '
        'AND textPayload:"no available instance"')
    assert policy["notificationChannels"] == ["projects/prova/notificationChannels/7"]
    assert policy["alertStrategy"]["notificationRateLimit"]["period"] == "1800s" and policy["severity"] == "CRITICAL"


SETUP_GCLOUD = r"""#!/usr/bin/env bash
echo "gcloud $*" >> "$STUB_DIR/calls.log"
for a in "$@"; do case "$a" in --policy-from-file=*) FILE="${a#--policy-from-file=}" ;; esac; done
case "$*" in
  *"services describe"*) echo '["https://servizio-1.europe-west8.run.app"]' ;;
  *"channels list"*) echo projects/p/notificationChannels/7 ;;
  *"uptime list-configs"*httpCheck*) echo /health ;;
  *"uptime list-configs"*contentMatchers*) echo '"status":"ok"' ;;
  *"uptime list-configs"*monitoredResource*) echo servizio-1.europe-west8.run.app ;;
  *"uptime list-configs"*) echo C1 ;;
  *"policies list"*"non raggiungibile"*) echo projects/p/alertPolicies/A ;;
  *"policies list"*"scrittura non riuscita"*) echo projects/p/alertPolicies/B ;;
  *"policies list"*"nessuna istanza"*) [ -f "$STUB_DIR/p429" ] && echo projects/p/alertPolicies/C ;;
  *"policies create"*|*"policies update"*) cp "$FILE" "$STUB_DIR/p429" ;;
  *"policies describe"*alertPolicies/A*conditionThreshold*) echo '"C1"' ;;
  *"policies describe"*alertPolicies/B*conditionMatchedLog*) cat "$STUB_DIR/messages" ;;
  *"policies describe"*alertPolicies/C*conditionMatchedLog*) grep '"filter"' "$STUB_DIR/p429" | sed 's/\\"/"/g' ;;
  *"policies describe"*notificationChannels*) echo projects/p/notificationChannels/7 ;;
  *"policies describe"*enabled*) echo True ;;
esac
exit 0
"""


SETUP_CURL = """#!/usr/bin/env bash
echo x >> "$STUB_DIR/curl.log"
[ "$(wc -l < "$STUB_DIR/curl.log")" -le "$(cat "$STUB_DIR/curl_fails" 2>/dev/null || echo 0)" ] && exit 28
echo '{"status":"ok"}'
"""


def _posix(path: Path) -> str:
    """A Windows path as Git Bash wants it in PATH: /c/Users/..."""
    s = path.as_posix()
    return f"/{s[0].lower()}/{s[3:]}" if s[1:3] == ":/" else s


@pytest.fixture
def setup(tmp_path):
    bash = _runner().git_bash()
    if not bash:
        pytest.skip("bash non disponibile")
    (tmp_path / "gcloud").write_text(SETUP_GCLOUD, encoding="utf-8", newline="\n")
    (tmp_path / "curl").write_text(SETUP_CURL, encoding="utf-8", newline="\n")
    (tmp_path / "messages").write_text(" ".join(f'"{m}"' for m in _messages()), encoding="utf-8")

    def run(dry=False, env=""):
        (tmp_path / "calls.log").write_text("", encoding="utf-8")
        (tmp_path / "curl.log").write_text("", encoding="utf-8")
        here = _posix(tmp_path)                                  # "C:/..." in PATH would split at the colon: the real gcloud
        cmd = (f'export PATH="{here}:$PATH" STUB_DIR="{here}"; chmod +x "{here}/gcloud" "{here}/curl"; '
               f'[ "$(command -v gcloud)" = "{here}/gcloud" ] || exit 99; '
               f'{"DRY_RUN=1 " if dry else ""}{env} GCP_PROJECT_ID=p EMAIL=a@b.it bash "{_posix(MONITORING)}/setup.sh"')
        out = subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=120)
        return out, (tmp_path / "calls.log").read_text(encoding="utf-8")
    run.dir = tmp_path
    return run


def test_setup_creates_the_429_alert_once(setup):
    out, calls = setup()
    assert out.returncode == 0, out.stdout + out.stderr
    assert calls.count("policies create") == 1 and "la regola «BFF: nessuna istanza disponibile (429)» guarda i 429 di domotica-bff" in out.stdout
    out, calls = setup()                                                       # idempotent
    assert out.returncode == 0, out.stdout + out.stderr
    assert "policies create" not in calls and "policies update" not in calls and "già presente: C" in out.stdout


def test_setup_corrects_a_wrong_429_filter(setup):
    assert setup()[0].returncode == 0
    policy = setup.dir / "p429"
    policy.write_text(policy.read_text(encoding="utf-8").replace("no available instance", "altro"), encoding="utf-8")
    out, calls = setup()
    assert out.returncode == 0, out.stdout + out.stderr
    assert calls.count("policies update") == 1 and "no available instance" in policy.read_text(encoding="utf-8")


def test_setup_waits_for_a_server_that_is_starting(setup):
    """A server at minimum 0 answered 200 in 10.01 s on 9 November, just after curl had given up."""
    (setup.dir / "curl_fails").write_text("2", encoding="utf-8")
    out, _ = setup(env="REACH_WAIT_S=0")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "tentativo 1 di 5" in out.stdout and "tentativo 2 di 5" in out.stdout and "tentativo 3 di 5" not in out.stdout
    assert (setup.dir / "curl.log").read_text(encoding="utf-8").count("x") == 3


def test_setup_stops_without_guessing_the_cause(setup):
    (setup.dir / "curl_fails").write_text("99", encoding="utf-8")
    out, _ = setup(env="REACH_WAIT_S=0")
    assert out.returncode != 0 and "dopo 5 tentativi" in out.stderr
    assert "pubblica prima" not in out.stderr and "stato del servizio" in out.stderr
    assert (setup.dir / "curl.log").read_text(encoding="utf-8").count("x") == 5


def test_setup_dry_run_creates_no_429_alert(setup):
    out, calls = setup(dry=True)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "(prova a secco) farei: creo la regola «BFF: nessuna istanza disponibile (429)»" in out.stdout
    assert "policies create" not in calls and "policies update" not in calls


# -------- the CI job in Linux on the PC (scripts/ci-linux.sh, "linux" suite) --------
def test_ci_linux_script_exists_is_executable_and_says_what_it_does():
    script = ROOT / "scripts" / "ci-linux.sh"
    assert script.is_file()
    if shutil.which("git"):
        line = subprocess.run(["git", "ls-files", "-s", "--", "scripts/ci-linux.sh"], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout
        assert line.startswith("100755 "), f"scripts/ci-linux.sh non eseguibile nell'indice: {line!r}"
    bash = _runner().git_bash()
    if not bash:
        pytest.skip("bash non disponibile")
    out = subprocess.run([bash, str(script), "--help"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                         timeout=30)
    assert out.returncode == 0, out.stderr
    for words in ("contratto-e-mock", "python:3.11-slim", "non-root", "core.autocrlf=false", "C14", "PASSO", "ESITO"):
        assert words in out.stdout, words


def test_ci_linux_verdict_counts_the_steps_and_never_skips():
    rt = _runner()
    ok = [f"PASSO {s}: ok" for s in ("contratto", "dipendenze", "prove del motore", "avvio del motore", "conformità",
                                     "C14 connector fermo")]
    c = rt.linux_counts(["ci-linux: commit abc", *ok, "ESITO: 0 rossi su 6 passi"], 0)
    assert (c["tests"], c["failures"], c["errors"], c["suite_skipped"]) == (6, 0, 0, False)
    one_red = ok[:2] + ["PASSO prove del motore: ROSSO"] + ok[3:]
    c = rt.linux_counts(one_red, 1)
    assert (c["tests"], c["failures"], c["errors"]) == (6, 1, 0) and "prove del motore" in c["note"]
    c = rt.linux_counts(["PASSO preparazione: ROSSO (Docker non risponde: avvia Docker Desktop)"], 3)
    assert (c["tests"], c["errors"], c["suite_skipped"]) == (1, 1, False) and "avvia Docker Desktop" in c["note"]
    c = rt.linux_counts(ok[:3], 1)                                               # stopped without a red step
    assert c["errors"] == 1 and "uscita 1" in c["note"]


def test_linux_runs_in_the_full_run_not_with_a_pytest_filter():
    rt = _runner()
    assert rt.LINUX_SUITE in rt.selected_suites([], [])
    assert rt.LINUX_SUITE not in rt.selected_suites([], ["-k", "webhook"])
    assert rt.selected_suites(["linux"], []) == [rt.LINUX_SUITE]
    assert rt.run_linux_suite(skip=True)["suite_skipped"] is True


def test_a_suite_that_hangs_is_stopped_and_counted_red(tmp_path, monkeypatch):
    """21 Oct: support_access hung for 36 minutes after the repository suite (never reproduced). A suite past
    SUITE_TIMEOUT_S is stopped and counted as one red with the reason; the run goes on."""
    rt = _runner()
    monkeypatch.setattr(rt, "SUITE_TIMEOUT_S", 2)
    suite = tmp_path / "ferma_test.py"
    suite.write_text("import time\n\ndef test_ferma():\n    time.sleep(60)\n", encoding="utf-8")
    c = rt.run_pytest(str(suite), tmp_path, [], {**__import__("os").environ})
    assert c["errors"] == 1 and "bloccata" in c["note"]


def test_e2e_totals_from_the_playwright_report():
    """P-73: the browser checks' totals from Playwright's JSON report; a red never hides behind an exit code."""
    rt = _runner()
    ok = rt.e2e_counts({"stats": {"expected": 14, "flaky": 1, "unexpected": 0, "skipped": 0}}, 0)
    assert (ok["tests"], ok["failures"], ok["errors"], ok["skipped"]) == (15, 0, 0, 0)
    red = rt.e2e_counts({"stats": {"expected": 13, "unexpected": 2, "skipped": 0}}, 1)
    assert (red["tests"], red["failures"]) == (15, 2)
    skipped = rt.e2e_counts({"stats": {"expected": 0, "unexpected": 0, "skipped": 15}}, 0)   # no browser: skipped
    assert (skipped["tests"], skipped["skipped"], skipped["errors"]) == (15, 15, 0)
    assert rt.e2e_counts({"stats": {}}, 0)["errors"] == 1                                # 0 checks declared
    assert rt.e2e_counts({"stats": {"expected": 3}}, 1)["errors"] == 1                  # exit code without a red
    broken = rt.e2e_counts({"stats": {}, "errors": [{"message": "http://127.0.0.1:8011 is already used" + chr(10) + "more"}]}, 1)
    assert broken["errors"] == 1 and broken["note"] == "http://127.0.0.1:8011 is already used"


def test_e2e_refuses_a_taken_port(tmp_path, monkeypatch):
    rt = _runner()
    monkeypatch.setattr(rt, "port_taken", lambda port: port == 5174)
    monkeypatch.setattr(rt.shutil, "which", lambda name: "yarn")
    c = rt.run_e2e_suite(tmp_path)
    assert c["errors"] == 1 and c["note"].startswith("porta 5174 già occupata")


# the patterns of the repository's test files, and where the full run takes the ones it does not list one by one
TEST_PATTERNS = ("tests/*_test.py", "engine/tests/test_*.py", "engine/connector/tests/test_*.py",
                 "engine/connector/*/tests/test_*.py", "bff/**/test_*.py")
RUN_ELSEWHERE = {"contract/conformance/test_scenari.py": "the «conformita» suite (CONFORMANCE_SUITE)"}


def test_every_test_file_of_the_repository_is_in_the_full_run():
    """D-198 (10 November 2026): run_tests.py lists the suites by hand and four new files of the engine were left out of
    the full run, without anybody noticing. Now a file that matches a test pattern and is in no list is red here,
    also before its first commit (the files on disk are read, not git's)."""
    mod = _runner()
    listed = set(mod.HTTP_SUITES) | set(mod.LOCAL_SUITES) | set(RUN_ELSEWHERE)
    found = {path.relative_to(ROOT).as_posix() for pattern in TEST_PATTERNS for path in ROOT.glob(pattern)
             if "__pycache__" not in path.parts and "node_modules" not in path.parts}
    found |= {path.relative_to(ROOT).as_posix() for path in (ROOT / "contract" / "conformance").glob("test_*.py")}
    assert not sorted(found - listed), f"prove fuori dal giro completo: {sorted(found - listed)}"
    assert not sorted(x for x in listed if not (ROOT / x).is_file()), "in elenco ma il file non esiste"


def test_every_test_file_of_the_site_is_found_by_its_runner():
    """Risposta 761 (10 November 2026): the site's tests are found by their runners, not listed by hand: vitest
    (vite.config.ts, test.include) for the «sito» suite and Playwright (playwright.config.ts, testDir) for «e2e». A test
    file that neither of them would find is red here, and so is a change of those two settings."""
    import re
    vite = (ROOT / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    playwright = (ROOT / "frontend" / "playwright.config.ts").read_text(encoding="utf-8")
    assert 'include: ["src/**/*.test.{ts,tsx}"]' in vite, "vitest non cerca più tutte le prove in src/"
    assert 'testDir: "./e2e"' in playwright, "Playwright non cerca più le prove in e2e/"
    site = ROOT / "frontend"
    files = [path.relative_to(site).as_posix() for path in site.rglob("*")
             if re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", path.name) and "node_modules" not in path.parts
             and "dist" not in path.parts]
    lost = [f for f in files if not re.fullmatch(r"src/.+\.test\.(ts|tsx)", f) and not f.startswith("e2e/")]
    assert not lost, f"prove del sito che né vitest né Playwright trovano: {lost}"
    assert len(files) > 50                                      # the folder was really read

