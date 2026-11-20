"""A6 (docs/proposta-a6.md; bff/API.md «Eliminazione di un appartamento»; answers 1210): deactivate, wait 7 days,
delete with the name. In-process, memory repository, dev auth, the agent, Pub/Sub, Secret Manager and the engine's
check replaced as in tests/creation_test.py; the emails captured, never sent.

One state: «Disattiva» of the platform manager and «Attivo» switched off by the administrator both write enabled false,
disattivato_at and disattivato_da; the 7 days count from disattivato_at. An apartment made from the app goes through
togli_motore, then its secrets, then the database; one linked by hand or a demonstration loses only its document;
dev never."""
from datetime import timedelta

import pytest

from bff import deletion
from bff import secret_admin as sa
from bff.repository import get_repository
from bff.repository.base import Apartment
from bff.repository.seed import DEMO_TENANT
from tests.creation_test import ADMIN, PLATFORM, call, push, to_ready, world  # noqa: F401  (world is the fixture)

APT = "lab-a2-61"
BASE = f"/app/platform/tenants/{DEMO_TENANT}/apartments"


@pytest.fixture
def mails(monkeypatch):
    sent = []

    async def deliver(to, subject, text):
        sent.append({"to": to, "subject": subject, "text": text})
    monkeypatch.setattr(deletion, "_deliver", deliver)
    monkeypatch.setattr(deletion, "_mail_ready", lambda: True)
    get_repository().mail_counts.clear()
    yield sent
    get_repository().mail_counts.clear()


def row(apt=APT):
    items = call("GET", BASE).json()
    return next((i for i in items if i["apartment_id"] == apt), None)


def disattiva(apt=APT):
    return call("POST", f"{BASE}/{apt}/disattiva")


def elimina(apt=APT, nome=None):
    return call("POST", f"{BASE}/{apt}/elimina", json={"nome": f"Prova {apt}" if nome is None else nome})


def later(world, **delta):
    world.now = world.now + timedelta(**delta)


def ready_and_disabled(world, apt=APT, days=7):
    to_ready(world, apt)
    assert disattiva(apt).status_code == 200
    later(world, days=days, seconds=1)


def audit_actions():
    return [e.action for e in get_repository().audit.get(DEMO_TENANT, {}).values()]


def hand_linked(apt="lab-a2-m1", url="http://10.198.0.2", port=8101):
    get_repository().apartments[apt] = Apartment(apartment_id=apt, tenant_id=DEMO_TENANT, name=f"Prova {apt}",
                                                 instance_url=url, port=port)


# ---- the fields ---------------------------------------------------------------------------------------------------
def test_an_active_apartment_has_the_new_fields_empty(world, mails):
    to_ready(world, APT)
    r = row()
    assert (r["disattivato_at"], r["disattivato_da"], r["eliminabile_dal"], r["eliminazione"]) == (None, None, None, None)
    assert r["origine"] == "app"


def test_origine_of_hand_linked_demonstration_and_dev(world, mails):
    hand_linked()
    hand_linked("lab-a2-m2", url="mock://builtin", port=None)
    assert row("lab-a2-m1")["origine"] == "a_mano"
    assert row("lab-a2-m2")["origine"] == "dimostrativo"
    dev = next((a for a in get_repository().apartments.values() if a.apartment_id == "dev"), None)
    if dev is not None:
        items = call("GET", f"/app/platform/tenants/{dev.tenant_id}/apartments").json()
        assert next(i for i in items if i["apartment_id"] == "dev")["origine"] == "dev"
    assert deletion.origine(Apartment(apartment_id="dev", tenant_id="t", name="d", instance_url="http://x")) == "dev"


# ---- «Disattiva» and «Riattiva» -----------------------------------------------------------------------------------
def test_disattiva_writes_the_time_who_and_from_when_deletable(world, mails):
    to_ready(world, APT)
    r = disattiva()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["enabled"] is False and body["disattivato_at"]
    assert body["disattivato_da"]["ruolo"] == "gestore" and "@" not in str(body["disattivato_da"])
    at = deletion.parse(body["disattivato_at"])
    assert deletion.parse(body["eliminabile_dal"]) == at + timedelta(days=7)
    assert "apartment_disabled" in audit_actions()
    assert {m["to"] for m in mails} >= {"admin@demo.it", "piattaforma@demo.it"}
    assert all(APT in m["text"] and "@" not in m["subject"] for m in mails)
    assert disattiva().json()["error"] == "already_disabled"


def test_riattiva_clears_and_a_new_deactivation_counts_from_zero(world, mails):
    to_ready(world, APT)
    disattiva()
    later(world, days=6)
    r = call("POST", f"{BASE}/{APT}/riattiva")
    assert r.status_code == 200, r.text
    assert (r.json()["enabled"], r.json()["disattivato_at"], r.json()["eliminabile_dal"]) == (True, None, None)
    assert "apartment_reenabled" in audit_actions()
    assert call("POST", f"{BASE}/{APT}/riattiva").json()["error"] == "not_disabled"
    disattiva()
    later(world, days=2)
    assert elimina().json()["error"] == "too_early"


