"""scripts/engine-vm.sh set/unset (P-60 step 7d, D-131): the engine's settings of an apartment in
<ETC>/<apartment_id>.settings.env, never in the key's file; the container recreated, health awaited, the previous file
put back when the engine does not come back. The real script, run by bash with stand-ins for docker, curl, id, sleep
and python3 in front of PATH, and its two folders moved to a temporary one (DOMHOUSE_ETC, DOMHOUSE_OPT)."""
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "engine-vm.sh"
APT = "apt-prova-01"


def _bash() -> str | None:
    spec = importlib.util.spec_from_file_location("run_tests", ROOT / "scripts" / "run_tests.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.git_bash()


def posix(path: Path) -> str:
    """A path as bash wants it in PATH: /c/... for C:/... (the colon of a drive would split PATH)."""
    s = path.as_posix()
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else s


STUBS = {
    "id": '#!/usr/bin/env bash\necho 0\n',
    "sleep": '#!/usr/bin/env bash\nexit 0\n',
    # docker inspect answers the state written in state-<container> (lot 39: the watch and start-all read it)
    "docker": ('#!/usr/bin/env bash\necho "$* [ENGINE_BIND_IP=${ENGINE_BIND_IP:-}]" >> "$STUB_DIR/docker.log"\n'
               'if [ "$1" = inspect ]; then cat "$STUB_DIR/state-${!#}" 2>/dev/null; fi\nexit 0\n'),
    # flock: refuses (as flock -n would) when the test put a file "locked"
    "flock": '#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/flock.log"\n[ ! -f "$STUB_DIR/locked" ]\n',
    "ip": '#!/usr/bin/env bash\ncat "$STUB_DIR/addresses" 2>/dev/null\nexit 0\n',
    # install without owner and modes: this machine has no user root, and Windows refuses them (write_key makes ETC
    # root's, 700); folders are made, files copied
    "install": ('#!/usr/bin/env bash\nd=""; pos=()\nwhile [ $# -gt 0 ]; do case "$1" in -o|-g|-m) shift 2 ;; '
                '-d) d=1; shift ;; *) pos+=("$1"); shift ;; esac; done\n'
                'if [ -n "$d" ]; then mkdir -p "${pos[@]}"; else cp "${pos[0]}" "${pos[1]}"; fi\n'),
    # health: 200 unless the test put a file "unhealthy" (503) or "code-<port>" (that code) next to the stand-ins
    "curl": ('#!/usr/bin/env bash\n'
             'echo "$*" >> "$STUB_DIR/curl.log"\n'
             # the metadata server and Secret Manager (write_key): a secret is the file secret-<name>
             'case "$*" in *service-accounts/default/token*) echo \'{"access_token": "tok"}\'; exit 0 ;; '
             '*project/project-id*) printf progetto; exit 0 ;; '
             '*versions/latest:access*) name=$(echo "$*" | grep -oE "secrets/[^/]+/versions" | cut -d/ -f2); '
             '[ -f "$STUB_DIR/secret-$name" ] || exit 22; '
             'printf \'{"payload": {"data": "%s"}}\' "$(base64 -w0 < "$STUB_DIR/secret-$name")"; exit 0 ;; esac\n'
             'port=$(echo "$*" | grep -oE "://[0-9.]+:[0-9]+/" | head -1 | cut -d: -f3 | tr -d /)\n'
             'host=$(echo "$*" | grep -oE "https://[^/ ]+" | head -1 | cut -d/ -f3)\n'
             'if [ -n "$host" ] && [ -f "$STUB_DIR/code-$host" ]; then code=$(cat "$STUB_DIR/code-$host"); '
             'elif [ -f "$STUB_DIR/code-$port" ]; then code=$(cat "$STUB_DIR/code-$port"); '
             'elif [ -f "$STUB_DIR/unhealthy" ]; then code=503; else code=200; fi\n'
             'case "$*" in *%{http_code}*) printf "%s" "$code" ;; '
             '*) echo \'{"status": "ok", "implementation": {}, "connector": {"status": "up"}}\' ;; esac\n'),
    "logger": '#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/syslog.log"\n',
    "systemctl": '#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/systemctl.log"\nexit 0\n',
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
    etc, opt, data, units = tmp_path / "etc", tmp_path / "opt", tmp_path / "data", tmp_path / "systemd"
    for folder in (etc, opt, data, units):
        folder.mkdir()
    (opt / f"{APT}.settings").write_text(f"APARTMENT_ID={APT}\nPORT=8100\nCONNECTOR=simulated\nENGINE_IMAGE=x:1\n",
                                         encoding="utf-8", newline="\n")
    (etc / f"{APT}.env").write_text("API_KEY=chiave-di-prova-lunga\n", encoding="utf-8", newline="\n")
    (tmp_path / "meminfo").write_text("MemTotal:        2000000 kB\nMemFree:          300000 kB\nMemAvailable:     500000 kB\n",
                                      encoding="utf-8", newline="\n")             # a Linux /proc/meminfo, e2-small sized

    def run(*args, bind="10.198.0.2", env=""):   # D-218: the VM's internal address, as the metadata server gives it
        cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}" {env} '
               f'DOMHOUSE_ETC="{posix(etc)}" DOMHOUSE_OPT="{posix(opt)}" DOMHOUSE_HEALTH_TRIES=2 '
               f'DOMHOUSE_DATA="{posix(data)}" DOMHOUSE_SYSTEMD="{posix(units)}" DOMHOUSE_BIND_IP="{bind}" '
               f'DOMHOUSE_OPS_CONFIG="{posix(tmp_path / "ops" / "config.yaml")}" DOMHOUSE_MEMINFO="{posix(tmp_path / "meminfo")}"; '
               f'bash "{posix(SCRIPT)}" ' + " ".join(f"'{a}'" for a in args))
        return subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=60)

    run.settings = etc / f"{APT}.settings.env"
    run.key = etc / f"{APT}.env"
    run.stubs = stubs
    run.opt, run.data, run.units, run.ops = opt, data, units, tmp_path / "ops" / "config.yaml"
    return run


