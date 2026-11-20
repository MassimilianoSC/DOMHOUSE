"""A7 (docs/proposta-a7.md; answers 1196-1202): the VM's capacity.

- The agent's «capienza» gives the real cap of the engine to create (120 MB in the staging, 256 MB in production),
  the sum of the caps of its environment's engines (ENGINE_MEM_LIMIT, or the default of engine-vm.sh) and the budget
  of the environment (BUDGET_MB_STAGING, 500; production: BUDGET_MB_PROD, absent until A10). The load test's engines
  (ports 8170-8199, «test-carico-»/«carico-») stay out (project §5.6).
- The rule, the same on the VM and in the server (a test keeps them equal): at most MAX_MOTORI_STAGING engines in the
  staging; after the new engine at least 400 MB available; the sum of the caps plus the new one within the budget
  (1196). Without a budget: refused (production until A10).
- The server keeps the last successful «capienza» per environment and shows it with the free places
  (GET /app/platform/capienza); «Aggiorna» asks a new one, at most every 30 s (1200)."""
import importlib.util
import itertools
import json
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from bff import capacity
from bff.repository import get_repository
from tests.creation_test import ROOM, call, new, push, world  # noqa: F401  (world is the fixture)

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
A7 = {"mem_available_mb": 1200, "motori": 2, "motori_staging": 2, "massimo_staging": 4, "motori_ambiente": 2,
      "tetto_nuovo_mb": 120, "somma_tetti_mb": 240, "budget_mb": 500}


# ---- the rule, the same on both sides ----------------------------------------------------------------------------
@pytest.mark.parametrize("change, problem", [
    ({}, None),
    ({"motori_ambiente": 4}, "staging_pieno"),
    ({"mem_available_mb": 519}, "capienza_insufficiente"),           # 519 - 120 < 400
    ({"mem_available_mb": 520}, None),
    ({"somma_tetti_mb": 381}, "capienza_insufficiente"),             # 381 + 120 > 500
    ({"somma_tetti_mb": 380}, None),
    ({"budget_mb": None}, "capienza_insufficiente"),                 # no budget: refused
])
def test_the_rule(change, problem):
    assert comune.room_problem({**A7, **change}, "staging") == problem
    assert capacity.room_problem({**A7, **change}, "staging") == problem


def test_the_rule_is_the_same_on_the_vm_and_in_the_server():
    grid = itertools.product((300, 519, 520, 2000), (0, 3, 4), (0, 380, 381, 1000), (None, 500), (120, 256),
                             ("staging", "prod"))
    for mem, n, somma, budget, tetto, env in grid:
        d = {**A7, "mem_available_mb": mem, "motori_ambiente": n, "somma_tetti_mb": somma, "budget_mb": budget,
             "tetto_nuovo_mb": tetto}
        assert comune.room_problem(d, env) == capacity.room_problem(d, env), d


def test_an_old_agent_without_the_new_fields_keeps_the_old_rule():
    old = {"mem_available_mb": 2000, "motori": 2, "motori_staging": 2, "massimo_staging": 4}
    assert capacity.room_problem(old, "staging") is None
    assert capacity.room_problem({**old, "mem_available_mb": 549}, "staging") == "capienza_insufficiente"
    assert capacity.room_problem({**old, "motori_staging": 4}, "staging") == "staging_pieno"


@pytest.mark.parametrize("change, places", [
    ({}, 2),                                                          # count 4-2=2, memory (1200-400)/120=6, budget 260/120=2
    ({"somma_tetti_mb": 380}, 1),
    ({"mem_available_mb": 640}, 2),
    ({"mem_available_mb": 639}, 1),
    ({"motori_ambiente": 4}, 0),
])
def test_the_free_places(change, places):
    assert capacity.free_places({**A7, **change}, "staging") == places


# ---- the agent's «capienza» ---------------------------------------------------------------------------------------
def make_executor(tmp_path, config_text="AMBIENTE=staging\n"):
    opt, state = tmp_path / "opt", tmp_path / "state"
    opt.mkdir()
    state.mkdir()
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 2014000 kB\nMemAvailable: 1228800 kB\n", encoding="utf-8")
    conf = tmp_path / "agent.conf"
    conf.write_text(config_text, encoding="utf-8")
    config = esecutore.read_config(conf, uid_of=lambda name: 4242, check_owner=False)
    config = config._replace(opt=opt, state=state, meminfo=meminfo)
    return esecutore.Esecutore(config, run=lambda *a: (0, ""), http_get=lambda *a, **k: (0, None), log=lambda line: None,
                               keys=lambda name: []), opt


