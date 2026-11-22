"""A2 (docs/proposta-a2.md §2, §4.1, §5, §6; docs/proposta-a2-sito.md §7): an apartment created from the app, in-process,
memory repository, dev auth, the agent configured with its keys, Pub/Sub, Secret Manager and the engine's check
replaced. The agent's results are pushed as the VM would (signed, with the order's fingerprint)."""
import asyncio
import base64
import dataclasses
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from bff import agent, creation, instances, secret_admin as sa
from bff.auth import require_platform
from bff.config import get_settings
from bff.main import app
from bff.repository import get_repository
from bff.repository.seed import DEMO_TENANT, OTHER_TENANT

K_ORD, K_RIS = bytes([0x41]) * 32, bytes([0x42]) * 32
PLATFORM = {"X-Dev-User": "piattaforma@demo.it"}
ADMIN = {"X-Dev-User": "admin@demo.it"}
SUBSCRIPTION = "projects/p/subscriptions/domhouse-staging-risultati-push"
NEW = f"/app/platform/tenants/{DEMO_TENANT}/apartments/nuovo"
ROOM = {"mem_available_mb": 2000, "motori": 2, "motori_staging": 2, "massimo_staging": 4}


class FakeSecrets:
    def __init__(self):
        self.secrets, self.versions, self.fail = {}, {}, None

    def create(self, secret_id, body):
        if self.fail:
            raise sa.SecretError(self.fail)
        if secret_id in self.secrets:
            raise sa.SecretExists(secret_id)
        self.secrets[secret_id] = sa.describe_body(body)
        self.versions[secret_id] = []

    def describe(self, secret_id):
        return dict(self.secrets[secret_id])

    def enabled_versions(self, secret_id):
        return [v for v, state in self.versions[secret_id] if state == "ENABLED"]

    def add_version(self, secret_id, data):
        self.versions[secret_id].append((f"{secret_id}/versions/{len(self.versions[secret_id]) + 1}", "ENABLED"))

    def live_versions(self, secret_id):
        return self.enabled_versions(secret_id) if secret_id in self.secrets else []

    def destroy(self, version):
        if self.fail:
            raise sa.SecretError(self.fail)
        for vs in self.versions.values():
            for i, (name, _) in enumerate(vs):
                if name == version:
                    vs[i] = (name, "DESTROY_PENDING")


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def world(monkeypatch):
    settings = dataclasses.replace(
        get_settings(), agent_ambiente="staging", agent_orders_topic="projects/p/topics/ordini",
        agent_push_audience="https://aud", agent_push_email="push@p.iam.gserviceaccount.com",
        agent_push_subscription=SUBSCRIPTION, agent_ordini_key=K_ORD.hex(), agent_risultati_key=K_RIS.hex())
    state = type("S", (), {"settings": settings, "published": [], "fail": False, "verify_ok": True,
                           "now": datetime.now(UTC), "secrets": FakeSecrets(), "verified": 0})()
    monkeypatch.setattr(agent, "get_settings", lambda: state.settings)
    monkeypatch.setattr(agent, "utcnow", lambda: state.now)

    def publish(topic, body, key):
        if state.fail:
            raise OSError("pubsub non risponde")
        state.published.append(json.loads(body))
    monkeypatch.setattr(agent, "publish", publish)

    async def yes(authorization):
        return True
    monkeypatch.setattr(agent, "authorised", yes)

    async def verify(apt, actor):
        state.verified += 1
        return {"ok": state.verify_ok, "error": None if state.verify_ok else "Sistema domotico non raggiungibile"}
    monkeypatch.setattr(instances, "verify", verify)
    sa.set_secret_admin(state.secrets)

    def configure(**changes):
        state.settings = dataclasses.replace(state.settings, **changes)
    state.configure = configure
    yield state
    sa.set_secret_admin(None)
    repo = get_repository()
    for apt_id in [a for a in repo.apartments if a.startswith(("lab-a2", "test-a2"))]:
        repo.apartments.pop(apt_id)
    repo.used_apartment_ids -= {a for a in repo.used_apartment_ids if a.startswith(("lab-a2", "test-a2"))}
    for key in [k for k in repo.external_id_owners if "10.198.0.2" in k]:
        repo.external_id_owners.pop(key)
    repo.creation_stamps.clear()
    for apt_id in [a for a in repo.agent_seq if a.startswith(("lab-a2", "test-a2"))]:
        repo.agent_seq.pop(apt_id)                   # the tombstones of this file only
    app.dependency_overrides.pop(require_platform, None)


