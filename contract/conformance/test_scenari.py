"""
Scenari C01–C16 di `x-conformita` in contract/openapi.yaml (1.0.4).
Ogni test cita lo scenario nel docstring. Regole in conftest.py.
"""
from __future__ import annotations

import time
import uuid

import pytest

from conftest import ACTOR, TIMEOUT_ASK_S, Client


# ---------------------------------------------------------------------------
# Sistema (settimana 1): C13, C14, C15
# ---------------------------------------------------------------------------

def test_c13_funzione_non_implementata(client: Client):
    """C13 · Per ogni feature della mappa x-features: se assente da features, ogni suo endpoint → 501
    (anche con body non valido); se presente → mai 501."""
    client.richiede_stato("il mock risponde con gli esempi, non con 501")
    mappa = {
        "apartment": [("GET", "/apartment"), ("POST", "/apartment/mode"), ("POST", "/apartment/hold")],
        "devices": [("GET", "/devices"), ("PATCH", "/devices/x")],
        "commands": [("POST", "/devices/x/commands"), ("GET", "/commands/x")],
        "energy": [("GET", "/energy")],
        "schedule": [("GET", "/schedule"), ("POST", "/schedule"), ("PATCH", "/schedule/x"), ("DELETE", "/schedule/x")],
        "rules": [("GET", "/rules"), ("PUT", "/rules")],
        "approvals": [("GET", "/approvals"), ("POST", "/approvals/x/decision")],
        "decisions": [("GET", "/decisions")],
        "ask": [("POST", "/ask"), ("GET", "/ask/x")],
        "bookings": [("POST", "/bookings")],
    }
    for feature, endpoints in mappa.items():
        for metodo, path in endpoints:
            # body volutamente non valido: il 501 deve precedere la validazione
            r = client.http.request(metodo, path, headers=client.headers(), json={"non": "valido"})
            if feature not in client.features:
                assert r.status_code == 501, f"{metodo} {path}: atteso 501 (feature {feature} assente), ricevuto {r.status_code}"
                assert r.json()["error"] == "not_implemented"
            else:
                assert r.status_code != 501, f"{metodo} {path}: feature {feature} attiva ma risponde 501"


def test_c14_salute(client: Client):
    """C14 · GET /health risponde senza X-API-Key; con il connector attivo (anche simulato) → 200 e
    connected_devices > 0. Il caso 503 (DOMOTICA_TEST_CONNECTOR_DOWN=1) si verifica con un'istanza avviata apposta:
    vedi test_c14_connector_fermo."""
    r = client.http.get("/health")  # nessun header
    assert r.status_code in (200, 503), r.text
    corpo = r.json()
    for campo in ("status", "apartment_id", "implementation", "uptime_s", "database", "connector", "model_provider", "devices", "checked_at"):
        assert campo in corpo, f"/health senza campo {campo}"
    if r.status_code == 200:
        assert corpo["status"] in ("ok", "degraded")
        assert corpo["connector"]["status"] == "up"
        assert corpo["connector"]["connected_devices"] > 0
    else:
        assert corpo["status"] == "down"
        assert corpo["connector"]["status"] == "down"


@pytest.mark.connector_down
def test_c14_connector_fermo(client: Client):
    """C14 (parte 503) · Da eseguire contro un'istanza avviata con DOMOTICA_TEST_CONNECTOR_DOWN=1:
        pytest -m connector_down --base-url ...
    Con il connector fermo GET /health → 503 status down."""
    r = client.http.get("/health")
    assert r.status_code == 503, f"atteso 503 con connector fermo, ricevuto {r.status_code}"
    assert r.json()["status"] == "down"


