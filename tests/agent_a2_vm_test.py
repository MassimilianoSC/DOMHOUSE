"""A2 (docs/proposta-a2.md §4.2, §4.3, §5.2; review points 4, 6, 8, 14, N3, N6): the executor's crea_motore and
togli_motore, with the programs replaced by a fake that does what engine-vm.sh and broker-vm.sh would do.

crea_motore: step 0 the checks (approved image only by digest from a root file read at every order, port of the
band free in the settings and in /proc/net/tcp*, capacity again, /data/<apt> absent, empty or with this apartment's
mark), step 1 «already there with the same parameters» only with the mark, 1b the mark first, 2 the empty catalog,
3 engine-vm.sh install --da-agente, 4 broker-vm.sh add-apartment; a failure takes back what this order made.
togli_motore: only with the mark (lab-01 and dev never); nothing there is «already removed»."""
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

K_ORD, K_RIS = bytes([0x51]) * 32, bytes([0x52]) * 32
READER_UID = 4242
REPO = "europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine"
DIGEST = f"{REPO}@sha256:{'b' * 64}"
APT = "lab-09"
TCP_HEADER = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"


def order(operazione="crea_motore", apartment=APT, seq=1, parametri=None) -> bytes:
    o = {"op_id": f"8b2f6a3e-4c1d-4e5f-9a0b-1c2d3e4f5a{seq:02d}", "operazione": operazione, "apartment_id": apartment,
         "seq": seq, "parametri": {"porta": 8150} if parametri is None and operazione == "crea_motore"
         else (parametri or {}), "ambiente": "staging", "richiesto_da": "Uk9TgS2vLmQ1",
         "firmato_at": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")}
    o["firma"] = comune.signature(K_ORD, o)
    return json.dumps(o).encode("utf-8")


class Vm:
    def __init__(self, tmp: Path):
        self.opt, self.state, self.etc, self.data, self.net = (tmp / n for n in ("opt", "state", "etc", "data", "net"))
        self.broker_etc = self.etc / "_broker"
        for d in (self.opt, self.state, self.etc, self.data, self.net, self.broker_etc):
            d.mkdir(parents=True, exist_ok=True)
        (self.broker_etc / "apartments").write_text("lab-01\n", encoding="utf-8")
        (self.net / "tcp").write_text(TCP_HEADER, encoding="utf-8")
        (self.net / "tcp6").write_text(TCP_HEADER, encoding="utf-8")
        self.meminfo = tmp / "meminfo"
        self.meminfo.write_text("MemTotal: 2014000 kB\nMemAvailable: 1200000 kB\n", encoding="utf-8")
        self.runs, self.logs, self.locks = [], [], 0
        self.codes = {"install": 0, "remove": 0, "add-apartment": 0, "remove-apartment": 0}
        self.approved = DIGEST
        config = esecutore.Config(ambiente="staging", condivisa=True, reader_uid=READER_UID, opt=self.opt,
                                  state=self.state, bind_ip="10.198.0.2", max_staging=4, meminfo=self.meminfo,
                                  broker_etc=self.broker_etc, etc=self.etc, data=self.data, proc_net=self.net)
        self.ex = esecutore.Esecutore(config, run=self.run, http_get=lambda *a, **k: (0, None), log=self.logs.append,
                                      keys=lambda name: {"ordini": [K_ORD], "risultati": [K_RIS]}[name],
                                      image=self.image, lock=self.lock)

    def image(self):
        if isinstance(self.approved, Exception):
            raise self.approved
        return self.approved

    def lock(self):
        vm = self

        class Held:
            def __enter__(self):
                vm.locks += 1

            def __exit__(self, *exc):
                return False
        return Held()

    def run(self, argv, env, timeout):
        """What the scripts would do, in the temporary folders."""
        self.runs.append((list(argv), dict(env)))
        what = argv[2]
        if what == "install":
            apt, port = argv[4], argv[5]
            assert (self.etc / f"{apt}.catalog.yaml").exists()            # step 2 before step 3
            if self.codes["install"] == 0:
                (self.opt / f"{apt}.settings").write_text(f"APARTMENT_ID={apt}\nPORT={port}\nENV=staging\n",
                                                          encoding="utf-8")
                (self.data / apt).mkdir(exist_ok=True)
                (self.data / apt / "engine.db").write_text("x", encoding="utf-8")
            return self.codes["install"], "install"
        if what == "remove":
            apt = argv[3]
            if self.codes["remove"] == 0:
                for f in (self.opt / f"{apt}.settings", self.etc / f"{apt}.catalog.yaml", self.etc / f"{apt}.env"):
                    f.unlink(missing_ok=True)
                if (self.data / apt).exists():
                    for f in (self.data / apt).iterdir():
                        f.unlink()
                    (self.data / apt).rmdir()
            return self.codes["remove"], "remove"
        if what in ("add-apartment", "remove-apartment"):
            apt = argv[3]
            known = (self.broker_etc / "apartments").read_text(encoding="utf-8").split()
            if self.codes[what] == 0:
                known = sorted(set(known) | {apt}) if what == "add-apartment" else [a for a in known if a != apt]
                (self.broker_etc / "apartments").write_text("".join(f"{a}\n" for a in known), encoding="utf-8")
            return self.codes[what], what
        return 0, ""

    def send(self, data: bytes) -> dict:
        return self.ex.handle(data, READER_UID)

    def steps(self):
        return [(argv[1].rsplit("/", 1)[-1].replace("\\", "/").rsplit("/", 1)[-1], argv[2]) for argv, _ in self.runs]


@pytest.fixture
def vm(tmp_path):
    return Vm(tmp_path)


# ---- crea_motore ------------------------------------------------------------------------------------------------
def test_crea_motore_marks_writes_the_catalog_installs_and_adds_to_the_broker(vm):
    out = vm.send(order())
    assert (out["esito"], out["codice"], out.get("dati")) == ("riuscito", "ok", {"porta": 8150, "immagine": DIGEST})
    mark = json.loads((vm.state / "creati" / APT).read_text(encoding="utf-8"))
    assert mark == {"porta": 8150, "immagine": DIGEST, "env": "staging"}
    assert (vm.etc / f"{APT}.catalog.yaml").read_text(encoding="utf-8") == "rooms: []\ndevices: []\n"
    assert vm.steps() == [("engine-vm.sh", "install"), ("broker-vm.sh", "add-apartment")]
    install, env = vm.runs[0]
    assert install[3:] == ["--da-agente", APT, "8150", DIGEST, "shelly", "staging", str(vm.etc / f"{APT}.catalog.yaml")]
    assert env == {"PATH": esecutore.CLEAN_ENV["PATH"], "DOCKER_CONFIG": str(vm.state / "docker"),
                   "DOMHOUSE_LOCK_HELD": "1"}
    assert vm.runs[1][0][3] == APT and vm.runs[1][1]["DOMHOUSE_LOCK_HELD"] == "1"
    assert vm.locks == 1


def test_crea_motore_again_with_the_same_parameters_completes_and_succeeds(vm):
    assert vm.send(order())["codice"] == "ok"
    out = vm.send(order(seq=2))
    assert (out["esito"], out["codice"]) == ("riuscito", "ok")             # own port, own data: not refused


@pytest.mark.parametrize("approved", [f"{REPO}:f4c6a20", ValueError("illeggibile"),
                                      f"altro.pkg.dev/x/engine@sha256:{'b' * 64}"])
def test_an_image_not_approved_by_digest_is_refused_and_nothing_is_written(vm, approved):
    vm.approved = approved
    out = vm.send(order())
    assert (out["esito"], out["codice"]) == ("rifiutato", "immagine_non_approvata")
    assert vm.runs == [] and not (vm.state / "creati" / APT).exists() and not (vm.etc / f"{APT}.catalog.yaml").exists()
    assert any("agent alarm codice=immagine_non_approvata" in line for line in vm.logs)


def test_a_port_of_another_engine_or_listening_is_porta_occupata(vm):
    (vm.opt / "lab-01.settings").write_text("APARTMENT_ID=lab-01\nPORT=8150\n", encoding="utf-8")
    assert vm.send(order())["codice"] == "porta_occupata"
    (vm.opt / "lab-01.settings").write_text("APARTMENT_ID=lab-01\nPORT=8169\n", encoding="utf-8")
    (vm.net / "tcp").write_text(TCP_HEADER + "   0: 0202C60A:1FD6 00000000:0000 0A 00000000:00000000 00:00000000 "
                                "00000000     0        0 1 1 0000000000000000 100 0 0 10 0\n", encoding="utf-8")
    assert vm.send(order(seq=2))["codice"] == "porta_occupata"             # 0x1FD6 = 8150, state 0A = listening
    (vm.net / "tcp").write_text(TCP_HEADER, encoding="utf-8")
    (vm.net / "tcp6").write_text(TCP_HEADER + "   0: 00000000000000000000000000000000:1FD6 "
                                 "00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0"
                                 "        0 1 1 0000000000000000 100 0 0 10 0\n", encoding="utf-8")
    assert vm.send(order(seq=3))["codice"] == "porta_occupata"
    (vm.net / "tcp6").write_text(TCP_HEADER + "   0: 00000000000000000000000000000000:1FD6 "
                                 "00000000000000000000000000000000:0000 01 00000000:00000000 00:00000000 00000000     0"
                                 "        0 1 1 0000000000000000 100 0 0 10 0\n", encoding="utf-8")
    assert vm.send(order(seq=4))["codice"] == "ok"                          # 01 = an established connection
    assert vm.runs and vm.steps()[0] == ("engine-vm.sh", "install")


def test_capacity_is_checked_again(vm):
    vm.meminfo.write_text("MemTotal: 2014000 kB\nMemAvailable: 500000 kB\n", encoding="utf-8")
    assert vm.send(order())["codice"] == "capienza_insufficiente"
    vm.meminfo.write_text("MemTotal: 2014000 kB\nMemAvailable: 1200000 kB\n", encoding="utf-8")
    for apt, port in (("dev", 8100), ("lab-01", 8169), ("lab-02", 8151), ("lab-03", 8152)):
        (vm.opt / f"{apt}.settings").write_text(f"APARTMENT_ID={apt}\nPORT={port}\n", encoding="utf-8")
    assert vm.send(order(seq=2))["codice"] == "staging_pieno"
    assert vm.runs == [] and not any("agent alarm codice=staging_pieno" in line for line in vm.logs)


def test_data_already_there_without_the_mark_is_dati_presenti(vm):
    (vm.data / APT).mkdir()
    (vm.data / APT / "engine.db").write_text("di qualcun altro", encoding="utf-8")
    assert vm.send(order())["codice"] == "dati_presenti"
    assert vm.runs == []


def test_an_apartment_not_made_by_the_agent_or_with_other_parameters_is_gia_esiste_diverso(vm):
    (vm.opt / f"{APT}.settings").write_text(f"APARTMENT_ID={APT}\nPORT=8150\n", encoding="utf-8")
    assert vm.send(order())["codice"] == "gia_esiste_diverso"               # no mark: like lab-01
    (vm.opt / f"{APT}.settings").unlink()
    assert vm.send(order(seq=2))["codice"] == "ok"
    assert vm.send(order(seq=3, parametri={"porta": 8151}))["codice"] == "gia_esiste_diverso"


@pytest.mark.parametrize("code, says", [(3, "segreto_illeggibile"), (4, "motore_non_sano"), (1, "errore_interno")])
def test_a_failed_install_takes_back_what_this_order_made(vm, code, says):
    vm.codes["install"] = code
    out = vm.send(order())
    assert (out["esito"], out["codice"]) == ("fallito", says)
    assert vm.steps() == [("engine-vm.sh", "install"), ("engine-vm.sh", "remove")]
    assert not (vm.state / "creati" / APT).exists() and not (vm.etc / f"{APT}.catalog.yaml").exists()


def test_a_broker_that_refuses_takes_back_the_engine_too(vm):
    vm.codes["add-apartment"] = 1
    out = vm.send(order())
    assert (out["esito"], out["codice"]) == ("fallito", "broker_fallito")
    assert vm.steps() == [("engine-vm.sh", "install"), ("broker-vm.sh", "add-apartment"),
                          ("broker-vm.sh", "remove-apartment"), ("engine-vm.sh", "remove")]
    assert not (vm.state / "creati" / APT).exists() and not (vm.opt / f"{APT}.settings").exists()


def test_a_takeback_that_fails_keeps_the_mark_for_togli_motore(vm):
    vm.codes["install"], vm.codes["remove"] = 4, 1
    assert vm.send(order())["codice"] == "motore_non_sano"
    assert (vm.state / "creati" / APT).exists()


# ---- togli_motore -----------------------------------------------------------------------------------------------
def test_togli_motore_removes_engine_and_broker_then_the_mark(vm):
    assert vm.send(order())["codice"] == "ok"
    vm.runs.clear()
    out = vm.send(order("togli_motore", seq=2))
    assert (out["esito"], out["codice"]) == ("riuscito", "ok")
    assert vm.steps() == [("engine-vm.sh", "remove"), ("broker-vm.sh", "remove-apartment")]
    assert not (vm.state / "creati" / APT).exists()
    assert (vm.state / "seq" / APT).read_text(encoding="utf-8").strip() == "2"           # the tombstone stays


def test_togli_motore_with_nothing_there_is_already_removed(vm):
    out = vm.send(order("togli_motore"))
    assert (out["esito"], out["codice"]) == ("riuscito", "ok") and vm.runs == []


def test_togli_motore_never_touches_what_the_agent_did_not_make(vm):
    (vm.opt / "lab-01.settings").write_text("APARTMENT_ID=lab-01\nPORT=8169\n", encoding="utf-8")
    out = vm.send(order("togli_motore", apartment="lab-01"))
    assert (out["esito"], out["codice"]) == ("rifiutato", "non_creato_da_agente") and vm.runs == []
    out = vm.send(order("togli_motore", apartment="dev"))
    assert out["codice"] == "dev_escluso" and vm.runs == []


def test_togli_motore_that_fails_keeps_the_mark(vm):
    assert vm.send(order())["codice"] == "ok"
    vm.codes["remove"] = 1
    out = vm.send(order("togli_motore", seq=2))
    assert (out["esito"], out["codice"]) == ("fallito", "errore_interno")
    assert (vm.state / "creati" / APT).exists()


# ---- the pieces -------------------------------------------------------------------------------------------------
def test_the_approved_image_file_is_one_digest_line(tmp_path):
    f = tmp_path / "agent-immagine-staging"
    f.write_text(DIGEST + "\n", encoding="utf-8")
    assert esecutore.read_image(f, check_owner=False) == DIGEST
    for bad in (f"{REPO}:f4c6a20\n", f"{DIGEST}\n{DIGEST}\n", ""):
        f.write_text(bad, encoding="utf-8")
        with pytest.raises(ValueError):
            esecutore.read_image(f, check_owner=False)


def test_the_codes_of_a2_are_known_to_both_sides():
    from bff import agent as server
    for code in ("capienza_insufficiente", "staging_pieno", "porta_occupata", "immagine_non_approvata",
                 "gia_esiste_diverso", "dati_presenti", "non_creato_da_agente", "segreto_illeggibile",
                 "motore_non_sano", "broker_fallito"):
        assert code in comune.CODES and code in server.CODES and server.MESSAGES[code]
    assert {"crea_motore", "togli_motore"} <= comune.EXECUTED


def test_the_executors_unit_opens_what_a2_writes():
    unit = (AGENT / "domhouse-agent-esecutore.service").read_text(encoding="utf-8")
    assert "\nReadWritePaths=/opt/domhouse /etc/domhouse /data\n" in unit
    assert "\nCapabilityBoundingSet=CAP_CHOWN CAP_DAC_OVERRIDE\n" in unit
    assert "\nProtectSystem=strict\n" in unit and "\nNoNewPrivileges=yes\n" in unit


def test_the_worst_crea_motore_ends_before_the_reader_stops_waiting():
    lettore = load("lettore", AGENT / "lettore.py")
    assert esecutore.WORST_CREATE_S + 60 < lettore.EXECUTOR_TIMEOUT_S


# ---- code review of A2 (20 November): points 2, 3, 4, 7, 8, 9 ---------------------------------------------------
@pytest.mark.parametrize("trace", ["broker", "env"])
def test_review4_an_apartment_with_traces_but_no_mark_is_gia_esiste_diverso(vm, trace):
    if trace == "broker":
        (vm.broker_etc / "apartments").write_text(f"lab-01\n{APT}\n", encoding="utf-8")
    else:
        (vm.etc / f"{APT}.env").write_text("API_KEY=x\n", encoding="utf-8")
    out = vm.send(order())
    assert (out["esito"], out["codice"]) == ("rifiutato", "gia_esiste_diverso") and vm.runs == []


def test_review4_an_empty_data_folder_alone_is_still_fine(vm):
    (vm.data / APT).mkdir()
    assert vm.send(order())["codice"] == "ok"


def test_review7_riprova_after_a_new_approved_image_updates_the_mark_when_no_engine_is_there(vm):
    vm.codes["install"] = 4
    assert vm.send(order())["codice"] == "motore_non_sano"
    vm.codes["install"], vm.codes["remove"] = 0, 0
    (vm.state / "creati").mkdir(exist_ok=True)
    old = f"{REPO}@sha256:{'e' * 64}"
    (vm.state / "creati" / APT).write_text(json.dumps({"porta": 8150, "immagine": old, "env": "staging"}),
                                           encoding="utf-8")         # left by an order with the image of before
    out = vm.send(order(seq=2))
    assert (out["esito"], out["codice"]) == ("riuscito", "ok")
    assert json.loads((vm.state / "creati" / APT).read_text(encoding="utf-8"))["immagine"] == DIGEST
    vm.approved = f"{REPO}@sha256:{'f' * 64}"                         # the engine is there now: no silent change
    assert vm.send(order(seq=3))["codice"] == "gia_esiste_diverso"


def test_review9_a_lock_that_does_not_come_is_a_failure_not_a_hang(vm):
    class Busy:
        def __enter__(self):
            raise TimeoutError("blocco della VM occupato")

        def __exit__(self, *exc):
            return False
    vm.ex.lock = lambda: Busy()
    out = vm.send(order())
    assert (out["esito"], out["codice"]) == ("fallito", "errore_interno") and vm.runs == []


def test_review3_a_program_past_its_time_is_stopped_with_its_children(tmp_path):
    import time as _time
    started = _time.monotonic()
    code, _ = esecutore.run_program([sys.executable, "-c", "import time; time.sleep(30)"], dict(esecutore.CLEAN_ENV),
                                    0.5)
    assert code == 127 and _time.monotonic() - started < 10


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="gruppi di processi: solo Linux (CI)")
def test_review3_on_linux_the_whole_group_is_killed(tmp_path):
    import os as _os
    import time as _time
    pid_file = tmp_path / "figlio"
    script = f"sleep 30 & echo $! > {pid_file}; wait"
    code, _ = esecutore.run_program(["/bin/bash", "-c", script], dict(esecutore.CLEAN_ENV), 1)
    assert code == 127
    child = int(pid_file.read_text().strip())
    _time.sleep(0.5)
    with pytest.raises(ProcessLookupError):
        _os.kill(child, 0)


def test_review2_8_the_unit_keeps_code_keys_and_configuration_read_only_and_has_room_for_docker():
    unit = (AGENT / "domhouse-agent-esecutore.service").read_text(encoding="utf-8")
    line = next(x for x in unit.splitlines() if x.startswith("ReadOnlyPaths="))
    for path in ("/opt/domhouse/agent", "/opt/domhouse/engine-vm.sh", "/opt/domhouse/broker-vm.sh",
                 "/opt/domhouse/broker_accounts.py", "-/opt/domhouse/compose.yaml", "-/opt/domhouse/compose.catalog.yaml",
                 "-/opt/domhouse/_broker", "/etc/domhouse/agent.conf", "-/etc/domhouse/agent-ordini.key",
                 "-/etc/domhouse/agent-risultati.key", "-/etc/domhouse/agent-immagine-staging",
                 "-/etc/domhouse/agent-immagine-prod", "-/data/_broker"):
        assert path in line.split("=", 1)[1].split(), path
    assert "\nMemoryMax=512M\n" in unit
