"""Tool A, package A1: scripts/agent-gcp.sh, the Google Cloud pieces of the order receiver for STAGING
(docs/progetto-strumento-a-base.md §1, §4.2, §4.3, §5.4, §6.7). Written only: the committente runs it after step 2.
Here gcloud is a stand-in that records what it is asked: DRY_RUN creates nothing, the real run creates only what is
missing with the exact options, a second run changes nothing, production is refused, and the only publisher of the
orders is the staging server's account."""
import json
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
name="$(echo "$*" | awk '{print $4}')"
case "$*" in
  *"subscriptions create "*|*"topics create "*) touch "$STUB_DIR/made-$name" ;;
esac
case "$*" in
  *"get-iam-policy"*|*"asset analyze-iam-policy"*|*"subscriptions describe"*)
    exec python3 "$STUB_DIR/stub.py" "$@" ;;
  *"projects describe"*) echo 444239063209; exit 0 ;;
  *"run services describe"*"run.googleapis.com/urls"*)
    [ -f "$STUB_DIR/stable-url" ] && echo '["https://domotica-bff-staging-444239063209.europe-west8.run.app","__URL__"]'
    exit 0 ;;
  *"run services describe"*) echo "__URL__"; exit 0 ;;
  *"channels list"*) echo "projects/__P__/notificationChannels/951"; exit 0 ;;
  *" describe "*) { [ -f "$STUB_DIR/exists" ] || [ -f "$STUB_DIR/made-$name" ]; } && { echo "esiste"; exit 0; }; exit 1 ;;
  *"policies list"*) [ -f "$STUB_DIR/exists" ] && { echo "esiste"; exit 0; }; exit 1 ;;
esac
exit 0
'''


STUB_PY = r'''"""gcloud's JSON answers for the checks of agent-gcp.sh: what the script made, changed by change-<x>.json;
the policies (policy-<resource>.json) and the analyses (asset.json, asset-sa.json) as the test writes them."""
import json
import os
import sys
from pathlib import Path

d = Path(os.environ["STUB_DIR"])
args = sys.argv[1:]
line = " ".join(args)
p = "__P__"
server = f"serviceAccount:domotica-bff-staging@{p}.iam.gserviceaccount.com"
vm = f"serviceAccount:langbrain-vm@{p}.iam.gserviceaccount.com"
agent = "serviceAccount:service-444239063209@gcp-sa-pubsub.iam.gserviceaccount.com"


def answer(name, default):
    f = d / name
    print(f.read_text() if f.exists() else json.dumps(default))
    sys.exit(0)


if "topics get-iam-policy" in line:
    name = args[args.index("get-iam-policy") + 1]
    who = {"domhouse-staging-ordini": server, "domhouse-staging-risultati": vm, "domhouse-staging-scarti": agent}[name]
    answer(f"policy-{name}.json", {"bindings": [{"role": "roles/pubsub.publisher", "members": [who]}]})
if "subscriptions get-iam-policy" in line:
    name = args[args.index("get-iam-policy") + 1]
    answer(f"policy-{name}.json", {"bindings": [{"role": "roles/pubsub.subscriber", "members": [vm, agent]}]})
if "asset analyze-iam-policy" in line:
    if (d / "asset-fails").exists():
        sys.exit(1)
    if "serviceAccounts/" in line:
        answer("asset-sa.json", {"mainAnalysis": {"fullyExplored": True, "analysisResults": []}})
    answer("asset.json", {"mainAnalysis": {"fullyExplored": True, "analysisResults": [
        {"iamBinding": {"role": "roles/pubsub.publisher", "members": [server]}}]}})
name = args[args.index("describe") + 1]
if not ((d / f"made-{name}").exists() or (d / "exists").exists()):
    sys.exit(1)
endpoint = ("https://domotica-bff-staging-444239063209.europe-west8.run.app" if (d / "stable-url").exists()
            else "__URL__") + "/internal/agent/risultati"