def test_capienza_gives_caps_sum_and_budget_and_leaves_the_load_test_out(tmp_path):
    ex, opt = make_executor(tmp_path)
    for apt, port, extra in (("dev", 8100, ""), ("lab-01", 8169, "ENV=staging\n"), ("lab-02", 8150, "ENGINE_MEM_LIMIT=200m\n"),
                             ("a-k3f9x2qm", 8101, "ENV=prod\n"), ("test-carico-01", 8170, ""), ("carico-02", 8171, "")):
        (opt / f"{apt}.settings").write_text(f"APARTMENT_ID={apt}\nPORT={port}\n{extra}", encoding="utf-8")
    d = ex._capacity()
    assert d["mem_available_mb"] == 1200 and d["massimo_staging"] == 4 and d["budget_mb"] == 500
    assert (d["motori"], d["motori_staging"], d["motori_ambiente"]) == (4, 3, 3)
    assert (d["tetto_nuovo_mb"], d["somma_tetti_mb"]) == (120, 120 + 120 + 200)


def test_the_budget_and_production(tmp_path):
    ex, _ = make_executor(tmp_path, "AMBIENTE=staging\nBUDGET_MB_STAGING=480\n")
    assert ex._capacity()["budget_mb"] == 480
    (tmp_path / "p").mkdir()
    ex, _ = make_executor(tmp_path / "p", "AMBIENTE=prod\nCONDIVISA=0\n")
    d = ex._capacity()
    assert d["tetto_nuovo_mb"] == 256 and d["budget_mb"] is None
    assert comune.room_problem(d, "prod") == "capienza_insufficiente"       # until A10 sets a budget
    (tmp_path / "q").mkdir()
    with pytest.raises(ValueError):
        make_executor(tmp_path / "q", "AMBIENTE=staging\nBUDGET_MB_STAGING=0\n")


def test_crea_motore_uses_the_same_rule(tmp_path):
    ex, opt = make_executor(tmp_path)
    for apt, port in (("dev", 8100), ("lab-01", 8169), ("lab-02", 8151), ("lab-03", 8152)):
        (opt / f"{apt}.settings").write_text(f"APARTMENT_ID={apt}\nPORT={port}\nENGINE_MEM_LIMIT=100m\n", encoding="utf-8")
    assert comune.room_problem(ex._capacity(), "staging") == "staging_pieno"
    source = (AGENT / "esecutore.py").read_text(encoding="utf-8")
    create = source[source.index("def _create("):source.index("def _take_back(")]
    assert "comune.room_problem(" in create and "NEW_ENGINE_MB" not in create


# ---- the server -----------------------------------------------------------------------------------------------------
def test_without_a_reading_there_is_no_number(world):
    r = call("GET", "/app/platform/capienza")
    assert r.status_code == 200, r.text
    assert r.json() == {"capienza": None, "aggiornamento": None, "aggiornabile_dal": None}


def test_aggiorna_asks_capienza_and_the_result_is_kept_and_shown(world):
    r = call("POST", "/app/platform/capienza/aggiorna")
    assert r.status_code == 202, r.text
    [order] = world.published
    assert order["operazione"] == "capienza" and order["apartment_id"] is None
    body = r.json()
    assert body["aggiornamento"]["stato"] == "inviato" and body["capienza"] is None
    assert body["aggiornabile_dal"]
    again = call("POST", "/app/platform/capienza/aggiorna")
    assert again.status_code == 429 and again.json()["details"]["riprova_dal"] and again.headers["Retry-After"]
    push(order, dati=A7)
    c = call("GET", "/app/platform/capienza").json()
    assert c["aggiornamento"]["stato"] == "riuscito"
    cap = c["capienza"]
    assert (cap["ambiente"], cap["posti_liberi"], cap["motivo"], cap["vecchia"]) == ("staging", 2, None, False)
    assert (cap["tetto_nuovo_mb"], cap["somma_tetti_mb"], cap["budget_mb"], cap["massimo_motori"]) == (120, 240, 500, 4)
    world.now += timedelta(minutes=11)
    assert call("GET", "/app/platform/capienza").json()["capienza"]["vecchia"] is True
    assert call("POST", "/app/platform/capienza/aggiorna").status_code == 202       # 30 s passed


