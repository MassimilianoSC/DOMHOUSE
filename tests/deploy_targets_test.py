"""scripts/deploy.sh by TARGET (P-67, D-136): staging and production in the same project, each with its Cloud Run
service, Firestore database and Hosting site; a manifest that is not the TARGET's stops before anything is published.
The real script in a throwaway copy of the repository, with stand-ins for gcloud, npx and yarn that record what they
are asked. D-197: the service's active values against the manifest's, the new revision checked, DRY_RUN writing
nothing."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def posix(path: Path) -> str:
    s = path.as_posix()
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else s


def _bash():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_tests", ROOT / "scripts" / "run_tests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.git_bash()


GCLOUD = r'''#!/usr/bin/env bash
echo "gcloud $*" >> "$STUB_DIR/calls.log"
case "$*" in
  *"run services replace"*) cp "$4" "$STUB_DIR/rendered.yaml" ;;
  *"services describe"*status.traffic*) [ -f "$STUB_DIR/staging_image.txt" ] && cat "$STUB_DIR/staging_image.txt" ;;
  *"services describe"*minScale*) [ -f "$STUB_DIR/live.txt" ] && cat "$STUB_DIR/live.txt" ;;
  *"services describe"*latestReadyRevisionName*) echo rev-nuova ;;
  *"services describe"*urls*) echo '["https://SERVIZIO-444.europe-west8.run.app"]' ;;
  *"revisions describe"*)
    if [ -f "$STUB_DIR/applied.txt" ]; then cat "$STUB_DIR/applied.txt"; else
      m() { sed -n "s#^ *$1: *\"\{0,1\}\([0-9]*\).*#\1#p" "$STUB_DIR/rendered.yaml" | head -1; }
      echo "$(m autoscaling.knative.dev/minScale)|$(m autoscaling.knative.dev/maxScale)|$(m containerConcurrency)|$(m timeoutSeconds)"
    fi ;;
esac
exit 0
'''
NPX = '#!/usr/bin/env bash\necho "npx $*" >> "$STUB_DIR/calls.log"\nexit 0\n'
YARN = ('#!/usr/bin/env bash\necho "yarn $*" >> "$STUB_DIR/calls.log"\n'
        'case "$*" in *build*) mkdir -p dist; echo x > dist/index.html ;; esac\nexit 0\n')


@pytest.fixture
def repo(tmp_path):
    bash = _bash()
    if not bash:
        pytest.skip("bash non disponibile")
    r = tmp_path / "app"
    for rel in ("scripts/deploy.sh", "bff/cloudrun.yaml", "bff/cloudrun.staging.yaml", "frontend/.firebaserc"):
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, r / rel)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in (("gcloud", GCLOUD), ("npx", NPX), ("yarn", YARN)):
        (stubs / name).write_text(body, encoding="utf-8", newline="\n")
        (stubs / name).chmod(0o755)

    def run(target, env="SKIP_BUILD=1"):
        cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}"; cd "{posix(r)}" && '
               f'TARGET={target} GCP_PROJECT_ID=progetto-prova VPC_NETWORK=default VPC_SUBNET=default {env} '
               f'bash scripts/deploy.sh')
        out = subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=60)
        calls = (stubs / "calls.log").read_text(encoding="utf-8") if (stubs / "calls.log").exists() else ""
        rendered = (stubs / "rendered.yaml").read_text(encoding="utf-8") if (stubs / "rendered.yaml").exists() else ""
        for f in ("calls.log", "rendered.yaml"):
            (stubs / f).unlink(missing_ok=True)
        return out, calls, rendered

    run.root = r
    run.stubs = stubs
    return run


def test_staging_publishes_its_service_database_and_site(repo):
    out, calls, rendered = repo("staging")
    assert out.returncode == 0, out.stderr
    assert "servizio domotica-bff-staging, database staging, sito progetto-prova-staging" in out.stdout
    assert "add-iam-policy-binding domotica-bff-staging" in calls and "services describe domotica-bff-staging" in calls
    assert "name: domotica-bff-staging" in rendered and "https://progetto-prova-staging.web.app" in rendered
    assert "your-" not in rendered                                        # every placeholder filled
    assert "target:apply hosting staging progetto-prova-staging" in calls and "deploy --only hosting:staging" in calls
    assert "PWA: https://progetto-prova-staging.web.app" in out.stdout
    assert (repo.root / "frontend" / ".firebaserc").read_text(encoding="utf-8") == \
        (ROOT / "frontend" / ".firebaserc").read_text(encoding="utf-8")    # put back as committed


def test_production_publishes_its_own(repo):
    out, calls, rendered = repo("prod")
    assert out.returncode == 0, out.stderr
    assert "servizio domotica-bff, database (default), sito progetto-prova" in out.stdout
    assert "add-iam-policy-binding domotica-bff " in calls and "deploy --only hosting:prod" in calls
    assert re.search(r"name: FIRESTORE_DATABASE[^\n]*\n\s*value: \"\(default\)\"", rendered)


def test_a_manifest_that_is_not_the_targets_stops_before_publishing(repo):
    staging = repo.root / "bff" / "cloudrun.staging.yaml"
    staging.write_text(staging.read_text(encoding="utf-8").replace("value: staging", "value: \"(default)\""),
                       encoding="utf-8")                                   # staging pointing at production's database
    out, calls, _ = repo("staging")
    assert out.returncode != 0 and "does not use the database staging" in out.stderr
    assert "gcloud" not in calls                                          # nothing published


def test_a_model_outside_europe_stops_before_publishing(repo):
    """D-180: deploy.sh reads AI_LOCATION in the TARGET's manifest and stops on global, us or anything not European."""
    prod = repo.root / "bff" / "cloudrun.yaml"
    original = prod.read_text(encoding="utf-8")
    for bad in ("global", "us"):
        prod.write_text(original.replace('value: "eu"', f'value: "{bad}"', 1), encoding="utf-8")
        out, calls, _ = repo("prod")
        assert out.returncode != 0 and f"AI_LOCATION {bad} is not European" in out.stderr
        assert "gcloud" not in calls                                      # nothing published
    prod.write_text(original.replace('value: "eu"', 'value: "europe-west1"', 1), encoding="utf-8")
    out, _, _ = repo("prod")
    assert out.returncode == 0, out.stderr