async def _call(method, path, **kw):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, path, **kw)


def call(method, path, headers=PLATFORM, **kw):
    return run(_call(method, path, headers=headers, **kw))


def new(apt="lab-a2-01", tenant=DEMO_TENANT, **extra):
    return call("POST", f"/app/platform/tenants/{tenant}/apartments/nuovo",
                json={"apartment_id": apt, "name": f"Prova {apt}", "timezone": "Europe/Rome", **extra})


def creazione(apt="lab-a2-01", tenant=DEMO_TENANT):
    r = call("GET", f"/app/platform/tenants/{tenant}/apartments/{apt}/creazione")
    return r.json().get("creazione") if r.status_code == 200 else r.status_code


def act(action, apt="lab-a2-01", version=None, tenant=DEMO_TENANT):
    if version is None:
        version = creazione(apt, tenant)["version"]
    return call("POST", f"/app/platform/tenants/{tenant}/apartments/{apt}/creazione/{action}", json={"version": version})


def push(order, esito="riuscito", codice="ok", dati=None):
    result = {"op_id": order["op_id"], "operazione": order["operazione"], "apartment_id": order["apartment_id"],
              "ambiente": "staging", "seq": order["seq"], "esito": esito, "codice": codice,
              "ordine_sha256": agent.order_sha256(order)}
    if dati:
        result["dati"] = dati
    result["firma"] = agent.signature(K_RIS, result)
    body = {"message": {"data": base64.b64encode(json.dumps(result).encode()).decode(), "messageId": "1"},
            "subscription": SUBSCRIPTION}
    return run(_call("POST", "/internal/agent/risultati", json=body, headers={"Authorization": "Bearer x"}))


def to_ready(world, apt="lab-a2-01"):
    assert new(apt).status_code == 202
    push(world.published[-1], dati=ROOM)
    push(world.published[-1])
    return creazione(apt)


# ---- the whole way ----------------------------------------------------------------------------------------------
def test_from_new_to_pronto_with_the_three_orders_signed(world):
    r = new()
    assert r.status_code == 202, r.text
    body = r.json()
    c = body["creazione"]
    assert (c["stato"], c["passo"], c["porta"], c["fatti"]) == ("in_preparazione", "capienza", 8150,
                                                               ["id", "porta", "segreti"])
    assert body["apartment"]["creazione"] == c and body["apartment"]["enabled"] is False
    key, conn = sa.names("lab-a2-01")
    assert len(world.secrets.versions[key]) == 1 and len(world.secrets.versions[conn]) == 1
    assert world.secrets.secrets[key]["labels"]["domhouse-apt"] == "lab-a2-01"
    [order] = world.published
    assert order["operazione"] == "capienza" and order["apartment_id"] is None and agent.signed_by([K_ORD], order)
    assert c["op"]["op_id"] == order["op_id"] and c["op"]["stato"] == "inviato"
    assert push(order, dati=ROOM).status_code == 204
    crea = world.published[-1]
    assert crea["operazione"] == "crea_motore" and crea["parametri"] == {"porta": 8150} and crea["seq"] == 1
    assert creazione()["passo"] == "motore"
    assert push(crea).status_code == 204
    c = creazione()
    assert (c["stato"], c["passo"], c["codice"]) == ("pronto", "collegamento", None)
    assert set(c["fatti"]) == {"id", "porta", "segreti", "motore", "broker"} and world.verified == 1
    apt = get_repository().apartments["lab-a2-01"]
    assert (apt.instance_url, apt.port, apt.enabled) == ("http://10.198.0.2", 8150, True)
    rows = get_repository().audit[DEMO_TENANT]
    assert any(e.action == "apartment_created" for e in rows.values())


