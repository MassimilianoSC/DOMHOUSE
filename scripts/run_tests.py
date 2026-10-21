"""Full local test run with a single command: starts a fresh BFF for every HTTP suite, runs all suites, prints totals.

    python scripts/run_tests.py                     # every suite
    python scripts/run_tests.py --suite phase3      # only the suites whose name contains "phase3" ("sito" = the PWA)
    python scripts/run_tests.py -- -k webhook       # everything after -- goes to pytest (only the pytest suites run)

Uses app/.venv when it exists (create it with: python -m venv .venv, then .venv/Scripts/python -m pip install
-r bff/requirements.txt pytest requests). Each HTTP suite gets its own BFF (dev auth, built-in mock, memory repository)
on a free port: the memory repository keeps state and the suites create users and apartments, so a shared BFF would
make results depend on the order. The repository suite needs no BFF but needs the Firestore emulator (P-42): an
emulator already pointed to by FIRESTORE_EMULATOR_HOST, or the JAR in ~/.cache/firebase/emulators started with java
(JDK 11 or later). Without it the suite counts one red with the reason and how to fix it; it is never skipped. Install
once: a JDK (e.g. `winget install EclipseAdoptium.Temurin.21.JDK`), then `npx firebase-tools setup:emulators:firestore`.
The "script_sh" check (P-41) wants every tracked scripts/**/*.sh with LF line endings in the repository and mode 100755
in the index: a commit by path from Windows can drop the executable bit. The "sito" suite is the PWA's `yarn --cwd frontend test:ci`: its totals come from
frontend/test-results/vitest.json, a missing report or a non-zero exit code counts as red, and the suite is declared
skipped while frontend/package.json has no test:ci script. The "dimensione" suite is `yarn --cwd frontend size:check`
(build included): one check, red on any non-zero exit code. A red listed in EXPECTED_RED is labelled as expected but
still counted, so the total stays true. The "linux" suite is scripts/ci-linux.sh: the CI job "contratto-e-mock" on
the last commit, in a python:3.11-slim container as a non-root user (about 3 minutes; E-16 and E-17 failed only
there). One check per step of the job; Docker missing or not running counts one red with the reason, never a skip.
It runs in the full run and with --suite linux; --no-linux declares it skipped (visible in the totals), and a pytest
filter (-- -k ...) leaves it out like the other non-pytest suites. It tests the COMMIT, not uncommitted changes.
Exit code 0 only when there are no failures and no errors.
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTTP_SUITES = ["tests/backend_test.py", "tests/backend_phase2_test.py", "tests/backend_phase3_test.py", "tests/backend_phase4_test.py",
               "tests/backend_isolation_test.py", "tests/backend_platform_test.py"]
LOCAL_SUITES = ["tests/repository_suite_test.py", "tests/instances_url_test.py", "tests/push_test.py",
                "tests/apartment_scope_test.py", "tests/tenant_test.py", "tests/routes_test.py", "tests/webhook_test.py",
                "tests/platform_test.py", "tests/real_mode_test.py", "tests/firebase_flows_test.py",
                "tests/proxy_path_test.py", "tests/mock_exposure_test.py", "tests/run_tests_checks_test.py",
                "tests/invite_limits_test.py", "tests/support_access_test.py",
                "tests/actors_test.py", "tests/erasure_test.py", "tests/fields_by_role_test.py",
                "tests/lot9_review_test.py", "tests/energy_export_test.py",
                "tests/simulated_apartments_test.py", "tests/cloudrun_manifests_test.py", "tests/engine_vm_settings_test.py", "tests/deploy_engine_test.py", "tests/ai_gateway_test.py", "tests/environments_test.py", "tests/deploy_targets_test.py", "tests/list_demos_test.py", "tests/engine_alerts_test.py",
                "engine/connector/tests/test_interface.py",
                "engine/tests/test_service.py", "engine/tests/test_store.py",
                "engine/tests/test_restart.py", "engine/tests/test_approvals.py",
                "engine/tests/test_scheduler.py", "engine/tests/test_schedule_rules.py",
                "engine/tests/test_rules.py", "engine/tests/test_thermostat.py",
                "engine/tests/test_hold_window.py", "engine/tests/test_energy.py",
                "engine/tests/test_confirmation.py", "engine/tests/test_settings.py",
                "engine/tests/test_approval_sources.py", "engine/tests/test_approvals_restart.py",
                "engine/tests/test_assistant.py", "engine/tests/test_health.py"]
SITE_SUITE = "sito"
CONFORMANCE_SUITE = "conformita"
CONFORMANCE_DIR = "contract/conformance"
ENGINE_VARS = ROOT / "ci" / "engine.vars"     # the engine's environment, the same file the CI reads


def engine_vars() -> dict[str, str]:
    """ci/engine.vars as a dict: KEY=VALUE lines, # comments."""
    out = {}
    for line in ENGINE_VARS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