# -------- D-197 (E-27): the service's values at every publication --------
WRITES = ("services replace", "builds submit", "add-iam-policy-binding", "npx ")


def test_the_active_values_are_shown_before_and_the_new_revision_checked_after(repo):
    (repo.stubs / "live.txt").write_text("|1|1000|300\n", encoding="utf-8")     # as Cloud Run says a minimum of 0: empty
    out, calls, _ = repo("prod")
    assert out.returncode == 0, out.stderr
    line = {w: next(x for x in out.stdout.splitlines() if w in x)
            for w in ("istanze minime", "istanze massime", "richieste contemporanee", "tempo massimo")}
    assert re.search(r"attivo: 0 +nuovo: 1 +CAMBIA", line["istanze minime"])
    assert re.search(r"attivo: 1 +nuovo: 3 +CAMBIA", line["istanze massime"])
    assert re.search(r"attivo: 1000 +nuovo: 250 +CAMBIA", line["richieste contemporanee"])
    assert re.search(r"attivo: 300 +nuovo: 300 +non cambia", line["tempo massimo"])
    assert calls.index("minScale") < calls.index("services replace") < calls.index("revisions describe rev-nuova")
    assert "La revisione rev-nuova ha i valori del manifesto." in out.stdout


def test_a_first_publication_says_the_active_values_were_not_read(repo):
    out, _, _ = repo("staging")                                                # no live.txt: nothing answers
    assert out.returncode == 0, out.stderr
    assert "Valori attivi non letti" in out.stdout and re.search(r"attivo: non letto +nuovo: 0 ", out.stdout)


def test_a_minimum_of_zero_comes_back_empty_and_is_right(repo):
    (repo.stubs / "applied.txt").write_text("|1|250|300\n", encoding="utf-8")
    out, _, _ = repo("staging")
    assert out.returncode == 0, out.stderr
    assert "ha i valori del manifesto" in out.stdout


@pytest.mark.parametrize("applied, words", [
    ("1|3|250|3600\n", "tempo massimo: atteso 300, trovato 3600"),
    ("0|3|250|300\n", "istanze minime: atteso 1, trovato 0"),
    ("1|2|250|300\n", "istanze massime: atteso 3, trovato 2"),
    ("1|3|1000|300\n", "richieste contemporanee: atteso 250, trovato 1000"),
])
def test_a_revision_unlike_the_manifest_stops_before_the_site(repo, applied, words):
    (repo.stubs / "applied.txt").write_text(applied, encoding="utf-8")
    out, calls, _ = repo("prod")
    assert out.returncode != 0 and "FERMO" in out.stderr and words in out.stderr and "rev-nuova" in out.stderr
    assert "services replace" in calls and "npx " not in calls and "yarn " not in calls