def test_c15_header_obbligatori(client: Client):
    """C15 · Senza X-API-Key → 401; senza X-Correlation-Id o X-Actor, o con X-Correlation-Id non UUID → 400;
    (solo con commands e decisions attivi) con header validi → Decision ed eventi portano quel correlation_id."""
    # Prism (mock) valida gli header con i propri codici: il caso 401/400 ha senso solo su un'istanza reale
    client.richiede_stato("codici 401/400 del middleware")

    r = client.http.get("/devices", headers={"X-Actor": ACTOR, "X-Correlation-Id": str(uuid.uuid4())})
    assert r.status_code == 401 and r.json()["error"] == "unauthorized"

    r = client.http.get("/devices", headers={"X-API-Key": client.api_key, "X-Actor": ACTOR})
    assert r.status_code == 400 and r.json()["error"] == "bad_request"

    r = client.http.get("/devices", headers={"X-API-Key": client.api_key, "X-Correlation-Id": str(uuid.uuid4())})
    assert r.status_code == 400

    r = client.http.get("/devices", headers={"X-API-Key": client.api_key, "X-Actor": ACTOR, "X-Correlation-Id": "non-un-uuid"})
    assert r.status_code == 400

    r = client.http.get("/devices", headers={"X-API-Key": client.api_key, "X-Actor": "nessuna-email-ne-system", "X-Correlation-Id": str(uuid.uuid4())})
    assert r.status_code == 400

    if {"commands", "decisions"} <= client.features:
        dev = client.dispositivo_con("switch")
        cid = str(uuid.uuid4())
        r = client.post(f"/devices/{dev['device_id']}/commands", {"capability": "switch", "action": "turn_on"}, headers=client.headers(cid))
        assert r.status_code == 202, r.text
        client.attendi_comando(r.json()["command_id"])
        dec = client.decisioni(cid)
        assert dec, "nessuna Decision con il correlation_id della chiamata"
        assert all(d["correlation_id"] == cid for d in dec)


# ---------------------------------------------------------------------------
# M1 (settimana 2): C01, C02, C03, C07
# ---------------------------------------------------------------------------

def test_c01_percorso_completo_comando(client: Client):
    """C01 · POST /devices/{id}/commands su switch → 202 pending → entro 10 s acked → su /stream command.updated per
    ogni transizione e device.state → GET /decisions contiene una Decision con lo stesso correlation_id e
    actor = "user:" + X-Actor."""
    client.richiede("devices", "commands", "decisions", "stream")
    dev = client.dispositivo_con("switch")
    cid = str(uuid.uuid4())
    nuovo = not dev["capabilities"]["switch"]["on"]

    cursore = client.cursore() if not client.mock else "0"
    r = client.post(f"/devices/{dev['device_id']}/commands",
                    {"capability": "switch", "action": "turn_on" if nuovo else "turn_off"},
                    headers=client.headers(cid))
    assert r.status_code == 202, r.text
    corpo = r.json()
    assert corpo["status"] == "pending"
    if not client.mock:
        assert corpo["correlation_id"] == cid, "la risposta deve riportare il correlation_id della chiamata"
    command_id = corpo["command_id"]

    finale = client.attendi_comando(command_id)
    assert finale["status"] == "acked", f"comando non eseguito: {finale}"

    if not client.mock:
        eventi = client.leggi_stream(max_eventi=50, timeout_s=3, last_event_id=cursore)
        tipi = {(e.get("event"), e.get("data", {}).get("command_id")) for e in eventi}
        assert any(ev == "command.updated" and c == command_id for ev, c in tipi), "nessun command.updated per il comando"
        assert any(e.get("event") == "device.state" and e.get("data", {}).get("device_id") == dev["device_id"] for e in eventi)

        dec = client.decisioni(cid)
        assert dec, "nessuna Decision con il correlation_id del comando"
        assert any(d["actor"] == f"user:{ACTOR}" for d in dec), f"actor atteso user:{ACTOR}, trovati {[d['actor'] for d in dec]}"
        assert any(d.get("command_id") == command_id for d in dec)


