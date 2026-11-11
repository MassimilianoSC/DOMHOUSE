"""scripts/publish-all.sh (D-214): a lot published with one command. The real script in a throwaway repository with a
bare «GitHub»; gcloud (Cloud Run, ssh and scp to the VM), curl, publish.sh and deploy-engine.sh are stand-ins that keep
their state in files, so the order of the steps, the stops, the dry run and the restart after a FERMO can be seen.
What only the first real run can show (Cloud Run's real output, IAP, Hosting) is not here: it is «da verificare»."""
import hashlib
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "publish-all.sh"
BFF = "europe-west8-docker.pkg.dev/progetto-prova/domotica/bff:"
ENGINE = "europe-west8-docker.pkg.dev/progetto-prova/domotica/engine:"


def _bash():
    spec = importlib.util.spec_from_file_location("run_tests", ROOT / "scripts" / "run_tests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.git_bash()


def posix(path: Path) -> str:
    s = path.as_posix()
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else s


GCLOUD = r'''#!/usr/bin/env bash
echo "gcloud $*" >> "$STUB_DIR/calls.log"
case "$*" in
  *"services describe domotica-bff-staging "*containers*) cat "$STUB_DIR/state-staging" 2>/dev/null ;;
  *"services describe domotica-bff "*containers*) cat "$STUB_DIR/state-prod" 2>/dev/null ;;
  *"services describe domotica-bff "*minScale*) cat "$STUB_DIR/values-prod" 2>/dev/null ;;
  *"compute scp"*) : ;;
  *"compute ssh"*)
    cmd="${*#*--command }"
    case "$cmd" in
      *ENGINE_IMAGE*) cat "$STUB_DIR/vm-image" ;;
      *engine-vm.sh*sha256sum*) cat "$STUB_DIR/vm-script-hash" ;;
      *compose.yaml*sha256sum*) cat "$STUB_DIR/vm-compose-hash" ;;
      *"install -m 644 ~/compose.yaml"*) echo compose-ok ;;
      *"engine-vm.sh timers"*) echo timer-ok ;;
      *"engine-vm.sh update"*)
        [ -f "$STUB_DIR/update-fails" ] && exit 1
        echo "$cmd" | awk '{for (i = 1; i <= NF; i++) if ($i == "update") print $(i + 2)}' > "$STUB_DIR/vm-image"
        echo update-ok ;;
    esac ;;
esac
exit 0
'''
CURL = r'''#!/usr/bin/env bash
echo "curl $*" >> "$STUB_DIR/calls.log"
host="$(echo "$*" | grep -oE 'https://[^/ ]+' | head -1 | cut -d/ -f3)"
if [ -f "$STUB_DIR/health-$host" ]; then cat "$STUB_DIR/health-$host"; else printf 200; fi
'''
PUBLISH = r'''#!/usr/bin/env bash
echo "publish ${TARGET} $1 dry=${DRY_RUN:-} confirmed=${PUBLISH_ALL_CONFIRMED:-} fcm=${VITE_FCM_ENABLED:-} site=${STAGING_SITE:-}" >> "$STUB_DIR/calls.log"
[ -n "${DRY_RUN:-}" ] && exit 0
[ -f "$STUB_DIR/publish-fails-${TARGET}" ] && exit 1
short="$(git rev-parse --short "$1")"
[ "${TARGET}" = prod ] && name=prod || name=staging
echo "BFFIMAGE${short}|rev-${short}|rev-${short}|rev-${short}|100|https://${name}.example" | sed "s#BFFIMAGE#$BFF#" > "$STUB_DIR/state-${name}"
'''
DEPLOY_ENGINE = r'''#!/usr/bin/env bash
echo "deploy-engine $1 dry=${DRY_RUN:-}" >> "$STUB_DIR/calls.log"
'''


@pytest.fixture
def pub(tmp_path):
    bash = _bash()
    if not bash or not shutil.which("git"):
        pytest.skip("bash o git non disponibili")
    r = tmp_path / "app"
    for rel in ("scripts/publish-all.sh", "bff/cloudrun.yaml", "engine/compose.yaml"):
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, r / rel)
    (r / "scripts" / "publish-settings.conf").write_text(
        "# di prova\nGCP_PROJECT_ID=progetto-prova\nGCP_REGION=europe-west8\nARTIFACT_REPO=domotica\n"
        "CLOUDSDK_CORE_ACCOUNT=prova@example.com\nSTAGING_SITE=sito-prova\nVPC_NETWORK=default\nVPC_SUBNET=default\n"
        "SMTP_USER=mittente@example.com\nVITE_FCM_ENABLED=true\nENGINE_APARTMENT=dev\nVM_NAME=vm-prova\nVM_ZONE=europe-west8-a\nVM_INTERNAL_IP=10.0.0.9\n",
        encoding="utf-8", newline="\n")
    (r / "scripts" / "engine-vm.sh").write_text("echo motore v1\n", encoding="utf-8", newline="\n")
    (r / "engine" / "core.py").write_text("x = 1\n", encoding="utf-8", newline="\n")
    (r / ".gitignore").write_text("logs/\n", encoding="utf-8", newline="\n")

    def git(*args):
        return subprocess.run(["git", "-C", str(r), "-c", "user.name=p", "-c", "user.email=p@e.com", *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
    git("init", "-q")
    git("config", "core.autocrlf", "false")
    git("add", "-A")
    git("commit", "-q", "-m", "sulla VM")
    git("branch", "-M", "main")
    git("remote", "add", "origin", str(bare))
    on_vm = git("rev-parse", "--short", "HEAD")
    (r / "engine" / "core.py").write_text("x = 2\n", encoding="utf-8", newline="\n")
    git("commit", "-q", "-am", "il lotto")
    git("push", "-q", "origin", "main")
    lot = git("rev-parse", "--short", "HEAD")

    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in (("gcloud", GCLOUD), ("curl", CURL), ("publish.sh", PUBLISH.replace("$BFF", BFF)),
                       ("deploy-engine.sh", DEPLOY_ENGINE)):
        (stubs / name).write_text(body, encoding="utf-8", newline="\n")
        (stubs / name).chmod(0o755)
    for name, host in (("staging", "staging"), ("prod", "prod")):
        (stubs / f"state-{name}").write_text(f"{BFF}{on_vm}|rev-a|rev-a|rev-a|100|https://{host}.example\n", encoding="utf-8")
    manifest = (ROOT / "bff" / "cloudrun.yaml").read_text(encoding="utf-8")
    number = lambda key: re.search(rf"^ *{re.escape(key)}: *\"?(\d+)", manifest, re.M).group(1)
    values = "|".join(number(k) for k in ("autoscaling.knative.dev/minScale", "autoscaling.knative.dev/maxScale",
                                          "containerConcurrency", "timeoutSeconds"))
    (stubs / "values-prod").write_text(values + "\n", encoding="utf-8")
    (stubs / "vm-image").write_text(f"{ENGINE}{on_vm}\n", encoding="utf-8")
    (stubs / "vm-script-hash").write_text("diverso  -\n", encoding="utf-8")
    (stubs / "vm-compose-hash").write_text("diverso  -\n", encoding="utf-8")

    def run(commit=None, answer="pubblica\n", env=""):
        (stubs / "calls.log").unlink(missing_ok=True)
        cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}"; cd "{posix(r)}" && '
               f'{env} PUBLISH_SH="{posix(stubs / "publish.sh")}" DEPLOY_ENGINE_SH="{posix(stubs / "deploy-engine.sh")}" '
               f'PUBLISH_HEALTH_TRIES=2 PUBLISH_HEALTH_WAIT_S=0 bash scripts/publish-all.sh {commit or lot}')
        done = subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=120, input=answer)
        calls = (stubs / "calls.log").read_text(encoding="utf-8") if (stubs / "calls.log").exists() else ""
        return done, calls

    run.root, run.stubs, run.git, run.lot, run.on_vm, run.values = r, stubs, git, lot, on_vm, values
    run.state = lambda: (r / "logs" / f"publish-state-{lot}.txt").read_text(encoding="utf-8")
    return run


