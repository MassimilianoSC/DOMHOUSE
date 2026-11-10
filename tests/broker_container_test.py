"""The real broker (D-196, D-199) in containers, driven by the real scripts/broker-vm.sh. The bench (tests/broker_rig) is a
Linux that runs the script as root and uses this machine's Docker through its socket: what is checked is the image, the
configuration and the file permissions that go on the VM. Only Secret Manager and the metadata server are stand-ins.
Clients are the broker image's own mosquitto_pub and mosquitto_sub. Docker missing is one red, never a skip.

The keys' disk (C-12): on the bench it is a folder mounted on itself, so that it is a mount point both for the script
and for Docker; its preparation (format, fstab, mount) runs apart, in a privileged bench on loop disks. Certificates
from ACME come from Pebble, Let's Encrypt's own test server, that accepts every challenge: lego is the real one."""
import json
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "eclipse-mosquitto:2@sha256:75d6662dee52c947dc9dd9c29f1d8d7ffef78ddaf38001caa09755681e8bbc98"
RIG, BENCH = "domhouse-broker-rig-run", "/tmp/domhouse-broker-bench"
INTERNAL_IP, INTERNAL_NET, BRIDGE_NET, CONTAINER = "172.30.83.2", "domhouse-broker-internal", "domhouse-broker_default", "domhouse-broker"
PORT = 18883
HOST = "mqtt.banco.test"
TLS = f"{BENCH}/tlsdisk/broker"
ACME = f"{BENCH}/tlsdisk/acme"
PEBBLE, PEBBLE_IMAGE = "domhouse-broker-pebble", "ghcr.io/letsencrypt/pebble@sha256:ddf230642b1a584f519f32e347de1b05a6e4c1f6c35c1863b33effeab5f78199"
DNS_ACCOUNT = "domhouse-dns-lab@domotica-poc-511707.iam.gserviceaccount.com"
A, B = "apt-a", "apt-b"
PW = {"connA": "connector-A-password-lunga-0001", "connB": "connector-B-password-lunga-0002",
      "a1": "device-a1-password-lunga-000001", "a2": "device-a2-password-lunga-000002",
      "b1": "device-b1-password-lunga-000003"}