def test_c02_idempotenza(client: Client):
    """C02 · Due POST identiche con lo stesso X-Correlation-Id entro 60 s → stesso command_id, una sola esecuzione,
    una sola Decision in GET /decisions."""
    client.richiede("devices", "commands", "decisions")
    client.richiede_stato("idempotenza")
    dev = client.dispositivo_con("switch")
    cid = str(uuid.uuid4())
    body = {"capability": "switch", "action": "turn_on"}
    r1 = client.post(f"/devices/{dev['device_id']}/commands", body, headers=client.headers(cid))
    r2 = client.post(f"/devices/{dev['device_id']}/commands", body, headers=client.headers(cid))
    assert r1.status_code == 202 and r2.status_code == 202
    assert r1.json()["command_id"] == r2.json()["command_id"]
    client.attendi_comando(r1.json()["command_id"])
    dec = [d for d in client.decisioni(cid) if d.get("command_id")]
    assert len(dec) == 1, f"attesa una sola Decision, trovate {len(dec)}"


def test_c03_comando_fuori_limite(client: Client):
    """C03 · set_climate con setpoint > setpoint_max → 422 setpoint_out_of_range con details {min, max};
    nessun comando creato."""
    client.richiede("devices", "commands")
    dev = client.dispositivo_con("climate")
    troppo = dev["capabilities"]["climate"]["setpoint_max"] + 5
    client.richiede_stato("validazione del setpoint")
    r = client.post(f"/devices/{dev['device_id']}/commands",
                    {"capability": "climate", "action": "set_climate", "params": {"setpoint": troppo}})
    assert r.status_code == 422, r.text
    corpo = r.json()
    assert corpo["error"] == "setpoint_out_of_range"
    assert {"min", "max"} <= set(corpo.get("details", {}))


def test_c07_riconnessione_sse(client: Client):
    """C07 · Aprire /stream, ricevere N eventi, chiudere; generare 3 eventi; riaprire con Last-Event-ID = ultimo id →
    arrivano esattamente i 3 eventi persi, in ordine, con id crescenti."""
    client.richiede("devices", "commands", "stream")
    client.richiede_stato("buffer SSE")
    dev = client.dispositivo_con("switch")

    # 1) un primo evento per conoscere l'ultimo id
    r = client.post(f"/devices/{dev['device_id']}/commands", {"capability": "switch", "action": "turn_on"})
    assert r.status_code == 202
    client.attendi_comando(r.json()["command_id"])
    prima = client.leggi_stream(max_eventi=10000, timeout_s=2, last_event_id="0")
    assert prima, "nessun evento sul flusso"
    ultimo_id = prima[-1]["id"]

    # 2) tre comandi = almeno tre eventi persi
    ids = []
    for azione in ("turn_off", "turn_on", "turn_off"):
        r = client.post(f"/devices/{dev['device_id']}/commands", {"capability": "switch", "action": azione})
        assert r.status_code == 202
        ids.append(r.json()["command_id"])
        client.attendi_comando(ids[-1])

    # 3) riconnessione
    dopo = client.leggi_stream(max_eventi=100, timeout_s=3, last_event_id=ultimo_id)
    assert dopo, "nessun evento dopo Last-Event-ID"
    numeri = [int(e["id"]) for e in dopo]
    assert numeri == sorted(numeri) and numeri[0] > int(ultimo_id), "id non crescenti o non successivi a Last-Event-ID"
    visti = {e.get("data", {}).get("command_id") for e in dopo if e.get("event") == "command.updated"}
    assert set(ids) <= visti, f"eventi persi non riconsegnati: {set(ids) - visti}"


# ---------------------------------------------------------------------------
# M2 (settimana 3): C04, C05, C06, C10, C11
# ---------------------------------------------------------------------------

def test_c04_dispositivo_offline(client: Client):
    """C04 · Dispositivo portato offline con POST /_test/state (o realmente offline) → comando → 409 device_offline;
    nessun comando creato."""
    client.richiede("devices", "commands")
    client.richiede_stato("dispositivo offline")
    dev = client.dispositivo_con("switch")
    client.stato_simulato({"device_id": dev["device_id"], "online": False})
    try:
        r = client.post(f"/devices/{dev['device_id']}/commands", {"capability": "switch", "action": "turn_on"})
        assert r.status_code == 409 and r.json()["error"] == "device_offline", r.text
    finally:
        client.stato_simulato({"device_id": dev["device_id"], "online": True})