def test_set_and_unset_write_only_the_settings_file_and_recreate_the_engine(vm):
    r = vm("set", APT, "CONFIRM_ON_WATTS=30")
    assert r.returncode == 0, r.stderr
    assert vm.settings.read_text(encoding="utf-8") == "CONFIRM_ON_WATTS=30\n"
    assert vm("set", APT, "CONFIRM_OFF_WATTS=8.5").returncode == 0
    assert vm("set", APT, "CONFIRM_ON_WATTS=40").returncode == 0                     # replaced, not added twice
    assert vm.settings.read_text(encoding="utf-8") == "CONFIRM_OFF_WATTS=8.5\nCONFIRM_ON_WATTS=40\n"
    assert vm.key.read_text(encoding="utf-8") == "API_KEY=chiave-di-prova-lunga\n"   # the key's file untouched
    docker = (vm.stubs / "docker.log").read_text(encoding="utf-8")
    assert docker.count("up -d --force-recreate") == 3
    status = vm("status", APT)
    assert "CONFIRM_ON_WATTS=40" in status.stdout and "API_KEY" not in status.stdout
    assert vm("unset", APT, "CONFIRM_ON_WATTS").returncode == 0
    assert vm.settings.read_text(encoding="utf-8") == "CONFIRM_OFF_WATTS=8.5\n"


@pytest.mark.parametrize("args, says", [
    (("set", APT, "API_KEY=altro"), "API_KEY non si cambia con set/unset"),
    (("set", APT, "PORT=9000"), "PORT non si cambia con set/unset"),
    (("set", APT, "confirm=3"), "nome di impostazione non valido"),
    (("set", APT, "CONFIRM_ON_WATTS=3;rm"), "valore non valido"),
    (("set", "apt-mai-installato", "CONFIRM_ON_WATTS=30"), "non è installato"),
])
def test_refusals(vm, args, says):
    r = vm(*args)
    assert r.returncode != 0 and says in r.stderr, r.stderr
    assert not vm.settings.exists()


