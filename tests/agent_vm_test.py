"""Tool A, package A1: scripts/agent-vm.sh (install, status, uninstall of the order receiver on the VM) and the two
systemd units. The real script, run by bash with stand-ins for id, getent, useradd, install, chown and systemctl, its
folders moved to a temporary one. Nothing is installed anywhere: the installation on the VM is a step of the
committente, after step 2 of the plan."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "agent-vm.sh"
AGENT = ROOT / "scripts" / "agent"
SUB = "projects/domotica-poc-511707/subscriptions/domhouse-staging-ordini-vm"
TOPIC = "projects/domotica-poc-511707/topics/domhouse-staging-risultati"


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


STUBS = {
    "id": '#!/usr/bin/env bash\n[ -f "$STUB_DIR/not-root" ] && echo 1000 || echo 0\n',
    # getent passwd domhouse-agent | group domhouse-broker | group 1883, from the files the tests put
    "getent": ('#!/usr/bin/env bash\ncase "$1 $2" in\n'
               '  "passwd domhouse-agent") [ -f "$STUB_DIR/user-exists" ] && { echo "domhouse-agent:x:996:996::/nonexistent:/usr/sbin/nologin"; exit 0; } ;;\n'
               '  "group domhouse-broker") [ -f "$STUB_DIR/group-broker" ] && { cat "$STUB_DIR/group-broker"; exit 0; } ;;\n'
               '  "group 1883") for f in group-1883 group-broker; do [ -f "$STUB_DIR/$f" ] && grep -q ":1883:" "$STUB_DIR/$f" && { cat "$STUB_DIR/$f"; exit 0; }; done ;;\n'
               'esac\nexit 2\n'),
    "groupadd": '#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/groupadd.log"\necho "domhouse-broker:x:1883:" > "$STUB_DIR/group-broker"\n',
    "useradd": '#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/useradd.log"\ntouch "$STUB_DIR/user-exists"\n',
    "chown": '#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/chown.log"\nexit 0\n',
    "systemctl": ('#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/systemctl.log"\n'
                  'case "$1" in is-active) echo active ;; esac\nexit 0\n'),
    "journalctl": '#!/usr/bin/env bash\necho "nov 17 09:00:00 vm domhouse-agent-lettore[1]: agent count ambiente=staging"\n',
    # install -d [-m M] [-o U] [-g G] DIR... | install [-m M] [-o U] [-g G] SRC DEST: copies, notes modes and owners
    "install": ('#!/usr/bin/env bash\necho "install $*" >> "$STUB_DIR/install.log"\nmode=; dir=\n'
                'while [ $# -gt 0 ]; do case "$1" in -d) dir=1; shift ;; -m) mode=$2; shift 2 ;; -o|-g) shift 2 ;; '
                '*) break ;; esac; done\n'
                'if [ -n "$dir" ]; then mkdir -p "$@"; else cp "$1" "$2"; fi\nexit 0\n'),
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
    (stubs / "python3").write_text(f'#!/usr/bin/env bash\nexec "{posix(Path(sys.executable))}" "$@"\n',
                                   encoding="utf-8", newline="\n")
    (stubs / "python3").chmod(0o755)
    etc, opt, units, lib = tmp_path / "etc", tmp_path / "opt", tmp_path / "systemd", tmp_path / "lib"
    for folder in (etc, opt, units, lib):
        folder.mkdir()

    def run(*args, env=""):
        cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}" {env} '
               f'DOMHOUSE_ETC="{posix(etc)}" DOMHOUSE_OPT="{posix(opt)}" DOMHOUSE_SYSTEMD="{posix(units)}" '
               f'DOMHOUSE_LIB="{posix(lib)}"; bash "{posix(SCRIPT)}" ' + " ".join(f"'{a}'" for a in args))
        return subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=120)

    run.etc, run.opt, run.units, run.lib, run.stubs = etc, opt, units, lib, stubs
    return run


GOOD = f'AMBIENTE=staging SOTTOSCRIZIONE="{SUB}" RISULTATI="{TOPIC}"'


def log(vm, name) -> str:
    path = vm.stubs / f"{name}.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_install_puts_the_code_the_configuration_and_the_units_and_starts_them(vm):
    r = vm("install", env=GOOD)
    assert r.returncode == 0, r.stderr + r.stdout
    for name in ("comune.py", "lettore.py", "esecutore.py"):
        assert (vm.opt / "agent" / name).read_bytes() == (AGENT / name).read_bytes()
    assert (vm.etc / "agent.conf").read_text(encoding="utf-8") == (
        "AMBIENTE=staging\nCONDIVISA=1\nLETTORE=domhouse-agent\nMAX_MOTORI_STAGING=4\n"
        "BUDGET_MB_STAGING=500\n")                           # A7, answer 1197: written, not only a default
    assert (vm.etc / "agent-lettore.conf").read_text(encoding="utf-8") == (
        f"AMBIENTE=staging\nSOTTOSCRIZIONE={SUB}\nRISULTATI={TOPIC}\n")
    for unit in ("domhouse-agent-esecutore.service", "domhouse-agent-lettore.service"):
        assert (vm.units / unit).read_bytes() == (AGENT / unit).read_bytes()
    install = log(vm, "install")
    assert re.search(r"-m 600 -o root -g root \S*agent\.conf\S* \S*agent\.conf", install), install
    assert re.search(r"-m 644 -o root -g root \S*agent-lettore\.conf", install)
    assert re.search(r"-d -m 755 -o root -g root \S*/opt/agent", install)
    assert "--system" in log(vm, "useradd") and "nologin" in log(vm, "useradd")
    systemctl = log(vm, "systemctl")
    assert "daemon-reload" in systemctl
    assert systemctl.index("enable --now domhouse-agent-esecutore.service") < \
        systemctl.index("enable --now domhouse-agent-lettore.service")


def test_install_again_does_not_add_the_user_twice(vm):
    (vm.stubs / "user-exists").write_text("", encoding="utf-8")
    assert vm("install", env=GOOD).returncode == 0
    assert log(vm, "useradd") == ""


@pytest.mark.parametrize("env, says", [
    (f'AMBIENTE=prod SOTTOSCRIZIONE="{SUB}" RISULTATI="{TOPIC}"', "prod"),
    (f'AMBIENTE=staging SOTTOSCRIZIONE="https://evil/x" RISULTATI="{TOPIC}"', "SOTTOSCRIZIONE"),
    (f'AMBIENTE=staging RISULTATI="{TOPIC}"', "SOTTOSCRIZIONE"),
])
def test_install_refuses_what_it_must_and_writes_nothing(vm, env, says):
    r = vm("install", env=env)
    assert r.returncode != 0 and says in (r.stderr + r.stdout)
    assert not (vm.opt / "agent").exists() and list(vm.units.iterdir()) == [] and list(vm.etc.iterdir()) == []
    assert log(vm, "systemctl") == ""


def test_only_root_installs(vm):
    (vm.stubs / "not-root").write_text("", encoding="utf-8")
    r = vm("install", env=GOOD)
    assert r.returncode != 0 and "root" in r.stderr and list(vm.units.iterdir()) == []


def test_status_says_both_services_and_the_last_lines(vm):
    r = vm("status")
    assert r.returncode == 0, r.stderr
    assert "domhouse-agent-esecutore.service: active" in r.stdout
    assert "domhouse-agent-lettore.service: active" in r.stdout and "agent count" in r.stdout


def test_uninstall_stops_and_removes_code_and_units_but_keeps_the_journals(vm):
    assert vm("install", env=GOOD).returncode == 0
    (vm.lib / "domhouse-executor" / "seq").mkdir(parents=True)
    (vm.lib / "domhouse-executor" / "seq" / "lab-01").write_text("7\n", encoding="utf-8")
    r = vm("uninstall")
    assert r.returncode == 0, r.stderr
    assert not (vm.opt / "agent").exists() and list(vm.units.iterdir()) == []
    assert (vm.lib / "domhouse-executor" / "seq" / "lab-01").exists()        # the tombstones stay
    assert "disable --now domhouse-agent-lettore.service" in log(vm, "systemctl")


def test_the_units_keep_the_reader_unprivileged_and_the_socket_folder_closed():
    reader = (AGENT / "domhouse-agent-lettore.service").read_text(encoding="utf-8")
    executor = (AGENT / "domhouse-agent-esecutore.service").read_text(encoding="utf-8")
    for line in ("User=domhouse-agent", "NoNewPrivileges=yes", "ProtectSystem=strict", "CapabilityBoundingSet=\n",
                 "ExecStart=/usr/bin/python3 -I /opt/domhouse/agent/lettore.py",
                 "Requires=domhouse-agent-esecutore.service"):
        assert line in reader, line
    for line in ("User=root", "Group=domhouse-agent", "RuntimeDirectory=domhouse-agent", "RuntimeDirectoryMode=0750",
                 "StateDirectoryMode=0700", "NoNewPrivileges=yes", "ExecStart=/usr/bin/python3 -I /opt/domhouse/agent/esecutore.py"):
        assert line in executor, line
    assert "Environment" not in reader + executor                     # no variable from outside the code


def test_r17_installing_again_restarts_both_services_executor_first(vm):
    """R17 (security review of A1): a new version of the code is running after install, not only on disk."""
    assert vm("install", env=GOOD).returncode == 0
    systemctl = log(vm, "systemctl")
    first, second = (systemctl.index("restart domhouse-agent-esecutore.service"),
                     systemctl.index("restart domhouse-agent-lettore.service"))
    assert systemctl.index("enable --now domhouse-agent-lettore.service") < first < second



# ---- A3, 20 November (Q2.3 stopped): the broker's group for the executor's unit ------------------------------------
# systemd refuses SupplementaryGroups=1883 when no group has that gid (status 216, EXIT_GROUP: seen on the VM, where
# 1883 is only the user of Mosquitto's container). install makes a system group domhouse-broker with gid 1883, the
# unit names it; a gid 1883 already used by another group, or domhouse-broker with another gid, stops before anything.
def test_install_makes_the_brokers_group_with_gid_1883(vm):
    r = vm("install", env=GOOD)
    assert r.returncode == 0, r.stderr + r.stdout
    assert log(vm, "groupadd").split() == ["--system", "--gid", "1883", "domhouse-broker"]


def test_install_again_keeps_the_brokers_group(vm):
    (vm.stubs / "group-broker").write_text("domhouse-broker:x:1883:\n", encoding="utf-8")
    assert vm("install", env=GOOD).returncode == 0
    assert log(vm, "groupadd") == ""


@pytest.mark.parametrize("name, line", [("group-1883", "altro:x:1883:\n"), ("group-broker", "domhouse-broker:x:1500:\n")])
def test_install_stops_if_gid_1883_or_the_name_is_taken_otherwise(vm, name, line):
    (vm.stubs / name).write_text(line, encoding="utf-8")
    r = vm("install", env=GOOD)
    assert r.returncode != 0 and "1883" in r.stderr
    assert log(vm, "groupadd") == "" and log(vm, "useradd") == "" and not list(vm.units.iterdir())
