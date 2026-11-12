"""scripts/load/carico_vm.py (P-84): the temporary test engines on the VM, with Docker, the VM's memory, the engines'
answers and Secret Manager replaced by stand-ins. Proved: every test engine starts with its memory limit, a low CPU
weight, no restart, logs the Ops Agent does not read, on its port of the internal address, with the image of dev and
nothing written where the watch looks (/opt/domhouse); the apartments' engines take the key of Secret Manager, the
others a local one; no step above 75% of memory, the last step removed above 85%; the ports of the real engines are
never taken; pulisci leaves nothing; the dry run starts and removes nothing."""
import importlib.util
import itertools
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def vm(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("carico_vm", ROOT / "scripts" / "load" / "carico_vm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    opt, etc, data = tmp_path / "opt", tmp_path / "etc", tmp_path / "data"
    opt.mkdir()
    (opt / "dev.settings").write_text("APARTMENT_ID=dev\nPORT=8100\nCONNECTOR=simulated\n"
                                      "ENGINE_IMAGE=registro/engine:abc123\n", encoding="utf-8")
    for name, value in (("OPT", opt), ("ETC", etc), ("DATA", data)):
        monkeypatch.setattr(mod, name, str(value))
    monkeypatch.setattr(mod, "SAMPLE_S", 0.02)
    monkeypatch.setenv("CARICO_ROOT_CHECK", "0")
    monkeypatch.setenv("CARICO_BIND_IP", "10.0.0.9")

    containers: dict[str, list[str]] = {}
    calls: list[tuple] = []

    def docker(*args, check=True):
        calls.append(args)
        if args[0] == "run":
            containers[args[args.index("--name") + 1]] = list(args)
        elif args[0] == "rm":
            containers.pop(args[-1], None)
        elif args[0] == "ps":
            return "\n".join(sorted(containers))
        elif args[0] == "stats":
            return "\n".join(f"{n}\t34.5MiB / 150MiB\t0.50%" for n in sorted(containers)) + "\ndev-x\t1GiB / 2GiB\t1%"
        return ""
    monkeypatch.setattr(mod, "docker", docker)
    monkeypatch.setattr(mod, "health", lambda ip, port, timeout=5.0: (200, 0.01))
    monkeypatch.setattr(mod, "read_secret", lambda name: f"segreto-di-{name}")
    monkeypatch.setattr(mod, "cpu_times", lambda: (1000, 500, 0))
    memory = {"values": itertools.repeat(40)}
    monkeypatch.setattr(mod, "memory_pct", lambda: next(memory["values"]))

    class Commands(mod.Commands):
        def request(self, i, method, path, body=None):
            if method == "GET":
                return 200, {"devices": [{"device_id": "presa", "online": True, "capabilities": {"switch": {"on": False}}}]}
            return 202, {"status": "pending"}
    Commands.EVERY_S = 0.05
    monkeypatch.setattr(mod, "Commands", Commands)
    # The data folder goes to the container's user: os.chown is refused on Linux to a user that is not root (the CI),
    # and Windows has none. Recorded here, on both, and checked by the first test.
    owners: dict[str, tuple[int, int]] = {}
    monkeypatch.setattr(mod.os, "chown", lambda path, uid, gid: owners.__setitem__(str(path), (uid, gid)), raising=False)
    mod.test = {"opt": opt, "etc": etc, "data": data, "containers": containers, "calls": calls, "memory": memory,
                "owners": owners}
    monkeypatch.chdir(tmp_path)
    return mod


def test_prepare_starts_the_apartments_engines_protected_and_out_of_the_watchs_sight(vm, capsys):
    assert vm.main(["prepara", "2"]) == 0
    c = vm.test["containers"]
    assert sorted(c) == ["engine-carico-01", "engine-carico-02"]
    run = c["engine-carico-02"]
    for flag, value in (("--memory", "150m"), ("--memory-swap", "150m"), ("--cpu-shares", "128"), ("--restart", "no"),
                        ("--log-driver", "local"), ("--label", "domhouse.carico=1"), ("-p", "10.0.0.9:8151:8151")):
        assert run[run.index(flag) + 1] == value, flag
    assert run[-1] == "registro/engine:abc123" and "PORT=8151" in run and "CONNECTOR=simulated" in run
    assert f"{vm.test['data'] / 'carico-02'}:/data/carico-02" in run
    assert vm.test["owners"] == {str(vm.test["data"] / f"carico-0{i}"): (vm.ENGINE_UID, vm.ENGINE_UID) for i in (1, 2)}
    env_file = vm.test["etc"] / "carico-02.env"
    assert env_file.read_text(encoding="utf-8") == "API_KEY=segreto-di-langbrain-api-key-carico-02\n"
    assert sorted(p.name for p in vm.test["opt"].iterdir()) == ["dev.settings"]     # nothing the watch would read
    assert (vm.test["etc"] / "app-count").read_text(encoding="utf-8") == "2"
    assert "pronti 2 motori su 2" in capsys.readouterr().out


def test_no_step_above_75_percent_of_memory(vm):
    vm.test["memory"]["values"] = itertools.repeat(80)
    with pytest.raises(SystemExit):
        vm.main(["prepara", "3"])
    assert not any(a[0] == "run" for a in vm.test["calls"])


def test_the_ports_of_the_real_engines_are_never_taken(vm):
    (vm.test["opt"] / "lab-01.settings").write_text("APARTMENT_ID=lab-01\nPORT=8151\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        vm.main(["prepara", "2"])
    assert not any(a[0] == "run" for a in vm.test["calls"])


def test_steps_measure_rest_and_commands_with_local_keys_beyond_the_apartments(vm, capsys):
    assert vm.main(["prepara", "2"]) == 0
    assert vm.main(["gradini", "2,4", "--minuti", "0.01", "--assesto-s", "0"]) == 0
    out = capsys.readouterr().out
    assert sorted(vm.test["containers"]) == [f"engine-carico-0{i}" for i in range(1, 5)]
    local = (vm.test["etc"] / "carico-04.env").read_text(encoding="utf-8")
    assert local.startswith("API_KEY=") and "segreto-di" not in local and len(local.strip()) > 30
    assert "INIZIO della prova dei motori per VM" in out and "FINE della prova dei motori per VM" in out
    assert "- 4 motori, a riposo: memoria della VM 40 %" in out and "34,5 MiB per motore" in out
    assert "- 4 motori, con i comandi:" in out and "dev risponde in 0,010 s" in out
    assert len(list(Path(".").glob("risultati-motori-*.json"))) == 1


def test_above_85_percent_the_last_step_goes_at_once(vm, capsys):
    assert vm.main(["prepara", "2"]) == 0
    # the reads: the first line, the check before the step of 4 (50), the first sample of its measure (90)
    vm.test["memory"]["values"] = itertools.chain([50, 50, 90], itertools.repeat(50))
    assert vm.main(["gradini", "4,6", "--minuti", "0.01", "--assesto-s", "0"]) == 0
    out = capsys.readouterr().out
    assert sorted(vm.test["containers"]) == ["engine-carico-01", "engine-carico-02"]  # carico-03 and 04 removed
    assert "oltre l'85 %: tolgo subito l'ultimo gradino" in out and "FERMATO, memoria al 90 %" in out
    assert "gradino: 6 motori" not in out and "RIEPILOGO" in out


def test_a_step_is_not_started_above_75_percent_and_the_summary_still_comes(vm, capsys):
    assert vm.main(["prepara", "2"]) == 0
    containers = vm.test["containers"]
    # the VM's memory follows the engines: 80% from the third one on (between the two thresholds: measured, not removed)
    vm.test["memory"]["values"] = (80 if len(containers) >= 3 else 50 for _ in itertools.count())
    assert vm.main(["gradini", "3,5", "--minuti", "0.01", "--assesto-s", "0"]) == 0
    out = capsys.readouterr().out
    assert "gradino: 3 motori" in out and "non salgo a 5 motori" in out and "gradino: 5 motori" not in out
    assert sorted(vm.test["containers"]) == [f"engine-carico-0{i}" for i in (1, 2, 3)]
    assert out.index("RIEPILOGO") < out.rindex("- 3 motori, con i comandi")


def test_the_watch_during_the_people_test_writes_a_line_and_removes_every_test_engine_above_85(vm, capsys):
    assert vm.main(["prepara", "3"]) == 0
    assert vm.main(["osserva", "0.01"]) == 0
    out = capsys.readouterr().out
    assert "INIZIO dell'osservazione" in out and "- 3 motori, osservazione" in out and "FINE dell'osservazione" in out
    vm.test["memory"]["values"] = itertools.chain([90], itertools.repeat(40))
    assert vm.main(["osserva", "1"]) == 0
    assert vm.test["containers"] == {} and "FERMATO, memoria al 90 %" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        vm.main(["osserva", "500"])


def test_clean_leaves_no_engine_no_key_no_data(vm):
    assert vm.main(["prepara", "3"]) == 0
    assert vm.main(["pulisci"]) == 0
    assert vm.test["containers"] == {} and not vm.test["etc"].exists() and not vm.test["data"].exists()
    assert sorted(p.name for p in vm.test["opt"].iterdir()) == ["dev.settings"]


def test_the_dry_run_starts_and_removes_nothing(vm, monkeypatch, capsys):
    monkeypatch.setattr(vm, "DRY", True)
    assert vm.main(["prepara", "2"]) == 0
    assert vm.main(["pulisci"]) == 0
    assert not any(a[0] in ("run", "rm") for a in vm.test["calls"]) and not vm.test["etc"].exists()
    assert vm.test["owners"] == {}
    assert "(prova a secco) avvierei engine-carico-02 sulla porta 8151" in capsys.readouterr().out


def test_memory_and_engine_sizes_are_read_as_the_watch_reads_them(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("carico_vm2", ROOT / "scripts" / "load" / "carico_vm.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:        2000000 kB\nMemFree:  100 kB\nMemAvailable:    1360000 kB\n", encoding="utf-8")
    monkeypatch.setattr(mod, "MEMINFO", str(meminfo))
    assert mod.memory_pct() == 32
    monkeypatch.setattr(mod, "docker", lambda *a, check=True:
                        "engine-carico-01\t34.5MiB / 150MiB\t0.20%\nengine-dev\t1.1GiB / 1.9GiB\t3.5%\nx\ty")
    assert mod.stats_of_engines() == {"carico-01": (34.5, 0.2), "dev": (1.1 * 1024, 3.5)}