def test_a_full_vm_says_why_and_a_creation_s_capienza_is_kept_too(world):
    new()
    push(world.published[-1], dati={**A7, "motori_ambiente": 4})
    cap = call("GET", "/app/platform/capienza").json()["capienza"]
    assert (cap["posti_liberi"], cap["motivo"]) == (0, "staging_pieno")
    assert get_repository().apartments["lab-a2-01"].creazione.codice == "staging_pieno"   # the same rule stopped it


def test_the_creation_refuses_over_the_budget(world):
    new()
    push(world.published[-1], dati={**A7, "somma_tetti_mb": 400})
    r = call("GET", "/app/platform/tenants/t-flatsharing-demo/apartments/lab-a2-01/creazione").json()["creazione"]
    assert (r["stato"], r["codice"]) == ("non_creato", "capienza_insufficiente")


def test_only_where_creation_is_available_and_only_for_the_platform(world):
    assert call("GET", "/app/platform/capienza", headers={"X-Dev-User": "admin@demo.it"}).status_code == 403
    world.configure(agent_ambiente="prod")
    for method, path in (("GET", "/app/platform/capienza"), ("POST", "/app/platform/capienza/aggiorna")):
        r = call(method, path)
        assert (r.status_code, r.json()["error"]) == (503, "agent_not_configured"), path
    assert json.dumps(call("GET", "/app/me").json()["env"]["creazione_disponibile"]) == "false"


@pytest.fixture(autouse=True)
def no_reading_left():
    """The memory repository is shared by the whole run: every test starts without a reading."""
    get_repository().capacity.clear()
    yield
    get_repository().capacity.clear()


# ---- o2 (406e150): an unreadable capienza is not a full VM ------------------------------------------------------------
def test_an_unreadable_capienza_is_not_saved_and_the_refresh_says_it_failed(world):
    call("POST", "/app/platform/capienza/aggiorna")
    push(world.published[-1], dati=A7)                                     # a good reading first
    world.now += timedelta(seconds=31)
    call("POST", "/app/platform/capienza/aggiorna")
    push(world.published[-1], dati={"motori": 2})                          # then one without its numbers
    c = call("GET", "/app/platform/capienza").json()
    assert c["capienza"]["posti_liberi"] == 2 and c["capienza"]["motivo"] is None   # the last good one stays
    assert (c["aggiornamento"]["stato"], c["aggiornamento"]["codice"]) == ("fallito", "errore_interno")
    assert c["aggiornamento"]["messaggio"] == "La capienza letta non è valida: riprova"


# ---- code review of A7 (20 November): points 1 and 5 ----------------------------------------------------------------
def test_review1_a_load_test_name_on_the_apps_ports_is_counted(tmp_path):
    """Only the port (8170-8199) says «load test»: a test-carico-… made from the app on 8150-8159 counts."""
    ex, opt = make_executor(tmp_path)
    (opt / "test-carico-x.settings").write_text("APARTMENT_ID=test-carico-x\nPORT=8150\n", encoding="utf-8")
    (opt / "test-carico-01.settings").write_text("APARTMENT_ID=test-carico-01\nPORT=8170\n", encoding="utf-8")
    d = ex._capacity()
    assert (d["motori"], d["motori_ambiente"], d["somma_tetti_mb"]) == (1, 1, 120)


def test_review1_the_load_test_s_names_are_refused_by_the_creation_and_by_crea_motore(world):
    for bad in ("test-carico-1", "carico-02"):
        r = new(bad)
        assert (r.status_code, r.json()["error"]) == (422, "invalid_apartment_id"), bad
    source = (AGENT / "esecutore.py").read_text(encoding="utf-8")
    create = source[source.index("def _create("):source.index("def _take_back(")]
    assert 'LOAD_NAMES' in create


def test_review5_the_cap_is_read_like_engine_vm_sh_first_line_then_its_form(tmp_path):
    ex, opt = make_executor(tmp_path)
    (opt / "lab-05.settings").write_text("APARTMENT_ID=lab-05\nPORT=8150\nENGINE_MEM_LIMIT=tanto\nENGINE_MEM_LIMIT=200m\n",
                                         encoding="utf-8")
    assert ex._capacity()["somma_tetti_mb"] == 120          # engine-vm.sh: the first line, not valid -> the default
    (opt / "lab-05.settings").write_text("APARTMENT_ID=lab-05\nPORT=8150\nENGINE_MEM_LIMIT=200m\nENGINE_MEM_LIMIT=90m\n",
                                         encoding="utf-8")
    assert ex._capacity()["somma_tetti_mb"] == 200
