"""P-36: isolation between two organisations, end to end on real data (seed: t-flatsharing-demo and t-altra-demo).
Every route a user of A can call is tried against resources of B, and list answers are checked for B's data.
Designed for the adversarial review: one assertion per way the separation could break."""
import hashlib
import hmac
import json
import os
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = BASE_URL + os.environ.get("BFF_API_PREFIX", "")
WEBHOOK_SECRET = "replace-me"

A_ADMIN, A_OPERATOR = "admin@demo.it", "operatore@demo.it"
B_ADMIN, B_OPERATOR = "admin@altra.it", "operatore@altra.it"
A_APT, B_APT = "apt-rimini-01", "apt-altra-01"
B_CODE = "IW-DEMO-ALTRA-01"
NOT_FOUND = {"error": "not_found", "message": "Appartamento inesistente"}


def hdr(email):
    return {"X-Dev-User": email, "Content-Type": "application/json"}


def _uid(admin, email):
    return next(u["uid"] for u in requests.get(f"{API}/app/admin/users", headers=hdr(admin)).json() if u["email"] == email)


# -------- apartment routes: B's apartment is exactly as invisible as a missing one --------
@pytest.mark.parametrize("method, path", [
    ("GET", ""), ("GET", "/bookings"), ("GET", "/instance/apartment"), ("GET", "/instance/devices"),
    ("GET", "/instance/energy?from=2026-10-01T00:00:00.000Z&to=2026-10-02T00:00:00.000Z&bucket=day"),
    ("GET", "/instance/approvals"), ("GET", "/instance/decisions"), ("GET", "/instance/schedule"), ("GET", "/instance/rules"),
    ("POST", "/instance/apartment/mode"), ("POST", "/instance/_test/state"), ("POST", "/simulator/booking"),
    ("POST", "/simulator/reset"),
])
@pytest.mark.parametrize("who", [A_ADMIN, A_OPERATOR])
def test_other_tenant_apartment_is_404(who, method, path):
    r = requests.request(method, f"{API}/app/apartments/{B_APT}{path}", headers=hdr(who), json={} if method == "POST" else None)
    # D-97: the simulator too looks the apartment up first: another organisation's reads as a missing one, for everyone
    assert r.status_code == 404, (who, method, path, r.text)
    assert r.json() == NOT_FOUND


def test_other_tenant_stream_is_404():
    with requests.get(f"{API}/app/apartments/{B_APT}/stream", headers=hdr(A_ADMIN), stream=True, timeout=10) as r:
        assert r.status_code == 404


def test_lists_hold_only_own_tenant():
    for who, own, other in ((A_ADMIN, A_APT, B_APT), (B_ADMIN, B_APT, A_APT)):
        ids = [a["apartment_id"] for a in requests.get(f"{API}/app/apartments", headers=hdr(who)).json()]
        assert own in ids and other not in ids
        admin_ids = [a["apartment_id"] for a in requests.get(f"{API}/app/admin/apartments", headers=hdr(who)).json()]
        assert own in admin_ids and other not in admin_ids
    a_emails = {u["email"] for u in requests.get(f"{API}/app/admin/users", headers=hdr(A_ADMIN)).json()}
    assert not {B_ADMIN, B_OPERATOR} & a_emails
    b_emails = {u["email"] for u in requests.get(f"{API}/app/admin/users", headers=hdr(B_ADMIN)).json()}
    assert b_emails == {B_ADMIN, B_OPERATOR}


def test_me_and_tenant_are_own():
    assert requests.get(f"{API}/app/me", headers=hdr(B_ADMIN)).json()["tenant"]["tenant_id"] == "t-altra-demo"
    assert requests.get(f"{API}/app/admin/tenant", headers=hdr(A_ADMIN)).json()["tenant_id"] == "t-flatsharing-demo"
    r = requests.patch(f"{API}/app/admin/tenant", headers=hdr(A_ADMIN), json={"enabled_features": ["devices"]})
    assert r.status_code == 200 and r.json()["tenant_id"] == "t-flatsharing-demo"
    assert requests.get(f"{API}/app/admin/tenant", headers=hdr(B_ADMIN)).json()["enabled_features"] != ["devices"]
    requests.patch(f"{API}/app/admin/tenant", headers=hdr(A_ADMIN), json={"clear_features": True})


