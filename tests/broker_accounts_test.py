"""scripts/broker_accounts.py and scripts/broker-secrets.sh, without Docker: what the broker's files contain, what a
malformed secret does, and that the PC's script never turns a failed read into a new version nor shows a password
(gcloud replaced by a stand-in that keeps the secrets in files). The broker's own acceptance of these hashes and
permissions is in tests/broker_container_test.py."""
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("broker_accounts", ROOT / "scripts" / "broker_accounts.py")
ba = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ba)
SCRIPT = ROOT / "scripts" / "broker-secrets.sh"
PASSWORD = "una-password-di-prova-abbastanza-lunga"


def _bash():
    run_spec = importlib.util.spec_from_file_location("run_tests", ROOT / "scripts" / "run_tests.py")
    mod = importlib.util.module_from_spec(run_spec)
    run_spec.loader.exec_module(mod)
    return mod.git_bash()


def posix(path: Path) -> str:
    s = path.as_posix()
    m = re.match(r"^([A-Za-z]):/(.*)$", s)
    return f"/{m.group(1).lower()}/{m.group(2)}" if m else s


def test_hash_in_the_brokers_format_and_verifiable():
    stored = ba.hash_password(PASSWORD)
    assert re.fullmatch(r"\$7\$1000\$[A-Za-z0-9+/=]{16}\$[A-Za-z0-9+/=]{88}", stored)
    assert ba.hash_matches(stored, PASSWORD) and not ba.hash_matches(stored, PASSWORD + "x")
    assert PASSWORD not in stored and ba.hash_password(PASSWORD) != stored


def test_files_give_each_account_only_its_own_topics(tmp_path):
    texts = ba.render({"apt-a": (PASSWORD, {"d1": PASSWORD}), "apt-b": (PASSWORD, {})}, tmp_path)
    assert set(texts) == set(ba.FILES)
    assert texts["devices.acl"] == "user apt-a.d1\ntopic readwrite apt-a/d1/#\ntopic write apt-a/connector/d1/rpc\n\n"   # D-215
    assert texts["connectors.acl"] == ("user apt-a.connector\ntopic readwrite apt-a/#\n\n"
                                       "user apt-b.connector\ntopic readwrite apt-b/#\n\n")
    assert [line.split(":")[0] for line in texts["connectors.passwd"].splitlines()] == ["apt-a.connector", "apt-b.connector"]
    assert not any(PASSWORD in text for text in texts.values())


def test_an_unchanged_password_keeps_its_line_and_a_changed_one_does_not(tmp_path):
    (tmp_path / "x").mkdir()
    auth = tmp_path / "x"
    first = ba.render({"a": (PASSWORD, {"d": PASSWORD})}, auth)
    assert ba.write_files(first, auth) is True
    assert ba.render({"a": (PASSWORD, {"d": PASSWORD})}, auth) == first
    assert ba.write_files(first, auth) is False
    changed = ba.render({"a": (PASSWORD, {"d": PASSWORD + "2"})}, auth)
    assert changed["devices.passwd"] != first["devices.passwd"] and changed["connectors.passwd"] == first["connectors.passwd"]


@pytest.mark.parametrize("text, part", [("{non json", "JSON"), ("[1]", "oggetto"), ('{"a/b": "' + PASSWORD + '"}', "device_id"),
                                        ('{"connector": "' + PASSWORD + '"}', "riservato"), ('{"d": "corta"}', "password"),
                                        ('{"d": "' + PASSWORD + ':x"}', "password"), ('{"d": 5}', "testo")])
def test_a_malformed_secret_is_refused_and_the_error_shows_no_password(text, part):
    with pytest.raises(ba.AccountError) as caught:
        ba.parse_devices(text, "nome-del-segreto")
    assert part in str(caught.value) and PASSWORD not in str(caught.value)


def test_ids_cannot_escape_their_topic_or_join_two_accounts():
    for bad in ("a/b", "a+", "#", "a.b", "", "a b", "$SYS", "x" * 65):
        with pytest.raises(ba.AccountError):
            ba.valid_id(bad, "id")


