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
    "docker": '#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/docker.log"\nexit 0\n',
    # health: 200 unless the test put a file "unhealthy" (503) or "code-<port>" (that code) next to the stand-ins
    "curl": ('#!/usr/bin/env bash\n'
             'port=$(echo "$*" | grep -oE "127.0.0.1:[0-9]+" | cut -d: -f2)\n'
             'if [ -f "$STUB_DIR/code-$port" ]; then code=$(cat "$STUB_DIR/code-$port"); '
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

    def run(*args):
        cmd = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}" '
               f'DOMHOUSE_ETC="{posix(etc)}" DOMHOUSE_OPT="{posix(opt)}" DOMHOUSE_HEALTH_TRIES=2 '
               f'DOMHOUSE_DATA="{posix(data)}" DOMHOUSE_SYSTEMD="{posix(units)}" '
               f'DOMHOUSE_OPS_CONFIG="{posix(tmp_path / "ops" / "config.yaml")}"; '
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
    r = vm("set", APT, "CONFIRM_ON_WATTS=9999")
    assert r.returncode != 0 and "impostazione CONFIRM_ON_WATTS non applicata" in r.stderr
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
    fresh = backup / "engine-2026-10-21.db"
    fresh.write_text("x", encoding="utf-8")
    (vm.stubs / "syslog.log").unlink()
    vm("check-all")
    assert "backup missing" not in (vm.stubs / "syslog.log").read_text(encoding="utf-8")   # a new backup stops it


def test_timers_installs_the_backup_and_the_5_minute_watch(vm):
    r = vm("timers")
    assert r.returncode == 0, r.stderr
    timer = (vm.units / "domhouse-engine-check.timer").read_text(encoding="utf-8")
    service = (vm.units / "domhouse-engine-check.service").read_text(encoding="utf-8")
    assert "OnCalendar=*:0/5" in timer and "engine-vm.sh check-all" in service
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
