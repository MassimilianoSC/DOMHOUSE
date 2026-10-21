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
    assert everything[0] == rt.SCRIPT_SUITE and everything[-2:] == [rt.SITE_SUITE, rt.SIZE_SUITE]


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