def test_an_engine_that_does_not_come_back_gets_the_previous_settings(vm):
    assert vm("set", APT, "CONFIRM_ON_WATTS=30").returncode == 0
    (vm.stubs / "unhealthy").write_text("", encoding="utf-8")                         # it refuses the new value
    (vm.stubs / "docker.log").unlink(missing_ok=True)
    r = vm("set", APT, "CONFIRM_ON_WATTS=9999")
    assert r.returncode != 0 and "impostazione CONFIRM_ON_WATTS non applicata" in r.stderr
    # T3c-1 (P-83): recreated with the new value, then again with the previous one: two recreations, not one
    assert (vm.stubs / "docker.log").read_text(encoding="utf-8").count("up -d --force-recreate") == 2
    assert vm.settings.read_text(encoding="utf-8") == "CONFIRM_ON_WATTS=30\n"


def test_compose_reads_the_settings_file_as_optional():
    text = (ROOT / "engine" / "compose.yaml").read_text(encoding="utf-8")
    block = re.search(r"env_file:\n((?:\s+- path: .+\n\s+required: \w+\n)+)", text)
    assert block, "env_file di compose.yaml non trovato"
    entries = re.findall(r"- path: (\S+)\n\s+required: (\w+)", block.group(1))
    assert entries == [("/etc/domhouse/${APARTMENT_ID}.env", "true"),
                       ("/etc/domhouse/${APARTMENT_ID}.settings.env", "false")]


def test_the_daily_cleanup_also_removes_old_databases_set_aside_by_restore(tmp_path):
    """P-71 (D-142): the 7-day clean-up of the backups takes before-restore-*.db (and -wal, -shm) too. The script's own
    find line, run by bash on a folder of old and recent files."""
    bash = _bash()
    if not bash:
        pytest.skip("bash non disponibile")
    line = next(l for l in SCRIPT.read_text(encoding="utf-8").splitlines() if l.strip().startswith('find "${dir}"'))
    folder = tmp_path / "backup"
    folder.mkdir()
    old = ["engine-2026-10-01.db", "before-restore-20261001T100000Z.db", "before-restore-20261001T100000Z.db-wal"]
    recent = ["engine-2026-10-20.db", "before-restore-20261020T100000Z.db", "altro-file.db"]
    for name in old + recent:
        (folder / name).write_text("x", encoding="utf-8")
    touch_old = " ".join(f"'{posix(folder / n)}'" for n in old)
    cmd = f'touch -d "10 days ago" {touch_old}; BACKUP_DAYS=7; dir="{posix(folder)}"; {line.strip()}'
    r = subprocess.run([bash, "-c", cmd], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in folder.iterdir()) == sorted(recent)    # "altro-file.db" is not ours: untouched


# -------- P-60 step 10 (D-104, D-148): the 5-minute watch, its timer, the engines' logs to Cloud Logging --------
def test_the_watch_writes_one_line_per_engine_backup_and_a_summary(vm):
    import os
    import time
    (vm.opt / "apt-muto.settings").write_text("APARTMENT_ID=apt-muto\nPORT=8101\n", encoding="utf-8", newline="\n")
    (vm.opt / "apt-giu.settings").write_text("APARTMENT_ID=apt-giu\nPORT=8102\n", encoding="utf-8", newline="\n")
    (vm.stubs / "code-8101").write_text("000", encoding="utf-8")
    (vm.stubs / "code-8102").write_text("503", encoding="utf-8")
    backup = vm.data / APT / "backup"
    backup.mkdir(parents=True)
    old = backup / "engine-2026-10-19.db"
    old.write_text("x", encoding="utf-8")
    two_days_ago = time.time() - 48 * 3600
    os.utime(old, (two_days_ago, two_days_ago))
    r = vm("check-all")
    assert r.returncode == 0, r.stderr
    syslog = (vm.stubs / "syslog.log").read_text(encoding="utf-8")
    assert f"-t domhouse-check engine ok {APT}" in syslog
    assert "-t domhouse-check engine silent apt-muto" in syslog and "-t domhouse-check engine down apt-giu" in syslog
    assert f"-t domhouse-check backup missing {APT} age_h=4" in syslog          # 48 hours (4x)
    assert "-t domhouse-check domhouse-check: 3 motori, 2 muti" in syslog
    assert re.search(r"-t domhouse-check vm mem_used_pct=75 disk_used_pct=\d+$", syslog, re.M), syslog   # D-210: 1.5 of 2 GB
    fresh = backup / "engine-2026-10-21.db"
    fresh.write_text("x", encoding="utf-8")
    (vm.stubs / "syslog.log").unlink()
    vm("check-all")
    assert "backup missing" not in (vm.stubs / "syslog.log").read_text(encoding="utf-8")   # a new backup stops it