# -------- admin routes on B's resources --------
def test_admin_cannot_touch_other_tenant_apartment():
    assert requests.patch(f"{API}/app/admin/apartments/{B_APT}", headers=hdr(A_ADMIN), json={"name": "x"}).status_code == 404
    assert requests.post(f"{API}/app/admin/apartments/{B_APT}/verify", headers=hdr(A_ADMIN)).status_code == 404
    r = requests.delete(f"{API}/app/admin/apartments/{B_APT}", headers=hdr(A_ADMIN))   # D-77: refused to every admin,
    assert r.status_code == 403 and r.json()["error"] == "platform_only"                # before any lookup: nothing leaks
    assert requests.get(f"{API}/app/apartments/{B_APT}", headers=hdr(B_ADMIN)).status_code == 200   # still there


def test_admin_cannot_touch_other_tenant_users():
    b_op = _uid(B_ADMIN, B_OPERATOR)
    assert requests.patch(f"{API}/app/admin/users/{b_op}", headers=hdr(A_ADMIN), json={"role": "viewer"}).status_code == 404
    assert requests.post(f"{API}/app/admin/users/{b_op}/invite", headers=hdr(A_ADMIN)).status_code == 404
    assert requests.delete(f"{API}/app/admin/users/{b_op}", headers=hdr(A_ADMIN)).status_code == 404
    assert _uid(B_ADMIN, B_OPERATOR) == b_op


def test_admin_cannot_give_other_tenant_apartment():
    r = requests.post(f"{API}/app/admin/users", headers=hdr(A_ADMIN),
                      json={"email": f"iso-{uuid.uuid4().hex[:6]}@demo.it", "role": "viewer", "apartment_ids": [B_APT]})
    assert r.status_code == 422 and r.json()["error"] == "unknown_apartment"


def test_invite_of_other_tenant_email_is_neutral():
    r = requests.post(f"{API}/app/admin/users", headers=hdr(A_ADMIN), json={"email": B_OPERATOR, "role": "viewer"})
    assert r.status_code == 409 and r.json()["message"] == "Questa email non può essere invitata"
    r = requests.post(f"{API}/app/admin/users", headers=hdr(A_ADMIN), json={"email": A_OPERATOR, "role": "viewer"})
    assert r.status_code == 409 and r.json()["message"] == "È già un utente della tua organizzazione"


def test_other_tenant_ids_and_codes_are_not_reusable():
    r = requests.post(f"{API}/app/platform/tenants/t-flatsharing-demo/apartments", headers=hdr(PLATFORM_ONLY),
                      json={"apartment_id": B_APT, "name": "x", "instance_url": "mock://builtin"})   # D-77: the platform
    assert r.status_code == 409 and r.json()["message"] == "Identificativo non disponibile"
    # D-72: the code is set by the platform only; even there B's code cannot be given to an apartment of A
    a_apts = f"{API}/app/platform/tenants/t-flatsharing-demo/apartments"
    r = requests.patch(f"{a_apts}/{A_APT}", headers=hdr(PLATFORM_ONLY), json={"italianway_id": B_CODE})
    assert r.status_code == 409 and r.json() == {"error": "external_id_in_use", "message": "Codice Italianway già in uso"}
    r = requests.post(a_apts, headers=hdr(PLATFORM_ONLY),
                      json={"apartment_id": f"apt-iso-{uuid.uuid4().hex[:6]}", "name": "x", "instance_url": "mock://builtin",
                            "italianway_id": B_CODE})
    assert r.status_code == 409 and r.json()["error"] == "external_id_in_use"
    assert requests.patch(f"{a_apts}/{A_APT}", headers=hdr(PLATFORM_ONLY),
                          json={"italianway_id": "IW-DEMO-RIMINI-01"}).status_code == 200   # own code: fine


# -------- webhook: a booking of B is routed to B and only B sees its log --------
def _signed(body: dict):
    raw = json.dumps(body).encode()
    return raw, {"Content-Type": "application/json", "X-Signature": hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()}


