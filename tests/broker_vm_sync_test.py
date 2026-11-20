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
    # A2: the VM's lock (this PC has no flock); refuses when the test put a file "locked"
    "flock": '#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/flock.log"\n[ ! -f "$STUB_DIR/locked" ]\n',
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

    def run(*args, env=""):
        env_line = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}" DOMHOUSE_OPT="{posix(opt)}" '
                    f'DOMHOUSE_ETC="{posix(etc)}" DOMHOUSE_DATA="{posix(data)}" {env}; ')
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


# ---- A3 §6.4 (answer 1174): lab-01's migration, the VM's half --------------------------------------------------
H1 = "$7$1000$" + "A" * 16 + "$" + "B" * 86 + "=="
H2 = "$7$1000$" + "C" * 16 + "$" + "D" * 86 + "=="


def test_devices_from_auth_copies_the_apartments_fingerprints_and_syncs(vm):
    """The fingerprints the broker uses today become devices/<apt>: no password is read, the sync then changes
    nothing (same fingerprints). It prints them, for the copy into Firestore (fingerprints are not passwords)."""
    run, stubs, etc = vm
    auth = etc / "_broker" / "auth"
    (auth / "devices.passwd").write_text(f"apt-a.plug:{H1}\napt-a.shelly-1:{H2}\napt-b.x:{H1}\n", encoding="utf-8")
    (stubs / "sync-out").write_text("apt-a: connector e 2 dispositivi\nunchanged\n", encoding="utf-8")
    r = run("devices-from-auth", "apt-a")
    assert r.returncode == 0, r.stderr
    written = (etc / "_broker" / "devices" / "apt-a").read_text(encoding="utf-8")
    assert written == f"plug {H1}\nshelly-1 {H2}\n"
    assert f"plug {H1}" in r.stdout and "unchanged" in r.stdout
    again = run("devices-from-auth", "apt-a")                     # never over a file that is there
    assert again.returncode != 0 and "c'è già" in again.stderr


def test_devices_from_auth_refuses_an_apartment_without_devices(vm):
    run, stubs, etc = vm
    (etc / "_broker" / "auth" / "devices.passwd").write_text(f"apt-b.x:{H1}\n", encoding="utf-8")
    r = run("devices-from-auth", "apt-a")
    assert r.returncode != 0 and "nessun dispositivo" in r.stderr
    assert not (etc / "_broker" / "devices" / "apt-a").exists()


# ---- A2 (project §2.1, §6.1, §6.9): the lock of the VM, repeatable remove-apartment, the id's rule -----------------
def test_a2_remove_apartment_of_one_not_in_the_list_is_already_removed(vm):
    run, stubs, etc = vm
    devices = etc / "_broker" / "devices"
    devices.mkdir()
    (devices / "lab-09").write_text("", encoding="utf-8")
    r = run("remove-apartment", "lab-09")
    assert r.returncode == 0 and "già tolto" in r.stdout, r.stderr
    assert not (devices / "lab-09").exists()


def test_a2_changes_take_the_vms_lock_unless_the_executor_holds_it(vm):
    run, stubs, etc = vm
    (stubs / "sync-out").write_text("unchanged\n", encoding="utf-8")
    assert run("sync").returncode == 0
    assert "-w 600 8" in (stubs / "flock.log").read_text(encoding="utf-8")
    (stubs / "flock.log").unlink()
    assert run("sync", env="DOMHOUSE_LOCK_HELD=1").returncode == 0
    assert not (stubs / "flock.log").exists()
    (stubs / "locked").write_text("", encoding="utf-8")
    r = run("remove-apartment", "apt-a")
    assert r.returncode == 1 and "blocco della VM" in r.stderr
    assert (etc / "_broker" / "apartments").read_text(encoding="utf-8") == "apt-a\n"


@pytest.mark.parametrize("bad", ["Apt-A", "apt_a", "apt.a"])
def test_a2_an_id_out_of_the_rule_is_refused(vm, bad):
    run, _, _ = vm
    r = run("add-apartment", bad)
    assert r.returncode == 1 and "apartment_id non valido" in r.stderr


# ---- A5 (docs/proposta-a5.md §2 steps 1-2, answers 1210): refused logins per device, for the server ----------------
NOW = "1795194750"     # 2026-11-20T17:12:30Z: the current slot is 17:10 (not complete), the two reported 17:05 and 17:00


