"""BFF backend tests - Phase 1 (no MongoDB, dev auth, mock instance)."""
import os
import time
import json
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = BASE + os.environ.get("BFF_API_PREFIX", "")  # "" = BFF diretto (/app/...); "/api" solo dietro un proxy che lo aggiunge

ADMIN = {"X-Dev-User": "admin@demo.it"}
OPERATOR = {"X-Dev-User": "operatore@demo.it"}
VIEWER = {"X-Dev-User": "lettura@demo.it"}
APT = "apt-rimini-01"


# ---------- Health / Auth ----------
def test_healthz():
    r = requests.get(f"{API}/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_public_health_same_answer_as_healthz():
    # /health is what the uptime check calls: /healthz is reserved by Cloud Run's front end from outside (E-12)
    r = requests.get(f"{API}/health")
    assert r.status_code == 200
    assert r.json() == requests.get(f"{API}/healthz").json()


def test_app_answers_are_not_stored_by_browsers():
    # P-36 point 12: per user and per organisation; the SSE stream keeps its own no-cache, /health is not /app
    assert requests.get(f"{API}/app/me", headers=ADMIN).headers.get("Cache-Control") == "no-store"
    assert requests.get(f"{API}/app/apartments/apt-unknown", headers=ADMIN).headers.get("Cache-Control") == "no-store"
    assert requests.get(f"{API}/app/me").headers.get("Cache-Control") == "no-store"            # errors too (401)
    with requests.get(f"{API}/app/apartments/{APT}/stream", headers=ADMIN, stream=True, timeout=10) as r:
        assert r.status_code == 200 and r.headers.get("Cache-Control") == "no-cache, no-transform"
        assert r.headers["Content-Type"].startswith("text/event-stream")
    assert requests.get(f"{API}/health").headers.get("Cache-Control") is None


def test_no_auth_returns_401():
    r = requests.get(f"{API}/app/me")
    assert r.status_code == 401


def test_dev_users():
    r = requests.get(f"{API}/app/dev/users")
    assert r.status_code == 200
    emails = {u["email"] for u in r.json()}
    assert {"admin@demo.it", "operatore@demo.it", "lettura@demo.it"} <= emails


def test_me_admin():
    r = requests.get(f"{API}/app/me", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["email"] == "admin@demo.it"
    assert data["role"] == "admin"
    assert data["env"]["instance_mode"] == "mock"


# ---------- Apartments list ----------
def test_apartments_list():
    r = requests.get(f"{API}/app/apartments", headers=ADMIN)
    assert r.status_code == 200
    apts = r.json()
    ids = {a["apartment_id"] for a in apts}
    assert {"apt-rimini-01", "apt-bologna-01"} <= ids
    rimini = next(a for a in apts if a["apartment_id"] == "apt-rimini-01")
    assert rimini["apartment"]["occupancy"] == "occupied"
    assert rimini["apartment"]["mode"] == "comfort"
    assert rimini["online"] is True
    assert "kwh_today" in rimini
    assert "energy_since" in rimini                          # D-130: null until found, then an ISO instant


def test_apartment_summary():
    r = requests.get(f"{API}/app/apartments/{APT}", headers=ADMIN)
    assert r.status_code == 200
    data = r.json()
    assert data["apartment_id"] == APT
    assert data["contract_version"] == "1.0.5"


def test_unknown_apartment_tenant_isolation():
    r = requests.get(f"{API}/app/apartments/apt-unknown", headers=ADMIN)
    assert r.status_code == 404
    # an apartment that EXISTS in another tenant (seed t-altra-demo) answers exactly like a missing one
    other = requests.get(f"{API}/app/apartments/apt-altra-01", headers=ADMIN)
    assert other.status_code == 404 and other.json() == r.json()


# ---------- Proxy: devices ----------
def test_proxy_devices_list():
    r = requests.get(f"{API}/app/apartments/{APT}/instance/devices", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    devices = body if isinstance(body, list) else body.get("devices", body.get("items", []))
    ids = {d["device_id"] for d in devices}
    assert "dev-presa-camera" in ids
    assert "dev-clima-soggiorno" in ids


def test_proxy_unknown_device():
    r = requests.post(
        f"{API}/app/apartments/{APT}/instance/devices/dev-nope/commands",
        headers={**ADMIN, "Content-Type": "application/json"},
        json={"capability": "switch", "command": "set", "params": {"on": True}},
    )
    assert r.status_code == 404


# ---------- Climate validation ----------
def test_climate_setpoint_out_of_range():
    r = requests.post(
        f"{API}/app/apartments/{APT}/instance/devices/dev-clima-soggiorno/commands",
        headers={**ADMIN, "Content-Type": "application/json"},
        json={"capability": "climate", "action": "set_climate", "params": {"on": True, "setpoint": 30}},
    )
    assert r.status_code == 422
    assert "setpoint_out_of_range" in json.dumps(r.json())


# ---------- Viewer forbidden ----------
def test_viewer_cannot_write():
    r = requests.post(
        f"{API}/app/apartments/{APT}/instance/devices/dev-presa-camera/commands",
        headers={**VIEWER, "Content-Type": "application/json"},
        json={"capability": "switch", "command": "toggle"},
    )
    assert r.status_code == 403
    assert r.json().get("error") == "forbidden"


# ---------- Operator can execute command ----------
def test_operator_command_toggle():
    # Get current state
    r0 = requests.get(f"{API}/app/apartments/{APT}/instance/devices", headers=OPERATOR)
    dev = next(d for d in r0.json()["devices"] if d["device_id"] == "dev-presa-camera")
    action = "turn_off" if dev["capabilities"]["switch"]["on"] else "turn_on"
    r = requests.post(
        f"{API}/app/apartments/{APT}/instance/devices/dev-presa-camera/commands",
        headers={**OPERATOR, "Content-Type": "application/json"},
        json={"capability": "switch", "action": action},
    )
    assert r.status_code in (200, 202), r.text


# ---------- _test simulator admin only ----------
def test_test_endpoint_forbidden_to_operator():
    r = requests.post(
        f"{API}/app/apartments/{APT}/instance/_test/state",
        headers={**OPERATOR, "Content-Type": "application/json"},
        json={"device_id": "dev-presa-camera", "online": False},
    )
    assert r.status_code == 403


def test_offline_then_command_returns_409():
    # Set offline via admin simulator
    r = requests.post(
        f"{API}/app/apartments/{APT}/instance/_test/state",
        headers={**ADMIN, "Content-Type": "application/json"},
        json={"device_id": "dev-presa-camera", "online": False},
    )
    assert r.status_code in (200, 204)
    try:
        # Command should now 409
        r2 = requests.post(
            f"{API}/app/apartments/{APT}/instance/devices/dev-presa-camera/commands",
            headers={**OPERATOR, "Content-Type": "application/json"},
            json={"capability": "switch", "action": "turn_on"},
        )
        assert r2.status_code == 409
        assert "device_offline" in json.dumps(r2.json())
    finally:
        requests.post(
            f"{API}/app/apartments/{APT}/instance/_test/state",
            headers={**ADMIN, "Content-Type": "application/json"},
            json={"device_id": "dev-presa-camera", "online": True},
        )


# ---------- Window rule blocks climate ----------
def test_window_rule_blocks_climate():
    # Open window
    r = requests.post(
        f"{API}/app/apartments/{APT}/instance/_test/state",
        headers={**ADMIN, "Content-Type": "application/json"},
        json={"device_id": "dev-finestra-camera", "capability": "contact", "state": {"open": True}},
    )
    assert r.status_code in (200, 204)
    try:
        time.sleep(3.5)  # wait for rule to turn climate off
        # Try to turn climate ON -> command accepted (202) but final status should be failed with blocked_by_rule
        r2 = requests.post(
            f"{API}/app/apartments/{APT}/instance/devices/dev-clima-soggiorno/commands",
            headers={**OPERATOR, "Content-Type": "application/json"},
            json={"capability": "climate", "action": "set_climate", "params": {"on": True, "mode": "heat", "setpoint": 21}},
        )
        assert r2.status_code in (200, 202), r2.text
        cmd = r2.json()
        cmd_id = (cmd.get("command_ids") or [cmd.get("command_id")])[0]
        # Poll command status
        final = None
        for _ in range(10):
            time.sleep(0.5)
            s = requests.get(f"{API}/app/apartments/{APT}/instance/commands/{cmd_id}", headers=OPERATOR)
            if s.status_code == 200 and s.json().get("status") in ("failed", "executed", "rejected"):
                final = s.json()
                break
        assert final is not None, "command never finalized"
        assert "blocked_by_rule" in json.dumps(final)
    finally:
        requests.post(
            f"{API}/app/apartments/{APT}/instance/_test/state",
            headers={**ADMIN, "Content-Type": "application/json"},
            json={"device_id": "dev-finestra-camera", "capability": "contact", "state": {"open": False}},
        )


# ---------- Blocked proxy paths ----------
def test_proxy_blocks_stream_subpath():
    r = requests.get(f"{API}/app/apartments/{APT}/instance/stream", headers=ADMIN)
    assert r.status_code == 403


def test_proxy_blocks_openapi():
    r = requests.get(f"{API}/app/apartments/{APT}/instance/openapi.json", headers=ADMIN)
    assert r.status_code == 403


# ---------- SSE stream basic (Phase 2: header-only auth) ----------
def test_sse_stream_connects():
    r = requests.get(
        f"{API}/app/apartments/{APT}/stream",
        headers=ADMIN,
        stream=True, timeout=5,
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers.get("content-type", "")
    chunk = next(r.iter_content(chunk_size=64, decode_unicode=True))
    r.close()
    assert "connected" in chunk or "retry" in chunk


def test_sse_stream_rejects_query_auth():
    r = requests.get(
        f"{API}/app/apartments/{APT}/stream",
        params={"dev_user": "admin@demo.it"},
        stream=True, timeout=5,
    )
    try:
        assert r.status_code == 401
    finally:
        r.close()