topic = lambda n: f"projects/{p}/topics/{n}"
base = {
    "domhouse-staging-ordini-vm": ("sub.json", {
        "topic": topic("domhouse-staging-ordini"),
        "ackDeadlineSeconds": 60, "messageRetentionDuration": "3600s", "enableMessageOrdering": True,
        "deadLetterPolicy": {"deadLetterTopic": topic("domhouse-staging-scarti"), "maxDeliveryAttempts": 5},
        "retryPolicy": {"minimumBackoff": "10s", "maximumBackoff": "60s"}}),
    "domhouse-staging-scarti-lettura": ("dead.json", {"topic": topic("domhouse-staging-scarti"),
                                                      "messageRetentionDuration": "604800s"}),
    "domhouse-staging-risultati-push": ("push.json", {"topic": topic("domhouse-staging-risultati"), "pushConfig": {
        "pushEndpoint": endpoint, "oidcToken": {
            "serviceAccountEmail": f"domhouse-push-staging@{p}.iam.gserviceaccount.com", "audience": endpoint}}}),
}[name]
data = dict(base[1])
change = d / f"change-{base[0]}"
if change.exists():
    data.update(json.loads(change.read_text()))
print(json.dumps(data))
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
    (stubs / "stub.py").write_text(STUB_PY.replace("__URL__", URL).replace("__P__", P), encoding="utf-8")
    (stubs / "python3").write_text(f'#!/usr/bin/env bash\nexec "{posix(Path(sys.executable))}" "$@"\n',
                                   encoding="utf-8", newline="\n")
    (stubs / "python3").chmod(0o755)

    def run(*args, dry=False, env=""):
        cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}" {env}; '
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


# ---- second reading, 16 November (security review of A1: R3, question b) -----------------------------------------
SERVER_SA = f"serviceAccount:domotica-bff-staging@{P}.iam.gserviceaccount.com"
PUBSUB_AGENT_SA = "serviceAccount:service-444239063209@gcp-sa-pubsub.iam.gserviceaccount.com"


def write(gcp, name, data):
    (gcp.stubs / name).write_text(json.dumps(data), encoding="utf-8")


def test_b_no_token_creator_for_pubsubs_agent(gcp):
    _, calls = gcp("staging")
    assert "serviceAccountTokenCreator" not in calls


def test_r3_the_checks_pass_on_what_the_script_made(gcp):
    out, calls = gcp("staging")
    assert out.returncode == 0, out.stderr + out.stdout
    assert "controlli superati" in out.stdout
    assert "topics get-iam-policy domhouse-staging-ordini" in calls
    assert "asset analyze-iam-policy" in calls and "--permissions=pubsub.topics.publish" in calls


def test_r3_another_publisher_on_the_orders_topic_stops_the_script(gcp):
    write(gcp, "policy-domhouse-staging-ordini.json", {"bindings": [{"role": "roles/pubsub.publisher",
                                              "members": [SERVER_SA, "serviceAccount:altro@x.iam.gserviceaccount.com"]}]})
    out, _ = gcp("staging")
    assert out.returncode != 0 and "altro@x" in (out.stderr + out.stdout)


def test_r3_a_service_account_that_can_publish_from_the_project_stops_it_an_admitted_person_does_not(gcp):
    write(gcp, "asset.json", {"mainAnalysis": {"fullyExplored": True, "analysisResults": [
        {"iamBinding": {"role": "roles/owner", "members": ["user:proprietario@example.com"]}},
        {"iamBinding": {"role": "roles/pubsub.publisher", "members": [SERVER_SA]}}]}})
    out, _ = gcp("staging", env="PERSONE_AMMESSE=proprietario@example.com")
    assert out.returncode == 0, out.stderr + out.stdout
    assert "proprietario@example.com" in out.stdout                        # listed, accepted: an admitted person
    out, _ = gcp("staging")                                                 # R3-d: not in PERSONE_AMMESSE: stops
    assert out.returncode != 0 and "proprietario@example.com" in (out.stderr + out.stdout)
    write(gcp, "asset.json", {"mainAnalysis": {"fullyExplored": True, "analysisResults": [
        {"iamBinding": {"role": "roles/editor", "members": ["serviceAccount:444239063209-compute@developer.gserviceaccount.com"]}},
        {"iamBinding": {"role": "roles/pubsub.publisher", "members": [SERVER_SA]}}]}})
    out, _ = gcp("staging")
    assert out.returncode != 0 and "compute@developer" in (out.stderr + out.stdout)