def _broker_log(*events: tuple[str, str, str]) -> str:
    """docker logs -t of the broker: for each (time, client id, door) a connection and its refusal. Door "out" is 8883,
    "in" the internal one (the container's own health check)."""
    lines, port = [], 40000
    for at, client, door in events:
        port += 1
        ip = f"203.0.113.{port % 7 + 1}:{port}"
        if door == "out":
            lines.append(f"2026-11-20T{at}.000000001Z 1795194000: New connection from {ip} on port 8883.")
        lines.append(f"2026-11-20T{at}.000000002Z 1795194000: Client {client} [{ip}] disconnected: not authorised.")
    return "\n".join(lines) + "\n"


def _registered(etc, *users: str) -> None:
    """The broker's users (A3), as broker_accounts.py writes them: «<apt>.<device>:<fingerprint>»."""
    (etc / "_broker" / "auth" / "devices.passwd").write_text("".join(f"{u}:{H1}\n" for u in users), encoding="utf-8",
                                                              newline="\n")


def _with_log(stubs, text: str) -> None:
    (stubs / "broker.log").write_text(text, encoding="utf-8", newline="\n")
    (stubs / "docker").write_text('#!/usr/bin/env bash\necho "$*" >> "$STUB_DIR/docker.log"\n'
                                  'if [ "$1" = logs ]; then cat "$STUB_DIR/broker.log"; fi\nexit 0\n',
                                  encoding="utf-8", newline="\n")


def test_a5_one_line_per_device_and_slot_without_addresses(vm):
    run, stubs, etc = vm
    _registered(etc, "apt-a.plug", "apt-a.shelly-1")
    _with_log(stubs, _broker_log(("17:06:10", "apt-a.plug", "out"), ("17:08:20", "apt-a.plug", "out"),
                                 ("17:01:00", "apt-a.plug", "out"), ("17:03:00", "apt-a.shelly-1", "out"),
                                 ("17:11:00", "apt-a.plug", "out"),          # current slot: next round
                                 ("16:58:00", "apt-a.plug", "out"),          # older than the two slots
                                 ("17:06:30", "apt-a.plug", "in"),           # the internal door
                                 ("17:06:40", "domhouse-check", "out")))     # check's own probe
    r = run("rifiuti", env=f"DOMHOUSE_NOW_EPOCH={NOW}")
    assert r.returncode == 0, r.stderr
    got = sorted(r.stdout.splitlines())
    assert got == sorted([
        "broker device refused apt=apt-a device=plug slot=2026-11-20T17:05:00Z count=2 last=2026-11-20T17:08:20Z",
        "broker device refused apt=apt-a device=plug slot=2026-11-20T17:00:00Z count=1 last=2026-11-20T17:01:00Z",
        "broker device refused apt=apt-a device=shelly-1 slot=2026-11-20T17:00:00Z count=1 last=2026-11-20T17:03:00Z",
    ]), r.stdout
    assert "203.0.113." not in r.stdout
    assert "--since" in (stubs / "docker.log").read_text(encoding="utf-8")


@pytest.mark.parametrize("client", ["apt-z.plug", "<script>x", "apt-a", "apt-a.Plug", "apt-a.a.b", "apt-a." + "x" * 65,
                                    ".plug"])
def test_a5_a_name_that_is_no_device_only_counts_as_other(vm, client):
    run, stubs, etc = vm
    _registered(etc, "apt-a.plug")
    _with_log(stubs, _broker_log(("17:06:10", client, "out"), ("17:06:20", client, "out")))
    r = run("rifiuti", env=f"DOMHOUSE_NOW_EPOCH={NOW}")
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["broker device refused other slot=2026-11-20T17:05:00Z count=2"], r.stdout
    assert client not in r.stdout or client == "apt-a"


def test_a5_lines_are_capped_and_the_rest_goes_to_other(vm):
    run, stubs, etc = vm
    _registered(etc, "apt-a.d1", "apt-a.d2")
    _with_log(stubs, _broker_log(("17:06:10", "apt-a.d1", "out"), ("17:06:20", "apt-a.d2", "out"),
                                 ("17:06:30", "apt-a.d2", "out"), ("17:06:40", "apt-z.x", "out")))
    r = run("rifiuti", env=f"DOMHOUSE_NOW_EPOCH={NOW} DOMHOUSE_AUTH_DEVICE_LINES=1")
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    devices = [x for x in lines if " device=" in x]
    other = [x for x in lines if " other " in x]
    assert len(devices) == 1 and len(other) == 1, lines
    shown = int(devices[0].split("count=")[1].split()[0])
    assert other[0] == f"broker device refused other slot=2026-11-20T17:05:00Z count={4 - shown}"