def test_c05_comando_bloccato_da_regola(client: Client):
    """C05 · Finestra aperta (contact.open = true, via /_test/state) e set_climate on → 202, poi failed con
    reason blocked_by_rule, Decision con outcome rejected in GET /decisions."""
    client.richiede("devices", "commands", "decisions", "rules")
    client.richiede_stato("finestra aperta")
    finestra = client.dispositivo_con("contact")
    clima = client.dispositivo_con("climate")
    client.stato_simulato({"device_id": finestra["device_id"], "capability": "contact", "state": {"open": True}})
    try:
        cid = str(uuid.uuid4())
        r = client.post(f"/devices/{clima['device_id']}/commands",
                        {"capability": "climate", "action": "set_climate", "params": {"on": True, "mode": "heat"}},
                        headers=client.headers(cid))
        assert r.status_code == 202, r.text
        finale = client.attendi_comando(r.json()["command_id"])
        assert finale["status"] == "failed" and finale["reason"] == "blocked_by_rule", finale
        dec = client.decisioni(cid)
        assert any(d["outcome"] == "rejected" for d in dec), dec
    finally:
        client.stato_simulato({"device_id": finestra["device_id"], "capability": "contact", "state": {"open": False}})


def test_c06_regole_dentro_e_fuori_limite(client: Client):
    """C06 · PUT /rules dentro limits → 200 e GET /rules riflette il valore; fuori limits → 422;
    rule editable = false → 422 rule_not_editable."""
    client.richiede("rules")
    r = client.get("/rules")
    assert r.status_code == 200, r.text
    regole = {x["rule_id"]: x for x in r.json()["rules"]}
    assert "window_open_off" in regole and "compressor_min_off" in regole

    lim = regole["window_open_off"]["limits"]["minutes"]
    valido = int(lim["min"])
    r = client.put("/rules", {"rules": [{"rule_id": "window_open_off", "params": {"minutes": valido}}]})
    assert r.status_code == 200, r.text
    if not client.mock:
        dopo = {x["rule_id"]: x for x in client.get("/rules").json()["rules"]}
        assert dopo["window_open_off"]["params"]["minutes"] == valido

    client.richiede_stato("validazione dei limiti")
    r = client.put("/rules", {"rules": [{"rule_id": "window_open_off", "params": {"minutes": int(lim["max"]) + 1}}]})
    assert r.status_code == 422, r.text
    r = client.put("/rules", {"rules": [{"rule_id": "compressor_min_off", "params": {"minutes": 3}}]})
    assert r.status_code == 422 and r.json()["error"] == "rule_not_editable", r.text


def test_c10_modalita_appartamento(client: Client):
    """C10 · POST /apartment/mode empty → 202 con command_ids; ogni command_id raggiunge uno stato finale;
    GET /apartment mostra mode = empty; evento apartment.changed emesso."""
    client.richiede("apartment", "commands")
    cursore = client.cursore()
    r = client.post("/apartment/mode", {"mode": "empty"})
    assert r.status_code == 202, r.text
    corpo = r.json()
    assert corpo["mode"] in ("comfort", "eco", "empty") and isinstance(corpo["command_ids"], list)
    client.richiede_stato("stato dell'appartamento")
    assert corpo["mode"] == "empty"
    for cid in corpo["command_ids"]:
        client.attendi_comando(cid)
    assert client.get("/apartment").json()["mode"] == "empty"
    eventi = client.leggi_stream(max_eventi=100, timeout_s=2, last_event_id=cursore)
    assert any(e.get("event") == "apartment.changed" for e in eventi)