def test_webhook_of_other_tenant_routes_and_logs_only_there():
    res = f"RES-ISO-{uuid.uuid4().hex[:6]}"
    raw, headers = _signed({"event": "reservation.created", "id": f"iw-ev-{res}", "sent_at": "2026-11-01T10:00:00Z", "reservation": {
        "id": res, "apartment_id": B_CODE, "checkin": "2026-12-01T15:00:00Z", "checkout": "2026-12-03T10:00:00Z", "guests": 2}})
    r = requests.post(f"{API}/webhooks/italianway", data=raw, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["apartment_id"] == B_APT
    in_b = [l for l in requests.get(f"{API}/app/admin/webhook-logs", headers=hdr(B_ADMIN)).json() if l.get("booking_id") == res]
    in_a = [l for l in requests.get(f"{API}/app/admin/webhook-logs", headers=hdr(A_ADMIN)).json() if l.get("booking_id") == res]
    assert len(in_b) == 1 and in_a == []
    assert requests.get(f"{API}/app/apartments/{B_APT}/bookings", headers=hdr(A_ADMIN)).status_code == 404


# -------- platform role (P-36): separate from the organisations --------
PLATFORM_ONLY, PLATFORM_ADMIN = "piattaforma@demo.it", "m.cracchiolo@hqe.it"   # seed


def test_me_shows_platform_role():
    me = requests.get(f"{API}/app/me", headers=hdr(PLATFORM_ONLY)).json()
    assert me["tenant"] is None and me["role"] is None and me["user"]["platform_manager"] is True
    me = requests.get(f"{API}/app/me", headers=hdr(PLATFORM_ADMIN)).json()
    assert me["tenant"]["tenant_id"] == "t-flatsharing-demo" and me["role"] == "admin" and me["user"]["platform_manager"] is True
    me = requests.get(f"{API}/app/me", headers=hdr(A_ADMIN)).json()
    assert me["user"]["platform_manager"] is False


def test_platform_only_manager_has_no_organisation_routes():
    for path in ("/app/apartments", f"/app/apartments/{A_APT}", f"/app/apartments/{B_APT}/instance/apartment",
                 "/app/admin/users", "/app/admin/apartments", "/app/admin/webhook-logs", "/app/push/status"):
        r = requests.get(f"{API}{path}", headers=hdr(PLATFORM_ONLY))
        assert r.status_code in (401, 403), (path, r.status_code)
    with requests.get(f"{API}/app/apartments/{B_APT}/stream", headers=hdr(PLATFORM_ONLY), stream=True, timeout=10) as r:
        assert r.status_code in (401, 403)


def test_manager_with_organisation_sees_only_it():
    ids = [a["apartment_id"] for a in requests.get(f"{API}/app/apartments", headers=hdr(PLATFORM_ADMIN)).json()]
    assert B_APT not in ids
    assert requests.get(f"{API}/app/apartments/{B_APT}/instance/apartment", headers=hdr(PLATFORM_ADMIN)).status_code == 404


# -------- F6 / D-72: the Italianway code is set by the platform only (also in mock) --------
def test_admin_cannot_set_an_italianway_code():
    # B's admin could claim a free code (e.g. one belonging to a structure of A) before A: refused now
    r = requests.patch(f"{API}/app/admin/apartments/{B_APT}", headers=hdr(B_ADMIN), json={"italianway_id": "IW-PRESO-DA-B"})
    assert r.status_code == 403 and r.json()["error"] == "platform_only"
    r = requests.post(f"{API}/app/admin/apartments", headers=hdr(B_ADMIN),
                      json={"apartment_id": f"apt-f6-{uuid.uuid4().hex[:6]}", "name": "x", "instance_url": "mock://builtin",
                            "italianway_id": "IW-PRESO-DA-B"})
    assert r.status_code == 403 and r.json()["error"] == "platform_only"
    # the PWA form resending the SAME code with other changes still works
    r = requests.patch(f"{API}/app/admin/apartments/{B_APT}", headers=hdr(B_ADMIN), json={"name": "Via Altra 1", "italianway_id": B_CODE})
    assert r.status_code == 200 and r.json()["italianway_id"] == B_CODE