def test_a_revision_that_cannot_be_read_stops_too(repo):
    (repo.stubs / "applied.txt").write_text("", encoding="utf-8")
    out, calls, _ = repo("prod")
    assert out.returncode != 0 and "Non riesco a rileggere la revisione nuova" in out.stderr and "npx " not in calls


def test_a_manifest_without_one_of_the_values_stops_before_anything(repo):
    prod = repo.root / "bff" / "cloudrun.yaml"
    prod.write_text(prod.read_text(encoding="utf-8").replace("timeoutSeconds: 300", "# no timeout"), encoding="utf-8")
    out, calls, _ = repo("prod")
    assert out.returncode != 0 and "non dichiara" in out.stderr and "gcloud" not in calls


def test_deploy_dry_run_only_reads(repo):
    (repo.stubs / "live.txt").write_text("1|1|250|3600\n", encoding="utf-8")
    out, calls, _ = repo("prod", env="DRY_RUN=1")                              # no SKIP_BUILD: it must not build either
    assert out.returncode == 0, out.stderr
    assert re.search(r"attivo: 3600 +nuovo: 300 +CAMBIA", out.stdout) and "Prova a secco" in out.stdout
    assert "services describe" in calls and not any(w in calls for w in WRITES) and "yarn " not in calls


@pytest.fixture
def publish(tmp_path):
    """The real publish.sh and deploy.sh in a throwaway repository with its first commit."""
    bash = _bash()
    if not bash:
        pytest.skip("bash non disponibile")
    r = tmp_path / "app"
    for rel in ("scripts/publish.sh", "scripts/deploy.sh", "bff/cloudrun.yaml", "bff/cloudrun.staging.yaml",
                "frontend/.firebaserc"):
        (r / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, r / rel)
    contract = subprocess.run(["git", "-C", str(ROOT), "show", "HEAD:contract/openapi.yaml"], capture_output=True,
                              check=True).stdout
    (r / "contract").mkdir()
    (r / "contract" / "openapi.yaml").write_bytes(contract)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in (("gcloud", GCLOUD), ("npx", NPX), ("yarn", YARN)):
        (stubs / name).write_text(body, encoding="utf-8", newline="\n")
        (stubs / name).chmod(0o755)
    (stubs / "live.txt").write_text("|1|250|3600\n", encoding="utf-8")
    env_file = tmp_path / "env.production"
    env_file.write_text("VITE_FIREBASE_API_KEY=chiave-di-prova\n", encoding="utf-8")
    for args in (["init", "-q"], ["config", "core.autocrlf", "false"], ["config", "user.email", "p@p.it"],
                 ["config", "user.name", "p"], ["add", "-A"], ["commit", "-q", "-m", "prova"]):
        subprocess.run(["git", "-C", str(r), *args], check=True, capture_output=True)

    def run(target, env="DRY_RUN=1"):
        (stubs / "calls.log").unlink(missing_ok=True)
        cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}"; cd "{posix(r)}" && '
               f'{env} TARGET={target} GCP_PROJECT_ID=progetto-prova VPC_NETWORK=default VPC_SUBNET=default '
               f'ENV_FILE="{posix(env_file)}" bash scripts/publish.sh')
        out = subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=120, stdin=subprocess.DEVNULL)
        return out, (stubs / "calls.log").read_text(encoding="utf-8") if (stubs / "calls.log").exists() else ""

    def git(*args):
        return subprocess.run(["git", "-C", str(r), *args], check=True, capture_output=True, text=True).stdout.strip()

    run.stubs, run.git = stubs, git
    return run


def test_publish_dry_run_shows_the_values_and_writes_nothing(publish):
    out, calls = publish("staging")
    assert out.returncode == 0, out.stdout + out.stderr
    assert re.search(r"attivo: 3600 +nuovo: 300 +CAMBIA", out.stdout) and "Prova a secco riuscita" in out.stdout
    assert "services describe domotica-bff-staging" in calls and not any(w in calls for w in WRITES)


# -------- D-203: production only with the commit that staging is running --------
READ_STAGING = "services describe domotica-bff-staging"
IMAGE = "europe-west8-docker.pkg.dev/progetto-prova/domotica/bff:"


def staging_runs(publish, tag, revisions="r1|r1|r1"):
    (publish.stubs / "staging_image.txt").write_text(f"{IMAGE}{tag}|{revisions}\n" if tag else "", encoding="utf-8")