def test_once_an_hour_the_watch_tries_the_ways_out_the_vm_uses(vm):
    """D-212: since the NAT went (10 November) the VM goes out from its own address. Once an hour: the server the
    assistant asks (MODEL_BASE_URL of an engine), Artifact Registry (401 = reached) and Let's Encrypt."""
    vm.settings.write_text("MODEL_BASE_URL=https://domotica-bff.example.run.app\n", encoding="utf-8", newline="\n")
    (vm.stubs / "code-europe-west8-docker.pkg.dev").write_text("401", encoding="utf-8")
    assert vm("check-all").returncode == 0
    syslog = (vm.stubs / "syslog.log").read_text(encoding="utf-8")
    assert "-t domhouse-check egress ok server=200 registry=401 acme=200" in syslog
    called = (vm.stubs / "curl.log").read_text(encoding="utf-8")
    assert "https://domotica-bff.example.run.app/health" in called and "acme-v02.api.letsencrypt.org/directory" in called
    (vm.stubs / "syslog.log").unlink()
    vm("check-all")                                                        # within the hour: not again
    assert "egress" not in (vm.stubs / "syslog.log").read_text(encoding="utf-8")
    (vm.opt / ".egress-checked").write_text("0", encoding="utf-8")       # an hour later, Let's Encrypt unreachable
    (vm.stubs / "code-acme-v02.api.letsencrypt.org").write_text("000", encoding="utf-8")
    vm("check-all")
    assert "-t domhouse-check egress failed server=200 registry=401 acme=000" in (vm.stubs / "syslog.log").read_text(encoding="utf-8")


def test_timers_installs_the_backup_and_the_5_minute_watch(vm):
    r = vm("timers")
    assert r.returncode == 0, r.stderr
    timer = (vm.units / "domhouse-engine-check.timer").read_text(encoding="utf-8")
    service = (vm.units / "domhouse-engine-check.service").read_text(encoding="utf-8")
    assert "OnCalendar=*:0/5" in timer and "engine-vm.sh check-all" in service
    assert "StandardOutput=null" in service and "StandardError" not in service   # one line per event in the syslog
    assert (vm.units / "domhouse-engine-backup.timer").exists()
    assert "enable --now domhouse-engine-backup.timer domhouse-engine-check.timer" in \
        (vm.stubs / "systemctl.log").read_text(encoding="utf-8")


def test_logs_agent_keeps_the_previous_configuration_and_restarts_the_agent(vm):
    vm.ops.parent.mkdir()
    vm.ops.write_text("# configurazione di prima\n", encoding="utf-8")
    r = vm("logs-agent")
    assert r.returncode == 0, r.stderr
    config = vm.ops.read_text(encoding="utf-8")
    assert "/var/lib/docker/containers/*/*-json.log" in config and "field: log" in config and "domhouse_engine" in config
    assert (vm.ops.parent / "config.yaml.before-domhouse").read_text(encoding="utf-8") == "# configurazione di prima\n"
    vm("logs-agent")                                                     # twice: the first copy is kept
    assert (vm.ops.parent / "config.yaml.before-domhouse").read_text(encoding="utf-8") == "# configurazione di prima\n"
    assert "restart google-cloud-ops-agent" in (vm.stubs / "systemctl.log").read_text(encoding="utf-8")


