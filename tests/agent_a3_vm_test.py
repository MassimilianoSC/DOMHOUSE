"""A3 on the VM (docs/proposta-a3-server.md §6.1, §6.2, §6.4; review points 4, 12, N9; the bench measure of
19 November: the reload alone drops a revoked or changed device, so no restart).

- The executor runs aggiorna_broker: lab-01 only after its migration (a root mark), only an apartment the broker
  knows, the list written atomically to /etc/domhouse/_broker/devices/<apt> (root, 600), then broker-vm.sh sync; a
  sync that keeps the apartment's old lines (E-33 «kept») is a failure.
- broker_accounts.py takes an apartment's devices from that file, fingerprints as they are; the old «-devices» secret
  only for lab-01 (an explicit list); an apartment with no file has no devices.
- The executor's unit opens exactly what A3 needs: /etc/domhouse/_broker, CAP_CHOWN, the broker's group 1883.
- broker-vm.sh: auth/ is root:1883 750 (the executor, root without CAP_DAC_OVERRIDE, writes as the folder's owner and
  re-reads the files through the group), devices/ root 700, the file made before add-apartment and removed with
  remove-apartment.
"""
import importlib.util
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
AGENT = ROOT / "scripts" / "agent"
sys.path.insert(0, str(AGENT))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


comune = load("comune", AGENT / "comune.py")
esecutore = load("esecutore", AGENT / "esecutore.py")
ba = load("a3_broker_accounts", ROOT / "scripts" / "broker_accounts.py")

K_ORD, K_RIS = bytes([0x41]) * 32, bytes([0x42]) * 32
OP = "8b2f6a3e-4c1d-4e5f-9a0b-1c2d3e4f5a6b"
READER_UID = 4242
H1 = "$7$1000$" + "A" * 16 + "$" + "B" * 86 + "=="
H2 = "$7$1000$" + "C" * 16 + "$" + "D" * 86 + "=="
PASSWORD = "una-password-di-prova-lunga-0001"


def order(apartment="lab-07", seq=1, devices=None, **kw) -> bytes:
    o = {"op_id": OP, "operazione": "aggiorna_broker", "apartment_id": apartment, "seq": seq,
         "parametri": {"dispositivi": devices if devices is not None else [{"id": "shelly-1", "impronta": H1}]},
         "ambiente": "staging", "richiesto_da": "Uk9TgS2vLmQ1",
         "firmato_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")}
    o.update(kw)
    o["firma"] = comune.signature(K_ORD, o)
    return json.dumps(o).encode("utf-8")


class Vm:
    def __init__(self, tmp: Path, sync_answer=(0, "lab-07: connector e 1 dispositivi\nchanged\n")):
        self.opt, self.state, self.broker_etc = tmp / "opt", tmp / "state", tmp / "broker"
        for d in (self.opt, self.state, self.broker_etc):
            d.mkdir()
        (self.broker_etc / "apartments").write_text("lab-01\nlab-07\n", encoding="utf-8")
        meminfo = tmp / "meminfo"
        meminfo.write_text("MemTotal: 2014000 kB\nMemAvailable: 812000 kB\n", encoding="utf-8")
        self.runs, self.logs, self.sync_answer = [], [], sync_answer
        config = esecutore.Config(ambiente="staging", condivisa=True, reader_uid=READER_UID, opt=self.opt,
                                  state=self.state, bind_ip="10.198.0.2", max_staging=4, meminfo=meminfo,
                                  broker_etc=self.broker_etc)
        self.ex = esecutore.Esecutore(config, run=self.run, http_get=lambda *a, **k: (0, None), log=self.logs.append,
                                      keys=lambda name: {"ordini": [K_ORD], "risultati": [K_RIS]}[name])

    def run(self, argv, env, timeout):
        self.runs.append((list(argv), dict(env)))
        return self.sync_answer

    def send(self, data: bytes) -> dict:
        return self.ex.handle(data, READER_UID)


@pytest.fixture
def vm(tmp_path):
    return Vm(tmp_path)


# ---- the executor ---------------------------------------------------------------------------------------------------
def test_aggiorna_broker_writes_the_list_then_runs_the_sync(vm):
    out = vm.send(order(devices=[{"id": "shelly-2", "impronta": H2}, {"id": "shelly-1", "impronta": H1}]))
    assert (out["esito"], out["codice"], out.get("dati")) == ("riuscito", "ok", {"dispositivi": 2})
    written = (vm.broker_etc / "devices" / "lab-07").read_text(encoding="utf-8")
    assert written == f"shelly-1 {H1}\nshelly-2 {H2}\n"
    [(argv, env)] = vm.runs
    assert argv == ["/bin/bash", str(vm.opt / "broker-vm.sh"), "sync"]
    # 20 November, Q2.3c on the VM: under the unit ProtectHome hides /root/.docker, and without DOCKER_CONFIG
    # «docker compose» is not found: the sync gets the same DOCKER_CONFIG as docker inspect (state/docker)
    # A2: the executor holds the VM's lock for the whole order and tells the script (DOMHOUSE_LOCK_HELD)
    assert env == {"PATH": esecutore.CLEAN_ENV["PATH"], "DOCKER_CONFIG": str(vm.state / "docker"),
                   "DOMHOUSE_LOCK_HELD": "1"}
    if sys.platform.startswith("linux"):
        assert (vm.broker_etc / "devices" / "lab-07").stat().st_mode & 0o777 == 0o600