def test_c11_forzatura(client: Client):
    """C11 · POST /apartment/hold 5 minuti → hold valorizzato; durante il hold una finestra aperta (via /_test/state)
    non spegne il clima; alla scadenza hold = null e la regola torna attiva."""
    client.richiede("apartment", "devices", "commands", "rules")
    client.richiede_stato("forzatura")
    finestra = client.dispositivo_con("contact")
    clima = client.dispositivo_con("climate")

    r = client.post("/apartment/hold", {"minutes": 1, "mode": "comfort"})
    assert r.status_code == 202, r.text
    assert client.get("/apartment").json()["hold"] is not None
    try:
        r = client.post(f"/devices/{clima['device_id']}/commands",
                        {"capability": "climate", "action": "set_climate", "params": {"on": True, "mode": "heat"}})
        assert r.status_code == 202
        assert client.attendi_comando(r.json()["command_id"])["status"] == "acked"
        client.stato_simulato({"device_id": finestra["device_id"], "capability": "contact", "state": {"open": True}})
        time.sleep(2)
        stato = next(d for d in client.get("/devices").json()["devices"] if d["device_id"] == clima["device_id"])
        assert stato["capabilities"]["climate"]["on"] is True, "il hold non ha sospeso la regola finestra aperta"
    finally:
        client.stato_simulato({"device_id": finestra["device_id"], "capability": "contact", "state": {"open": False}})
        client.post("/apartment/hold", {"minutes": 0})
    assert client.get("/apartment").json()["hold"] is None


# ---------------------------------------------------------------------------
# M3 (settimana 4): C08, C09
# ---------------------------------------------------------------------------

def _evento(tipo: str, booking_id: str, checkin: str, checkout: str) -> dict:
    return {
        "event_id": f"evt-conf-{uuid.uuid4().hex[:12]}",
        "type": tipo,
        "booking_id": booking_id,
        "checkin_at": checkin,
        "checkout_at": checkout,
        "guests": 2,
        "source": "simulator",
        "ts": "2026-10-14T13:00:00.000Z",
    }


def test_c08_prenotazione_e_schedule(client: Client):
    """C08 · POST /bookings booking_created → 202 con schedule_ids; GET /schedule mostra prearrival e checkout;
    secondo POST con lo stesso event_id → 200 duplicate = true e nessuna voce doppia."""
    client.richiede("bookings", "schedule")
    booking_id = f"bk-conf-{uuid.uuid4().hex[:6]}"
    ev = _evento("booking_created", booking_id, "2026-12-01T15:00:00.000Z", "2026-12-04T08:00:00.000Z")
    r = client.post("/bookings", ev)
    assert r.status_code == 202, r.text
    corpo = r.json()
    assert corpo["accepted"] is True and corpo["duplicate"] is False and corpo["schedule_ids"]

    client.richiede_stato("schedule e idempotenza su event_id")
    voci = [v for v in client.get("/schedule").json()["items"] if v.get("booking_id") == booking_id]
    tipi = {v["kind"] for v in voci}
    assert {"prearrival", "checkout"} <= tipi, f"voci attese prearrival e checkout, trovate {tipi}"

    r2 = client.post("/bookings", ev)
    assert r2.status_code == 200 and r2.json()["duplicate"] is True, r2.text
    voci2 = [v for v in client.get("/schedule").json()["items"] if v.get("booking_id") == booking_id]
    assert len(voci2) == len(voci), "voci duplicate dopo lo stesso event_id"


def test_c09_modifica_e_cancellazione_prenotazione(client: Client):
    """C09 · booking_changed con nuovo checkin_at → voci ricalcolate, non duplicate; booking_cancelled → voci cancelled."""
    client.richiede("bookings", "schedule")
    client.richiede_stato("ricalcolo dello schedule")
    booking_id = f"bk-conf-{uuid.uuid4().hex[:6]}"
    assert client.post("/bookings", _evento("booking_created", booking_id, "2026-12-10T15:00:00.000Z", "2026-12-12T08:00:00.000Z")).status_code == 202
    n1 = len([v for v in client.get("/schedule").json()["items"] if v.get("booking_id") == booking_id and v["status"] == "planned"])

    assert client.post("/bookings", _evento("booking_changed", booking_id, "2026-12-10T12:00:00.000Z", "2026-12-12T08:00:00.000Z")).status_code == 202
    attive = [v for v in client.get("/schedule").json()["items"] if v.get("booking_id") == booking_id and v["status"] == "planned"]
    assert len(attive) == n1, "voci duplicate dopo booking_changed"
    pre = next(v for v in attive if v["kind"] == "prearrival")
    assert pre["run_at"] < "2026-12-10T12:00:00.000Z"

    assert client.post("/bookings", _evento("booking_cancelled", booking_id, "2026-12-10T12:00:00.000Z", "2026-12-12T08:00:00.000Z")).status_code == 202
    dopo = [v for v in client.get("/schedule").json()["items"] if v.get("booking_id") == booking_id]
    assert dopo and all(v["status"] == "cancelled" for v in dopo)