def test_editing_the_devices_secret():
    one = json.loads(ba.edit_devices("add", "d1", "{}"))
    assert list(one) == ["d1"] and len(one["d1"]) >= ba.MIN_PASSWORD
    text = json.dumps(one)
    with pytest.raises(ba.AccountError):
        ba.edit_devices("add", "d1", text)
    assert json.loads(ba.edit_devices("rotate", "d1", text))["d1"] != one["d1"]
    assert json.loads(ba.edit_devices("remove", "d1", text)) == {}
    with pytest.raises(ba.AccountError):
        ba.edit_devices("remove", "altro", text)


def test_sync_changes_nothing_if_a_secret_cannot_be_read(tmp_path, monkeypatch, capsys):
    auth = tmp_path / "auth"
    auth.mkdir()
    list_file = tmp_path / "apartments"
    list_file.write_text("apt-a\n", encoding="utf-8")
    (auth / "devices.passwd").write_text("apt-a.d1:$7$1000$x$y\n", encoding="utf-8")

    def get(url, headers):
        if url.endswith("/token"):
            return b'{"access_token": "t"}'
        if url.endswith("/project-id"):
            return b"p"
        raise OSError("404")
    monkeypatch.setattr(ba, "_get", get)
    assert ba.main(["sync", str(list_file), str(auth)]) == 1
    assert "non leggibile" in capsys.readouterr().err
    assert (auth / "devices.passwd").read_text(encoding="utf-8") == "apt-a.d1:$7$1000$x$y\n"
    assert not (auth / "devices.acl").exists()


GCLOUD = r"""#!/usr/bin/env bash
echo "$*" >> "$STUB_DIR/gcloud.log"
name=""
case "$*" in
  secrets\ describe*) [ -f "$STUB_DIR/s-$3" ] || [ -f "$STUB_DIR/c-$3" ]; exit $? ;;
  secrets\ create*) touch "$STUB_DIR/c-$3"; exit 0 ;;
  secrets\ versions\ list*) [ -f "$STUB_DIR/s-$4" ] && echo 1; exit 0 ;;
  secrets\ versions\ access*) secret="${5#--secret=}"; [ -f "$STUB_DIR/fail-read" ] && exit 1; cat "$STUB_DIR/s-$secret"; exit $? ;;
  secrets\ versions\ add*) cat > "$STUB_DIR/s-$4"; echo "${4}" >> "$STUB_DIR/added"; exit 0 ;;
  secrets\ add-iam*) exit 0 ;;
esac
exit 9
"""


