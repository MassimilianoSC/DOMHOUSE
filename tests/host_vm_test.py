"""Step 3 of the plan (security check inside the VM, 17 November): scripts/host-vm.sh, three small files of our own on
the VM's host, each with its way back. sysctl kernel.kptr_restrict=1 and kernel.yama.ptrace_scope=1 (Debian leaves both
at 0), LLMNR=no for systemd-resolved (port 5355 on every address), and an sshd file: X11Forwarding no,
AllowAgentForwarding no, MaxAuthTries 3 (AllowTcpForwarding stays: the IAP tunnels may need it). sshd -t before the
reload, and a revert of the sshd file by itself after 10 minutes unless «confirm» comes from a NEW connection: a
change that locked gcloud compute ssh out puts itself back. The real script, run by bash with stand-ins for id,
sysctl, systemctl, sshd, systemd-run and ss, its folders moved to a temporary one."""
import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "host-vm.sh"


def _bash() -> str | None:
    spec = importlib.util.spec_from_file_location("run_tests", ROOT / "scripts" / "run_tests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.git_bash()


def posix(path: Path) -> str:
    s = path.as_posix()
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else s


LOG = 'echo "$(basename "$0") $*" >> "$STUB_DIR/calls.log"\n'
STUBS = {
    "id": "#!/usr/bin/env bash\necho 0\n",
    # sysctl -n <key>: the value in the file sysctl-<key> (0 if missing); anything else recorded
    "sysctl": ("#!/usr/bin/env bash\n" + LOG +
               'if [ "$1" = -n ]; then cat "$STUB_DIR/sysctl-$2" 2>/dev/null || echo 0; fi\nexit 0\n'),
    "systemctl": ("#!/usr/bin/env bash\n" + LOG +
                  'if [ "$1" = is-active ] && [ -f "$STUB_DIR/timer-inactive" ]; then exit 3; fi\nexit 0\n'),
    "systemd-run": "#!/usr/bin/env bash\n" + LOG + '[ ! -f "$STUB_DIR/run-fails" ]\n',
    # sshd -t fails when the test put a file "sshd-bad"; sshd -T prints the file sshd-T
    "sshd": ("#!/usr/bin/env bash\n" + LOG +
             'if [ "$1" = -t ]; then [ ! -f "$STUB_DIR/sshd-bad" ]; exit; fi\n'
             'if [ "$1" = -T ]; then cat "$STUB_DIR/sshd-T" 2>/dev/null; fi\nexit 0\n'),
    "ss": "#!/usr/bin/env bash\n" + LOG + 'cat "$STUB_DIR/ss" 2>/dev/null\nexit 0\n',
}


@pytest.fixture
def host(tmp_path):
    bash = _bash()
    if not bash:
        pytest.skip("bash non disponibile")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in STUBS.items():
        (stubs / name).write_text(body, encoding="utf-8", newline="\n")
        (stubs / name).chmod(0o755)
    dirs = {name: tmp_path / name for name in ("sysctl.d", "resolved.conf.d", "sshd_config.d", "opt")}
    for d in dirs.values():
        d.mkdir()

    def run(*args):
        env = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}" '
               f'DOMHOUSE_SYSCTL_DIR="{posix(dirs["sysctl.d"])}" DOMHOUSE_RESOLVED_DIR="{posix(dirs["resolved.conf.d"])}" '
               f'DOMHOUSE_SSHD_DIR="{posix(dirs["sshd_config.d"])}" DOMHOUSE_OPT="{posix(dirs["opt"])}"; ')
        return subprocess.run([bash, "-c", env + f'bash "{posix(SCRIPT)}" ' + " ".join(args)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)

    run.stubs, run.dirs = stubs, dirs
    return run


def calls(host) -> str:
    f = host.stubs / "calls.log"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def test_apply_writes_the_three_files_and_applies_them(host):
    r = host("apply")
    assert r.returncode == 0, r.stdout + r.stderr
    sysctl = (host.dirs["sysctl.d"] / "90-domhouse.conf").read_text(encoding="utf-8")
    assert "kernel.kptr_restrict = 1" in sysctl and "kernel.yama.ptrace_scope = 1" in sysctl
    resolved = (host.dirs["resolved.conf.d"] / "90-domhouse.conf").read_text(encoding="utf-8")
    assert "[Resolve]" in resolved and "LLMNR=no" in resolved
    sshd = (host.dirs["sshd_config.d"] / "90-domhouse.conf").read_text(encoding="utf-8")
    for line in ("X11Forwarding no", "AllowAgentForwarding no", "MaxAuthTries 3"):
        assert re.search(rf"^{line}$", sshd, re.MULTILINE), line
    assert "AllowTcpForwarding" not in sshd                       # the IAP tunnels may need it
    log = calls(host)
    assert "sysctl -p " in log and "systemctl restart systemd-resolved" in log
    assert log.index("sshd -t") < log.index("systemctl reload ssh")
    assert "confirm" in r.stdout


def test_apply_keeps_the_values_before_for_undo(host):
    (host.stubs / "sysctl-kernel.kptr_restrict").write_text("0\n", encoding="utf-8")
    (host.stubs / "sysctl-kernel.yama.ptrace_scope").write_text("0\n", encoding="utf-8")
    assert host("apply").returncode == 0
    before = (host.dirs["opt"] / "host-vm.prima").read_text(encoding="utf-8")
    assert "kernel.kptr_restrict=0" in before and "kernel.yama.ptrace_scope=0" in before


def test_the_sshd_change_reverts_by_itself_unless_confirmed(host):
    assert host("apply").returncode == 0
    run = [l for l in calls(host).splitlines() if l.startswith("systemd-run ")]
    assert len(run) == 1 and "--on-active=600" in run[0] and "--unit=domhouse-sshd-ritorno" in run[0]
    assert "host-vm.sh undo-sshd" in run[0]
    r = host("confirm")
    assert r.returncode == 0, r.stderr
    assert "systemctl stop domhouse-sshd-ritorno.timer" in calls(host)


def test_a_wrong_sshd_file_is_removed_and_nothing_is_reloaded(host):
    (host.stubs / "sshd-bad").write_text("", encoding="utf-8")
    r = host("apply")
    assert r.returncode != 0 and "sshd" in r.stderr
    assert not (host.dirs["sshd_config.d"] / "90-domhouse.conf").exists()
    assert "systemctl reload ssh" not in calls(host) and "systemd-run" not in calls(host)


def test_undo_sshd_removes_only_the_sshd_file(host):
    assert host("apply").returncode == 0
    r = host("undo-sshd")
    assert r.returncode == 0, r.stderr
    assert not (host.dirs["sshd_config.d"] / "90-domhouse.conf").exists()
    assert (host.dirs["sysctl.d"] / "90-domhouse.conf").exists()
    assert calls(host).count("systemctl reload ssh") == 2


def test_undo_removes_the_three_files_and_puts_the_values_back(host):
    (host.stubs / "sysctl-kernel.kptr_restrict").write_text("0\n", encoding="utf-8")
    (host.stubs / "sysctl-kernel.yama.ptrace_scope").write_text("0\n", encoding="utf-8")
    assert host("apply").returncode == 0
    r = host("undo")
    assert r.returncode == 0, r.stderr
    for d in ("sysctl.d", "resolved.conf.d", "sshd_config.d"):
        assert not (host.dirs[d] / "90-domhouse.conf").exists(), d
    log = calls(host)
    assert "sysctl -w kernel.kptr_restrict=0" in log and "sysctl -w kernel.yama.ptrace_scope=0" in log
    assert log.count("systemctl restart systemd-resolved") == 2


def test_check_says_what_is_in_force(host):
    (host.stubs / "sysctl-kernel.kptr_restrict").write_text("1\n", encoding="utf-8")
    (host.stubs / "sysctl-kernel.yama.ptrace_scope").write_text("1\n", encoding="utf-8")
    (host.stubs / "sshd-T").write_text("port 22\nx11forwarding no\nallowagentforwarding no\nmaxauthtries 3\n"
                                       "allowtcpforwarding yes\n", encoding="utf-8")
    r = host("check")
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "kernel.kptr_restrict 1" in out and "kernel.yama.ptrace_scope 1" in out
    assert "x11forwarding no" in out and "maxauthtries 3" in out and "allowtcpforwarding yes" in out
    assert "porte LLMNR 5355 in ascolto: 0" in out


# ---- review of the procedure (17 November): never locked out, confirm only what is pending ---------------------
def test_the_revert_is_armed_before_the_reload_and_an_old_one_is_stopped_first(host):
    assert host("apply").returncode == 0
    log = calls(host)
    stop, run, reload = (log.index("systemctl stop domhouse-sshd-ritorno.timer"), log.index("systemd-run "),
                         log.index("systemctl reload ssh"))
    assert stop < run < reload, log
    [run_line] = [l for l in log.splitlines() if l.startswith("systemd-run ")]
    assert "--timer-property=RemainAfterElapse=no" in run_line


def test_a_second_apply_arms_the_revert_again(host):
    assert host("apply").returncode == 0
    r = host("apply")
    assert r.returncode == 0, r.stderr
    assert calls(host).count("systemd-run ") == 2


def test_if_the_revert_cannot_be_armed_sshd_is_not_reloaded_and_the_file_goes(host):
    (host.stubs / "run-fails").write_text("", encoding="utf-8")
    r = host("apply")
    assert r.returncode != 0 and "ritorno" in r.stderr
    assert "systemctl reload ssh" not in calls(host)
    assert not (host.dirs["sshd_config.d"] / "90-domhouse.conf").exists()


def test_confirm_after_the_revert_says_there_is_nothing_to_confirm(host):
    assert host("apply").returncode == 0
    assert host("undo-sshd").returncode == 0                     # what the timer runs after 10 minutes
    r = host("confirm")
    assert r.returncode != 0 and "già stato tolto" in r.stderr
    assert "il file di sshd resta" not in r.stdout


def test_confirm_without_a_pending_revert_says_so(host):
    assert host("apply").returncode == 0
    (host.stubs / "timer-inactive").write_text("", encoding="utf-8")
    r = host("confirm")
    assert r.returncode != 0 and "niente da confermare" in r.stderr
