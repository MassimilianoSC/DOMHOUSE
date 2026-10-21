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