def test_an_empty_list_is_written_too(vm):
    assert vm.send(order(devices=[]))["codice"] == "ok"
    assert (vm.broker_etc / "devices" / "lab-07").read_text(encoding="utf-8") == ""


def test_lab_01_only_after_its_migration(vm):
    out = vm.send(order(apartment="lab-01"))
    assert (out["esito"], out["codice"]) == ("rifiutato", "migrazione_non_fatta") and vm.runs == []
    assert not (vm.broker_etc / "devices" / "lab-01").exists()
    (vm.state / "migrati").mkdir()
    (vm.state / "migrati" / "lab-01").write_text("", encoding="utf-8")
    assert vm.send(order(apartment="lab-01", seq=2))["codice"] == "ok"


def test_an_apartment_the_broker_does_not_know(vm):
    out = vm.send(order(apartment="lab-09"))
    assert (out["esito"], out["codice"]) == ("rifiutato", "appartamento_sconosciuto") and vm.runs == []


@pytest.mark.parametrize("answer", [(1, ""), (0, "kept lab-07\nlab-01: connector e 2 dispositivi\nunchanged\n")])
def test_a_sync_that_fails_or_keeps_the_apartment_is_a_failure(tmp_path, answer):
    vm = Vm(tmp_path, sync_answer=answer)
    out = vm.send(order())
    assert (out["esito"], out["codice"]) == ("fallito", "sync_fallito")


def test_the_codes_are_known_to_both_sides():
    from bff import agent
    for code in ("appartamento_sconosciuto", "sync_fallito", "migrazione_non_fatta"):
        assert code in comune.CODES and code in agent.CODES and agent.MESSAGES[code]


# ---- broker_accounts: the devices from the file of fingerprints -------------------------------------------------
def _secrets(readable):
    import base64

    def get(url, headers):
        if url.endswith("/token"):
            return b'{"access_token": "t"}'
        if url.endswith("/project-id"):
            return b"p"
        name = url.split("/secrets/")[1].split("/")[0]
        if name not in readable:
            raise OSError("404")
        return json.dumps({"payload": {"data": base64.b64encode(readable[name].encode()).decode()}}).encode()
    return get


@pytest.fixture
def broker(tmp_path):
    etc = tmp_path / "_broker"
    (etc / "auth").mkdir(parents=True)
    (etc / "devices").mkdir()
    (etc / "apartments").write_text("lab-01\nlab-07\nlab-08\n", encoding="utf-8")
    return etc


def test_the_devices_come_from_the_file_as_they_are(broker, monkeypatch, capsys):
    (broker / "devices" / "lab-07").write_text(f"shelly-1 {H1}\n", encoding="utf-8")
    monkeypatch.setattr(ba, "_get", _secrets({"langbrain-shelly-lab-01": PASSWORD,
                                              "langbrain-shelly-lab-01-devices": json.dumps({"plug": PASSWORD}),
                                              "langbrain-shelly-lab-07": PASSWORD,
                                              "langbrain-shelly-lab-07-devices": json.dumps({"vecchio": PASSWORD}),
                                              "langbrain-shelly-lab-08": PASSWORD}))
    assert ba.main(["sync", str(broker / "apartments"), str(broker / "auth")]) == 0
    devices = ba.read_passwd(broker / "auth" / "devices.passwd")
    assert devices["lab-07.shelly-1"] == H1                              # the fingerprint as it is
    assert "lab-07.vecchio" not in devices                               # the old secret is never read for lab-07
    assert ba.hash_matches(devices["lab-01.plug"], PASSWORD)             # lab-01: the old secret, until its migration
    assert not [u for u in devices if u.startswith("lab-08.")]           # no file: no devices
    out = capsys.readouterr().out.splitlines()
    assert not [line for line in out if line.startswith("kept")]
    # 20 November, Q6.1 on the VM: lab-01 with its file said «connector e 0 dispositivi» while it kept 3: the line
    # counts the devices that go to the broker, from the file or from the old secret
    assert "lab-07: connector e 1 dispositivi" in out and "lab-01: connector e 1 dispositivi" in out
    assert "lab-08: connector e 0 dispositivi" in out