def test_d203_the_commit_running_in_staging_goes_on(publish):
    staging_runs(publish, publish.git("rev-parse", "--short", "HEAD"))
    out, calls = publish("prod")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "in staging c'è lo stesso commit" in out.stdout
    assert f"gcloud run {READ_STAGING}" in calls and not any(w in calls for w in WRITES)


@pytest.mark.parametrize("env", ["DRY_RUN=1", "X=1"])
def test_d203_another_commit_in_staging_stops_before_anything(publish, env):
    """In a dry run as in a real publication; and before the questions, so nobody answers for nothing."""
    tag = publish.git("rev-parse", "--short", "HEAD")
    publish.git("commit", "-q", "--allow-empty", "-m", "un altro commit")
    head = publish.git("rev-parse", "--short", "HEAD")
    staging_runs(publish, tag)
    out, calls = publish("prod", env=env)
    assert out.returncode != 0 and "FERMO" in out.stderr
    assert f"In staging c'è: {tag} — prova" in out.stderr and f"Volevi pubblicare: {head} — un altro commit" in out.stderr
    assert not any(w in calls for w in WRITES) and "yarn " not in calls and "Per continuare" not in out.stdout


@pytest.mark.parametrize("tag, words", [
    ("deadbee", "In staging c'è: deadbee"),
    ("", "Non riesco a leggere quale commit c'è in staging"),
])
def test_d203_a_staging_that_cannot_be_recognised_stops(publish, tag, words):
    staging_runs(publish, tag)
    out, calls = publish("prod")
    assert out.returncode != 0 and "FERMO" in out.stderr and words in out.stderr
    assert not any(w in calls for w in WRITES) and "yarn " not in calls


@pytest.mark.parametrize("revisions", ["r2|r1|r1", "r2|r2|r1"])
def test_d203_a_publication_of_staging_that_did_not_take_over_stops(publish, revisions):
    """The right commit in the template, but a failed revision or the traffic left on an older one: staging is not running it."""
    staging_runs(publish, publish.git("rev-parse", "--short", "HEAD"), revisions=revisions)
    out, calls = publish("prod")
    assert out.returncode != 0 and "FERMO" in out.stderr and "non è quella che riceve il traffico" in out.stderr
    assert not any(w in calls for w in WRITES) and "yarn " not in calls


def test_d203_the_emergency_exit_warns_and_is_never_the_default(publish):
    staging_runs(publish, "deadbee")
    out, calls = publish("prod", env="DRY_RUN=1 SKIP_STAGING_CHECK=1")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "AVVISO: controllo su staging SALTATO" in out.stdout and "status.traffic" not in calls


def test_d203_staging_itself_is_not_checked(publish):
    staging_runs(publish, "deadbee")
    out, calls = publish("staging")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "status.traffic" not in calls


# -------- D-214: called by publish-all.sh, after its one question --------
def on_github(publish, tmp_path):
    """A bare repository as origin, with the commit pushed to main: what «is it on GitHub?» reads."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
    publish.git("branch", "-M", "main")
    publish.git("remote", "add", "origin", str(bare))
    publish.git("push", "-q", "origin", "main")


def test_d214_from_publish_all_a_commit_not_on_github_stops_and_asks_nothing(publish):
    out, calls = publish("staging", env="PUBLISH_ALL_CONFIRMED=pubblica X=1")
    assert out.returncode != 0 and "FERMO" in out.stderr and "non è su GitHub" in out.stderr and "git push" in out.stderr
    assert "pubblicare lo stesso?" not in out.stdout and not any(w in calls for w in WRITES)


def test_d214_from_publish_all_production_is_not_asked_again(publish, tmp_path):
    on_github(publish, tmp_path)
    staging_runs(publish, publish.git("rev-parse", "--short", "HEAD"))
    out, calls = publish("prod", env="PUBLISH_ALL_CONFIRMED=pubblica X=1")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "la conferma l'hai già data all'inizio di publish-all.sh" in out.stdout and "Per continuare" not in out.stdout
    assert "run services replace" in calls                                # it really published, with the stubs


def test_d214_without_publish_all_production_still_asks(publish, tmp_path):
    on_github(publish, tmp_path)
    staging_runs(publish, publish.git("rev-parse", "--short", "HEAD"))
    out, calls = publish("prod", env="PUBLISH_ALL_CONFIRMED=si X=1")      # any other value is not the confirmation
    assert out.returncode != 0 and "Per continuare scrivi prod:" in out.stdout and "Pubblicazione annullata" in out.stderr
    assert not any(w in calls for w in WRITES)
