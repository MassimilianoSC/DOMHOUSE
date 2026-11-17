"""Step 3 of the plan (security check inside the VM, 17 November), C2 and C5. C2: nothing in the broker starts a connection
(devices and engines come in, lego runs on the host's network), so new connections out of the broker's default network
are dropped: broker-vm.sh limit writes, in its table inet domhouse_broker, two chains (forward and input) on the
subnet that engine/broker/compose.yaml fixes for that network; Docker had chosen 172.19.0.0/16 itself, and compose
does not move an existing network, so broker-vm.sh network (and install) makes it again when it differs. C5:
tls_version tlsv1.2 written on the TLS listener. The real script, run by bash with stand-ins for id, docker, nft and
logger (tests/broker_vm_sync_test.py), its folders moved to a temporary one. The nft rules on a real kernel are proved
in the bench of tests/broker_container_test.py and on the VM (docs/procedura-passo3-vm.md)."""
import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "broker-vm.sh"
SUBNET = "172.30.84.0/24"


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
    "python3": "#!/usr/bin/env bash\nexit 0\n",
    "mountpoint": "#!/usr/bin/env bash\nexit 0\n",
    "logger": '#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/syslog.log"\n',
    # nft: -f copies the file it applies; list prints the file net-current.nft (the table as the kernel shows it)
    "nft": ('#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/nft.log"\n'
            'if [ "$1" = -f ]; then cp "$2" "$STUB_DIR/applied.nft"; exit 0; fi\n'
            'if [ "$1" = list ]; then cat "$STUB_DIR/net-current.nft" 2>/dev/null; exit 0; fi\nexit 0\n'),
    # docker: network inspect answers with the file subnet (absent: no network); compose and the rest are recorded
    "docker": ('#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/docker.log"\n'
               'case "$*" in\n'
               '  "network inspect"*) [ -f "$STUB_DIR/subnet" ] || exit 1; cat "$STUB_DIR/subnet"; exit 0 ;;\n'
               '  "compose version"*) exit 0 ;;\n'
               '  inspect*) echo healthy; exit 0 ;;\n'
               'esac\nexit 0\n'),
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
    (etc / "_broker" / "apartments").write_text("", encoding="utf-8", newline="\n")
    for name in ("devices.passwd", "connectors.passwd"):
        (etc / "_broker" / "auth" / name).write_text("", encoding="utf-8", newline="\n")
    tls = tmp_path / "tls"                                    # the keys' disk: mountpoint says yes (stand-in)
    (tls / "broker").mkdir(parents=True)
    (tls / "acme").mkdir()

    def run(*args):
        env_line = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}" DOMHOUSE_OPT="{posix(opt)}" '
                    f'DOMHOUSE_ETC="{posix(etc)}" DOMHOUSE_DATA="{posix(data)}" DOMHOUSE_TLS_MOUNT="{posix(tls)}" '
                    f'DOMHOUSE_HEALTH_TRIES=1; ')
        return subprocess.run([bash, "-c", env_line + f'bash "{posix(SCRIPT)}" ' + " ".join(args)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)

    run.stubs = stubs
    return run


def read(stubs: Path, name: str) -> str:
    f = stubs / name
    return f.read_text(encoding="utf-8") if f.exists() else ""


def test_c2_the_limit_also_closes_new_connections_out_of_the_broker(vm):
    r = vm("limit")
    assert r.returncode == 0, r.stdout + r.stderr
    rules = read(vm.stubs, "applied.nft")
    assert rules.count('comment "domhouse-broker-limit"') == 2                      # the limit as before
    egress = [l.strip() for l in rules.splitlines() if "domhouse-broker-egress" in l]
    assert egress == [f'ip saddr {SUBNET} ct state new counter drop comment "domhouse-broker-egress"'] * 2, rules
    assert "hook forward" in rules and "hook input" in rules
    assert "uscita" in r.stdout


def test_c2_the_subnet_is_the_same_in_the_compose_and_in_the_script():
    compose = (ROOT / "engine/broker/compose.yaml").read_text(encoding="utf-8")
    script = SCRIPT.read_text(encoding="utf-8")
    default = compose[compose.index("\nnetworks:"):]
    default = default[default.index("  default:"):default.index("  internal:")]
    assert f"- subnet: {SUBNET}" in default
    assert f"BROKER_SUBNET={SUBNET}" in script


def test_c2_a_network_on_another_subnet_is_made_again(vm):
    (vm.stubs / "subnet").write_text("172.19.0.0/16\n", encoding="utf-8")
    r = vm("network")
    assert r.returncode == 0, r.stdout + r.stderr
    log = read(vm.stubs, "docker.log")
    order = [k for k in ("stop broker", "rm -f broker", "network rm domhouse-broker_default", "up -d") if k in log]
    assert order == ["stop broker", "rm -f broker", "network rm domhouse-broker_default", "up -d"], log
    assert log.index("stop broker") < log.index("network rm") < log.index("up -d")
    assert f"172.19.0.0/16 -> {SUBNET}" in r.stdout


def test_c2_a_network_already_on_its_subnet_is_left_alone(vm):
    (vm.stubs / "subnet").write_text(f"{SUBNET}\n", encoding="utf-8")
    r = vm("network")
    assert r.returncode == 0, r.stdout + r.stderr
    log = read(vm.stubs, "docker.log")
    assert "network rm" not in log and "stop broker" not in log
    assert "già" in r.stdout


def test_c2_status_counts_the_limit_and_the_way_out_apart(vm):
    (vm.stubs / "net-current.nft").write_text(
        'tcp dport 8883 ct state new add @sources4 { ip saddr limit rate over 30/minute burst 60 packets } '
        'counter packets 20 bytes 1200 drop comment "domhouse-broker-limit"\n'
        f'ip saddr {SUBNET} ct state new counter packets 3 bytes 180 drop comment "domhouse-broker-egress"\n',
        encoding="utf-8")
    r = vm("status")
    out = r.stdout
    assert "collegamenti scartati dal limite: 20" in out, out + r.stderr
    assert "collegamenti in uscita dal broker scartati: 3" in out


def test_c5_tls_1_2_written_on_the_tls_listener():
    conf = (ROOT / "engine/broker/mosquitto.conf").read_text(encoding="utf-8")
    tls = conf[conf.index("listener 8883"):conf.index("listener 1883")]
    assert re.search(r"^tls_version tlsv1\.2$", tls, re.MULTILINE), tls
