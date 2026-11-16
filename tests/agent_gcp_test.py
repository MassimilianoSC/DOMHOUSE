"""Tool A, package A1: scripts/agent-gcp.sh, the Google Cloud pieces of the order receiver for STAGING
(docs/progetto-strumento-a-base.md §1, §4.2, §4.3, §5.4, §6.7). Written only: the committente runs it after step 2.
Here gcloud is a stand-in that records what it is asked: DRY_RUN creates nothing, the real run creates only what is
missing with the exact options, a second run changes nothing, production is refused, and the only publisher of the
orders is the staging server's account."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "agent-gcp.sh"
P = "domotica-poc-511707"
URL = "https://domotica-bff-staging-abc123-ew.a.run.app"

GCLOUD = r'''#!/usr/bin/env bash
echo "gcloud $*" >> "$STUB_DIR/calls.log"
case "$*" in
  *"projects describe"*) echo 444239063209; exit 0 ;;
  *"run services describe"*) echo "__URL__"; exit 0 ;;
  *"channels list"*) echo "projects/__P__/notificationChannels/951"; exit 0 ;;
  *" describe "*|*"policies list"*) [ -f "$STUB_DIR/exists" ] && { echo "esiste"; exit 0; }; exit 1 ;;
esac
exit 0
'''


def _bash():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_tests", ROOT / "scripts" / "run_tests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.git_bash()


def posix(path: Path) -> str:
    s = path.as_posix()
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else s


@pytest.fixture
def gcp(tmp_path):
    bash = _bash()
    if not bash:
        pytest.skip("bash non disponibile")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "gcloud").write_text(GCLOUD.replace("__URL__", URL).replace("__P__", P), encoding="utf-8", newline="\n")
    (stubs / "gcloud").chmod(0o755)
    (stubs / "python3").write_text(f'#!/usr/bin/env bash\nexec "{posix(Path(sys.executable))}" "$@"\n',
                                   encoding="utf-8", newline="\n")
    (stubs / "python3").chmod(0o755)

    def run(*args, dry=False):
        cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}"; '
               f'{"DRY_RUN=1 " if dry else ""}GCP_PROJECT_ID={P} bash "{posix(SCRIPT)}" ' + " ".join(args))
        out = subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=300)
        log = stubs / "calls.log"
        calls = log.read_text(encoding="utf-8") if log.exists() else ""
        log.unlink(missing_ok=True)
        return out, calls

    run.stubs = stubs
    return run


def creates(calls: str) -> list[str]:
    return [line for line in calls.splitlines() if re.search(r" (create|add-iam-policy-binding)( |$)", line)]


def test_dry_run_creates_nothing(gcp):
    out, calls = gcp("staging", dry=True)
    assert out.returncode == 0, out.stderr
    assert creates(calls) == [] and "(prova a secco)" in out.stdout


def test_the_real_run_creates_the_queues_the_subscriptions_and_the_permissions(gcp):
    out, calls = gcp("staging")
    assert out.returncode == 0, out.stderr
    made = creates(calls)
    topics = [c for c in made if "pubsub topics create" in c]
    assert [re.search(r"topics create (\S+)", c).group(1) for c in topics] == [
        "domhouse-staging-ordini", "domhouse-staging-risultati", "domhouse-staging-scarti"]
    [orders] = [c for c in made if "subscriptions create domhouse-staging-ordini-vm" in c]
    for option in ("--topic=domhouse-staging-ordini", "--ack-deadline=60", "--message-retention-duration=1h",
                   "--dead-letter-topic=domhouse-staging-scarti", "--max-delivery-attempts=5",
                   "--min-retry-delay=10s", "--max-retry-delay=60s", "--enable-message-ordering",
                   "--expiration-period=never"):
        assert option in orders, option
    [dead] = [c for c in made if "subscriptions create domhouse-staging-scarti-lettura" in c]
    assert "--message-retention-duration=7d" in dead
    [push] = [c for c in made if "subscriptions create domhouse-staging-risultati-push" in c]
    assert f"--push-endpoint={URL}/internal/agent/risultati" in push
    assert f"--push-auth-token-audience={URL}/internal/agent/risultati" in push
    assert f"--push-auth-service-account=domhouse-push-staging@{P}.iam.gserviceaccount.com" in push
    assert any("service-accounts create domhouse-push-staging" in c for c in made)


def test_who_may_do_what(gcp):
    _, calls = gcp("staging")
    made = creates(calls)
    bindings = [c for c in made if "add-iam-policy-binding" in c]

    def who(target, role):
        return sorted(re.search(r"--member=(\S+)", c).group(1) for c in bindings
                      if f" {target} " in c and f"--role={role}" in c)
    vm = f"serviceAccount:langbrain-vm@{P}.iam.gserviceaccount.com"
    server = f"serviceAccount:domotica-bff-staging@{P}.iam.gserviceaccount.com"
    pubsub_agent = "serviceAccount:service-444239063209@gcp-sa-pubsub.iam.gserviceaccount.com"
    assert who("domhouse-staging-ordini", "roles/pubsub.publisher") == [server]        # the only publisher (§10.3)
    assert who("domhouse-staging-ordini-vm", "roles/pubsub.subscriber") == sorted([vm, pubsub_agent])
    assert who("domhouse-staging-risultati", "roles/pubsub.publisher") == [vm]
    assert who("domhouse-staging-scarti", "roles/pubsub.publisher") == [pubsub_agent]
    assert not any("domhouse-prod" in c or "projects add-iam-policy-binding" in c for c in made)  # never project-wide


def test_two_alarms_on_the_existing_channel(gcp):
    _, calls = gcp("staging")
    policies = [c for c in creates(calls) if "policies create" in c]
    assert len(policies) == 2
    files = sorted((ROOT / "scripts" / "agent" / "allarmi").glob("*.json"))
    assert [f.name for f in files] == ["agente-allarme.json", "scarti-non-vuoti.json"]


def test_a_second_run_changes_nothing(gcp):
    (gcp.stubs / "exists").write_text("", encoding="utf-8")
    out, calls = gcp("staging")
    assert out.returncode == 0 and [c for c in creates(calls) if "create" in c] == []
    assert "esiste già" in out.stdout


def test_production_is_refused(gcp):
    out, calls = gcp("prod")
    assert out.returncode != 0 and "produzione" in (out.stderr + out.stdout) and creates(calls) == []
