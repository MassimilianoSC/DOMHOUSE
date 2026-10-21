"""scripts/deploy.sh by TARGET (P-67, D-136): staging and production in the same project, each with its Cloud Run
service, Firestore database and Hosting site; a manifest that is not the TARGET's stops before anything is published.
The real script in a throwaway copy of the repository, with stand-ins for gcloud, npx and yarn that record what they
are asked."""
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
  *"services describe"*urls*) echo '["https://SERVIZIO-444.europe-west8.run.app"]' ;;
esac
exit 0
'''
NPX = '#!/usr/bin/env bash\necho "npx $*" >> "$STUB_DIR/calls.log"\nexit 0\n'
YARN = '#!/usr/bin/env bash\necho "yarn $*" >> "$STUB_DIR/calls.log"\nexit 0\n'


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

    def run(target):
        cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}"; cd "{posix(r)}" && '
               f'TARGET={target} GCP_PROJECT_ID=progetto-prova VPC_NETWORK=default VPC_SUBNET=default SKIP_BUILD=1 '
               f'bash scripts/deploy.sh')
        out = subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=60)
        calls = (stubs / "calls.log").read_text(encoding="utf-8") if (stubs / "calls.log").exists() else ""
        rendered = (stubs / "rendered.yaml").read_text(encoding="utf-8") if (stubs / "rendered.yaml").exists() else ""
        for f in ("calls.log", "rendered.yaml"):
            (stubs / f).unlink(missing_ok=True)
        return out, calls, rendered

    run.root = r
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