def test_r3_if_the_analysis_cannot_be_read_the_script_stops(gcp):
    (gcp.stubs / "asset-fails").write_text("", encoding="utf-8")
    out, _ = gcp("staging")
    assert out.returncode != 0 and "Cloud Asset" in (out.stderr + out.stdout)


@pytest.mark.parametrize("name, change, says", [
    ("sub.json", {"enableMessageOrdering": False}, "enableMessageOrdering"),
    ("sub.json", {"deadLetterPolicy": {"deadLetterTopic": "projects/x/topics/altro", "maxDeliveryAttempts": 5}},
     "deadLetterTopic"),
    ("push.json", {"pushConfig": {"pushEndpoint": "https://evil.example/x",
                                  "oidcToken": {"serviceAccountEmail": "x@y", "audience": "https://evil.example/x"}}},
     "pushEndpoint"),
    ("dead.json", {"messageRetentionDuration": "3600s"}, "messageRetentionDuration"),
])
def test_r3_an_existing_resource_that_differs_stops_the_script(gcp, name, change, says):
    (gcp.stubs / "exists").write_text("", encoding="utf-8")
    write(gcp, f"change-{name}", change)
    out, _ = gcp("staging")
    assert out.returncode != 0 and says in (out.stderr + out.stdout)


def test_the_push_goes_to_the_stable_address_of_the_service_like_deploy_sh(gcp):
    """The audience the manifest of the staging server holds (AGENT_PUSH_AUDIENCE) is written before the script runs:
    https://domotica-bff-staging-<project number>.europe-west8.run.app, as scripts/deploy.sh prefers."""
    (gcp.stubs / "stable-url").write_text("", encoding="utf-8")
    stable = "https://domotica-bff-staging-444239063209.europe-west8.run.app/internal/agent/risultati"
    out, calls = gcp("staging")
    assert out.returncode == 0, out.stderr + out.stdout
    [push] = [c for c in creates(calls) if "subscriptions create domhouse-staging-risultati-push" in c]
    assert f"--push-endpoint={stable}" in push and f"--push-auth-token-audience={stable}" in push


# ---- third reading, 16 November (R3-a to R3-e) ---------------------------------------------------------------------
VM_SA = f"serviceAccount:langbrain-vm@{P}.iam.gserviceaccount.com"


def test_r3a_an_existing_resource_that_differs_stops_before_any_write(gcp):
    (gcp.stubs / "exists").write_text("", encoding="utf-8")
    write(gcp, "change-sub.json", {"enableMessageOrdering": False})
    out, calls = gcp("staging")
    assert out.returncode != 0 and "prima" in (out.stderr + out.stdout)
    assert creates(calls) == []                                              # nothing written


@pytest.mark.parametrize("analysis, says", [
    ({"mainAnalysis": {"fullyExplored": True, "analysisResults": []}}, "non vede il server"),
    ({"mainAnalysis": {"fullyExplored": False, "analysisResults": [
        {"iamBinding": {"role": "roles/pubsub.publisher", "members": [SERVER_SA]}}]}}, "non completa"),
    ({"mainAnalysis": {"fullyExplored": True, "nonCriticalErrors": [{"cause": "x"}], "analysisResults": [
        {"iamBinding": {"role": "roles/pubsub.publisher", "members": [SERVER_SA]}}]}}, "con errori"),
])
def test_r3b_an_analysis_that_cannot_be_trusted_stops(gcp, analysis, says):
    write(gcp, "asset.json", analysis)
    out, _ = gcp("staging")
    assert out.returncode != 0 and says in (out.stderr + out.stdout)


