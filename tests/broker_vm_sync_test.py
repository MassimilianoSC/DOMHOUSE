"""scripts/broker-vm.sh sync and add-apartment around broker_accounts.py (E-33): an apartment whose secrets cannot be
read is kept as it was and named in a line of the watch («broker sync kept <apartment_id>»), the others are reloaded;
a NEW apartment that cannot be read is not added. The real script, run by bash with stand-ins for id, docker, logger
and python3 (which prints what the test wants broker_accounts.py to print), its folders moved to a temporary one."""
import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "broker-vm.sh"


def _bash() -> str | None:
    spec = importlib.util.spec_from_file_location("run_tests", ROOT / "scripts" / "run_tests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.git_bash()


def posix(path: Path) -> str:
    s = path.as_posix()
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else s


STUBS = {
    "id": "#!/usr/bin/env bash\necho 0\n",
    "openssl": "#!/usr/bin/env bash\nexit 0\n",
    "docker": ('#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/docker.log"\n'
               'if [ "$1" = inspect ]; then echo true; fi\nexit 0\n'),
    "logger": '#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/syslog.log"\n',
    # broker_accounts.py sync: prints the file sync-out and exits with sync-code (0 if missing)
    "python3": ('#!/usr/bin/env bash\ncat "$STUB_DIR/sync-out"\n'
                'exit "$(cat "$STUB_DIR/sync-code" 2>/dev/null || echo 0)"\n'),
}


@pytest.fixture
def vm(tmp_path):
    bash = _bash()
    if not bash:
        pytest.skip("bash non disponibile")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in STUBS.items():
        (stubs / name).write_text(body, encoding="utf-8", newline="\n")
        (stubs / name).chmod(0o755)
    opt, etc, data = tmp_path / "opt", tmp_path / "etc", tmp_path / "data"
    (opt / "_broker").mkdir(parents=True)
    (etc / "_broker" / "auth").mkdir(parents=True)
    (opt / "_broker" / "broker.settings").write_text("BROKER_TLS_PORT=8883\n", encoding="utf-8", newline="\n")
    (etc / "_broker" / "apartments").write_text("apt-a\n", encoding="utf-8", newline="\n")

    def run(*args):
        env_line = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}" DOMHOUSE_OPT="{posix(opt)}" '
                    f'DOMHOUSE_ETC="{posix(etc)}" DOMHOUSE_DATA="{posix(data)}"; ')
        return subprocess.run([bash, "-c", env_line + f'bash "{posix(SCRIPT)}" ' + " ".join(args)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)

    return run, stubs, etc


def test_sync_names_a_kept_apartment_in_the_watch(vm):
    run, stubs, _ = vm
    (stubs / "sync-out").write_text("apt-a: connector e 2 dispositivi\nkept apt-b\nchanged\n", encoding="utf-8")
    r = run("sync")
    assert r.returncode == 0, r.stderr
    syslog = (stubs / "syslog.log").read_text(encoding="utf-8")
    assert "broker sync kept apt-b" in syslog
    assert "kill -s HUP domhouse-broker" in (stubs / "docker.log").read_text(encoding="utf-8")   # the others reloaded


def test_add_apartment_whose_secrets_cannot_be_read_is_not_added(vm):
    run, stubs, etc = vm
    (stubs / "sync-out").write_text("apt-a: connector e 2 dispositivi\nkept apt-new\nunchanged\n", encoding="utf-8")
    r = run("add-apartment", "apt-new")
    assert r.returncode != 0
    assert "apt-new" in r.stderr
    assert (etc / "_broker" / "apartments").read_text(encoding="utf-8").split() == ["apt-a"]


def test_add_apartment_still_works_when_another_apartment_is_kept(vm):
    run, stubs, etc = vm
    (stubs / "sync-out").write_text("apt-new: connector e 0 dispositivi\nkept apt-a\nchanged\n", encoding="utf-8")
    r = run("add-apartment", "apt-new")
    assert r.returncode == 0, r.stderr
    assert (etc / "_broker" / "apartments").read_text(encoding="utf-8").split() == ["apt-a", "apt-new"]
    assert "broker sync kept apt-a" in (stubs / "syslog.log").read_text(encoding="utf-8")