def test_the_daily_backup_writes_its_line(vm):
    import sqlite3
    db = vm.data / APT / "engine.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    sqlite3.connect(db).close()
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'logger -t domhouse-backup "backup ok ${apt} ${file}"' in script


def _connector(vm, name):
    path = vm.opt / f"{APT}.settings"
    path.write_text(path.read_text(encoding="utf-8").replace("CONNECTOR=simulated", f"CONNECTOR={name}"), encoding="utf-8", newline="\n")
    (vm.opt / "compose.broker.yaml").write_text("services: {}\n", encoding="utf-8", newline="\n")


def test_a_simulated_engine_stays_out_of_the_brokers_network(vm):
    (vm.opt / "compose.broker.yaml").write_text("services: {}\n", encoding="utf-8", newline="\n")
    assert vm("set", APT, "CONFIRM_ON_WATTS=30").returncode == 0
    assert "compose.broker.yaml" not in (vm.stubs / "docker.log").read_text(encoding="utf-8")


def test_an_engine_with_a_real_connector_joins_the_brokers_network(vm):
    _connector(vm, "shelly")
    assert vm("set", APT, "CONFIRM_ON_WATTS=30").returncode == 0
    assert "compose.broker.yaml" in (vm.stubs / "docker.log").read_text(encoding="utf-8")


def test_the_watch_calls_the_brokers_check_only_when_it_is_installed_and_after_the_summary(vm):
    assert "broker" not in vm("check-all").stdout
    (vm.opt / "_broker").mkdir()
    (vm.opt / "_broker" / "broker.settings").write_text("BROKER_IMAGE=x\n", encoding="utf-8", newline="\n")
    (vm.opt / "broker-vm.sh").write_text('echo "broker ok cert_days=50"\n', encoding="utf-8", newline="\n")
    out = vm("check-all").stdout
    assert out.index("domhouse-check: 1 motori") < out.index("broker ok cert_days=50")
    (vm.opt / "broker-vm.sh").write_text("exit 3\n", encoding="utf-8", newline="\n")
    done = vm("check-all")
    assert done.returncode == 0 and "broker down (controllo non riuscito)" in done.stdout


def test_d218_the_engines_are_reached_and_published_on_the_vms_internal_address_only(vm):
    """D-218: the ports go on the VM's internal address (ENGINE_BIND_IP, from the metadata server; here the tests' own),
    not on every interface; the watch, the waits and the api command call the engines there, never on 127.0.0.1."""
    assert vm("check-all").returncode == 0
    assert vm("api", APT, "GET", "/health").returncode == 0
    called = (vm.stubs / "curl.log").read_text(encoding="utf-8")
    assert "http://10.198.0.2:8100/api/v1/health" in called and "127.0.0.1" not in called
    assert vm("set", APT, "CONFIRM_ON_WATTS=30").returncode == 0                  # a restart: compose with the address
    assert "[ENGINE_BIND_IP=10.198.0.2]" in (vm.stubs / "docker.log").read_text(encoding="utf-8")
    compose = (ROOT / "engine" / "compose.yaml").read_text(encoding="utf-8")
    assert '- "${ENGINE_BIND_IP:?ENGINE_BIND_IP}:${PORT}:${PORT}"' in compose and '- "${PORT}:${PORT}"' not in compose


def test_d218_without_the_internal_address_nothing_is_started(vm):
    """The metadata server does not give the address (the stand-in curl answers something that is not one): the script
    stops before touching an engine, instead of publishing on an empty address."""
    done = vm("status", APT, bind="")
    assert done.returncode != 0 and "non leggo l'indirizzo interno della VM" in done.stderr, done.stderr
    log = (vm.stubs / "docker.log").read_text(encoding="utf-8") if (vm.stubs / "docker.log").exists() else ""
    assert "--env-file" not in log                        # only the start's «docker compose version»: no engine touched