@pytest.fixture
def pc(tmp_path):
    bash = _bash()
    if not bash:
        pytest.skip("bash non disponibile")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "gcloud").write_text(GCLOUD, encoding="utf-8", newline="\n")
    (stubs / "gcloud").chmod(0o755)

    def run(*args, dry=False):
        env = "DRY_RUN=1 " if dry else ""
        command = f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}"; {env}GCP_PROJECT_ID=p "{posix(SCRIPT)}" ' + " ".join(args)
        return subprocess.run([bash, "-c", command], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    run.stubs = stubs
    return run


def test_a_python3_that_is_no_python_is_passed_over(tmp_path):
    """The full run of 10 November: in a clean copy without .venv, `python3` in Git Bash was the Microsoft Store alias,
    found by command -v but no Python, and add-apartment stopped with «testo vuoto». The script, copied away from the
    repository's .venv, with such a python3 first in the PATH and a real python after it."""
    bash = _bash()
    if not bash:
        pytest.skip("bash non disponibile")
    alone = tmp_path / "copia" / "scripts"
    alone.mkdir(parents=True)
    for name in ("broker-secrets.sh", "broker_accounts.py"):
        shutil.copy(ROOT / "scripts" / name, alone / name)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name, body in (("gcloud", GCLOUD),
                       ("python3", '#!/usr/bin/env bash\necho "Python non è stato trovato; eseguire senza argomenti da '
                                   'installare dal Microsoft Store" >&2\nexit 9009\n'),
                       ("python", f'#!/usr/bin/env bash\nexec "{posix(Path(sys.executable))}" "$@"\n')):
        (stubs / name).write_text(body, encoding="utf-8", newline="\n")
        (stubs / name).chmod(0o755)
    command = (f'export PATH="{posix(stubs)}:$PATH" STUB_DIR="{posix(stubs)}"; '
               f'GCP_PROJECT_ID=p "{posix(alone / "broker-secrets.sh")}" add-apartment apt-a')
    done = subprocess.run([bash, "-c", command], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=90)
    assert done.returncode == 0, done.stderr
    assert len((stubs / "s-langbrain-shelly-apt-a").read_text(encoding="utf-8")) >= 32      # a real password, written


def secret(pc, name):
    return (pc.stubs / f"s-{name}").read_text(encoding="utf-8")


def added(pc):
    path = pc.stubs / "added"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_a_new_apartment_gets_both_secrets_in_europe_readable_by_the_vm(pc):
    done = pc("add-apartment", "apt-a")
    assert done.returncode == 0, done.stderr
    connector = secret(pc, "langbrain-shelly-apt-a")
    assert re.fullmatch(r"[A-Za-z0-9_-]{32}", connector) and secret(pc, "langbrain-shelly-apt-a-devices") == "{}"
    log = (pc.stubs / "gcloud.log").read_text(encoding="utf-8")
    assert "--locations=europe-west8" in log and "--replication-policy=user-managed" in log
    assert log.count("serviceAccount:langbrain-vm@p.iam.gserviceaccount.com") == 2
    assert connector not in log and connector not in done.stdout + done.stderr
    assert "broker-vm.sh add-apartment apt-a" in done.stdout


def test_running_it_twice_keeps_the_passwords(pc):
    pc("add-apartment", "apt-a")
    first = secret(pc, "langbrain-shelly-apt-a")
    assert pc("add-apartment", "apt-a").returncode == 0
    assert secret(pc, "langbrain-shelly-apt-a") == first and len(added(pc)) == 2


def test_adding_and_removing_a_device_never_shows_a_password(pc):
    pc("add-apartment", "apt-a")
    done = pc("add-device", "apt-a", "d1")
    assert done.returncode == 0, done.stderr
    devices = json.loads(secret(pc, "langbrain-shelly-apt-a-devices"))
    assert list(devices) == ["d1"]
    log = (pc.stubs / "gcloud.log").read_text(encoding="utf-8")
    assert devices["d1"] not in log and devices["d1"] not in done.stdout + done.stderr
    assert pc("remove-device", "apt-a", "d1").returncode == 0
    assert secret(pc, "langbrain-shelly-apt-a-devices") == "{}"


def test_a_failed_read_never_writes_a_version(pc):
    pc("add-apartment", "apt-a")
    pc("add-device", "apt-a", "d1")
    before, count = secret(pc, "langbrain-shelly-apt-a-devices"), len(added(pc))
    (pc.stubs / "fail-read").write_text("", encoding="utf-8")
    done = pc("add-device", "apt-a", "d2")
    assert done.returncode != 0 and "non leggibile" in done.stderr
    assert secret(pc, "langbrain-shelly-apt-a-devices") == before and len(added(pc)) == count


def test_an_invalid_edit_writes_nothing(pc):
    pc("add-apartment", "apt-a")
    pc("add-device", "apt-a", "d1")
    count = len(added(pc))
    done = pc("add-device", "apt-a", "d1")
    assert done.returncode != 0 and "esiste già" in done.stderr and len(added(pc)) == count


def test_dry_run_touches_nothing(pc):
    for args in (("add-apartment", "apt-a"), ("add-device", "apt-a", "d1"), ("rotate-connector", "apt-a")):
        assert pc(*args, dry=True).returncode == 0
    assert not (pc.stubs / "gcloud.log").exists()


@pytest.mark.parametrize("args", [("add-apartment", "a/b"), ("add-device", "apt-a", "x y"), ("add-device", "a#", "d")])
def test_a_bad_id_stops_before_gcloud(pc, args):
    assert pc(*[f'"{a}"' for a in args]).returncode != 0
    assert not (pc.stubs / "gcloud.log").exists()
