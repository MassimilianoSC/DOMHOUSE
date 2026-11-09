"""The real broker (D-196, D-199) in containers, driven by the real scripts/broker-vm.sh. The bench (tests/broker_rig) is a
Linux that runs the script as root and uses this machine's Docker through its socket: what is checked is the image, the
configuration and the file permissions that go on the VM. Only Secret Manager and the metadata server are stand-ins.
Clients are the broker image's own mosquitto_pub and mosquitto_sub. Docker missing is one red, never a skip."""
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
    docker("rm", "-f", RIG, check=False)
    docker("run", "-d", "--name", RIG, "--network", "host",
           "-v", "/var/run/docker.sock:/var/run/docker.sock", "-v", f"{BENCH}:{BENCH}", "-v", f"{ROOT.as_posix()}:/repo:ro",
           "-e", f"DOMHOUSE_OPT={BENCH}/opt", "-e", f"DOMHOUSE_ETC={BENCH}/etc", "-e", f"DOMHOUSE_DATA={BENCH}/data",
           "-e", f"DOMHOUSE_BROKER_PORT={PORT}", "-e", "DOMHOUSE_METADATA=http://127.0.0.1:18090",
           "-e", "DOMHOUSE_SECRETS_API=http://127.0.0.1:18090/v1", "-e", "DOMHOUSE_HEALTH_TRIES=45",
           "domhouse-broker-rig", "sleep", "3600")
    rig(f"rm -rf {BENCH}/opt {BENCH}/etc {BENCH}/data {BENCH}/certs {BENCH}/secrets {BENCH}/up; "
        f"mkdir -p {BENCH}/up {BENCH}/opt {BENCH}/etc/_broker/tls {BENCH}/data {BENCH}/certs {BENCH}/secrets; "
        f"cd /repo && cp scripts/broker-vm.sh scripts/broker_accounts.py engine/broker/compose.yaml engine/broker/mosquitto.conf "
        f"engine/compose.broker.yaml {BENCH}/up/; sed -i 's/\\r$//' {BENCH}/up/broker-vm.sh; sed -i 's/$/\\r/' {BENCH}/up/mosquitto.conf {BENCH}/up/compose.yaml; "
        f"python3 /repo/tests/broker_rig/stub_gcp.py {BENCH}/secrets > /dev/null 2>&1 &")
    rig(f"""cd {BENCH}/certs && openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 30 -subj /CN=CA-di-prova 2>/dev/null &&
        openssl req -x509 -newkey rsa:2048 -nodes -keyout altra.key -out altra.crt -days 30 -subj /CN=CA-estranea 2>/dev/null""")
    make_cert("uno")
    outcome = {"senza_certificato": rig(f"bash {BENCH}/up/broker-vm.sh install {IMAGE}", check=False)}
    rig(f"cp {BENCH}/certs/uno.crt {BENCH}/etc/_broker/tls/fullchain.pem; cp {BENCH}/certs/uno.key {BENCH}/etc/_broker/tls/privkey.pem")
    outcome["install"] = rig(f"bash {BENCH}/up/broker-vm.sh install {IMAGE}", timeout=200)
    return outcome


def stop_bench():
    if docker("ps", "-a", "-q", "-f", f"name=^{RIG}$", check=False).stdout.strip():
        rig(f"docker compose --env-file {BENCH}/opt/_broker/broker.settings -f {BENCH}/opt/_broker/compose.yaml down -v; rm -rf {BENCH}/opt {BENCH}/etc {BENCH}/data {BENCH}/certs {BENCH}/secrets {BENCH}/up", check=False, timeout=90)
    docker("rm", "-f", RIG, check=False)


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
    assert can_connect("tls", f"{A}.a2", PW["a2"])
    assert pub("internal", f"{A}.connector", PW["connA"], f"{A}/a1/rpc", "dopo-la-ricarica").returncode == 0
    assert connected.wait_for("dopo-la-ricarica") and connected.running()
    assert docker("inspect", "-f", "{{.State.StartedAt}}", CONTAINER).stdout == started


@pytest.mark.parametrize("cert, key, reason", [("due.crt", "uno.key", "non corrisponde"), ("due.key", "due.key", "non è un certificato"),
                                               ("mancante.crt", "due.key", "manca")])
def test_a_bad_certificate_never_reaches_the_broker(bench, cert, key, reason):
    live = rig(f"sha256sum {BENCH}/etc/_broker/tls/fullchain.pem {BENCH}/etc/_broker/tls/privkey.pem").stdout
    served = served_fingerprint()
    done = vm("install-cert", f"{BENCH}/certs/{cert}", f"{BENCH}/certs/{key}", check=False)
    assert done.returncode != 0 and reason in done.stderr
    assert rig(f"sha256sum {BENCH}/etc/_broker/tls/fullchain.pem {BENCH}/etc/_broker/tls/privkey.pem").stdout == live
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


def test_data_are_written_on_the_data_folder(bench):
    docker("exec", CONTAINER, "sh", "-c", "kill -0 1")
    rig(f"docker compose --env-file {BENCH}/opt/_broker/broker.settings -f {BENCH}/opt/_broker/compose.yaml restart", timeout=90)
    time.sleep(2)
    assert "mosquitto.db" in rig(f"ls {BENCH}/data/_broker").stdout


def test_the_address_of_the_internal_listener_is_the_same_everywhere():
    conf = (ROOT / "engine/broker/mosquitto.conf").read_text(encoding="utf-8")
    compose = (ROOT / "engine/broker/compose.yaml").read_text(encoding="utf-8")
    assert f"listener 1883 {INTERNAL_IP}" in conf and f"ipv4_address: {INTERNAL_IP}" in compose
    assert f"-h {INTERNAL_IP} -p 1883" in compose and "172.30.83.0/24" in compose
    assert INTERNAL_NET in (ROOT / "engine/compose.broker.yaml").read_text(encoding="utf-8")