def steps(calls):
    """The writing steps in order: publications, engine image, copy, timers, update."""
    out = []
    for line in calls.splitlines():
        if line.startswith(("publish ", "deploy-engine ")):
            out.append(line.split(" dry=")[0] + (" (a secco)" if "dry=1" in line else ""))
        elif "compute scp" in line:
            out.append("scp")
        elif "install -m 644 ~/compose.yaml" in line:
            out.append("compose")
        elif "engine-vm.sh timers" in line:
            out.append("timers")
        elif "engine-vm.sh update" in line:
            out.append("update")
    return out


def test_a_lot_goes_to_staging_then_production_then_the_engine_with_one_question(pub):
    done, calls = pub()
    assert done.returncode == 0, done.stdout + done.stderr
    assert steps(calls) == [f"publish staging {pub.git('rev-parse', pub.lot)}", f"publish prod {pub.git('rev-parse', pub.lot)}",
                            f"deploy-engine {pub.git('rev-parse', pub.lot)}", "scp", "compose", "timers", "update"]
    assert "confirmed=pubblica fcm=true site=sito-prova" in calls        # the settings reach publish.sh
    assert done.stdout.count("scrivi pubblica") == 1
    assert f"motore dev: da {pub.on_vm} a {pub.lot}" in done.stdout and "valori attivi uguali al manifesto" in done.stdout
    assert "update-traffic domotica-bff --to-revisions=rev-a=100" in done.stdout   # going back: printed, never run
    assert "update-traffic" not in calls
    assert [x for x in pub.state().splitlines() if "=" not in x] == ["staging", "prod", "engine"]
    logs = list((pub.root / "logs").glob(f"publish-*-{pub.lot}.log"))
    assert len(logs) == 1 and "Riepilogo da incollare" in logs[0].read_text(encoding="utf-8")
    assert not (pub.root / "logs" / "publish.lock").exists()


