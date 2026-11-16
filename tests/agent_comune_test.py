"""Tool A, package A1 (docs/progetto-strumento-a-base.md §2.1, §3, §5): the rules the two services of the order
receiver share, scripts/agent/comune.py. The reader applies them to what Pub/Sub gives it; the executor applies them
again, without trusting the reader. Here: the order's schema and size, the closed list of operations, the ids and
prefixes per environment, «dev», the parameters of each operation, and the result sent back (codes only)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("agent_comune", ROOT / "scripts" / "agent" / "comune.py")
comune = importlib.util.module_from_spec(spec)
sys.modules["agent_comune"] = comune
spec.loader.exec_module(comune)

OP = "8b2f6a3e-4c1d-4e5f-9a0b-1c2d3e4f5a6b"
HASH = "$7$101$" + "A" * 16 + "$" + "B" * 86 + "=="


def order(**kw) -> dict:
    base = {"op_id": OP, "operazione": "stato", "apartment_id": "lab-01", "seq": 3, "parametri": {},
            "ambiente": "staging", "richiesto_da": "Uk9TgS2vLmQ1"}
    base.update(kw)
    return base


def raw(o) -> bytes:
    return json.dumps(o).encode("utf-8")


def code(o, ambiente="staging") -> str:
    with pytest.raises(comune.Refused) as refused:
        comune.check_order(raw(o) if isinstance(o, dict) else o, ambiente)
    return refused.value.code


def test_a_valid_order_comes_back_as_its_fields():
    o = comune.check_order(raw(order()), "staging")
    assert (o.op_id, o.operazione, o.apartment_id, o.seq, o.ambiente) == (OP, "stato", "lab-01", 3, "staging")
    assert o.parametri == {} and o.richiesto_da == "Uk9TgS2vLmQ1"


def test_the_closed_list_of_operations():
    assert comune.OPERATIONS == ("capienza", "crea_motore", "aggiorna_motore", "aggiorna_broker", "applica_catalogo",
                                 "stato", "togli_motore")
    assert comune.EXECUTED == {"stato", "capienza"}               # A1: the others come with their package
    assert code(order(operazione="cambia_password")) == "operazione_sconosciuta"
    assert code(order(operazione="sh -c id")) == "operazione_sconosciuta"


def test_size_and_shape():
    assert code(b"x" * (128 * 1024 + 1)) == "troppo_grande"
    assert code(b"{not json") == "json_non_valido"
    assert code(b"[1, 2]") == "json_non_valido"
    for field in ("op_id", "operazione", "apartment_id", "seq", "parametri", "ambiente", "richiesto_da"):
        o = order()
        o.pop(field)
        assert code(o) == "campo_mancante", field
    assert code(order(extra=1)) == "campo_non_valido"                # no free fields
    assert code(order(op_id="non-un-uuid")) == "campo_non_valido"
    assert code(order(seq=0)) == "campo_non_valido" and code(order(seq="3")) == "campo_non_valido"
    assert code(order(seq=True)) == "campo_non_valido"
    assert code(order(parametri=[])) == "campo_non_valido"


def test_who_asked_is_a_uid_never_an_email():
    assert code(order(richiesto_da="mario.rossi@example.com")) == "campo_non_valido"
    assert code(order(richiesto_da="")) == "campo_non_valido"


def test_the_environment_is_the_subscriptions():
    assert code(order(ambiente="prod"), ambiente="staging") == "ambiente_diverso"
    assert code(order(ambiente="sviluppo")) == "ambiente_diverso"


@pytest.mark.parametrize("apt", ["Lab-01", "lab_01", "lab.01", "lab-01-devices", "lab-", "-lab-01", "x" * 70,
                                 "../etc", "lab-01\n"])
def test_ids_outside_the_rule(apt):
    assert code(order(apartment_id=apt)) == "id_non_valido"


def test_prefixes_per_environment():
    assert code(order(apartment_id="a-k3f9x2qm")) == "prefisso_sbagliato"           # production's, on staging
    assert comune.check_order(raw(order(apartment_id="test-carico-01")), "staging").apartment_id == "test-carico-01"
    prod = order(apartment_id="a-k3f9x2qm", ambiente="prod")
    assert comune.check_order(raw(prod), "prod").apartment_id == "a-k3f9x2qm"
    assert code(order(apartment_id="lab-01", ambiente="prod"), ambiente="prod") == "prefisso_sbagliato"
    assert code(order(apartment_id="a-k3f9x2q", ambiente="prod"), ambiente="prod") == "id_non_valido"   # 7, not 8


def test_dev_only_for_stato():
    assert comune.check_order(raw(order(apartment_id="dev")), "staging").apartment_id == "dev"
    assert code(order(apartment_id="dev", operazione="togli_motore")) == "dev_escluso"
    assert code(order(apartment_id="dev", operazione="aggiorna_motore")) == "dev_escluso"


def test_capacity_has_no_apartment_and_no_sequence():
    o = comune.check_order(raw(order(operazione="capienza", apartment_id=None, seq=None)), "staging")
    assert (o.apartment_id, o.seq) == (None, None)
    assert code(order(operazione="capienza")) == "campo_non_valido"
    assert code(order(operazione="stato", apartment_id=None, seq=None)) == "campo_non_valido"


def test_the_parameters_of_each_operation():
    assert code(order(parametri={"porta": 8150})) == "parametri_non_validi"            # stato takes none
    ok = comune.check_order(raw(order(operazione="crea_motore", apartment_id="lab-02", parametri={"porta": 8151})),
                            "staging")
    assert ok.parametri == {"porta": 8151}
    for porta in (8149, 8160, 8169, "8150", 81500, True):
        assert code(order(operazione="crea_motore", apartment_id="lab-02", parametri={"porta": porta})) in (
            "porta_fuori_fascia", "parametri_non_validi"), porta
    prod = order(operazione="crea_motore", apartment_id="a-k3f9x2qm", ambiente="prod", parametri={"porta": 8101})
    assert comune.check_order(raw(prod), "prod").parametri == {"porta": 8101}
    assert code({**prod, "parametri": {"porta": 8150}}, ambiente="prod") == "porta_fuori_fascia"
    assert code(order(operazione="crea_motore", apartment_id="lab-02", parametri={"porta": 8151, "immagine": "x"})) \
        == "parametri_non_validi"                                                       # the image is never a parameter


def test_the_broker_list_takes_only_hashes():
    devices = [{"id": "shellyplugmg3-9070695cb0d0", "impronta": HASH}]
    ok = comune.check_order(raw(order(operazione="aggiorna_broker", parametri={"dispositivi": devices})), "staging")
    assert ok.parametri["dispositivi"] == devices
    assert comune.check_order(raw(order(operazione="aggiorna_broker", parametri={"dispositivi": []})), "staging")
    plain = [{"id": "shellyplugmg3-9070695cb0d0", "impronta": "unapasswordinchiaro"}]
    assert code(order(operazione="aggiorna_broker", parametri={"dispositivi": plain})) == "impronta_non_valida"
    bad_id = [{"id": "Shelly_Plug", "impronta": HASH}]
    assert code(order(operazione="aggiorna_broker", parametri={"dispositivi": bad_id})) == "id_non_valido"
    twice = devices * 2
    assert code(order(operazione="aggiorna_broker", parametri={"dispositivi": twice})) == "parametri_non_validi"
    many = [{"id": f"d{n}", "impronta": HASH} for n in range(201)]
    assert code(order(operazione="aggiorna_broker", parametri={"dispositivi": many})) == "troppi_dispositivi"
    extra = [{"id": "d1", "impronta": HASH, "password": "x"}]
    assert code(order(operazione="aggiorna_broker", parametri={"dispositivi": extra})) == "parametri_non_validi"


def test_the_catalog_has_a_size_and_a_version():
    ok = order(operazione="applica_catalogo", parametri={"catalogo": "rooms: []\ndevices: []\n", "versione": 2})
    assert comune.check_order(raw(ok), "staging").parametri["versione"] == 2
    big = order(operazione="applica_catalogo", parametri={"catalogo": "x" * (64 * 1024 + 1), "versione": 2})
    assert code(big) == "catalogo_troppo_grande"
    assert code(order(operazione="applica_catalogo", parametri={"catalogo": "", "versione": 0})) == "parametri_non_validi"


def test_the_image_rule_is_anchored():
    good = ["europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:247fda0",
            "europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine@sha256:" + "a" * 64]
    bad = ["evil.example/europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:247fda0",
           "europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:latest",
           "europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:247fda0\n",
           "europe-west8-docker.pkg.dev/domotica-poc-511707/domotica/engine:247fda0;id"]
    assert all(comune.valid_image(i) for i in good) and not any(comune.valid_image(i) for i in bad)


def test_a_result_carries_codes_only():
    o = comune.check_order(raw(order()), "staging")
    r = comune.result(o, "riuscito", "ok", {"health": 200, "immagine": "engine:247fda0"})
    assert r == {"op_id": OP, "operazione": "stato", "apartment_id": "lab-01", "ambiente": "staging", "seq": 3,
                 "esito": "riuscito", "codice": "ok", "dati": {"health": 200, "immagine": "engine:247fda0"}}
    with pytest.raises(ValueError):
        comune.result(o, "riuscito", "uscita dello script: ...")              # not a code of the list
    with pytest.raises(ValueError):
        comune.result(o, "andato", "ok")
    with pytest.raises(ValueError):
        comune.result(o, "riuscito", "ok", {"testo": "x" * 300})              # data: short values only
    assert len(json.dumps(comune.result(o, "fallito", "interrotto"))) < 1024