def test_lab_01_with_its_file_leaves_the_old_secret(broker, monkeypatch):
    (broker / "devices" / "lab-01").write_text(f"plug {H2}\n", encoding="utf-8")
    monkeypatch.setattr(ba, "_get", _secrets({"langbrain-shelly-lab-01": PASSWORD, "langbrain-shelly-lab-07": PASSWORD,
                                              "langbrain-shelly-lab-08": PASSWORD}))
    assert ba.main(["sync", str(broker / "apartments"), str(broker / "auth")]) == 0
    assert ba.read_passwd(broker / "auth" / "devices.passwd")["lab-01.plug"] == H2


@pytest.mark.parametrize("line", [f"Shelly {H1}", "shelly-1 $7$non-valida", f"connector {H1}", f"a {H1} extra",
                                  f"a {H1}\na {H2}"])
def test_a_bad_file_keeps_the_apartments_lines(broker, monkeypatch, capsys, line):
    (broker / "auth" / "devices.passwd").write_text(f"lab-07.d1:{H2}\n", encoding="utf-8")
    (broker / "devices" / "lab-07").write_text(line + "\n", encoding="utf-8")
    monkeypatch.setattr(ba, "_get", _secrets({"langbrain-shelly-lab-01": PASSWORD,
                                              "langbrain-shelly-lab-01-devices": "{}",
                                              "langbrain-shelly-lab-07": PASSWORD, "langbrain-shelly-lab-08": PASSWORD}))
    assert ba.main(["sync", str(broker / "apartments"), str(broker / "auth")]) == 0
    assert "kept lab-07" in capsys.readouterr().out.splitlines()
    assert ba.read_passwd(broker / "auth" / "devices.passwd")["lab-07.d1"] == H2


# ---- the unit and broker-vm.sh ------------------------------------------------------------------------------------
def test_the_executor_unit_opens_exactly_what_a3_and_a2_need():
    unit = (AGENT / "domhouse-agent-esecutore.service").read_text(encoding="utf-8")
    # A2 (proposta §4.2, N3): /opt/domhouse, /etc/domhouse (it covers _broker) and /data; CAP_DAC_OVERRIDE declared
    for line in ("ProtectSystem=strict\n", "ReadWritePaths=/opt/domhouse /etc/domhouse /data\n",
                 "CapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE\n", "SupplementaryGroups=domhouse-broker\n",
                 "RestrictAddressFamilies=AF_UNIX AF_INET\n", "NoNewPrivileges=yes\n"):
        assert line in unit, line
    assert "CAP_FOWNER" not in unit and "CAP_SETUID" not in unit and "CAP_SYS_ADMIN" not in unit


def test_broker_vm_makes_auth_roots_with_the_brokers_group_and_the_devices_folder():
    script = (ROOT / "scripts" / "broker-vm.sh").read_text(encoding="utf-8")
    assert 'install -d -m 750 -o root -g "${BROKER_UID}" "${AUTH}"' in script
    assert 'install -d -m 700 "${DEVICES}"' in script
    add = script[script.index("  add-apartment)"):script.index("  remove-apartment)")]
    assert add.index('"${DEVICES}/$1"') < add.index("sync_accounts")             # the file before the sync
    remove = script[script.index("  remove-apartment)"):script.index("  sync)")]
    assert 'rm -f "${DEVICES}/$1"' in remove


# ---- code review of A3 (19 November, night): points 1, 2, 3 ---------------------------------------------------------
def test_review_1_a_normal_refusal_of_a3_raises_no_alarm(vm):
    """lab-01 before its migration and an apartment the broker does not know are normal: no R16 «compromised reader»."""
    assert vm.send(order(apartment="lab-01"))["codice"] == "migrazione_non_fatta"
    assert vm.send(order(apartment="lab-09", seq=2))["codice"] == "appartamento_sconosciuto"
    assert not [line for line in vm.logs if line.startswith("agent alarm")]


def test_review_2_a_lost_result_raises_the_vms_alarm():
    alarm = json.loads((AGENT / "allarmi" / "agente-allarme.json").read_text(encoding="utf-8"))
    log_filter = alarm["conditions"][0]["conditionMatchedLog"]["filter"]
    assert "fault publish" in log_filter
    lettore_src = (AGENT / "lettore.py").read_text(encoding="utf-8")
    assert "agent fault publish op_id=" in lettore_src                 # the line the filter must match


def test_review_3_connector_is_refused_in_the_orders_checks():
    with pytest.raises(comune.Refused) as e:
        comune.check_order(order(devices=[{"id": "connector", "impronta": H1}]), "staging")
    assert e.value.code == "id_non_valido"
