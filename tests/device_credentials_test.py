"""A3 (docs/proposta-a3-server.md): the devices' credentials, the logic without input or output
(bff/device_credentials.py). The fingerprint is the broker's own format; the state is computed when read (§4.1, §4.2,
N1); the actions allowed per state are a table where every «no» has its code (§4.3, review point 10)."""
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bff import device_credentials as dc
from bff.repository.base import AgentOp

ROOT = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 11, 19, 20, 0, tzinfo=UTC)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def op(stato="inviato", minutes=1, operazione="aggiorna_broker", seq=5):
    created = (NOW - timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")
    return AgentOp(op_id="00000000-0000-4000-8000-000000000001", operazione=operazione, apartment_id="lab-01",
                   seq=seq, ambiente="staging", richiesto_da="uid1", stato=stato, creato_at=created)


def doc(azione=None, stato_salvato="attivo", pending_seq=5, version=3):
    return {"device_id": "shelly-1", "impronta": "$7$x" if stato_salvato == "attivo" else None,
            "stato_salvato": stato_salvato, "azione": azione, "pending_seq": pending_seq, "op_id": op().op_id,
            "version": version}


# ---- the password and its fingerprint -----------------------------------------------------------------------------
def test_the_fingerprint_is_the_brokers_own_and_the_agent_accepts_it():
    accounts = _load("dc_broker_accounts", ROOT / "scripts" / "broker_accounts.py")
    comune = _load("dc_agent_comune", ROOT / "scripts" / "agent" / "comune.py")
    password = dc.new_password()
    assert len(password) == 32 and accounts.check_password(password, "prova") == password
    stored = dc.hash_password(password)
    assert accounts.hash_matches(stored, password) and not accounts.hash_matches(stored, password + "x")
    assert comune.HASH_RE.fullmatch(stored)
    assert dc.hash_matches(accounts.hash_password(password), password)
    assert dc.ITERATIONS == accounts.ITERATIONS and dc.RESERVED_DEVICE == accounts.RESERVED_DEVICE
    assert dc.DEVICE_ID_RE.pattern == comune.DEVICE_ID_RE.pattern and dc.MAX_DEVICES == comune.MAX_DEVICES


@pytest.mark.parametrize("bad", ["Shelly-1", "-x", "", "a" * 65, "connector", None, 7, "a b"])
def test_a_device_id_is_refused_never_converted(bad):
    with pytest.raises(dc.DeviceError) as e:
        dc.check_device_id(bad)
    assert e.value.error == "invalid_device_id" and e.value.status == 422


# ---- the state, computed when read --------------------------------------------------------------------------------
def test_the_state_from_the_order_and_the_last_successful_update():
    assert dc.state_of(None, None, 0, NOW) is None
    assert dc.state_of(doc(), None, 0, NOW) == "pronto"
    assert dc.state_of(doc(stato_salvato="revocato"), None, 0, NOW) == "revocato"
    assert dc.state_of(doc("registra"), op(), 4, NOW) == "in_attesa"
    assert dc.state_of(doc("rigenera"), op(), 4, NOW) == "cambio_in_corso"
    assert dc.state_of(doc("revoca", "revocato"), op(), 4, NOW) == "revoca_in_corso"
    assert dc.state_of(doc("revoca", "revocato"), op(), 5, NOW) == "revocato"        # confirmed up to seq 5
    assert dc.state_of(doc("registra"), op(), 9, NOW) == "pronto"                    # a later full list confirms it
    assert dc.state_of(doc("registra"), op(minutes=21), 4, NOW) == "non_applicato"   # 20 minutes, no timer
    assert dc.state_of(doc("revoca", "revocato"), op("fallito"), 4, NOW) == "non_applicato"


def test_n1_only_a_successful_aggiorna_broker_confirms():
    """N1: «Prova l'agente» (stato) shares the sequence: its success never makes a revocation look applied."""
    assert dc.state_of(doc("revoca", "revocato"), op("riuscito", operazione="stato"), 4, NOW) == "non_applicato"
    assert dc.state_of(doc("revoca", "revocato"), op("riuscito"), 4, NOW) == "revocato"


def test_the_action_waiting_is_shown_only_while_it_waits():
    assert dc.shown_action(doc("rigenera"), "cambio_in_corso") == "rigenera"
    assert dc.shown_action(doc("rigenera"), "non_applicato") == "rigenera"
    assert dc.shown_action(doc("rigenera"), "pronto") is None


# ---- §4.3: the actions allowed, every «no» with its code ----------------------------------------------------------
@pytest.mark.parametrize("state, azione, action, answer", [
    ("in_attesa", "registra", "rigenera", None), ("in_attesa", "registra", "riprova", "invalid_state"),
    ("pronto", None, "registra", "already_registered"), ("pronto", None, "revoca", None),
    ("cambio_in_corso", "rigenera", "rigenera", "operation_in_progress"), ("cambio_in_corso", "rigenera", "revoca", None),
    ("revoca_in_corso", "revoca", "registra", "operation_in_progress"), ("revoca_in_corso", "revoca", "riprova", "operation_in_progress"),
    ("revocato", None, "rigenera", "invalid_state"), ("revocato", None, "registra", None),
    ("non_applicato", "rigenera", "rigenera", None), ("non_applicato", "registra", "riprova", None),
    # review point 10: a revocation not applied closes only with «Riprova»
    ("non_applicato", "revoca", "rigenera", "invalid_state"), ("non_applicato", "revoca", "revoca", "invalid_state"),
    ("non_applicato", "revoca", "riprova", None), ("non_applicato", "revoca", "registra", "already_registered"),
])
def test_the_table_of_section_4_3(state, azione, action, answer):
    d = doc(azione, "revocato" if azione == "revoca" or state == "revocato" else "attivo")
    if answer is None:
        dc.check_action(action, state, d)
    else:
        with pytest.raises(dc.DeviceError) as e:
            dc.check_action(action, state, d)
        assert e.value.error == answer


def test_every_state_has_every_action():
    for row in dc.TABLE.values():
        assert set(row) == set(dc.ACTIONS)
    assert set(dc.TABLE) == set(dc.STATES) | {"non_applicato_revoca"}


# ---- the change of one device -------------------------------------------------------------------------------------
def test_decide_checks_the_version_first_and_keeps_the_action_on_a_retry():
    with pytest.raises(dc.DeviceError) as e:
        dc.decide("rigenera", "shelly-1", 2, "$7$new", "uid2", NOW)(doc(), None, 0)
    assert e.value.error == "version_changed"
    retried = dc.decide("riprova", "shelly-1", 3, None, "uid2", NOW)(doc("revoca", "revocato"), op("fallito"), 4)
    assert retried["azione"] == "revoca" and retried["version"] == 4 and retried["impronta"] is None
    assert retried["updated_by"] == "uid2"


def test_decide_registers_again_a_revoked_device_and_refuses_a_living_one():
    again = dc.decide("registra", "shelly-1", None, "$7$new", "uid2", NOW)(doc(None, "revocato"), None, 0)
    assert (again["stato_salvato"], again["azione"], again["impronta"], again["version"]) == ("attivo", "registra", "$7$new", 4)
    with pytest.raises(dc.DeviceError) as e:
        dc.decide("registra", "shelly-1", None, "$7$new", "uid2", NOW)(doc(), None, 0)
    assert e.value.error == "already_registered"
    first = dc.decide("registra", "shelly-1", None, "$7$new", "uid2", NOW)(None, None, 0)
    assert first["version"] == 1 and first["device_id"] == "shelly-1"


def test_a_revocation_takes_the_fingerprint_away():
    gone = dc.decide("revoca", "shelly-1", 3, None, "uid2", NOW)(doc(), None, 0)
    assert gone["impronta"] is None and gone["stato_salvato"] == "revocato" and gone["revoked_at"]


def test_the_broker_list_is_complete_sorted_and_bounded():
    docs = [{"device_id": "b", "stato_salvato": "attivo", "impronta": "$7$b"},
            {"device_id": "a", "stato_salvato": "attivo", "impronta": "$7$a"},
            {"device_id": "c", "stato_salvato": "revocato", "impronta": None}]
    assert dc.broker_list(docs) == [{"id": "a", "impronta": "$7$a"}, {"id": "b", "impronta": "$7$b"}]
    many = [{"device_id": f"d{i:03d}", "stato_salvato": "attivo", "impronta": "$7$x"} for i in range(201)]
    with pytest.raises(dc.DeviceError) as e:
        dc.broker_list(many)
    assert e.value.error == "too_many_devices"


def test_the_canonical_form_does_not_depend_on_the_order_of_the_keys():
    assert dc.canonical({"b": 1, "a": "è"}) == dc.canonical({"a": "è", "b": 1}) == '{"a":"è","b":1}'.encode("utf-8")