def test_not_ready_is_invisible_to_the_organisation_and_visible_to_the_platform(world):
    new()
    admin_list = call("GET", "/app/admin/apartments", headers=ADMIN).json()
    assert "lab-a2-01" not in [a["apartment_id"] for a in admin_list]
    assert call("GET", "/app/apartments/lab-a2-01", headers=ADMIN).status_code == 404
    assert call("PATCH", "/app/admin/apartments/lab-a2-01", headers=ADMIN, json={"name": "x"}).status_code == 404
    rows = call("GET", f"/app/platform/tenants/{DEMO_TENANT}/apartments").json()
    mine = next(r for r in rows if r["apartment_id"] == "lab-a2-01")
    assert mine["creazione"]["stato"] == "in_preparazione"
    assert all(r["creazione"] is None for r in rows if r["apartment_id"] != "lab-a2-01")    # linked by hand
    push(world.published[-1], dati=ROOM)
    push(world.published[-1])
    admin_list = call("GET", "/app/admin/apartments", headers=ADMIN).json()
    assert "lab-a2-01" in [a["apartment_id"] for a in admin_list]


def test_the_fields_the_site_reads(world):
    assert call("GET", "/app/me").json()["env"]["creazione_disponibile"] is True
    new()
    push(world.published[-1], esito="rifiutato", codice="capienza_insufficiente")
    new("lab-a2-02")
    tenants = {t["tenant_id"]: t for t in call("GET", "/app/platform/tenants").json()}
    assert (tenants[DEMO_TENANT]["appartamenti_non_creati"], tenants[DEMO_TENANT]["appartamenti_in_preparazione"]) \
        == (1, 1)
    assert (tenants[OTHER_TENANT]["appartamenti_non_creati"], tenants[OTHER_TENANT]["appartamenti_in_preparazione"]) \
        == (0, 0)
    detail = call("GET", f"/app/platform/tenants/{DEMO_TENANT}").json()
    assert detail["creazioni_ultima_ora"] == {"usate": 2, "limite": 5, "libera_dal": None}
    world.configure(agent_ambiente="")
    assert call("GET", "/app/me").json()["env"]["creazione_disponibile"] is False


# ---- the checks of the call ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ["apt-x", "dev", "lab-01-devices", "LAB-02", "lab_02", "lab-", "a-k3f9x2qm"])
def test_an_id_out_of_the_staging_rule_is_refused(world, bad):
    r = new(bad)
    assert (r.status_code, r.json()["error"]) == (422, "invalid_apartment_id")
    assert world.published == []


def test_name_timezone_and_availability(world):
    assert new(name="").json()["error"] == "invalid_name"
    assert new(name="x" * 81).json()["error"] == "invalid_name"
    assert new(timezone="Marte/Olimpo").json()["error"] == "invalid_timezone"
    world.configure(agent_ambiente="prod")
    assert (new().status_code, new().json()["error"]) == (503, "agent_not_configured")
    world.configure(agent_ambiente="staging", agent_ordini_key="")
    assert new().status_code == 503
    assert call("POST", NEW, headers=ADMIN, json={"apartment_id": "lab-a2-01", "name": "x"}).status_code == 403


def test_an_id_used_now_or_before_is_not_available(world):
    assert new().status_code == 202
    r = new()
    assert (r.status_code, r.json()["error"]) == (409, "already_exists")