def test_a5_check_writes_the_device_lines_to_the_watch(vm):
    """check runs every 5 minutes: the lines go to syslog (tag domhouse-check), where the log view of A5 reads them."""
    text = (ROOT / "scripts" / "broker-vm.sh").read_text(encoding="utf-8")
    body = text[text.index("\ncheck() {"):]
    body = body[:body.index("\n}\n")]
    assert 'auth_refused_devices_report || watch_line "broker device refused error"' in body   # review A5, point 2
    assert 'watch_line "${line}"' in text[text.index("auth_refused_devices_report() {"):]


def test_a5_device_lines_do_not_fire_the_alert_of_many_refusals():
    """The alert «broker accessi rifiutati» (over 100 an hour on the whole VM) matches «broker auth refused»."""
    import json
    import re as _re
    policy = json.loads((ROOT / "scripts" / "monitoring" / "engine-alerts" / "broker-accessi-rifiutati.json").read_text(
        encoding="utf-8"))
    flt = policy["conditions"][0]["conditionMatchedLog"]["filter"]
    pattern = flt.split('jsonPayload.message=~"')[1].rsplit('"', 1)[0].replace("\\\\", "\\")
    for line in ("broker device refused apt=apt-a device=plug slot=2026-11-20T17:05:00Z count=2 last=2026-11-20T17:08:20Z",
                 "broker device refused other slot=2026-11-20T17:05:00Z count=2"):
        assert not _re.search(pattern, f"domhouse-check[42]: {line}"), line
    assert _re.search(pattern, "domhouse-check[42]: broker auth refused hour=101 top_ip=x(1) top_client=y(1)")


def test_a5_review_1_an_invented_device_of_a_listed_apartment_is_not_named(vm):
    """Review A5, point 1: only the broker's registered users are named; lab-01.x1…x500 cannot fill the 50 lines."""
    run, stubs, etc = vm
    _registered(etc, "apt-a.plug")
    _with_log(stubs, _broker_log(("17:06:10", "apt-a.plug", "out"),
                                 *((f"17:06:{20 + i:02d}", f"apt-a.x{i}", "out") for i in range(5))))
    r = run("rifiuti", env=f"DOMHOUSE_NOW_EPOCH={NOW} DOMHOUSE_AUTH_DEVICE_LINES=1")
    assert r.returncode == 0, r.stderr
    assert sorted(r.stdout.splitlines()) == [
        "broker device refused apt=apt-a device=plug slot=2026-11-20T17:05:00Z count=1 last=2026-11-20T17:06:10Z",
        "broker device refused other slot=2026-11-20T17:05:00Z count=5"], r.stdout
    assert "fingerprint" not in r.stdout and H1 not in r.stdout


@pytest.mark.parametrize("users", [None, ""])
def test_a5_review_1_without_users_nobody_is_named_and_it_is_an_error(vm, users):
    """Second reading of A5, point 2: no users file (or an empty one) is a failure, which check turns into «broker
    device refused error»: never a silent 0 on the page."""
    run, stubs, etc = vm
    if users is not None:
        (etc / "_broker" / "auth" / "devices.passwd").write_text(users, encoding="utf-8")
    _with_log(stubs, _broker_log(("17:06:10", "apt-a.plug", "out")))
    r = run("rifiuti", env=f"DOMHOUSE_NOW_EPOCH={NOW}")
    assert r.returncode != 0 and "utenti" in r.stderr
    assert "broker device refused apt=" not in r.stdout


def test_a5_review_2_a_failure_of_the_reading_is_an_exit_code_that_check_turns_into_one_line(vm):
    """Review A5, point 2: «rifiuti» fails when docker logs fails; check catches it with «broker device refused error»
    (never «broker down», never a line the sink keeps)."""
    run, stubs, etc = vm
    _registered(etc, "apt-a.plug")
    (stubs / "docker").write_text('#!/usr/bin/env bash\nif [ "$1" = logs ]; then echo boom >&2; exit 1; fi\nexit 0\n',
                                  encoding="utf-8", newline="\n")
    r = run("rifiuti", env=f"DOMHOUSE_NOW_EPOCH={NOW}")
    assert r.returncode != 0
    assert "broker device refused apt=" not in r.stdout


def test_a5_review_6_the_apartments_reach_awk_as_a_variable_not_through_filename(vm):
    text = (ROOT / "scripts" / "broker-vm.sh").read_text(encoding="utf-8")
    body = text[text.index("auth_refused_devices() {"):text.index("auth_refused_devices_report() {")]
    assert "FILENAME" not in body and '-v apts=' in body and '-v users=' in body