def docker(*args, check=True, timeout=60, input_text=None):
    done = subprocess.run(["docker", *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, input=input_text)
    if check and done.returncode:
        raise AssertionError(f"docker {' '.join(args)[:200]} -> {done.returncode}: {(done.stdout + done.stderr)[-1500:]}")
    return done


def rig(script, check=True, timeout=120, input_text=None):
    return docker("exec", "-i", RIG, "bash", "-c", script, check=check, timeout=timeout, input_text=input_text)


def vm(*args, check=True):
    return rig("bash " + BENCH + "/opt/broker-vm.sh " + " ".join(args), check=check)


def put_secret(name, value):
    rig(f"cat > {BENCH}/secrets/{name}", input_text=value)


def put_devices(apartment, devices):
    put_secret(f"langbrain-shelly-{apartment}-devices", json.dumps(devices))


def make_cert(name, host=HOST, days=30, ca="ca"):
    rig(f"""cd {BENCH}/certs && openssl req -new -newkey rsa:2048 -nodes -keyout {name}.key -subj /CN={host} -out {name}.csr 2>/dev/null &&
        printf 'subjectAltName=DNS:{host}\\n' > {name}.ext &&
        openssl x509 -req -in {name}.csr -CA {ca}.crt -CAkey {ca}.key -CAcreateserial -days {days} -extfile {name}.ext -out {name}.crt 2>/dev/null""")


def fingerprint(name):
    return rig(f"openssl x509 -in {BENCH}/certs/{name}.crt -noout -fingerprint -sha256 | sed 's/.*=//'").stdout.strip()


def served_fingerprint():
    return rig(f"python3 {BENCH}/opt/broker_accounts.py probe 127.0.0.1 {PORT} | openssl x509 -noout -fingerprint -sha256 | sed 's/.*=//'").stdout.strip()


def _client_args(where, user, password):
    """The network and host options of a client: "tls" from outside, "internal" from a motor's network."""
    who = ["-u", user, "-P", password] if user else []
    if where == "tls":
        return (["--network", "host", "--add-host", f"{HOST}:127.0.0.1", "-v", f"{BENCH}/certs:/certs:ro"],
                ["-h", HOST, "-p", str(PORT), "--cafile", "/certs/ca.crt", *who])
    return (["--network", INTERNAL_NET], ["-h", INTERNAL_IP, "-p", "1883", *who])


def pub(where, user, password, topic, message="m", extra=()):
    net, opts = _client_args(where, user, password)
    return docker("run", "--rm", *net, IMAGE, "mosquitto_pub", *opts, "-t", topic, "-m", message, "-q", "1", *extra, check=False)


def can_connect(where, user, password):
    return pub(where, user, password, "nessuno/qui").returncode == 0


class Sub:
    """A mosquitto_sub left running; its lines come from docker logs."""

    def __init__(self, where, user, password, topic, client_id=None, persistent=False):
        self.name = f"bench-sub-{uuid.uuid4().hex[:10]}"
        net, opts = _client_args(where, user, password)
        extra = ["-i", client_id or self.name] + (["-c"] if persistent else [])
        docker("run", "-d", "--name", self.name, *net, IMAGE, "mosquitto_sub", *opts, "-t", topic, "-q", "1", "-F", "%t %p", *extra)
        time.sleep(1.5)

    def lines(self):
        return docker("logs", self.name, check=False).stdout.splitlines()

    def wait_for(self, text, seconds=6):
        end = time.time() + seconds
        while time.time() < end:
            if any(text in line for line in self.lines()):
                return True
            time.sleep(0.25)
        return False

    def running(self):
        return docker("inspect", "-f", "{{.State.Running}}", self.name, check=False).stdout.strip() == "true"

    def close(self):
        docker("rm", "-f", self.name, check=False)


@pytest.fixture
def sub():
    opened = []

    def make(*args, **kwargs):
        opened.append(Sub(*args, **kwargs))
        return opened[-1]
    yield make
    for each in opened:
        each.close()


def start_bench() -> dict:
    """The bench up, the certificates made, the broker installed by the real script. Returns the install's outcomes."""
    docker("build", "-q", "-t", "domhouse-broker-rig", str(ROOT / "tests" / "broker_rig"), timeout=240)
    docker("rm", "-f", RIG, PEBBLE, check=False)
    docker("run", "-d", "--name", PEBBLE, "-p", "14000:14000", "-e", "PEBBLE_VA_ALWAYS_VALID=1", PEBBLE_IMAGE, timeout=180)
    docker("run", "-d", "--name", RIG, "--network", "host",
           "-v", "/var/run/docker.sock:/var/run/docker.sock", "-v", f"{BENCH}:{BENCH}", "-v", f"{BENCH}/tlsdisk:{BENCH}/tlsdisk",
           "-v", f"{ROOT.as_posix()}:/repo:ro",
           "-e", f"DOMHOUSE_OPT={BENCH}/opt", "-e", f"DOMHOUSE_ETC={BENCH}/etc", "-e", f"DOMHOUSE_DATA={BENCH}/data",
           "-e", f"DOMHOUSE_TLS_MOUNT={BENCH}/tlsdisk", "-e", f"DOMHOUSE_SYSTEMD={BENCH}/systemd",
           "-e", f"DOMHOUSE_BROKER_PORT={PORT}", "-e", "DOMHOUSE_METADATA=http://127.0.0.1:18090",
           "-e", "DOMHOUSE_SECRETS_API=http://127.0.0.1:18090/v1", "-e", "DOMHOUSE_HEALTH_TRIES=45",
           "-e", "DOMHOUSE_ACME_TEST=1", "-e", "DOMHOUSE_ACME_SERVER=https://127.0.0.1:14000/dir", "-e", "DOMHOUSE_LEGO_NETWORK=host",
           # the limit on new connections would change this machine's own firewall: it has a privileged bench of its own
           "-e", "DOMHOUSE_LIMIT=off", "-e", "DOMHOUSE_AUTH_ALERT_PER_HOUR=3",
           "domhouse-broker-rig", "sleep", "3600")
    rig(f"rm -rf {BENCH}/opt {BENCH}/etc {BENCH}/data {BENCH}/certs {BENCH}/secrets {BENCH}/up {BENCH}/systemd {BENCH}/finto {BENCH}/systemctl.log; "
        f"find {BENCH}/tlsdisk -mindepth 1 -delete; install -d -m 700 {TLS} {ACME}; "
        f"mkdir -p {BENCH}/up {BENCH}/opt {BENCH}/data {BENCH}/certs {BENCH}/secrets {BENCH}/systemd {BENCH}/finto; "
        f"printf '#!/bin/sh\\necho \"$*\" >> {BENCH}/systemctl.log\\n' > /usr/local/bin/systemctl; chmod 755 /usr/local/bin/systemctl; "
        f"cd /repo && cp scripts/broker-vm.sh scripts/broker_accounts.py engine/broker/compose.yaml engine/broker/mosquitto.conf "
        f"engine/compose.broker.yaml {BENCH}/up/; sed -i 's/\\r$//' {BENCH}/up/broker-vm.sh; sed -i 's/$/\\r/' {BENCH}/up/mosquitto.conf {BENCH}/up/compose.yaml; "
        f"python3 /repo/tests/broker_rig/stub_gcp.py {BENCH}/secrets > /dev/null 2>&1 &")
    rig(f"""cd {BENCH}/certs && openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 30 -subj /CN=CA-di-prova 2>/dev/null &&
        openssl req -x509 -newkey rsa:2048 -nodes -keyout altra.key -out altra.crt -days 30 -subj /CN=CA-estranea 2>/dev/null""")
    make_cert("uno")
    outcome = {"senza_disco": rig(f"DOMHOUSE_TLS_MOUNT={BENCH}/finto bash {BENCH}/up/broker-vm.sh install {IMAGE}", check=False),
               "senza_certificato": rig(f"bash {BENCH}/up/broker-vm.sh install {IMAGE}", check=False),
               "cert_prima": rig(f"bash {BENCH}/up/broker-vm.sh install-cert {BENCH}/certs/uno.crt {BENCH}/certs/uno.key")}
    outcome["install"] = rig(f"bash {BENCH}/up/broker-vm.sh install {IMAGE}", timeout=200)
    return outcome


def stop_bench():
    if docker("ps", "-a", "-q", "-f", f"name=^{RIG}$", check=False).stdout.strip():
        rig(f"docker compose --env-file {BENCH}/opt/_broker/broker.settings -f {BENCH}/opt/_broker/compose.yaml down -v; "
            f"rm -rf {BENCH}/opt {BENCH}/etc {BENCH}/data {BENCH}/certs {BENCH}/secrets {BENCH}/up {BENCH}/systemd {BENCH}/finto; "
            f"find {BENCH}/tlsdisk -mindepth 1 -delete", check=False, timeout=90)
    docker("rm", "-f", RIG, PEBBLE, check=False)


@pytest.fixture(scope="module")
def bench():
    if shutil.which("docker") is None or docker("info", check=False).returncode:
        pytest.fail("Docker non disponibile: questa prova ha bisogno del broker vero in un contenitore")
    outcome = start_bench()
    for apartment, connector, devices in ((A, PW["connA"], {"a1": PW["a1"], "a2": PW["a2"]}), (B, PW["connB"], {"b1": PW["b1"]})):
        put_secret(f"langbrain-shelly-{apartment}", connector)
        put_devices(apartment, devices)
        outcome[f"add-{apartment}"] = vm("add-apartment", apartment)
    time.sleep(1)
    yield outcome
    stop_bench()


def test_install_refuses_a_missing_certificate(bench):
    done = bench["senza_certificato"]
    assert done.returncode and "certificato" in done.stderr, done.stderr
    assert "sano" in bench["install"].stdout


def key_modes():
    """Every folder and file on the keys' disk, as "<kind> <owner> <mode>": the set C-12 allows is two lines."""
    return set(rig(f"find {BENCH}/tlsdisk -mindepth 1 -exec stat -c '%F %u %a' {{}} +").stdout.splitlines())


ONLY_THE_BROKER = {"directory 1883 700", "regular file 1883 600"}


def test_the_keys_are_readable_only_by_the_broker(bench):
    assert "certificato pronto" in bench["cert_prima"].stdout and "ora install" in bench["cert_prima"].stdout
    assert key_modes() == ONLY_THE_BROKER
    assert rig(f"ls {TLS}").stdout.split() == ["fullchain.pem", "privkey.pem"]


def test_without_the_keys_disk_nothing_is_written_and_the_watch_says_down(bench):
    done = bench["senza_disco"]
    assert done.returncode and f"disco delle chiavi non montato su {BENCH}/finto" in done.stderr, done.stderr
    live = rig(f"sha256sum {TLS}/fullchain.pem {TLS}/privkey.pem").stdout
    elsewhere = f"DOMHOUSE_TLS_MOUNT={BENCH}/finto bash {BENCH}/opt/broker-vm.sh"
    refused = rig(f"{elsewhere} install-cert {BENCH}/certs/uno.crt {BENCH}/certs/uno.key", check=False)
    assert refused.returncode and "non montato" in refused.stderr, refused.stderr
    assert rig(f"{elsewhere} cert-new {HOST} domhouse-lab {DNS_ACCOUNT}", check=False).returncode
    assert rig(f"ls -A {BENCH}/finto").stdout == "", "una chiave scritta fuori dal disco delle chiavi"
    assert rig(f"sha256sum {TLS}/fullchain.pem {TLS}/privkey.pem").stdout == live
    assert f"broker down (disco delle chiavi non montato su {BENCH}/finto)" in rig(f"{elsewhere} check").stdout


def test_without_its_keys_folder_the_broker_does_not_start_and_docker_creates_nothing(bench):
    docker("stop", CONTAINER, timeout=60)
    rig(f"mv {TLS} {TLS}-via")
    try:
        started = docker("start", CONTAINER, check=False)
        missing = rig(f"test -e {TLS}", check=False).returncode
        text = vm("check").stdout
    finally:
        rig(f"mv {TLS}-via {TLS}")
    assert started.returncode and "does not exist" in started.stderr, started.stderr
    assert missing, "docker ha creato la cartella delle chiavi"
    assert "broker down (disco delle chiavi senza le cartelle broker e acme)" in text, text
    assert "sano" in vm("restart").stdout
    assert can_connect("tls", f"{A}.a1", PW["a1"])


def test_files_copied_from_windows_lose_their_carriage_returns(bench):
    assert rig(f"grep -c $'\\r' {BENCH}/up/mosquitto.conf").stdout.strip() != "0"         # the copy really had them
    assert rig(f"grep -c $'\\r' {BENCH}/opt/_broker/mosquitto.conf", check=False).stdout.strip() == "0"


def test_the_container_runs_unprivileged_and_publishes_only_the_tls_port(bench):
    info = json.loads(docker("inspect", CONTAINER).stdout)[0]
    assert info["Config"]["User"] == "1883:1883" and info["HostConfig"]["ReadonlyRootfs"] is True
    assert info["HostConfig"]["CapDrop"] == ["ALL"] and "no-new-privileges:true" in info["HostConfig"]["SecurityOpt"]
    assert info["HostConfig"]["RestartPolicy"]["Name"] == "unless-stopped"
    assert list(info["HostConfig"]["PortBindings"]) == ["8883/tcp"] and info["HostConfig"]["PortBindings"]["8883/tcp"][0]["HostPort"] == str(PORT)
    assert docker("exec", CONTAINER, "sh", "-c", "touch /etc/prova", check=False).returncode != 0
    internal = json.loads(docker("network", "inspect", INTERNAL_NET).stdout)[0]
    assert internal["Internal"] is True


def test_the_broker_keeps_only_hashes(bench):
    every = rig(f"cat {BENCH}/etc/_broker/auth/*").stdout
    assert not any(p in every for p in PW.values())
    lines = rig(f"cat {BENCH}/etc/_broker/auth/devices.passwd").stdout.splitlines()
    assert len(lines) == 3 and all(re.fullmatch(r"apt-[ab]\.[ab][12]:\$7\$1000\$[^$]+\$[^$]+", line) for line in lines)
    assert rig(f"stat -c '%u %a' {BENCH}/etc/_broker/auth/devices.passwd").stdout.strip() == "1883 640"
    assert not any(p in bench[k].stdout + bench[k].stderr for k in bench for p in PW.values())


def test_a_device_needs_tls_its_password_and_the_outside_door(bench):
    assert can_connect("tls", f"{A}.a1", PW["a1"])
    assert not can_connect("tls", f"{A}.a1", "password-sbagliata-ma-lunga-00001")
    assert not can_connect("tls", None, None)
    assert not can_connect("internal", f"{A}.a1", PW["a1"])           # the device's account has no place inside
    plain = docker("run", "--rm", "--network", "host", IMAGE, "mosquitto_pub", "-h", "127.0.0.1", "-p", str(PORT),
                   "-u", f"{A}.a1", "-P", PW["a1"], "-t", "x", "-m", "m", check=False)
    assert plain.returncode != 0


def test_the_connector_enters_only_from_the_internal_door(bench):
    assert can_connect("internal", f"{A}.connector", PW["connA"])
    assert not can_connect("internal", f"{A}.connector", "password-sbagliata-ma-lunga-00001")
    assert not can_connect("internal", None, None)
    assert not can_connect("tls", f"{A}.connector", PW["connA"])


def _tcp_reaches(network, host, port):
    return docker("run", "--rm", "--network", network, IMAGE, "nc", "-z", "-w", "3", host, str(port), check=False).returncode == 0


def test_the_internal_port_is_reachable_only_on_the_internal_network(bench):
    assert _tcp_reaches(INTERNAL_NET, INTERNAL_IP, 1883)
    info = json.loads(docker("inspect", CONTAINER).stdout)[0]
    outside_ip = info["NetworkSettings"]["Networks"][BRIDGE_NET]["IPAddress"]
    assert not _tcp_reaches(BRIDGE_NET, outside_ip, 1883), "la 1883 ascolta anche sulla rete che pubblica la 8883"
    assert not _tcp_reaches(BRIDGE_NET, INTERNAL_IP, 1883)
    docker("network", "create", "bench-altra", check=False)
    try:
        assert not _tcp_reaches("bench-altra", INTERNAL_IP, 1883), "un container estraneo raggiunge la porta interna"
    finally:
        docker("network", "rm", "bench-altra", check=False)


def test_the_client_can_verify_the_certificate(bench):
    good = docker("run", "--rm", "--network", "host", "--add-host", f"{HOST}:127.0.0.1", "-v", f"{BENCH}/certs:/certs:ro", IMAGE,
                  "mosquitto_pub", "-h", HOST, "-p", str(PORT), "--cafile", "/certs/altra.crt", "-u", f"{A}.a1", "-P", PW["a1"],
                  "-t", "x", "-m", "m", check=False)
    assert good.returncode != 0, "accettato un certificato di una CA diversa"
    wrong_name = docker("run", "--rm", "--network", "host", "-v", f"{BENCH}/certs:/certs:ro", IMAGE, "mosquitto_pub",
                        "-h", "127.0.0.1", "-p", str(PORT), "--cafile", "/certs/ca.crt", "-u", f"{A}.a1", "-P", PW["a1"],
                        "-t", "x", "-m", "m", check=False)
    assert wrong_name.returncode != 0, "accettato un certificato per un altro nome"


def test_a_connector_cannot_see_or_write_another_apartment(bench, sub):
    listener_b = sub("internal", f"{B}.connector", PW["connB"], f"{B}/#")
    spy = sub("internal", f"{A}.connector", PW["connA"], f"{B}/#")
    every = sub("internal", f"{A}.connector", PW["connA"], "#")
    assert pub("tls", f"{B}.b1", PW["b1"], f"{B}/b1/events/rpc", "segreto-di-b").returncode == 0
    assert listener_b.wait_for("segreto-di-b")
    pub("internal", f"{A}.connector", PW["connA"], f"{B}/b1/rpc", "comando-estraneo")
    time.sleep(1.5)
    assert not any("segreto-di-b" in line or "comando-estraneo" in line for line in spy.lines() + every.lines())
    assert not any("comando-estraneo" in line for line in listener_b.lines())


def test_a_device_cannot_leave_its_own_topics(bench, sub):
    connector_a = sub("internal", f"{A}.connector", PW["connA"], f"{A}/#")
    other_device = sub("tls", f"{A}.a2", PW["a2"], f"{A}/a2/#")
    spy_sibling = sub("tls", f"{A}.a1", PW["a1"], f"{A}/a2/#")
    spy_b = sub("tls", f"{A}.a1", PW["a1"], f"{B}/#")
    pub("tls", f"{A}.a1", PW["a1"], f"{A}/a2/rpc", "finto-comando")
    pub("tls", f"{A}.a1", PW["a1"], f"{B}/b1/rpc", "fuori-appartamento")
    pub("internal", f"{A}.connector", PW["connA"], f"{A}/a2/rpc", "comando-vero")
    assert other_device.wait_for("comando-vero")
    time.sleep(1)
    assert not any("finto-comando" in line for line in other_device.lines() + connector_a.lines())
    assert not any("comando-vero" in line for line in spy_sibling.lines())
    assert not any("fuori-appartamento" in line for line in spy_b.lines())


def test_request_and_answer_between_the_connector_and_its_device(bench, sub):
    device = sub("tls", f"{A}.a1", PW["a1"], f"{A}/a1/rpc")
    connector = sub("internal", f"{A}.connector", PW["connA"], f"{A}/connector/rpc")
    assert pub("internal", f"{A}.connector", PW["connA"], f"{A}/a1/rpc", "richiesta-1").returncode == 0
    assert device.wait_for("richiesta-1")
    assert pub("tls", f"{A}.a1", PW["a1"], f"{A}/connector/rpc", "risposta-1").returncode == 0
    assert connector.wait_for("risposta-1")


def test_a_second_sync_with_the_same_secrets_changes_nothing(bench):
    before = rig(f"stat -c %Y:%i {BENCH}/etc/_broker/auth/devices.passwd").stdout
    assert vm("sync").stdout.strip().endswith("unchanged")
    assert rig(f"stat -c %Y:%i {BENCH}/etc/_broker/auth/devices.passwd").stdout == before


def test_a_broken_secret_takes_nothing_away(bench):
    before = rig(f"cat {BENCH}/etc/_broker/auth/devices.passwd").stdout
    put_secret(f"langbrain-shelly-{A}-devices", "{non e' json")
    done = vm("sync", check=False)
    put_devices(A, {"a1": PW["a1"], "a2": PW["a2"]})
    assert done.returncode != 0 and "JSON" in done.stderr
    assert rig(f"cat {BENCH}/etc/_broker/auth/devices.passwd").stdout == before
    assert can_connect("tls", f"{A}.a1", PW["a1"])


def test_an_apartment_without_secrets_does_not_stay_on_the_list(bench):
    before = rig(f"cat {BENCH}/etc/_broker/apartments").stdout
    done = vm("add-apartment", "apt-senza-segreti", check=False)
    assert done.returncode != 0 and "non leggibile" in done.stderr
    assert rig(f"cat {BENCH}/etc/_broker/apartments").stdout == before
    assert vm("sync").returncode == 0, "un appartamento rimasto a metà bloccherebbe tutti gli altri"


def test_a_new_device_works_at_once_and_a_removed_one_stops(bench, sub):
    new_pw = "device-a3-password-lunga-000004"
    put_devices(A, {"a1": PW["a1"], "a2": PW["a2"], "a3": new_pw})
    assert not can_connect("tls", f"{A}.a3", new_pw)
    assert vm("sync").stdout.strip().endswith("ricaricati")
    assert can_connect("tls", f"{A}.a3", new_pw)
    connected = sub("tls", f"{A}.a3", new_pw, f"{A}/a3/#")
    assert pub("internal", f"{A}.connector", PW["connA"], f"{A}/a3/rpc", "prima").returncode == 0
    assert connected.wait_for("prima")
    put_devices(A, {"a1": PW["a1"], "a2": PW["a2"]})
    vm("sync")
    time.sleep(1.5)
    assert not can_connect("tls", f"{A}.a3", new_pw)
    pub("internal", f"{A}.connector", PW["connA"], f"{A}/a3/rpc", "dopo")
    time.sleep(1.5)
    assert not any("dopo" in line for line in connected.lines()), "un dispositivo tolto riceve ancora i messaggi"


def test_a_new_certificate_is_loaded_without_dropping_anyone(bench, sub):
    started = docker("inspect", "-f", "{{.State.StartedAt}}", CONTAINER).stdout
    connected = sub("tls", f"{A}.a1", PW["a1"], f"{A}/a1/#")
    make_cert("due")
    assert served_fingerprint() != fingerprint("due")
    vm("install-cert", f"{BENCH}/certs/due.crt", f"{BENCH}/certs/due.key")
    assert served_fingerprint() == fingerprint("due")
    assert key_modes() == ONLY_THE_BROKER
    assert can_connect("tls", f"{A}.a2", PW["a2"])
    assert pub("internal", f"{A}.connector", PW["connA"], f"{A}/a1/rpc", "dopo-la-ricarica").returncode == 0
    assert connected.wait_for("dopo-la-ricarica") and connected.running()
    assert docker("inspect", "-f", "{{.State.StartedAt}}", CONTAINER).stdout == started


@pytest.mark.parametrize("cert, key, reason", [("due.crt", "uno.key", "non corrisponde"), ("due.key", "due.key", "non è un certificato"),
                                               ("mancante.crt", "due.key", "manca")])
def test_a_bad_certificate_never_reaches_the_broker(bench, cert, key, reason):
    live = rig(f"sha256sum {TLS}/fullchain.pem {TLS}/privkey.pem").stdout
    served = served_fingerprint()
    done = vm("install-cert", f"{BENCH}/certs/{cert}", f"{BENCH}/certs/{key}", check=False)
    assert done.returncode != 0 and reason in done.stderr
    assert rig(f"sha256sum {TLS}/fullchain.pem {TLS}/privkey.pem").stdout == live
    assert served_fingerprint() == served and can_connect("tls", f"{A}.a1", PW["a1"])


def test_after_a_restart_clients_reconnect_and_nothing_queued_is_lost(bench, sub):
    connector = sub("internal", f"{A}.connector", PW["connA"], f"{A}/#", client_id="connettore-persistente", persistent=True)
    assert pub("tls", f"{A}.a1", PW["a1"], f"{A}/a1/online", "true", extra=["-r"]).returncode == 0
    assert connector.wait_for("online true")
    docker("rm", "-f", connector.name)
    assert pub("tls", f"{A}.a1", PW["a1"], f"{A}/a1/events/rpc", "mentre-era-via").returncode == 0
    vm("restart")
    assert can_connect("tls", f"{A}.a2", PW["a2"]) and can_connect("internal", f"{B}.connector", PW["connB"])
    again = sub("internal", f"{A}.connector", PW["connA"], f"{A}/#", client_id="connettore-persistente", persistent=True)
    assert again.wait_for("mentre-era-via"), "messaggio QoS 1 perso nel riavvio"
    fresh = sub("internal", f"{A}.connector", PW["connA"], f"{A}/a1/online")
    assert fresh.wait_for("online true"), "messaggio conservato perso nel riavvio"


def test_the_watch_says_ok_expiring_and_down(bench):
    assert re.search(r"^broker ok cert_days=\d+$", vm("check").stdout, re.M)
    make_cert("breve", days=5)
    vm("install-cert", f"{BENCH}/certs/breve.crt", f"{BENCH}/certs/breve.key")
    text = vm("check").stdout
    assert re.search(r"^broker ok cert_days=[45]$", text, re.M) and re.search(r"^broker cert expiring days=[45]$", text, re.M)
    make_cert("tre")
    vm("install-cert", f"{BENCH}/certs/tre.crt", f"{BENCH}/certs/tre.key")
    docker("stop", CONTAINER, timeout=60)
    try:
        text = vm("check").stdout
    finally:
        docker("start", CONTAINER)
        vm("status", check=False)
    assert re.search(r"^broker down \(container: \w+, porta TLS: muta\)$", text, re.M), text


def test_every_refused_login_leaves_a_line_and_many_raise_the_alert(bench):
    """D-209: Mosquitto's own line names the client id and the address; the client id is the device's user name."""
    for _ in range(4):
        assert pub("tls", f"{A}.a1", "password-sbagliata-ma-lunga-00001", f"{A}/a1/x", extra=["-i", f"{A}.a1"]).returncode
    for _ in range(6):            # the internal door is not the way in from the internet: these must not count
        assert pub("internal", f"{A}.connector", "password-sbagliata-ma-lunga-00001", "x", extra=["-i", "porta-interna"]).returncode
    logs = docker("logs", "--since", "3m", CONTAINER).stdout + docker("logs", "--since", "3m", CONTAINER).stderr
    assert re.search(rf"Client {A}\.a1 \[[0-9a-f.:]+:\d+\] disconnected: not authorised\.", logs), logs[-800:]
    text = vm("check").stdout
    assert re.search(rf"^broker auth refused hour=\d+ top_ip=[0-9a-f.:]+\(\d+\) top_client={A}\.a1\([4-9]\d*\)$", text, re.M), text
    assert re.search(r"^broker ok cert_days=\d+$", text, re.M)
    assert "porta-interna" not in text and "domhouse-check" not in text      # nor check's own probe, every 5 minutes
    assert re.search(r"^accessi rifiutati sulla 8883 nell'ultima ora: \d+$", vm("status").stdout, re.M)


def test_no_anonymous_login_on_either_door():
    """D-209: both listeners refuse a client without a user (the bench proves it too: can_connect with no user)."""
    conf = (ROOT / "engine/broker/mosquitto.conf").read_text(encoding="utf-8")
    listeners = re.split(r"^listener ", conf, flags=re.M)[1:]
    assert [l.split("\n")[0] for l in listeners] == ["8883", f"1883 {INTERNAL_IP}"]
    for section in listeners:
        assert re.search(r"^allow_anonymous false$", section, re.M) and re.search(r"^password_file ", section, re.M)
    assert "per_listener_settings true" in conf


def test_data_are_written_on_the_data_folder(bench):
    docker("exec", CONTAINER, "sh", "-c", "kill -0 1")
    rig(f"docker compose --env-file {BENCH}/opt/_broker/broker.settings -f {BENCH}/opt/_broker/compose.yaml restart", timeout=90)
    time.sleep(2)
    assert "mosquitto.db" in rig(f"ls {BENCH}/data/_broker").stdout


def file_fingerprint(path):
    return rig(f"openssl x509 -in {path} -noout -fingerprint -sha256 | sed 's/.*=//'").stdout.strip()


def test_without_acme_settings_the_daily_renewal_does_nothing(bench):
    assert "niente da fare" in vm("cert-renew").stdout
    assert "OnCalendar=*-*-* 04:17:00" in rig(f"cat {BENCH}/systemd/domhouse-broker-cert.timer").stdout
    assert f"ExecStart=/bin/bash {BENCH}/opt/broker-vm.sh cert-renew" in rig(f"cat {BENCH}/systemd/domhouse-broker-cert.service").stdout
    assert "enable --now domhouse-broker-cert.timer" in rig(f"cat {BENCH}/systemctl.log").stdout
    limit_unit = rig(f"cat {BENCH}/systemd/domhouse-broker-limit.service").stdout
    assert f"ExecStart=/bin/bash {BENCH}/opt/broker-vm.sh limit" in limit_unit and "WantedBy=multi-user.target" in limit_unit
    assert "enable domhouse-broker-limit.service" in rig(f"cat {BENCH}/systemctl.log").stdout


def test_a_certificate_from_acme_is_served_at_once_and_renewed_only_when_due(bench):
    done = vm("cert-new", HOST, "domhouse-lab", DNS_ACCOUNT)
    crt = f"{ACME}/certificates/{HOST}.crt"
    assert "ricarica fatta" in done.stdout and served_fingerprint() == file_fingerprint(crt)
    settings = rig(f"cat {BENCH}/etc/_broker/acme.settings").stdout.splitlines()
    assert settings == [f"ACME_DOMAIN={HOST}", "ACME_DNS_ZONE=domhouse-lab", f"ACME_DNS_ACCOUNT={DNS_ACCOUNT}",
                        "ACME_SERVER=https://127.0.0.1:14000/dir"]
    assert rig(f"ls {ACME}/accounts/*/domhouse-broker/domhouse-broker.key").returncode == 0      # the account key, on that disk
    assert key_modes() == ONLY_THE_BROKER
    again = vm("cert-renew")
    assert "rinnovo non ancora dovuto" in again.stdout and served_fingerprint() == file_fingerprint(crt)
    assert vm("cert-new", "Non Valido", "domhouse-lab", DNS_ACCOUNT, check=False).returncode


def test_revoking_gives_a_new_key_that_the_broker_serves_at_once(bench, sub):
    connected = sub("internal", f"{A}.connector", PW["connA"], f"{A}/#")
    key_before = rig(f"sha256sum < {TLS}/privkey.pem").stdout
    served_before = served_fingerprint()
    assert vm("cert-revoke", "boh", check=False).returncode
    done = vm("cert-revoke", "key-compromise")
    assert f"broker cert revoked ({HOST}, key-compromise)" in done.stdout and "ricarica fatta" in done.stdout
    assert rig(f"sha256sum < {TLS}/privkey.pem").stdout != key_before
    assert served_fingerprint() != served_before and served_fingerprint() == file_fingerprint(f"{ACME}/certificates/{HOST}.crt")
    assert rig(f"ls {ACME}/archives/certificates/").stdout.strip().endswith(".zip")    # the old pair, still on that disk
    assert key_modes() == ONLY_THE_BROKER
    assert connected.running(), "la riemissione ha fatto cadere il connector"


def test_a_forced_renewal_gives_a_new_certificate_at_once(bench):
    """D-210: the first automatic renewal falls after the delivery, so one is forced during the run-in."""
    served_before = served_fingerprint()
    assert vm("cert-renew", "now", check=False).returncode
    done = vm("cert-renew", "force")
    assert "broker cert new notAfter=" in done.stdout and "ricarica fatta" in done.stdout, done.stdout
    assert served_fingerprint() != served_before and served_fingerprint() == file_fingerprint(f"{ACME}/certificates/{HOST}.crt")
    assert "rinnovo non ancora dovuto" in vm("cert-renew").stdout
    assert key_modes() == ONLY_THE_BROKER


DISK_RIG = "domhouse-broker-disk-run"
OPTIONS = "defaults,nofail,nodev,nosuid,noexec,x-systemd.device-timeout=30s,x-systemd.before=docker.service"


def on_disk_rig(script, check=True):
    return docker("exec", DISK_RIG, "bash", "-c", script, check=check, timeout=120)


@pytest.fixture(scope="module")
def disk():
    """A privileged bench: /vm is an ext4 loop disk standing for the VM's boot disk; loop disks stand for the keys'
    disk (empty), one already formatted ext2, one with data and no file system, a new keys' disk after a restore, plus
    a name that is no disk."""
    if shutil.which("docker") is None or docker("info", check=False).returncode:
        pytest.fail("Docker non disponibile: questa prova ha bisogno di un contenitore privilegiato")
    docker("build", "-q", "-t", "domhouse-broker-rig", str(ROOT / "tests" / "broker_rig"), timeout=240)
    docker("rm", "-f", DISK_RIG, check=False)
    docker("run", "-d", "--name", DISK_RIG, "--privileged", "-v", f"{ROOT.as_posix()}:/repo:ro", "domhouse-broker-rig", "sleep", "1800")
    loops = {}
    try:
        on_disk_rig("mkdir -p /w /vm && truncate -s 64M /w/boot.img && mkfs.ext4 -q /w/boot.img && mount -o loop /w/boot.img /vm && "
                    "cp /repo/scripts/broker-vm.sh /w/ && sed -i 's/\\r$//' /w/broker-vm.sh")
        for name in ("tls", "ext2", "dirty", "fresh"):
            on_disk_rig(f"truncate -s 16M /w/{name}.img")
            loops[name] = on_disk_rig(f"losetup -f --show /w/{name}.img").stdout.strip()
            on_disk_rig(f"ln -s {loops[name]} /w/google-{name}")
        on_disk_rig(f"mkfs.ext2 -q {loops['ext2']} && dd if=/dev/urandom of={loops['dirty']} bs=4k seek=8 count=16 conv=notrunc 2>/dev/null")
        yield loops
    finally:
        on_disk_rig("umount /vm/mnt/* 2>/dev/null; " + " ".join(f"losetup -d {dev};" for dev in loops.values()) + " umount /vm", check=False)
        docker("rm", "-f", DISK_RIG, check=False)


def prepare(name, mount):
    return on_disk_rig(f"DOMHOUSE_TLS_DEVICE=/w/google-{name} DOMHOUSE_TLS_MOUNT={mount} bash /w/broker-vm.sh prepare-tls-disk", check=False)


def fstab_lines(mount):
    return [line for line in on_disk_rig("cat /etc/fstab").stdout.splitlines() if f" {mount} " in line]


def test_the_keys_disk_is_formatted_once_mounted_at_boot_and_closed_when_absent(disk):
    mount = "/vm/mnt/domhouse-tls"
    first = prepare("tls", mount)
    assert first.returncode == 0 and "Formattazione" in first.stdout, first.stdout + first.stderr
    uuid = on_disk_rig(f"blkid -p -o value -s UUID {disk['tls']}").stdout.strip()
    assert fstab_lines(mount) == [f"UUID={uuid} {mount} ext4 {OPTIONS} 0 2"]
    assert on_disk_rig(f"findmnt -n -o SOURCE --mountpoint {mount}").stdout.strip() == disk["tls"]
    assert on_disk_rig(f"stat -c '%u %a' {mount}/broker {mount}/acme").stdout.split("\n")[:2] == ["1883 700", "1883 700"]
    on_disk_rig(f"echo segno > {mount}/broker/segno")
    second = prepare("tls", mount)
    assert second.returncode == 0 and "Formattazione" not in second.stdout and "già presente" in second.stdout
    assert on_disk_rig(f"cat {mount}/broker/segno").stdout.strip() == "segno" and len(fstab_lines(mount)) == 1
    on_disk_rig(f"umount {mount}")
    assert on_disk_rig(f"touch {mount}/chiave", check=False).returncode, "con il disco assente si scrive sul disco di avvio"
    assert on_disk_rig(f"ls -A {mount}").stdout == ""
    third = prepare("tls", mount)                       # mounts through the fstab line: the line is a valid one
    assert third.returncode == 0 and on_disk_rig(f"cat {mount}/broker/segno").stdout.strip() == "segno"


def test_a_disk_that_holds_something_is_never_formatted(disk):
    other = prepare("ext2", "/vm/mnt/altro")
    assert other.returncode and "ext2" in other.stderr
    assert on_disk_rig(f"blkid -p -o value -s TYPE {disk['ext2']}").stdout.strip() == "ext2"
    dirty = prepare("dirty", "/vm/mnt/sporco")
    assert dirty.returncode and "non è vuoto" in dirty.stderr
    assert on_disk_rig(f"blkid -p -o value -s TYPE {disk['dirty']}", check=False).stdout.strip() == ""
    absent = prepare("nessuno", "/vm/mnt/nessuno")
    assert absent.returncode and "manca il disco" in absent.stderr
    assert not fstab_lines("/vm/mnt/altro") and not fstab_lines("/vm/mnt/sporco") and not fstab_lines("/vm/mnt/nessuno")


LIMIT_RIG = "domhouse-broker-limit-run"
CONNECT = """import socket, sys
ok = 0
for _ in range(int(sys.argv[3])):
    s = socket.socket(); s.settimeout(0.4)
    try:
        s.connect((sys.argv[1], int(sys.argv[2]))); ok += 1
    except OSError:
        pass
    s.close()
print(ok)
"""


def on_limit_rig(script, check=True):
    return docker("exec", LIMIT_RIG, "bash", "-c", script, check=check, timeout=120)


LIMIT_NET, LIMIT_RIG_IP = "bench-limit", "10.98.0.2"


def connections_from(source, count):
    """Opens `count` connections one after the other from the address `source`: how many got in."""
    done = docker("run", "--rm", "--network", LIMIT_NET, "--ip", source, "--entrypoint", "python3", "domhouse-broker-rig",
                  "-c", CONNECT, LIMIT_RIG_IP, "18883", str(count), timeout=120)
    return int(done.stdout.strip())


@pytest.fixture(scope="module")
def limited():
    """A privileged bench with the VM's path: port 18883 goes through a DNAT to a server on 8883 in another network
    namespace, as docker publishes the broker; the limit is the real broker-vm.sh limit, on the forward hook."""
    if shutil.which("docker") is None or docker("info", check=False).returncode:
        pytest.fail("Docker non disponibile: questa prova ha bisogno di un contenitore privilegiato")
    docker("build", "-q", "-t", "domhouse-broker-rig", str(ROOT / "tests" / "broker_rig"), timeout=240)
    docker("rm", "-f", LIMIT_RIG, check=False)
    docker("network", "rm", LIMIT_NET, check=False)
    docker("network", "create", "--subnet", "10.98.0.0/24", LIMIT_NET)
    docker("run", "-d", "--name", LIMIT_RIG, "--privileged", "--network", LIMIT_NET, "--ip", LIMIT_RIG_IP, "-v", f"{ROOT.as_posix()}:/repo:ro", "-e", "DOMHOUSE_OPT=/w/opt",
           "domhouse-broker-rig", "sleep", "900")
    try:
        on_limit_rig(
            "mkdir -p /w && cp /repo/scripts/broker-vm.sh /w/ && sed -i 's/\\r$//' /w/broker-vm.sh && "
            "ip netns add srv && ip link add vs type veth peer name vs-in && ip link set vs-in netns srv && "
            "ip addr add 10.99.0.1/24 dev vs && ip link set vs up && ip netns exec srv ip addr add 10.99.0.2/24 dev vs-in && "
            "ip netns exec srv ip link set vs-in up && ip netns exec srv ip link set lo up && "
            "ip netns exec srv ip route add default via 10.99.0.1 && sysctl -q -w net.ipv4.ip_forward=1 && "
            "nft add table ip docker_finto && "
            "nft 'add chain ip docker_finto pre { type nat hook prerouting priority -100; }' && "
            "nft add rule ip docker_finto pre tcp dport 18883 dnat to 10.99.0.2:8883")
        on_limit_rig("ip netns exec srv python3 -c \"import socket; s = socket.socket(); "
                     "s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); s.bind(('0.0.0.0', 8883)); s.listen(512)\n"
                     "while True: s.accept()[0].close()\" > /dev/null 2>&1 &")
        yield
    finally:
        docker("rm", "-f", LIMIT_RIG, check=False)
        docker("network", "rm", LIMIT_NET, check=False)


def test_new_connections_are_limited_per_address_and_never_banned(limited):
    assert connections_from("10.98.0.11", 10) == 10                              # the way through works without the limit
    first = on_limit_rig("bash /w/broker-vm.sh limit")
    assert first.returncode == 0 and "limite attivo" in first.stdout
    on_limit_rig("bash /w/broker-vm.sh limit")                                   # a repeat leaves one copy
    table = on_limit_rig("nft list table inet domhouse_broker").stdout
    assert table.count('comment "domhouse-broker-limit"') == 2 and "hook forward" in table
    assert on_limit_rig("nft list tables").stdout.count("domhouse_broker") == 1
    flood = connections_from("10.98.0.12", 90)
    assert 60 <= flood <= 70, f"{flood} collegamenti su 90 da un solo indirizzo"   # the burst, then 30 a minute
    assert connections_from("10.98.0.13", 10) == 10, "un altro indirizzo è stato fermato"
    assert int(re.search(r"counter packets (\d+)", table := on_limit_rig("nft list table inet domhouse_broker").stdout).group(1)) > 0, table


def test_after_a_restore_with_a_new_disk_the_line_of_the_old_one_is_replaced(disk):
    mount = "/vm/mnt/ripristino"
    gone = f"UUID=0b5e55ed-dead-4bad-beef-000000000001 {mount} ext4 {OPTIONS} 0 2"
    on_disk_rig(f"echo '{gone}' >> /etc/fstab")
    done = prepare("fresh", mount)
    assert done.returncode == 0 and "sostituita" in done.stdout, done.stdout + done.stderr
    uuid = on_disk_rig(f"blkid -p -o value -s UUID {disk['fresh']}").stdout.strip()
    assert fstab_lines(mount) == [f"UUID={uuid} {mount} ext4 {OPTIONS} 0 2"]
    assert on_disk_rig("ls /etc/fstab.before-domhouse-tls-*").returncode == 0      # the previous file, kept
    on_disk_rig(f"umount {mount}")
    ext2 = on_disk_rig(f"blkid -p -o value -s UUID {disk['ext2']}").stdout.strip()   # a disk that is there: not ours to drop
    on_disk_rig(f"sed -i 's#^UUID=[^ ]* {mount} #UUID={ext2} {mount} #' /etc/fstab")
    refused = prepare("fresh", mount)
    assert refused.returncode and "diversa da quella attesa" in refused.stderr
    assert fstab_lines(mount) == [f"UUID={ext2} {mount} ext4 {OPTIONS} 0 2"]


def test_the_address_of_the_internal_listener_is_the_same_everywhere():
    conf = (ROOT / "engine/broker/mosquitto.conf").read_text(encoding="utf-8")
    compose = (ROOT / "engine/broker/compose.yaml").read_text(encoding="utf-8")
    assert f"listener 1883 {INTERNAL_IP}" in conf and f"ipv4_address: {INTERNAL_IP}" in compose
    assert f"-h {INTERNAL_IP} -p 1883" in compose and "172.30.83.0/24" in compose
    assert INTERNAL_NET in (ROOT / "engine/compose.broker.yaml").read_text(encoding="utf-8")
