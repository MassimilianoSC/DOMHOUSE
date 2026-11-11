"""scripts/deploy-engine.sh <commit>: the engine's image of a given commit, built from a clean export of it, whatever the
working copy holds (the lot's commit can be published while work goes on). DRY_RUN=1, in a throwaway git repository:
nothing reaches Google Cloud."""
import importlib.util
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "deploy-engine.sh"


def _bash() -> str | None:
    spec = importlib.util.spec_from_file_location("run_tests", ROOT / "scripts" / "run_tests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.git_bash()


def posix(path: Path) -> str:
    s = path.as_posix()
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else s


@pytest.fixture
def repo(tmp_path):
    bash = _bash()
    if not bash or not shutil.which("git"):
        pytest.skip("bash o git non disponibili")
    r = tmp_path / "app"
    (r / "engine").mkdir(parents=True)
    (r / "scripts").mkdir()
    shutil.copy(SCRIPT, r / "scripts" / "deploy-engine.sh")
    for rel, text in (("engine/Dockerfile", "FROM python:3.11-slim\n"), ("cloudbuild.engine.yaml", "steps: []\n"),
                      (".gcloudignore", ".git\n")):
        (r / rel).write_text(text, encoding="utf-8", newline="\n")

    def git(*args):
        return subprocess.run(["git", "-c", "user.name=p", "-c", "user.email=p@e.com", *args], cwd=r, check=True,
                              capture_output=True, text=True).stdout.strip()

    git("init", "-q")
    git("add", ".")
    git("commit", "-q", "-m", "uno")
    first = git("rev-parse", "--short", "HEAD")
    (r / "engine" / "core.py").write_text("x = 1\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "due")
    second = git("rev-parse", "--short", "HEAD")

    def run(*args):
        cmd = (f'cd "{posix(r)}" && DRY_RUN=1 GCP_PROJECT_ID=progetto-prova bash scripts/deploy-engine.sh '
               + " ".join(f"'{a}'" for a in args))
        return subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=60)

    run.root, run.first, run.second = r, first, second
    return run


def test_head_by_default_and_a_given_commit_with_uncommitted_work_in_engine(repo):
    (repo.root / "engine" / "core.py").write_text("x = 2  # not committed\n", encoding="utf-8")   # work in progress
    (repo.root / "engine" / "new.py").write_text("y = 1\n", encoding="utf-8")                    # untracked
    image = "europe-west8-docker.pkg.dev/progetto-prova/domotica/engine:"
    r = repo()
    assert r.returncode == 0, r.stderr
    assert f"Immagine (non costruita): {image}{repo.second}" in r.stdout
    r = repo(repo.first)
    assert r.returncode == 0, r.stderr
    assert f"Immagine (non costruita): {image}{repo.first}" in r.stdout and f"dal commit {repo.first}" in r.stdout


def test_an_unknown_commit_stops(repo):
    r = repo("abcdef123456")
    assert r.returncode != 0 and "commit sconosciuto: abcdef123456" in r.stderr


GCLOUD = r"""#!/usr/bin/env bash
echo "gcloud $*" >> "$STUB_DIR/calls.log"
case "$*" in
  *"artifacts docker images describe"*) [ -f "$STUB_DIR/image-exists" ]; exit $? ;;
esac
exit 0
"""


def real_run(repo, tmp_path, exists):
    """deploy-engine.sh for real, with gcloud stubbed: whether Cloud Build is called."""
    stubs = tmp_path / "stubs"
    stubs.mkdir(exist_ok=True)
    (stubs / "gcloud").write_text(GCLOUD, encoding="utf-8", newline="\n")
    (stubs / "gcloud").chmod(0o755)
    (stubs / "calls.log").unlink(missing_ok=True)
    (stubs / "image-exists").unlink(missing_ok=True)
    if exists:
        (stubs / "image-exists").write_text("", encoding="utf-8")
    cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}"; cd "{posix(repo.root)}" && '
           f'GCP_PROJECT_ID=progetto-prova bash scripts/deploy-engine.sh {repo.second}')
    done = subprocess.run([_bash(), "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=60)
    return done, (stubs / "calls.log").read_text(encoding="utf-8")


def test_d214_an_image_that_exists_is_not_built_again(repo, tmp_path):
    image = f"europe-west8-docker.pkg.dev/progetto-prova/domotica/engine:{repo.second}"
    done, calls = real_run(repo, tmp_path, exists=True)
    assert done.returncode == 0, done.stderr
    assert f"Immagine già presente, non la ricostruisco: {image}" in done.stdout and "builds submit" not in calls
    done, calls = real_run(repo, tmp_path, exists=False)
    assert done.returncode == 0, done.stderr
    assert "builds submit" in calls and f"Immagine pronta: {image}" in done.stdout


GCLOUD_SUBMIT = r'''#!/usr/bin/env bash
case "$*" in
  *"artifacts docker images describe"*) exit 1 ;;                     # the image does not exist yet
  *"builds submit"*) rm -rf "$STUB_DIR/received"; cp -r "$3" "$STUB_DIR/received"; echo "submit $3" >> "$STUB_DIR/calls" ;;
esac
exit 0
'''


def test_cloud_build_receives_the_commit_never_the_working_copy(repo, tmp_path):
    """T3c-2 (P-83): the DRY_RUN checks only said the image's name; a version that sent ${ROOT} (the working copy, with
    work not committed) to Cloud Build stayed green. Here a stand-in gcloud keeps the folder it receives."""
    bash = _bash()
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "gcloud").write_text(GCLOUD_SUBMIT, encoding="utf-8", newline="\n")
    (stubs / "gcloud").chmod(0o755)
    (repo.root / "engine" / "core.py").write_text("x = 2  # not committed\n", encoding="utf-8")
    (repo.root / "engine" / "new.py").write_text("y = 1\n", encoding="utf-8")
    cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}"; cd "{posix(repo.root)}" && '
           f'GCP_PROJECT_ID=progetto-prova bash scripts/deploy-engine.sh {repo.second}')
    r = subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    received = stubs / "received"
    assert (received / "engine" / "core.py").read_text(encoding="utf-8") == "x = 1\n"      # the commit's
    assert not (received / "engine" / "new.py").exists() and not (received / ".git").exists()