# ---- lot 39: the broker account of a Shelly engine (D-221, D-223), the engines after a boot ---------------------------
MQTT_PASSWORD = "Pw-del-connector_0123456789abcdef"


def _secrets(vm, mqtt=MQTT_PASSWORD):
    (vm.stubs / f"secret-langbrain-api-key-{APT}").write_text("chiave-nuova-lunga-0001", encoding="utf-8", newline="")
    if mqtt is not None:
        (vm.stubs / f"secret-langbrain-shelly-{APT}").write_text(mqtt, encoding="utf-8", newline="")


def test_the_key_of_a_shelly_engine_brings_its_broker_account(vm):
    """CONNECTOR=shelly: the engine's env file gets, next to API_KEY, the variables of Youssouf's transport for the
    broker's internal door, the user <apartment_id>.connector and the password of langbrain-shelly-<apartment_id>.
    Nothing of the two secrets on screen."""
    _connector(vm, "shelly")
    _secrets(vm)
    done = vm("key", APT)
    assert done.returncode == 0, done.stderr
    assert vm.key.read_text(encoding="utf-8") == (
        "API_KEY=chiave-nuova-lunga-0001\nSHELLY_MQTT_HOST=172.30.83.2\nSHELLY_MQTT_PORT=1883\nSHELLY_MQTT_TLS=false\n"
        f"SHELLY_MQTT_USERNAME={APT}.connector\nSHELLY_MQTT_PASSWORD={MQTT_PASSWORD}\n")
    assert MQTT_PASSWORD not in done.stdout + done.stderr and "chiave-nuova" not in done.stdout + done.stderr
    assert "conto del connector sul broker" in done.stdout
    assert "up -d --force-recreate" in (vm.stubs / "docker.log").read_text(encoding="utf-8")


def test_the_key_of_a_simulated_engine_is_the_key_alone(vm):
    _secrets(vm)
    assert vm("key", APT).returncode == 0
    assert vm.key.read_text(encoding="utf-8") == "API_KEY=chiave-nuova-lunga-0001\n"
    assert "langbrain-shelly" not in (vm.stubs / "curl.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("mqtt, says", [
    (None, "segreto langbrain-shelly-apt-prova-01 non leggibile"),
    ("corta", "non ha la forma prevista"),
    ("password con spazi # e altro 0123456789", "non ha la forma prevista"),
])
def test_a_missing_or_strange_broker_password_leaves_the_key_file_as_it_was(vm, mqtt, says):
    _connector(vm, "shelly")
    _secrets(vm, mqtt)
    done = vm("key", APT)
    assert done.returncode != 0 and says in done.stderr, done.stderr
    assert vm.key.read_text(encoding="utf-8") == "API_KEY=chiave-di-prova-lunga\n"
    assert mqtt is None or mqtt not in done.stdout + done.stderr


def test_the_watch_starts_again_an_engine_whose_container_is_stopped(vm):
    """Docker never retries a container that failed to start (after a boot with the internal address late, the port
    cannot be bound): the watch starts it again and says so; a running one, or one it cannot read, is left alone."""
    (vm.stubs / "code-8100").write_text("000", encoding="utf-8")
    (vm.stubs / f"state-engine-{APT}").write_text("exited", encoding="utf-8")
    assert vm("check-all").returncode == 0
    syslog = (vm.stubs / "syslog.log").read_text(encoding="utf-8")
    assert f"-t domhouse-check engine silent {APT}" in syslog
    assert f"-t domhouse-check engine restarted {APT} (il contenitore era exited)" in syslog
    assert "up -d [ENGINE_BIND_IP=10.198.0.2]" in (vm.stubs / "docker.log").read_text(encoding="utf-8")
    assert "-n 9" in (vm.stubs / "flock.log").read_text(encoding="utf-8")            # never waits for the lock
    for state in ("running", "restarting", ""):
        (vm.stubs / "syslog.log").unlink()
        (vm.stubs / "docker.log").unlink()
        (vm.stubs / f"state-engine-{APT}").write_text(state, encoding="utf-8")
        vm("check-all")
        assert "restarted" not in (vm.stubs / "syslog.log").read_text(encoding="utf-8"), state
        assert " up -d" not in (vm.stubs / "docker.log").read_text(encoding="utf-8"), state


