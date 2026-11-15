"""scripts/broker-vm.sh and the certificate after E-31: lego runs on the host's network (the metadata server is closed
to the containers' networks, and lego needs the VM's token to act as the DNS account), and «cert-test» runs a whole
renewal against Let's Encrypt's test server, in a folder of its own, without touching the certificate the broker
serves nor the real ACME account. The real script, run by bash with stand-ins for id, openssl, docker, logger and
mountpoint, its folders moved to a temporary one."""
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
    "mountpoint": "#!/usr/bin/env bash\nexit 0\n",
    "python3": "#!/usr/bin/env bash\nexit 0\n",
    "chown": "#!/usr/bin/env bash\nexit 0\n",
    # docker run of lego: notes its arguments; fails when the test put a file "lego-fails"
    "docker": ('#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/docker.log"\n'
               'if [ "$1" = run ] && [ -f "$STUB_DIR/lego-fails" ]; then exit 1; fi\nexit 0\n'),
    "logger": '#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/syslog.log"\n',
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
    opt, etc, data, tls = tmp_path / "opt", tmp_path / "etc", tmp_path / "data", tmp_path / "tls"
    for folder in (opt / "_broker", etc / "_broker", data, tls / "broker", tls / "acme"):
        folder.mkdir(parents=True)
    (tls / "broker" / "fullchain.pem").write_text("certificato servito\n", encoding="utf-8")
    (tls / "acme" / "conto").write_text("conto ACME vero\n", encoding="utf-8")
    (etc / "_broker" / "acme.settings").write_text(
        "ACME_DOMAIN=mqtt.dh-lab.eu\nACME_DNS_ZONE=domhouse-lab\n"
        "ACME_DNS_ACCOUNT=domhouse-dns-lab@domotica-poc-511707.iam.gserviceaccount.com\n"
        "ACME_SERVER=https://acme-v02.api.letsencrypt.org/directory\nACME_KEY_TYPE=rsa2048\n", encoding="utf-8", newline="\n")

    def run(*args):
        env_line = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}" DOMHOUSE_OPT="{posix(opt)}" '
                    f'DOMHOUSE_ETC="{posix(etc)}" DOMHOUSE_DATA="{posix(data)}" DOMHOUSE_TLS_MOUNT="{posix(tls)}"; ')
        return subprocess.run([bash, "-c", env_line + f'bash "{posix(SCRIPT)}" ' + " ".join(args)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)

    return run, stubs, tls


def test_cert_test_runs_a_renewal_against_the_test_server_on_the_hosts_network(vm):
    run, stubs, tls = vm
    r = run("cert-test")
    assert r.returncode == 0, r.stderr
    docker = (stubs / "docker.log").read_text(encoding="utf-8")
    assert "--network host" in docker
    assert "https://acme-staging-v02.api.letsencrypt.org/directory" in docker
    assert "GCE_IMPERSONATE_SERVICE_ACCOUNT=domhouse-dns-lab@domotica-poc-511707.iam.gserviceaccount.com" in docker
    assert f"{posix(tls / 'acme')}:/acme" not in docker                    # never the real ACME folder
    assert (tls / "broker" / "fullchain.pem").read_text(encoding="utf-8") == "certificato servito\n"
    assert (tls / "acme" / "conto").read_text(encoding="utf-8") == "conto ACME vero\n"
    assert not (tls / "acme-test").exists()                               # its own folder, removed at the end
    assert "broker cert test ok" in (stubs / "syslog.log").read_text(encoding="utf-8")


def test_cert_test_says_when_the_renewal_would_fail(vm):
    run, stubs, tls = vm
    (stubs / "lego-fails").write_text("", encoding="utf-8")
    r = run("cert-test")
    assert r.returncode != 0
    assert "broker cert test failed" in (stubs / "syslog.log").read_text(encoding="utf-8")
    assert not (tls / "acme-test").exists()
    assert (tls / "broker" / "fullchain.pem").read_text(encoding="utf-8") == "certificato servito\n"


def test_lego_runs_on_the_hosts_network_by_default():
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'DOMHOUSE_LEGO_NETWORK:-host' in script