def test_five_an_hour_per_organisation_with_the_time_it_frees(world):
    first = world.now
    for i in range(5):
        assert new(f"lab-a2-0{i}").status_code == 202
        world.now += timedelta(minutes=1)
    r = new("lab-a2-09")
    assert r.status_code == 429
    body = r.json()
    free = (first + timedelta(hours=1)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    assert body["error"] == "rate_limited" and body["details"] == {"limite": 5, "riprova_dal": free}
    assert int(r.headers["Retry-After"]) == 55 * 60
    assert call("GET", f"/app/platform/tenants/{DEMO_TENANT}").json()["creazioni_ultima_ora"] == \
        {"usate": 5, "limite": 5, "libera_dal": free}
    assert new("lab-a2-09", tenant=OTHER_TENANT).status_code == 202          # another organisation
    push(world.published[0], esito="rifiutato", codice="capienza_insufficiente")
    assert act("riprova", "lab-a2-00").status_code == 202                   # «Riprova» does not count
    world.now = first + timedelta(hours=1, seconds=1)
    assert new("lab-a2-08").status_code == 202


def test_a_full_band_is_no_free_port(world):
    for i in range(5):
        assert new(f"lab-a2-0{i}").status_code == 202
        assert new(f"lab-a2-1{i}", tenant=OTHER_TENANT).status_code == 202
    r = new("lab-a2-20", tenant=OTHER_TENANT)
    world.now += timedelta(hours=2)
    r = new("lab-a2-20")
    assert (r.status_code, r.json()["error"]) == (409, "no_free_port")


# ---- stopped half-way, «Riprova» ---------------------------------------------------------------------------------
def test_no_room_stops_it_and_riprova_asks_again(world):
    new()
    push(world.published[-1], dati={**ROOM, "mem_available_mb": 500})
    c = creazione()
    assert (c["stato"], c["codice"], c["passo"]) == ("non_creato", "capienza_insufficiente", "capienza")
    assert c["messaggio"] == "La VM non ha memoria per un motore in più."
    assert act("riprova", version=c["version"] - 1).json()["error"] == "version_changed"
    r = act("riprova")
    assert r.status_code == 202 and r.json()["creazione"]["stato"] == "in_preparazione"
    assert world.published[-1]["operazione"] == "capienza" and len(world.published) == 2
    assert act("riprova").json()["error"] == "invalid_state"
    push(world.published[-1], dati={**ROOM, "motori_staging": 4})
    assert creazione()["codice"] == "staging_pieno"
    rows = get_repository().audit[DEMO_TENANT]
    assert any(e.action == "apartment_creation_retried" for e in rows.values())


def test_twenty_minutes_without_progress_is_non_creato(world):
    new()
    world.now += timedelta(minutes=21)
    c = creazione()
    assert (c["stato"], c["codice"]) == ("non_creato", "tempo_scaduto")
    assert act("riprova").status_code == 202


def test_porta_occupata_takes_the_next_port_and_keeps_the_busy_one_marked(world):
    new()
    push(world.published[-1], dati=ROOM)
    push(world.published[-1], esito="rifiutato", codice="porta_occupata")
    assert creazione()["codice"] == "porta_occupata"
    act("riprova")
    assert creazione()["porta"] == 8151
    push(world.published[-1], dati=ROOM)
    assert world.published[-1]["parametri"] == {"porta": 8151}
    assert get_repository().external_id_owners["link:10.198.0.2:8150"] == creation.OCCUPIED_OWNER
    assert new("lab-a2-02").json()["creazione"]["porta"] == 8152


def test_the_link_that_fails_is_retried_without_a_new_order(world):
    world.verify_ok = False
    to_ready(world)
    c = creazione()
    assert (c["stato"], c["codice"]) == ("non_creato", "collegamento_fallito")
    sent = len(world.published)
    world.verify_ok = True
    act("riprova")
    assert creazione()["stato"] == "pronto" and len(world.published) == sent


def test_a_secret_not_ours_is_a_conflict_with_an_alarm(world, caplog):
    key, _ = sa.names("lab-a2-01")
    world.secrets.secrets[key] = sa.describe_body(sa.secret_body("staging", "lab-a2-01", "un-altro-op"))
    world.secrets.versions[key] = []
    with caplog.at_level(logging.WARNING):
        r = new()
    assert (r.status_code, r.json()["error"]) == (409, "secret_conflict")
    assert "agent alarm codice=secret_conflict" in caplog.text
    assert world.secrets.versions[key] == [] and world.published == []
    c = creazione()
    assert (c["stato"], c["codice"], c["passo"]) == ("non_creato", "secret_conflict", "segreti")


def test_secret_manager_refusing_stops_at_the_secrets_and_riprova_goes_on(world):
    world.secrets.fail = "PermissionDenied"
    r = new()
    assert r.status_code == 202
    assert (r.json()["creazione"]["stato"], r.json()["creazione"]["codice"]) == ("non_creato", "segreti_non_creati")
    world.secrets.fail = None
    act("riprova")
    assert creazione()["passo"] == "capienza" and world.published[-1]["operazione"] == "capienza"


def test_a_publish_that_fails_is_502_with_the_op_and_non_creato(world):
    world.fail = True
    r = new()
    assert (r.status_code, r.json()["error"]) == (502, "agent_publish_failed")
    assert r.json()["details"]["op"]["codice"] == "non_inviato"
    world.fail = False
    assert creazione()["codice"] == "non_inviato"


# ---- «Annulla» ---------------------------------------------------------------------------------------------------
def test_annulla_before_any_engine_removes_everything_and_the_id_stays_used(world):
    new()
    push(world.published[-1], esito="rifiutato", codice="capienza_insufficiente")
    sent = len(world.published)
    r = act("annulla")
    assert r.status_code == 202 and r.json()["creazione"]["stato"] == "annullato"
    assert len(world.published) == sent                                     # nothing on the VM: no togli_motore
    assert "lab-a2-01" not in get_repository().apartments
    key, conn = sa.names("lab-a2-01")
    assert world.secrets.versions[key][0][1] == world.secrets.versions[conn][0][1] == "DESTROY_PENDING"
    assert creazione() == 404
    assert new().json()["error"] == "already_exists"
    assert new("lab-a2-02").json()["creazione"]["porta"] == 8150            # the port is free again


def test_annulla_after_crea_motore_sends_togli_motore_and_waits_for_it(world):
    new()
    push(world.published[-1], dati=ROOM)
    push(world.published[-1], esito="fallito", codice="motore_non_sano")
    r = act("annulla")
    assert r.json()["creazione"]["stato"] == "annullamento_in_corso"
    togli = world.published[-1]
    assert togli["operazione"] == "togli_motore" and togli["apartment_id"] == "lab-a2-01" and togli["seq"] == 2
    assert agent.signed_by([K_ORD], togli) and togli["parametri"] == {}
    assert act("riprova").json()["error"] == "invalid_state"
    assert act("annulla").json()["error"] == "invalid_state"
    push(togli)
    assert creazione() == 404
    key, _ = sa.names("lab-a2-01")
    assert world.secrets.versions[key][0][1] == "DESTROY_PENDING"


def test_togli_motore_refused_goes_back_to_non_creato(world):
    new()
    push(world.published[-1], dati=ROOM)
    push(world.published[-1], esito="fallito", codice="motore_non_sano")
    act("annulla")
    push(world.published[-1], esito="rifiutato", codice="non_creato_da_agente")
    c = creazione()
    assert (c["stato"], c["codice"]) == ("non_creato", "non_creato_da_agente")
    key, _ = sa.names("lab-a2-01")
    assert world.secrets.versions[key][0][1] == "ENABLED"


def test_a_late_togli_motore_success_closes_only_without_a_later_order(world):
    new()
    push(world.published[-1], dati=ROOM)
    push(world.published[-1], esito="fallito", codice="motore_non_sano")
    act("annulla")
    togli = world.published[-1]
    world.now += timedelta(minutes=25)
    assert creazione()["stato"] == "non_creato"
    push(togli)
    assert creazione() == 404                                                # N8: closed all the same

    new("lab-a2-02")
    push(world.published[-1], dati=ROOM)
    push(world.published[-1], esito="fallito", codice="motore_non_sano")
    act("annulla", "lab-a2-02")
    togli = world.published[-1]
    world.now += timedelta(minutes=25)
    act("riprova", "lab-a2-02")                                              # a new order for the apartment
    push(togli)
    c = creazione("lab-a2-02")
    assert c != 404 and c["stato"] == "in_preparazione"                      # ignored: secrets and record stay
    key, _ = sa.names("lab-a2-02")
    assert world.secrets.versions[key][0][1] == "ENABLED"


# ---- code review of A2 (20 November), point 1: «Riprova» and «Annulla» never cross; point 5: the old routes ------------
def test_review1_annulla_is_refused_while_riprova_has_not_sent_its_order_yet(world, monkeypatch):
    import types
    new()
    push(world.published[-1], esito="rifiutato", codice="capienza_insufficiente")
    who = types.SimpleNamespace(uid="dev-platform", email="piattaforma@demo.it", display_name=None)
    real = agent.new_order
    seen = {}

    async def in_the_window(*args, **kwargs):              # «Riprova» saved, its order not yet
        apt = get_repository().apartments["lab-a2-01"]
        try:
            await creation.cancel(apt, apt.creazione.version, who)
            seen["annulla"] = "accettato"
        except creation.CreationRefused as exc:
            seen["annulla"] = exc.error
        return await real(*args, **kwargs)
    monkeypatch.setattr(agent, "new_order", in_the_window)
    assert act("riprova").status_code == 202
    assert seen["annulla"] == "invalid_state"
    assert creazione()["stato"] == "in_preparazione"


def test_review1_a_capienza_result_after_annulla_starts_nothing(world):
    new()
    capienza = world.published[-1]
    apt = get_repository().apartments["lab-a2-01"]
    apt.creazione.stato = "annullamento_in_corso"           # as if «Annulla» had won the race
    sent = len(world.published)
    push(capienza, dati=ROOM)
    assert len(world.published) == sent                     # no crea_motore
    assert get_repository().apartments["lab-a2-01"].creazione.stato == "annullamento_in_corso"


def test_review5_the_old_link_and_delete_refuse_an_apartment_created_from_the_app(world):
    new()
    base = f"/app/platform/tenants/{DEMO_TENANT}/apartments/lab-a2-01"
    r = call("PATCH", base, json={"port": 8199})
    assert (r.status_code, r.json()["error"]) == (409, "created_from_app")
    r = call("DELETE", base)
    assert (r.status_code, r.json()["error"]) == (409, "use_elimina")      # A6: never the old way, for any apartment
    assert "lab-a2-01" in get_repository().apartments


def test_the_italianway_code_is_added_and_removed_on_an_apartment_created_from_the_app(world):
    """Usability reading (22 November, D-198): «Nuovo appartamento» says the Italianway code «Si può aggiungere anche
    dopo», but the old link refused every change of an apartment created from the app (409 created_from_app), so the
    code could never come and the bookings never arrived. Now PATCH with italianway_id alone changes it (null removes
    it), with its italianway_changed entry; any other field still gets 409 created_from_app."""
    from bff import audit
    new()
    base = f"/app/platform/tenants/{DEMO_TENANT}/apartments/lab-a2-01"
    r = call("PATCH", base, json={"italianway_id": "IW-A2-01"})
    assert r.status_code == 200 and r.json()["italianway_id"] == "IW-A2-01", r.text
    assert get_repository().apartments["lab-a2-01"].external_ids.italianway == "IW-A2-01"
    r = call("PATCH", base, json={"italianway_id": "IW-A2-01", "port": 8199})
    assert (r.status_code, r.json()["error"]) == (409, "created_from_app")
    assert (call("PATCH", base, json={"instance_url": "http://10.198.0.2:8151"}).json()["error"]) == "created_from_app"
    r = call("PATCH", base, json={"italianway_id": None})
    assert r.status_code == 200 and r.json()["italianway_id"] is None
    items = run(audit.page(DEMO_TENANT, 20, None, viewer="platform"))["items"]
    changed = [i for i in items if i["action"] == "italianway_changed" and i["target"]["id"] == "lab-a2-01"]
    assert [(i["details"]["from"], i["details"]["to"]) for i in changed][:2] == [("IW-A2-01", None), (None, "IW-A2-01")]


def test_a_code_already_used_is_refused_on_an_apartment_created_from_the_app(world):
    new()
    new("lab-a2-02")
    base = f"/app/platform/tenants/{DEMO_TENANT}/apartments"
    assert call("PATCH", f"{base}/lab-a2-01", json={"italianway_id": "IW-A2-SAME"}).status_code == 200
    r = call("PATCH", f"{base}/lab-a2-02", json={"italianway_id": "IW-A2-SAME"})
    assert (r.status_code, r.json()["error"]) == (409, "external_id_in_use")