def test_the_dry_run_reads_the_real_state_and_writes_nothing(pub):
    done, calls = pub(answer="", env="DRY_RUN=1")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "PROVA A SECCO" in done.stdout and "scrivi pubblica" not in done.stdout
    assert steps(calls) == [f"publish staging {pub.git('rev-parse', pub.lot)} (a secco)",
                            f"deploy-engine {pub.git('rev-parse', pub.lot)} (a secco)"]
    assert "la produzione si prova a secco solo quando lo staging serve già" in done.stdout   # D-203
    assert "services describe domotica-bff-staging" in calls and "ENGINE_IMAGE" in calls          # it did read
    assert not (pub.root / "logs" / f"publish-state-{pub.lot}.txt").exists()
    # the summary says what is to be done: on 10 November it said «aggiornato» for what the dry run had not touched
    summary = done.stdout.split("Riepilogo", 1)[1]
    assert (f"motore dev: da aggiornare, da {pub.on_vm} a {pub.lot}; engine-vm.sh da aggiornare sulla VM; "
            f"compose.yaml da aggiornare sulla VM") in summary
    assert "aggiornato" not in summary and "ricreato" not in summary


def test_a_dry_run_with_only_a_new_compose_file_says_the_engine_is_to_be_recreated(pub):
    (pub.stubs / "vm-image").write_text(f"{ENGINE}{pub.lot}\n", encoding="utf-8")
    same_on_vm(pub)
    (pub.stubs / "vm-compose-hash").write_text("diverso  -\n", encoding="utf-8")
    done, calls = pub(answer="", env="DRY_RUN=1")
    assert done.returncode == 0, done.stdout + done.stderr
    summary = done.stdout.split("Riepilogo", 1)[1]
    assert (f"motore dev: da ricreare con la stessa immagine ({pub.lot}) per il nuovo compose.yaml; "
            f"compose.yaml da aggiornare sulla VM") in summary
    assert "scp" not in steps(calls) and "update" not in steps(calls)


def test_any_other_answer_changes_nothing(pub):
    done, calls = pub(answer="si\n")
    assert done.returncode != 0 and "FERMO: Pubblicazione annullata" in done.stdout + done.stderr
    assert steps(calls) == []


def test_production_never_starts_when_staging_is_not_healthy(pub):
    (pub.stubs / "health-staging.example").write_text("503", encoding="utf-8")
    done, calls = pub()
    out = done.stdout + done.stderr
    assert done.returncode != 0 and "domotica-bff-staging non risponde 200 su /health (ultimo codice: 503)" in out
    assert "update-traffic domotica-bff-staging --to-revisions=rev-a=100" in out
    assert steps(calls) == [f"publish staging {pub.git('rev-parse', pub.lot)}"]


def test_after_a_fermo_the_same_command_starts_again_from_the_right_place(pub):
    (pub.stubs / "publish-fails-prod").write_text("", encoding="utf-8")
    done, calls = pub()
    assert done.returncode != 0 and "publish.sh TARGET=prod si è fermato" in done.stdout + done.stderr
    (pub.stubs / "publish-fails-prod").unlink()
    done, calls = pub()
    assert done.returncode == 0, done.stdout + done.stderr
    assert "già fatto in un giro precedente" in done.stdout
    assert [s for s in steps(calls) if s.startswith("publish")] == [f"publish prod {pub.git('rev-parse', pub.lot)}"]
    assert "update-traffic domotica-bff-staging --to-revisions=rev-a=100" in done.stdout   # the revision of before stays


def test_documents_in_engine_do_not_rebuild_the_engine_and_the_same_script_is_not_copied(pub):
    """D-215: only what goes into the engine's image counts (no *.md, no tests/)."""
    pub.git("commit", "-q", "--allow-empty", "-m", "segnaposto")
    (pub.stubs / "vm-image").write_text(f"{ENGINE}{pub.lot}\n", encoding="utf-8")       # the VM runs the lot's engine
    (pub.root / "engine" / "connector").mkdir()
    (pub.root / "engine" / "connector" / "connector-v2.md").write_text("# contratto\n", encoding="utf-8")
    (pub.root / "engine" / "tests").mkdir()
    (pub.root / "engine" / "tests" / "test_x.py").write_text("def test(): pass\n", encoding="utf-8")
    pub.git("add", "-A")
    pub.git("commit", "-q", "-m", "solo documenti e prove")
    pub.git("push", "-q", "origin", "main")
    head = pub.git("rev-parse", "--short", "HEAD")
    same_on_vm(pub)
    done, calls = pub(commit=head)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "codice del motore invariato" in done.stdout and "motore dev: invariato" in done.stdout
    assert [s for s in steps(calls) if not s.startswith("publish")] == []