def test_r3c_the_vm_must_not_impersonate_the_server(gcp):
    write(gcp, "asset-sa.json", {"mainAnalysis": {"fullyExplored": True, "analysisResults": [
        {"iamBinding": {"role": "roles/iam.serviceAccountTokenCreator", "members": [VM_SA]}}]}})
    out, calls = gcp("staging")
    assert out.returncode != 0 and "impersonare" in (out.stderr + out.stdout)
    assert "serviceAccounts/domotica-bff-staging@" in calls


def test_r3d_a_custom_role_on_the_orders_topic_stops(gcp):
    write(gcp, "policy-domhouse-staging-ordini.json", {"bindings": [
        {"role": "roles/pubsub.publisher", "members": [SERVER_SA]},
        {"role": f"projects/{P}/roles/qualcosa", "members": ["user:x@example.com"]}]})
    out, _ = gcp("staging")
    assert out.returncode != 0 and "ruolo personalizzato" in (out.stderr + out.stdout)


def test_r3e_topics_publishers_of_the_results_and_readers_of_the_orders(gcp):
    (gcp.stubs / "exists").write_text("", encoding="utf-8")
    write(gcp, "change-dead.json", {"topic": f"projects/{P}/topics/un-altra"})
    out, _ = gcp("staging")
    assert out.returncode != 0 and "topic" in (out.stderr + out.stdout)
    (gcp.stubs / "change-dead.json").unlink()
    write(gcp, "policy-domhouse-staging-risultati.json", {"bindings": [
        {"role": "roles/pubsub.publisher", "members": [VM_SA, "serviceAccount:altro@x.iam.gserviceaccount.com"]}]})
    out, _ = gcp("staging")
    assert out.returncode != 0 and "coda dei risultati" in (out.stderr + out.stdout)
    (gcp.stubs / "policy-domhouse-staging-risultati.json").unlink()
    write(gcp, "policy-domhouse-staging-ordini-vm.json", {"bindings": [
        {"role": "roles/pubsub.subscriber", "members": [VM_SA, "user:curioso@example.com"]}]})
    out, _ = gcp("staging")
    assert out.returncode != 0 and "legge la sottoscrizione" in (out.stderr + out.stdout)


# ---- fourth reading, 16 November (impersonation by allow-list, the stop message) -----------------------------------
@pytest.mark.parametrize("member", ["principal://iam.googleapis.com/projects/1/locations/global/workloadIdentityPools/p/subject/s",
                                    "principalSet://iam.googleapis.com/projects/1/locations/global/workloadIdentityPools/p/*",
                                    "deleted:serviceAccount:vecchio@x.iam.gserviceaccount.com?uid=1"])
def test_impersonation_only_the_server_and_the_admitted_persons(gcp, member):
    write(gcp, "asset-sa.json", {"mainAnalysis": {"fullyExplored": True, "analysisResults": [
        {"iamBinding": {"role": "roles/iam.serviceAccountTokenCreator", "members": [member]}}]}})
    out, _ = gcp("staging")
    assert out.returncode != 0 and "impersonare" in (out.stderr + out.stdout)


def test_the_stop_message_before_writing_says_nothing_changed(gcp):
    (gcp.stubs / "exists").write_text("", encoding="utf-8")
    write(gcp, "change-sub.json", {"enableMessageOrdering": False})
    out, _ = gcp("staging")
    text = out.stderr + out.stdout
    assert "Controlli non superati (prima): niente è stato cambiato." in text and "cambiatoprima" not in text