def test_the_administrators_attivo_reaches_the_same_state_and_mails_too(world, mails):
    to_ready(world, APT)
    r = call("PATCH", f"/app/admin/apartments/{APT}", headers=ADMIN, json={"enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["disattivato_da"]["ruolo"] == "amministratore" and "uid" not in r.json()["disattivato_da"]
    assert "eliminazione" not in r.json()
    assert row()["disattivato_at"] and row()["disattivato_da"]["ruolo"] == "amministratore"
    assert mails and "apartment_disabled" in audit_actions()
    sent = len(mails)
    call("PATCH", f"/app/admin/apartments/{APT}", headers=ADMIN, json={"enabled": False})    # no change: no mail
    assert len(mails) == sent
    r = call("PATCH", f"/app/admin/apartments/{APT}", headers=ADMIN, json={"enabled": True})
    assert r.status_code == 200 and r.json()["disattivato_at"] is None and row()["disattivato_da"] is None


def test_an_apartment_disabled_before_a6_starts_counting_at_disattiva(world, mails):
    to_ready(world, APT)
    get_repository().apartments[APT].enabled = False             # switched off before A6: no time
    assert row()["eliminabile_dal"] is None
    assert elimina().json()["error"] == "too_early"
    r = disattiva()
    assert r.status_code == 200 and r.json()["disattivato_at"]


# ---- the checks of «Elimina» ----------------------------------------------------------------------------------------
def test_elimina_refuses_in_order(world, mails):
    to_ready(world, APT)
    assert elimina().json()["error"] == "not_disabled"
    disattiva()
    r = elimina()
    assert r.status_code == 409 and r.json()["error"] == "too_early" and r.json()["details"]["eliminabile_dal"]
    later(world, days=7, seconds=1)
    for wrong in ("prova lab-a2-61", "Prova", "Prova lab-a2-61 "[:-2]):
        assert elimina(nome=wrong).json()["error"] == "name_mismatch"
    assert call("POST", f"{BASE}/nessuno/elimina", json={"nome": "x"}).status_code == 404
    assert elimina(nome="  Prova lab-a2-61  ").status_code == 202                # the spaces around do not count


def test_an_apartment_still_in_creation_is_cancelled_not_deleted(world, mails):
    assert call("POST", f"{BASE}/nuovo", json={"apartment_id": APT, "name": f"Prova {APT}",
                                               "timezone": "Europe/Rome"}).status_code == 202
    assert elimina().json()["error"] == "creation_not_ready"


def test_dev_is_never_deleted(world, mails):
    hand_linked("dev-a2-x")
    apt = get_repository().apartments.pop("dev-a2-x")
    apt.apartment_id = "dev"
    get_repository().apartments.setdefault("dev", apt)
    try:
        r = call("POST", f"/app/platform/tenants/{get_repository().apartments['dev'].tenant_id}/apartments/dev/elimina",
                 json={"nome": get_repository().apartments["dev"].name})
        assert r.status_code == 409 and r.json()["error"] == "not_deletable"
    finally:
        if get_repository().apartments.get("dev") is apt:
            get_repository().apartments.pop("dev")


def test_the_old_delete_route_never_skips_the_wait(world, mails):
    hand_linked()
    r = call("DELETE", f"{BASE}/lab-a2-m1")
    assert r.status_code == 409 and r.json()["error"] == "use_elimina"
    assert "lab-a2-m1" in get_repository().apartments


def test_two_deletions_a_day_per_organisation(world, mails):
    for apt in ("lab-a2-m1", "lab-a2-m2", "lab-a2-m3"):
        hand_linked(apt, port=8101 + int(apt[-1]))
        assert disattiva(apt).status_code == 200
    later(world, days=7, seconds=1)
    assert elimina("lab-a2-m1").status_code == 200
    assert elimina("lab-a2-m2").status_code == 200
    r = elimina("lab-a2-m3")
    assert r.status_code == 429 and r.json()["error"] == "rate_limited"
    assert r.json()["details"]["riprova_dal"] and int(r.headers["Retry-After"]) >= 1


# ---- the deletion of an apartment linked by hand ----------------------------------------------------------------
def test_hand_linked_loses_only_its_document_at_once(world, mails):
    hand_linked()
    disattiva("lab-a2-m1")
    later(world, days=7, seconds=1)
    sent, before = len(mails), len(world.published)
    r = elimina("lab-a2-m1")
    assert r.status_code == 200, r.text
    assert r.json()["eliminazione"]["stato"] == "eliminato"
    assert "lab-a2-m1" not in get_repository().apartments and "lab-a2-m1" in get_repository().used_apartment_ids
    assert len(world.published) == before                       # nothing to the VM
    assert len(mails) > sent and {"apartment_deletion_started", "apartment_deleted"} <= set(audit_actions())


# ---- the deletion of an apartment made from the app --------------------------------------------------------------
def test_engine_then_secrets_then_database(world, mails):
    ready_and_disabled(world)
    repo = get_repository()
    repo.device_creds[APT] = {"plug": {"device_id": "plug", "version": 1}}
    port = repo.apartments[APT].creazione.porta
    r = elimina()
    assert r.status_code == 202, r.text
    e = r.json()["eliminazione"]
    assert (e["stato"], e["passo"], e["op"]["operazione"]) == ("in_corso", "motore", "togli_motore")
    order = world.published[-1]
    assert order["operazione"] == "togli_motore" and order["apartment_id"] == APT
    assert row()["eliminazione"]["stato"] == "in_corso" and row()["eliminabile_dal"] is None
    assert call("POST", f"{BASE}/{APT}/riattiva").json()["error"] == "deletion_in_progress"
    assert call("PATCH", f"/app/admin/apartments/{APT}", headers=ADMIN, json={"enabled": True}).status_code == 409
    assert push(order).status_code == 204
    assert APT not in repo.apartments and APT in repo.used_apartment_ids
    key, conn = sa.names(APT)
    assert all(state == "DESTROY_PENDING" for _, state in world.secrets.versions[key] + world.secrets.versions[conn])
    assert not repo.device_creds.get(APT)
    assert not any(owner == APT for owner in repo.external_id_owners.values())
    assert f"link:10.198.0.2:{port}" not in repo.external_id_owners
    assert "apartment_deleted" in audit_actions()


def test_a_failed_togli_motore_is_retried(world, mails):
    ready_and_disabled(world)
    elimina()
    push(world.published[-1], esito="fallito", codice="errore_interno")
    e = call("GET", f"{BASE}/{APT}/eliminazione").json()["eliminazione"]
    assert (e["stato"], e["passo"], e["codice"]) == ("non_riuscita", "motore", "errore_interno") and e["messaggio"]
    assert "apartment_deletion_failed" in audit_actions()
    r = call("POST", f"{BASE}/{APT}/eliminazione/riprova", json={"version": e["version"]})
    assert r.status_code == 202, r.text
    assert call("POST", f"{BASE}/{APT}/eliminazione/riprova", json={"version": e["version"]}).status_code == 409
    push(world.published[-1])
    assert APT not in get_repository().apartments


def test_secrets_not_destroyed_stop_at_their_step_and_retry_without_the_vm(world, mails):
    ready_and_disabled(world)
    elimina()
    world.secrets.fail = "permesso negato"
    push(world.published[-1])
    e = call("GET", f"{BASE}/{APT}/eliminazione").json()["eliminazione"]
    assert (e["stato"], e["passo"], e["codice"]) == ("non_riuscita", "segreti", "chiavi_non_distrutte")
    world.secrets.fail = None
    sent = len(world.published)
    r = call("POST", f"{BASE}/{APT}/eliminazione/riprova", json={"version": e["version"]})
    assert r.status_code == 200 and r.json()["eliminazione"]["stato"] == "eliminato", r.text
    assert len(world.published) == sent and APT not in get_repository().apartments


def test_twenty_minutes_without_an_answer_read_as_not_done(world, mails):
    ready_and_disabled(world)
    elimina()
    later(world, minutes=21)
    e = call("GET", f"{BASE}/{APT}/eliminazione").json()["eliminazione"]
    assert (e["stato"], e["codice"]) == ("non_riuscita", "tempo_scaduto")


def test_a_late_success_still_closes_when_no_other_order_followed(world, mails):
    ready_and_disabled(world)
    elimina()
    order = world.published[-1]
    later(world, minutes=21)
    assert push(order).status_code == 204
    assert APT not in get_repository().apartments


def test_a_failed_publish_is_502_and_reads_not_sent(world, mails):
    ready_and_disabled(world)
    world.fail = True
    r = elimina()
    assert r.status_code == 502 and r.json()["error"] == "agent_publish_failed"
    world.fail = False
    e = call("GET", f"{BASE}/{APT}/eliminazione").json()["eliminazione"]
    assert (e["stato"], e["codice"]) == ("non_riuscita", "non_inviato")


def test_without_the_agent_an_app_apartment_is_not_touched(world, mails):
    ready_and_disabled(world)
    world.configure(agent_ordini_key="")
    r = elimina()
    assert r.status_code == 503 and r.json()["error"] == "agent_not_configured"
    assert row()["eliminazione"] is None


def test_only_the_platform_deletes(world, mails):
    ready_and_disabled(world)
    r = call("POST", f"{BASE}/{APT}/elimina", headers=ADMIN, json={"nome": f"Prova {APT}"})
    assert r.status_code == 403
    assert deletion.can_delete(type("I", (), {"platform_manager": True})())
