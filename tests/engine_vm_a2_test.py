"""A2 (docs/proposta-a2.md §4.2 step 3, §4.3; docs/progetto-strumento-a-base.md §2.1, §3, §3.1, §8.2, §9.2):
scripts/engine-vm.sh for the agent's crea_motore and togli_motore.

- install --da-agente: ENV and the catalog as arguments, the image only by digest from our repository, the catalog in
  /etc mounted read only (compose.catalog.yaml), no timers and no Ops Agent, the lock left to the caller
  (DOMHOUSE_LOCK_HELD=1); exit 3 for a secret not readable, 4 for an engine not healthy.
- the rules for everyone: ids in lower case, normalised ports compared with the other engines, the anchored image,
  update without a sed on the image.
- remove: engine, settings, key, catalog and data away, each step skipped when done; never dev.
- env: the ENV line of an engine installed by hand.
The real script, run by bash with the stand-ins of tests/engine_vm_settings_test.py."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "engine-vm.sh"
_spec = importlib.util.spec_from_file_location("engine_vm_settings_test", ROOT / "tests" / "engine_vm_settings_test.py")
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

REPO = "europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine"
DIGEST = f"{REPO}@sha256:{'a' * 64}"
APT = "lab-09"
HELD = "DOMHOUSE_LOCK_HELD=1"


@pytest.fixture
def vm(tmp_path):
    run = base.make_vm(tmp_path)
    docker = run.stubs / "docker"                 # docker login reads the token from stdin, as the real one does
    docker.write_text(docker.read_text(encoding="utf-8").replace(
        "#!/usr/bin/env bash\n", '#!/usr/bin/env bash\nif [ "$1" = login ]; then cat > /dev/null; fi\n', 1),
        encoding="utf-8", newline="\n")
    etc = tmp_path / "etc"
    (run.opt / "compose.yaml").write_text("services: {}\n", encoding="utf-8")
    (run.opt / "compose.catalog.yaml").write_text("services: {}\n", encoding="utf-8")
    (run.stubs / f"secret-langbrain-api-key-{APT}").write_text("chiave-del-motore-lunga-abbastanza", encoding="utf-8")
    (run.stubs / f"secret-langbrain-shelly-{APT}").write_text("PasswordDelConnector_0123456789", encoding="utf-8")
    (etc / f"{APT}.catalog.yaml").write_text("rooms: []\ndevices: []\n", encoding="utf-8")
    run.etc = etc
    run.catalog = str(base.posix(etc / f"{APT}.catalog.yaml"))
    return run


def log(vm, name):
    path = vm.stubs / f"{name}.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def agent_install(vm, *, apt=APT, port="8150", image=DIGEST, connector="shelly", env="staging", catalog=None,
                  extra=HELD):
    return vm("install", "--da-agente", apt, port, image, connector, env, catalog or vm.catalog, env=extra)


def test_the_agents_install_writes_env_mounts_the_catalog_and_installs_no_timer(vm):
    r = agent_install(vm)
    assert r.returncode == 0, r.stderr
    settings = (vm.opt / f"{APT}.settings").read_text(encoding="utf-8")
    assert f"ENGINE_IMAGE={DIGEST}\n" in settings and "ENV=staging\n" in settings and "PORT=8150\n" in settings
    assert "CONNECTOR=shelly\n" in settings
    docker = log(vm, "docker")
    assert "compose.catalog.yaml" in docker and "up -d" in docker
    assert log(vm, "systemctl") == "" and not vm.ops.exists()               # no timers, no Ops Agent
    assert log(vm, "flock") == ""                                            # the executor holds the lock
    key = (vm.etc / f"{APT}.env").read_text(encoding="utf-8")
    assert "API_KEY=chiave-del-motore-lunga-abbastanza" in key and f"SHELLY_MQTT_USERNAME={APT}.connector" in key
    assert (vm.data / APT / "backup").is_dir()


@pytest.mark.parametrize("change, says", [
    ({"image": f"{REPO}:f4c6a20"}, "solo per digest"),
    ({"image": f"europe-west1-docker.pkg.dev/altro/x/engine@sha256:{'a' * 64}"}, "solo per digest"),
    ({"env": "prova"}, "ENV non valido"),
    ({"catalog": "/tmp/altro.yaml"}, "catalogo non valido"),
    ({"port": "08150"}, "porta non valida"),
    ({"port": "8100"}, "porta 8100 già di apt-prova-01"),
    ({"apt": "Lab-09"}, "apartment_id non valido"),
    ({"apt": "lab_09"}, "apartment_id non valido"),
])
def test_the_agents_install_refuses_and_writes_nothing(vm, change, says):
    r = agent_install(vm, **change)
    assert r.returncode == 1 and says in r.stderr, r.stderr
    assert not (vm.opt / f"{change.get('apt', APT)}.settings").exists()
    assert "up -d" not in log(vm, "docker")


def test_a_missing_catalog_is_refused(vm):
    (vm.etc / f"{APT}.catalog.yaml").unlink()
    r = agent_install(vm)
    assert r.returncode == 1 and "catalogo assente" in r.stderr


def test_a_secret_not_readable_is_exit_3_and_an_unhealthy_engine_exit_4(vm):
    (vm.stubs / f"secret-langbrain-shelly-{APT}").unlink()
    r = agent_install(vm)
    assert r.returncode == 3 and "non leggibile" in r.stderr, r.stderr
    (vm.stubs / f"secret-langbrain-shelly-{APT}").write_text("PasswordDelConnector_0123456789", encoding="utf-8")
    (vm.stubs / "unhealthy").write_text("", encoding="utf-8")
    r = agent_install(vm)
    assert r.returncode == 4, r.stderr


def test_without_the_held_lock_the_script_takes_it(vm):
    agent_install(vm, extra="")
    assert "600" in log(vm, "flock")


def test_by_hand_the_image_must_be_ours_and_update_never_seds_it(vm):
    r = vm("update", "apt-prova-01", "altro.registro/engine:1")
    assert r.returncode == 1 and "immagine non ammessa" in r.stderr
    r = vm("update", "apt-prova-01", f"{REPO}:f4c6a20")
    assert r.returncode == 0, r.stderr
    assert f"ENGINE_IMAGE={REPO}:f4c6a20\n" in (vm.opt / "apt-prova-01.settings").read_text(encoding="utf-8")
    text = SCRIPT.read_text(encoding="utf-8")
    assert 's#^ENGINE_IMAGE=' not in text
    assert '[ "${host}" = "${REGISTRY_HOST}" ]' in text                     # registry_login, the second defence


def test_an_engine_without_catalog_gets_no_catalog_mount(vm):
    (vm.stubs / "secret-langbrain-api-key-apt-prova-01").write_text("chiave-di-prova-lunga", encoding="utf-8")
    r = vm("key", "apt-prova-01")
    assert r.returncode == 0, r.stderr
    assert "compose.catalog.yaml" not in log(vm, "docker")


def test_remove_takes_everything_away_and_twice_is_fine(vm):
    assert agent_install(vm).returncode == 0
    (vm.data / APT / "engine.db").write_text("x", encoding="utf-8")
    r = vm("remove", APT, env=HELD)
    assert r.returncode == 0 and f"tolto {APT}" in r.stdout, r.stderr
    assert "down --remove-orphans" in log(vm, "docker")
    for gone in (vm.opt / f"{APT}.settings", vm.etc / f"{APT}.env", vm.etc / f"{APT}.catalog.yaml", vm.data / APT):
        assert not gone.exists(), gone
    r = vm("remove", APT, env=HELD)
    assert r.returncode == 0 and f"tolto {APT}" in r.stdout


def test_remove_never_touches_dev(vm):
    r = vm("remove", "dev")
    assert r.returncode == 1 and "dev non si toglie" in r.stderr


def test_env_writes_the_line_once(vm):
    r = vm("env", "apt-prova-01", "staging")
    assert r.returncode == 0, r.stderr
    vm("env", "apt-prova-01", "staging")
    assert (vm.opt / "apt-prova-01.settings").read_text(encoding="utf-8").count("ENV=staging\n") == 1
    assert vm("env", "apt-prova-01", "lab").returncode == 1