SCRIPT_SUITE = "script_sh"
SCRIPTS_PATHSPEC = "scripts/*.sh"  # a git pathspec: "*" also crosses "/", so scripts in subfolders are included
SITE_REPORT = ROOT / "frontend" / "test-results" / "vitest.json"
SIZE_SUITE = "dimensione"
LINUX_SUITE = "linux"
LINUX_SCRIPT = ROOT / "scripts" / "ci-linux.sh"
LINUX_TIMEOUT_S = 900
SUITE_TIMEOUT_S = 900          # 15 minutes for one pytest suite (the longest takes about 2)
SIZE_EXIT = {1: "blocco principale sopra la soglia", 2: "build mancante"}
# Suites known to be red while a planned piece of work is open: shown as such, never hidden or skipped.
EXPECTED_RED: dict[str, str] = {}  # e.g. {SIZE_SUITE: "P-20 in corso"} (P-20 closed on 16/10: empty)

# Every variable the BFF reads is set here, so a developer's bff/.env (loaded with override=False) cannot change the run.
BFF_ENV = {
    "APP_ENV": "dev",
    "AUTH_MODE": "dev",
    "INSTANCE_MODE": "mock",
    "REPOSITORY": "memory",
    "FCM_ENABLED": "false",
    "BFF_ROOT_PATH": "",
    "INSTANCE_API_KEY_FALLBACK": "dev-key",
    "MOCK_TIME_SCALE": "1",
    "GCP_PROJECT_ID": "your-gcp-project-id",
    "FIREBASE_PROJECT_ID": "your-gcp-project-id",
    "CORS_ORIGINS": "",
    "ITALIANWAY_WEBHOOK_SECRET": "replace-me",  # placeholder also hard-coded in the suites; not a real secret
    "ITALIANWAY_SIGNATURE_HEADER": "X-Signature",
    "SMTP_USER": "",  # invitations are only recorded: no email leaves the machine
    "SMTP_PASSWORD": "",
    "APP_PUBLIC_URL": "http://localhost:5173",
}


def result(tests=0, failures=0, errors=0, skipped=0, note="", suite_skipped=False) -> dict:
    return {"tests": tests, "failures": failures, "errors": errors, "skipped": skipped, "note": note,
            "suite_skipped": suite_skipped}


def venv_python() -> Path | None:
    for rel in ("Scripts/python.exe", "bin/python"):
        p = ROOT / ".venv" / rel
        if p.exists():
            return p
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_healthy(url: str, proc: subprocess.Popen, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(f"{url}/healthz", timeout=2) as r:
                if r.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.3)
    return False


def start_bff(log_path: Path) -> tuple[subprocess.Popen, str]:
    port = free_port()
    env = {**os.environ, **BFF_ENV, "PORT": str(port), "PYTHONUNBUFFERED": "1"}
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "bff.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    return proc, f"http://127.0.0.1:{port}"