# ---------------------------------------------------------------------------
# M4 (settimana 5): C12, C16
# ---------------------------------------------------------------------------

def test_c12_approvazione(client: Client):
    """C12 · Provocare un'azione che richiede il consenso del gestore (/_test/state trigger approval) → approval.pending su /stream e voce
    in GET /approvals; decisione approve → 200, Decision con actor = X-Actor, comandi a stato finale; seconda decisione → 409."""
    client.richiede("approvals", "decisions", "stream")
    client.richiede_stato("approvazione")
    # Il contratto ammette una sola approvazione pendente per istanza: chiudiamo quelle lasciate da esecuzioni
    # precedenti, altrimenti il trigger si mette in coda senza produrre alcun evento.
    for _ in range(50):  # ogni decisione può aprire la successiva in coda: si ripete finché non resta nulla
        pendenti_vecchie = [a for a in client.get("/approvals").json()["items"] if a["status"] == "pending"]
        if not pendenti_vecchie:
            break
        for vecchia in pendenti_vecchie:
            client.post(f"/approvals/{vecchia['approval_id']}/decision", {"decision": "reject", "note": "pulizia test"})
        time.sleep(0.2)
    cursore = client.cursore()
    client.stato_simulato({"trigger": "approval"})

    scadenza = time.monotonic() + 15
    pendenti = []
    while time.monotonic() < scadenza and not pendenti:
        pendenti = [a for a in client.get("/approvals").json()["items"] if a["status"] == "pending"]
        time.sleep(0.5)
    assert pendenti, "nessuna approvazione pendente dopo il trigger"
    appr = pendenti[0]
    assert appr["description"] and appr["reason"], "descrizione o motivo mancanti"

    eventi = client.leggi_stream(max_eventi=100, timeout_s=2, last_event_id=cursore)
    assert any(e.get("event") == "approval.pending" for e in eventi)

    cid = str(uuid.uuid4())
    r = client.post(f"/approvals/{appr['approval_id']}/decision", {"decision": "approve", "note": "test di conformità"}, headers=client.headers(cid))
    assert r.status_code == 200 and r.json()["status"] == "approved", r.text
    dec = client.decisioni(cid)
    assert any(d["actor"] == f"user:{ACTOR}" for d in dec), dec

    r = client.post(f"/approvals/{appr['approval_id']}/decision", {"decision": "reject"})
    assert r.status_code == 409


def test_c16_assistente(client: Client):
    """C16 · POST /ask → 202; entro 30 s GET /ask/{id} answered con actions non vuote, oppure needs_approval con
    approval_id; ogni action ha un command_id o schedule_id rintracciabile."""
    client.richiede("ask")
    r = client.post("/ask", {"text": "Spegni il climatizzatore del soggiorno"})
    assert r.status_code == 202, r.text
    ask_id = r.json()["ask_id"]
    client.richiede_stato("risposta dell'assistente")
    scadenza = time.monotonic() + TIMEOUT_ASK_S
    stato = None
    while time.monotonic() < scadenza:
        stato = client.get(f"/ask/{ask_id}").json()
        if stato["status"] != "pending":
            break
        time.sleep(1)
    assert stato and stato["status"] in ("answered", "needs_approval"), stato
    if stato["status"] == "answered":
        assert stato["actions"], "answered senza actions"
        for a in stato["actions"]:
            assert a.get("command_id") or a.get("schedule_id") or a["type"] == "rules", a
    else:
        assert stato["approval_id"]