def test_the_watch_leaves_a_stopped_engine_alone_while_another_command_holds_the_lock(vm):
    """A restore stops the engine on purpose: while it holds the lock the watch only writes «silent»."""
    (vm.stubs / "code-8100").write_text("000", encoding="utf-8")
    (vm.stubs / f"state-engine-{APT}").write_text("exited", encoding="utf-8")
    (vm.stubs / "locked").write_text("", encoding="utf-8")
    assert vm("check-all").returncode == 0
    syslog = (vm.stubs / "syslog.log").read_text(encoding="utf-8")
    assert f"engine silent {APT}" in syslog and "restarted" not in syslog
    assert " up -d" not in (vm.stubs / "docker.log").read_text(encoding="utf-8")


def test_commands_that_stop_or_recreate_an_engine_take_the_lock(vm):
    assert vm("set", APT, "CONFIRM_ON_WATTS=30").returncode == 0
    assert vm("unset", APT, "CONFIRM_ON_WATTS").returncode == 0
    assert (vm.stubs / "flock.log").read_text(encoding="utf-8").splitlines() == ["9", "9"]   # waits (no -n)


def test_after_a_boot_start_all_waits_for_the_address_then_starts_what_is_down(vm):
    (vm.stubs / "addresses").write_text("2: ens4    inet 10.198.0.2/32 brd 10.198.0.2 scope global dynamic ens4\n",
                                         encoding="utf-8")
    (vm.opt / "apt-acceso.settings").write_text("APARTMENT_ID=apt-acceso\nPORT=8101\nCONNECTOR=simulated\n",
                                                 encoding="utf-8", newline="\n")
    (vm.stubs / f"state-engine-{APT}").write_text("exited", encoding="utf-8")
    (vm.stubs / "state-engine-apt-acceso").write_text("running", encoding="utf-8")
    done = vm("start-all")
    assert done.returncode == 0, done.stderr
    syslog = (vm.stubs / "syslog.log").read_text(encoding="utf-8")
    assert f"-t domhouse-check engine started {APT} (all'avvio della VM, il contenitore era exited)" in syslog
    assert "apt-acceso" not in syslog
    docker = (vm.stubs / "docker.log").read_text(encoding="utf-8")
    assert docker.count(" up -d") == 1 and "domhouse-apt-acceso" not in docker.replace("inspect", "")


def test_start_all_without_the_address_says_so_and_still_tries(vm):
    (vm.stubs / f"state-engine-{APT}").write_text("created", encoding="utf-8")
    cmd_env = "DOMHOUSE_ADDRESS_WAIT_S=0"
    done = vm("start-all", env=cmd_env)
    assert done.returncode == 0, done.stderr
    syslog = (vm.stubs / "syslog.log").read_text(encoding="utf-8")
    assert "engines start: indirizzo 10.198.0.2 non sulla scheda dopo 0 s" in syslog
    assert f"engine started {APT}" in syslog


def test_timers_also_installs_the_boot_unit_of_the_engines(vm):
    assert vm("timers").returncode == 0
    unit = (vm.units / "domhouse-engines-start.service").read_text(encoding="utf-8")
    assert "After=docker.service network-online.target" in unit and "engine-vm.sh start-all" in unit
    assert "WantedBy=multi-user.target" in unit
    assert "enable domhouse-engines-start.service" in (vm.stubs / "systemctl.log").read_text(encoding="utf-8")