def stop(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def junit_counts(junit: Path) -> dict:
    out = result()
    if not junit.exists():
        return out
    root = ET.parse(junit).getroot()
    for suite in ([root] if root.tag == "testsuite" else root.iter("testsuite")):
        for k in ("tests", "failures", "errors", "skipped"):
            out[k] += int(suite.get(k, 0))
    return out


def run_pytest(suite: str, work: Path, extra: list[str], env: dict) -> dict:
    """One pytest suite in its own process, at most SUITE_TIMEOUT_S: a suite that hangs (seen once on 21 Oct,
    support_access for 36 minutes, never reproduced) is stopped and counted red with the reason, the run goes on."""
    junit = work / f"{Path(suite).stem}.xml"
    cmd = [sys.executable, "-m", "pytest", suite, "-q", "-rfE", "-p", "no:cacheprovider", f"--junitxml={junit}", *extra]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
    try:
        code = proc.wait(timeout=SUITE_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        stop_tree(proc)
        return result(errors=1, note=f"bloccata: ferma oltre {SUITE_TIMEOUT_S // 60} minuti, fermata dal giro")
    c = junit_counts(junit)
    if c["tests"] == 0:
        if code == 5 and extra:   # lot 11: pytest "no tests collected" because of the user's filter, not a failure
            return result(note="nessuna prova corrisponde al filtro", suite_skipped=True)
        c["errors"] += 1
        c["note"] = "nessun risultato (raccolta fallita?)"
    return c


def run_http_suite(suite: str, work: Path, extra: list[str]) -> dict:
    log = work / f"{Path(suite).stem}.bff.log"
    proc, url = start_bff(log)
    try:
        if not wait_healthy(url, proc):
            return result(errors=1, note=f"BFF non partito, vedi {log}")
        print(f"\n=== {Path(suite).stem} contro {url}")
        c = run_pytest(suite, work, extra, {**os.environ, "REACT_APP_BACKEND_URL": url, "BFF_API_PREFIX": ""})
    finally:
        stop(proc)
    c["note"] = c["note"] or f"log BFF: {log}"
    return c


def start_engine(log_path: Path, connector_down: bool) -> tuple[subprocess.Popen, str]:
    """The engine as a service of its own (python -m engine, simulated connector), as the CI runs it for the
    conformance suite: the environment of ci/engine.vars (the CI's), plus what differs here: HOST, a free PORT and a
    fresh DATA_DIR (engine.db starts empty, as on the CI runner)."""
    port = free_port()
    data = log_path.parent / f"{log_path.stem}-data"
    env = {**os.environ, **engine_vars(), "HOST": "127.0.0.1", "PORT": str(port), "DATA_DIR": str(data),
           "PYTHONUNBUFFERED": "1"}
    env.pop("DOMOTICA_TEST_CONNECTOR_DOWN", None)
    if connector_down:
        env["DOMOTICA_TEST_CONNECTOR_DOWN"] = "1"
    log = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "engine"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    return proc, f"http://127.0.0.1:{port}/api/v1"


def wait_answering(url: str, proc: subprocess.Popen, timeout: float = 60.0) -> bool:
    """Any HTTP answer from /health counts: with the connector down it is a 503 on purpose (scenario C14)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            urllib.request.urlopen(f"{url}/health", timeout=2).close()
            return True
        except urllib.error.HTTPError:
            return True
        except OSError:
            time.sleep(0.3)
    return False


def run_conformance_suite(work: Path) -> dict:
    """Step 0 of plan B (P-60): the contract's conformance suite against the simulated engine, on this PC as in the CI:
    C01-C16 with the connector up, then C14's 503 part with the connector down. One verdict, both runs added up."""
    total = result()
    for down, marker in ((False, []), (True, ["-m", "connector_down"])):
        log = work / f"engine{'-down' if down else ''}.log"
        proc, url = start_engine(log, down)
        try:
            if not wait_answering(url, proc):
                return result(errors=1, note=f"motore simulato non partito, vedi {log}")
            print(f"\n=== {CONFORMANCE_SUITE}{' (connector fermo)' if down else ''} contro {url}")
            key = engine_vars()["API_KEY"]
            c = run_pytest(CONFORMANCE_DIR, work, ["--base-url", url, "--api-key", key, *marker], os.environ.copy())
        finally:
            stop(proc)
        for k in ("tests", "failures", "errors", "skipped"):
            total[k] += c[k]
        if c["note"] and not total["note"]:
            total["note"] = c["note"]
    return total


def run_site_suite() -> dict:
    """PWA tests owned by o2: totals from the vitest JSON report, cross-checked with the exit code."""
    try:
        scripts = frontend_scripts()
    except (OSError, ValueError) as exc:
        return result(errors=1, note=f"frontend/package.json illeggibile: {exc}")
    if "test:ci" not in scripts:
        return result(note="manca lo script test:ci in frontend/package.json", suite_skipped=True)
    yarn = shutil.which("yarn")
    if not yarn:
        return result(errors=1, note="yarn non trovato nel PATH")
    SITE_REPORT.unlink(missing_ok=True)  # a report left by an earlier run must not be counted
    print(f"\n=== {SITE_SUITE}: yarn --cwd frontend test:ci")
    code = subprocess.call([yarn, "--cwd", "frontend", "test:ci"], cwd=ROOT)
    try:
        report = json.loads(SITE_REPORT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return result(errors=1, note=f"rapporto {SITE_REPORT.relative_to(ROOT).as_posix()} assente o illeggibile (uscita {code})")
    c = result(tests=int(report.get("numTotalTests", 0)), failures=int(report.get("numFailedTests", 0)),
               skipped=int(report.get("numPendingTests", 0)) + int(report.get("numTodoTests", 0)))
    if c["tests"] == 0:
        c["errors"] += 1
        c["note"] = "il rapporto dichiara 0 prove"
    elif code != 0 and c["failures"] == 0:
        c["errors"] += 1
        c["note"] = f"uscita {code} senza prove fallite nel rapporto"
    return c


def frontend_scripts() -> dict:
    return json.loads((ROOT / "frontend" / "package.json").read_text(encoding="utf-8")).get("scripts", {})


def check_shell_scripts(root: Path = ROOT) -> dict:
    """P-41: every shell script must run after a checkout on Linux or Cloud Shell: LF line endings in the repository
    and the executable bit (100755) in the index AND in the commit HEAD. The second because a commit by path from
    Windows (core.fileMode=false) records 100644 even when the index says 100755 (b284268, fixed in 374e4a5): the
    index alone stayed green. One check per script; the problems go in the note."""
    git = shutil.which("git")
    if not git:
        return result(errors=1, note="git non trovato nel PATH")

    def run(*args: str) -> str:
        return subprocess.run([git, *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                              check=True).stdout

    def listing(*args: str) -> dict[str, str]:
        out = run("ls-files", *args, "--", SCRIPTS_PATHSPEC)
        return {line.split("\t", 1)[1]: line.split()[0] for line in out.splitlines() if "\t" in line}

    def committed() -> dict[str, str]:
        """The scripts' modes in HEAD; none before the first commit."""
        if subprocess.run([git, "rev-parse", "--verify", "-q", "HEAD"], cwd=root, capture_output=True).returncode:
            return {}
        out = run("ls-tree", "-r", "--full-tree", "HEAD", "--", "scripts")
        return {line.split("\t", 1)[1]: line.split()[0] for line in out.splitlines()
                if "\t" in line and line.split("\t", 1)[1].endswith(".sh")}

    try:
        modes, eols, head = listing("-s"), listing("--eol"), committed()
    except (OSError, subprocess.CalledProcessError) as exc:
        return result(errors=1, note=f"git ls-files o ls-tree non riuscito: {exc}")
    if not modes:
        return result(errors=1, note=f"nessuno script trovato con {SCRIPTS_PATHSPEC}")
    problems: dict[str, list[str]] = {}
    for path, mode in sorted(modes.items()):
        if mode != "100755":
            problems.setdefault(path, []).append(f"mode {mode} invece di 100755 (git update-index --chmod=+x {path})")
        if path in head and head[path] != "100755":
            problems.setdefault(path, []).append(
                f"mode {head[path]} nel commit HEAD invece di 100755 (commit del solo modo con un GIT_INDEX_FILE "
                f"temporaneo: read-tree HEAD, update-index --chmod=+x, write-tree, commit-tree, update-ref)")
        if eols.get(path) != "i/lf":
            problems.setdefault(path, []).append(f"fine riga {eols.get(path)} nel repository invece di i/lf")
    note = "; ".join(f"{path}: {', '.join(p)}" for path, p in problems.items())
    return result(tests=len(modes), failures=len(problems), note=note)


FIRESTORE_SUITE = "tests/repository_suite_test.py"
FIRESTORE_JARS = Path.home() / ".cache" / "firebase" / "emulators"  # where firebase-tools keeps its emulators


def start_firestore_emulator(work: Path) -> tuple[subprocess.Popen | None, str | None, str]:
    """(process, host, note) for the repository suite's Firestore cases. An emulator already pointed to by
    FIRESTORE_EMULATOR_HOST is used as is; otherwise the emulator JAR already on disk is started with java on a free
    port. Nothing is downloaded or installed: without either, host is None and the caller counts a red (P-42)."""
    if os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return None, os.environ["FIRESTORE_EMULATOR_HOST"], "Firestore: emulatore già avviato (FIRESTORE_EMULATOR_HOST)"
    jars = sorted(FIRESTORE_JARS.glob("cloud-firestore-emulator-*.jar"))
    java = shutil.which("java")
    if not jars or not java:
        missing = ("java (installa un JDK 11 o successivo, es. winget install EclipseAdoptium.Temurin.21.JDK)" if jars
                   else f"l'emulatore in {FIRESTORE_JARS} (npx firebase-tools setup:emulators:firestore)")
        return None, None, f"Firestore obbligatorio (P-42): manca {missing}"
    port = free_port()
    log = work / "firestore-emulator.log"
    proc = subprocess.Popen([java, "-jar", str(jars[-1]), "--host=127.0.0.1", f"--port={port}"],
                            stdout=open(log, "w", encoding="utf-8"), stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and proc.poll() is None:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return proc, f"127.0.0.1:{port}", f"Firestore: emulatore {jars[-1].name}"
        except OSError:
            time.sleep(0.3)
    stop_tree(proc)
    return None, None, f"Firestore obbligatorio (P-42): emulatore non partito, vedi {log}"


def with_firestore_verdict(c: dict, host: str | None, note: str) -> dict:
    """P-42: the Firestore cases are mandatory. Without an emulator the suite gets one red with the reason, never a
    skip, so the total and the exit code show it."""
    if host:
        return {**c, "note": c["note"] or note}
    return {**c, "tests": c["tests"] + 1, "errors": c["errors"] + 1, "note": note}


def stop_tree(proc: subprocess.Popen) -> None:
    """On Windows `java` is often the javapath launcher, which starts the real JVM as a child: terminating the launcher
    alone leaves the emulator running. Kill the whole tree."""
    if os.name == "nt":
        subprocess.call(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.wait()
    else:
        stop(proc)


def run_size_suite() -> dict:
    """Bundle size check owned by o2 (P-20): a single check, its exit code is the verdict."""
    try:
        scripts = frontend_scripts()
    except (OSError, ValueError) as exc:
        return result(errors=1, note=f"frontend/package.json illeggibile: {exc}")
    if "size:check" not in scripts:
        return result(note="manca lo script size:check in frontend/package.json", suite_skipped=True)
    yarn = shutil.which("yarn")
    if not yarn:
        return result(errors=1, note="yarn non trovato nel PATH")
    print(f"\n=== {SIZE_SUITE}: yarn --cwd frontend size:check")
    code = subprocess.call([yarn, "--cwd", "frontend", "size:check"], cwd=ROOT)
    if code == 0:
        return result(tests=1)
    return result(tests=1, failures=1, note=f"uscita {code}: {SIZE_EXIT.get(code, 'errore')}")


def git_bash() -> str | None:
    """The bash that runs our scripts: on Windows Git Bash (next to git), never WSL's bash in System32."""
    if os.name != "nt":
        return shutil.which("bash")
    git = shutil.which("git")
    if git:
        for parent in Path(git).resolve().parents:
            candidate = parent / "bin" / "bash.exe"
            if candidate.is_file():
                return str(candidate)
    found = shutil.which("bash")
    return found if found and "system32" not in found.lower() else None


def linux_counts(lines: list[str], code: int) -> dict:
    """The verdict of scripts/ci-linux.sh from its "PASSO <name>: ok|ROSSO" lines and exit code: one check per step.
    Exit 3 (Docker or git missing, unknown commit) is one error with the script's reason, never a skip; an exit code
    that disagrees with the steps is one more error."""
    steps = [line[len("PASSO "):] for line in lines if line.startswith("PASSO ")]
    red = [s for s in steps if ": ROSSO" in s]
    if code == 3:
        return result(tests=1, errors=1, note=red[0] if red else "uscita 3")     # "1 rossa su 1", as Firestore
    c = result(tests=len(steps), failures=len(red), note="rossi: " + ", ".join(red) if red else "")
    if (code != 0) != bool(red):
        c["errors"] += 1
        c["note"] = f"{c['note']}; uscita {code}".lstrip("; ")
    return c


def run_linux_suite(skip: bool) -> dict:
    """The CI job on the last commit, in Linux (scripts/ci-linux.sh); its output goes to the console as it comes."""
    if skip:
        return result(note="--no-linux", suite_skipped=True)
    bash = git_bash()
    if not bash:
        return result(errors=1, note="bash non trovato (su Windows serve Git Bash)")
    print(f"\n=== {LINUX_SUITE}: bash scripts/ci-linux.sh (job contratto-e-mock in python:3.11-slim, circa 3 minuti)")
    lines: list[str] = []
    try:
        proc = subprocess.Popen([bash, str(LINUX_SCRIPT)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace")
        assert proc.stdout is not None
        start = time.monotonic()
        for line in proc.stdout:
            print(line, end="")
            lines.append(line.rstrip("\n"))
            if time.monotonic() - start > LINUX_TIMEOUT_S:
                proc.kill()
                break
        code = proc.wait(timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return result(errors=1, note=f"scripts/ci-linux.sh non avviato o bloccato: {exc}")
    return linux_counts(lines, code)


def selected_suites(chosen: list[str], extra: list[str]) -> list[str]:
    """--suite picks by name; otherwise a pytest filter (-- -k …) runs only the pytest suites: "sito", "dimensione" and
    "script_sh" never receive pytest's arguments and would only add a long, unrelated run (lot 11); the same for "linux"."""
    every = [SCRIPT_SUITE] + HTTP_SUITES + LOCAL_SUITES + [CONFORMANCE_SUITE, LINUX_SUITE, SITE_SUITE, SIZE_SUITE]
    if chosen:
        return [s for s in every if any(f in s for f in chosen)]
    return HTTP_SUITES + LOCAL_SUITES if extra else every


def main() -> int:
    # utf-8: on Windows a piped stdout defaults to cp1252 and «», accents come out garbled; line buffering keeps our
    # headers in order with the children's output
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    argv = sys.argv[1:]
    extra: list[str] = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", action="append", default=[], help="run only suites whose name contains this text")
    ap.add_argument("--no-linux", action="store_true",
                    help="skip the Linux run of the CI job (scripts/ci-linux.sh); shown as skipped in the totals")
    args = ap.parse_args(argv)

    vpy = venv_python()
    if vpy and Path(sys.executable).resolve() != vpy.resolve() and not os.environ.get("RUN_TESTS_NO_VENV"):
        return subprocess.call([str(vpy), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT)

    selected = selected_suites(args.suite, extra)
    if not selected:
        print("Nessuna suite corrisponde a", args.suite)
        return 2
    work = Path(tempfile.mkdtemp(prefix="domotica-tests-"))
    print(f"Python {sys.version.split()[0]} ({sys.executable}); log in {work}")

    results: list[tuple[str, dict]] = []
    for suite in selected:
        if suite == SCRIPT_SUITE:
            print(f"\n=== {SCRIPT_SUITE}: git ls-files {SCRIPTS_PATHSPEC}")
            c = check_shell_scripts()
        elif suite in HTTP_SUITES:
            c = run_http_suite(suite, work, extra)
        elif suite == CONFORMANCE_SUITE:
            c = run_conformance_suite(work)
        elif suite == LINUX_SUITE:
            c = run_linux_suite(args.no_linux)
        elif suite == SITE_SUITE:
            c = run_site_suite()
        elif suite == SIZE_SUITE:
            c = run_size_suite()
        elif suite == FIRESTORE_SUITE:
            proc, host, note = start_firestore_emulator(work)
            print(f"\n=== {Path(suite).stem} ({note})")
            env = os.environ.copy()
            if host:
                env.update(FIRESTORE_EMULATOR_HOST=host, GCP_PROJECT_ID="demo-test")
            try:
                c = run_pytest(suite, work, extra, env)
            finally:
                if proc:
                    stop_tree(proc)
            c = with_firestore_verdict(c, host, note)
        else:
            print(f"\n=== {Path(suite).stem}")
            c = run_pytest(suite, work, extra, os.environ.copy())
        results.append((Path(suite).stem, c))

    print("\n=== Totale")
    tot = result()
    skipped_suites = []
    expected = 0
    for name, c in results:
        if c["suite_skipped"]:
            skipped_suites.append(name)
            print(f"{name:32} SALTATA: {c['note']}")
            continue
        red = c["failures"] + c["errors"]
        note = c["note"] if red or c["note"].startswith("Firestore") else ""
        if red and name in EXPECTED_RED:
            expected += red
            note = f"rossa attesa ({EXPECTED_RED[name]}); {note}"
        elif not red and name in EXPECTED_RED:
            note = f"verde: «{EXPECTED_RED[name]}» si può togliere da EXPECTED_RED"
        print(f"{name:32} {red:3} rosse su {c['tests']:3}  ({c['skipped']} saltati)  {note}".rstrip())
        for k in ("tests", "failures", "errors", "skipped"):
            tot[k] += c[k]
    red = tot["failures"] + tot["errors"]
    tail = f"; suite saltate: {', '.join(skipped_suites)}" if skipped_suites else ""
    of_which = f", di cui {expected} attese" if expected else ""
    print(f"{'TOTALE':32} {red:3} rosse su {tot['tests']:3}{of_which}  ({tot['skipped']} saltati{tail})")
    return 0 if red == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