def same_on_vm(pub):
    """The VM has the commit's engine-vm.sh and compose.yaml (their hashes without \\r, as the script reads them)."""
    for name, rel in (("vm-script-hash", "scripts/engine-vm.sh"), ("vm-compose-hash", "engine/compose.yaml")):
        data = (pub.root / rel).read_bytes().replace(b"\r", b"")
        (pub.stubs / name).write_text(f"{hashlib.sha256(data).hexdigest()}  -\n", encoding="utf-8")


def test_a_new_compose_file_alone_recreates_the_engine_with_the_same_image(pub):
    """D-218: install copies engine/compose.yaml once; when only that file changes (the ports on the internal address),
    publish-all copies it and recreates the engine with the image it already runs, so the change takes effect."""
    (pub.stubs / "vm-image").write_text(f"{ENGINE}{pub.lot}\n", encoding="utf-8")       # the engine's code is current
    same_on_vm(pub)
    (pub.stubs / "vm-compose-hash").write_text("diverso  -\n", encoding="utf-8")       # but not its compose.yaml
    done, calls = pub()
    assert done.returncode == 0, done.stdout + done.stderr
    assert [s for s in steps(calls) if not s.startswith("publish")] == ["scp", "compose", "update"]
    update = next(line for line in calls.splitlines() if "engine-vm.sh update" in line)
    assert f"update dev {ENGINE}{pub.lot}" in update                                    # the same image
    assert f"ricreato con la stessa immagine ({pub.lot}) per il nuovo compose.yaml" in done.stdout
    assert "compose.yaml aggiornato sulla VM" in done.stdout


def test_a_commit_not_on_github_stops_before_the_question(pub):
    pub.git("commit", "-q", "--allow-empty", "-m", "non ancora su GitHub")
    done, calls = pub(commit=pub.git("rev-parse", "--short", "HEAD"))
    assert done.returncode != 0 and "non è su GitHub" in done.stdout + done.stderr and "scrivi pubblica" not in done.stdout
    assert steps(calls) == []


def test_production_values_unlike_the_manifest_stop(pub):
    (pub.stubs / "values-prod").write_text("1|1|1000|3600\n", encoding="utf-8")
    done, calls = pub()
    out = done.stdout + done.stderr
    assert done.returncode != 0 and "Valori attivi della produzione diversi dal manifesto: attivi 1|1|1000|3600" in out
    assert "engine" not in pub.state().splitlines() and "deploy-engine" not in calls


def test_an_engine_that_does_not_come_back_healthy_says_how_to_go_back(pub):
    (pub.stubs / "update-fails").write_text("", encoding="utf-8")
    done, calls = pub()
    out = done.stdout + done.stderr
    assert done.returncode != 0 and "non è tornato sano" in out
    assert f"engine-vm.sh update dev {ENGINE}{pub.on_vm}" in out


@pytest.mark.parametrize("change, words", [
    ("unknown", "un nome che non conosco: ALTRO"),
    ("missing", "manca SMTP_USER"),
    ("lock", "C'è già una pubblicazione in corso"),
])
def test_settings_and_the_lock_are_checked_first(pub, change, words):
    settings = pub.root / "scripts" / "publish-settings.conf"
    text = settings.read_text(encoding="utf-8")
    if change == "unknown":
        settings.write_text(text + "ALTRO=1\n", encoding="utf-8", newline="\n")
    elif change == "missing":
        settings.write_text(re.sub(r"^SMTP_USER=.*\n", "", text, flags=re.M), encoding="utf-8", newline="\n")
    else:
        (pub.root / "logs" / "publish.lock").mkdir(parents=True)
    done, calls = pub()
    assert done.returncode != 0 and words in done.stdout + done.stderr
    assert steps(calls) == []


def test_the_real_settings_have_every_name_and_no_secret():
    text = (ROOT / "scripts" / "publish-settings.conf").read_text(encoding="utf-8")
    names = {line.split("=", 1)[0] for line in text.splitlines() if line and not line.startswith("#")}
    known = re.search(r'^KNOWN="([^"]+)"', SCRIPT.read_text(encoding="utf-8"), re.M).group(1).split()
    assert names == set(known)
    values = " ".join(line for line in text.splitlines() if line and not line.startswith("#"))
    assert not re.search(r"(?i)password|secret|token|key", values)          # the comments may name them, never a value
