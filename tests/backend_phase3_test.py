"""Phase 3 backend tests: admin users/apartments/features, webhook HMAC, simulator booking, push."""
import hashlib
import hmac
import json
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = BASE_URL + os.environ.get("BFF_API_PREFIX", "")  # "" = BFF diretto (/app/...); "/api" solo dietro un proxy che lo aggiunge
WEBHOOK_SECRET = "replace-me"

ADMIN = "m.cracchiolo@hqe.it"
ADMIN2 = "admin@demo.it"
OPERATOR = "operatore@demo.it"
VIEWER = "lettura@demo.it"


def hdr(email):
    return {"X-Dev-User": email, "Content-Type": "application/json"}


# -------- admin users --------
class TestAdminUsers:
    created_uid = None

    def test_list_users_has_at_least_4(self):
        r = requests.get(f"{API}/app/admin/users", headers=hdr(ADMIN))
        assert r.status_code == 200
        users = r.json()
        assert len(users) >= 4
        emails = {u["email"] for u in users}
        assert ADMIN in emails and VIEWER in emails

    def test_invite_user_pending(self):
        email = f"TEST_invite_{int(time.time())}@demo.it"
        r = requests.post(f"{API}/app/admin/users", headers=hdr(ADMIN),
                          json={"email": email, "role": "operator", "display_name": "Test Invite"})
        assert r.status_code == 201, r.text
        data = r.json()
        assert data["pending"] is True
        assert data["role"] == "operator"
        assert data["uid"].startswith("inv-")
        TestAdminUsers.created_uid = data["uid"]
        TestAdminUsers.created_email = email

    def test_invite_duplicate_returns_409(self):
        r = requests.post(f"{API}/app/admin/users", headers=hdr(ADMIN),
                          json={"email": TestAdminUsers.created_email, "role": "viewer"})
        assert r.status_code == 409

    def test_patch_role(self):
        uid = TestAdminUsers.created_uid
        r = requests.patch(f"{API}/app/admin/users/{uid}", headers=hdr(ADMIN), json={"role": "viewer"})
        assert r.status_code == 200
        assert r.json()["role"] == "viewer"

    def test_self_demotion_blocked(self):
        # find admin uid
        users = requests.get(f"{API}/app/admin/users", headers=hdr(ADMIN)).json()
        me = next(u for u in users if u["email"] == ADMIN)
        r = requests.patch(f"{API}/app/admin/users/{me['uid']}", headers=hdr(ADMIN), json={"role": "viewer"})
        assert r.status_code == 409
        assert r.json()["error"] == "self_demotion"

    def test_self_delete_blocked(self):
        users = requests.get(f"{API}/app/admin/users", headers=hdr(ADMIN)).json()
        me = next(u for u in users if u["email"] == ADMIN)
        r = requests.delete(f"{API}/app/admin/users/{me['uid']}", headers=hdr(ADMIN))
        assert r.status_code == 409

    def test_delete_invited_user(self):
        uid = TestAdminUsers.created_uid
        r = requests.delete(f"{API}/app/admin/users/{uid}", headers=hdr(ADMIN))
        assert r.status_code == 204

    def test_viewer_forbidden(self):
        r = requests.get(f"{API}/app/admin/users", headers=hdr(VIEWER))
        assert r.status_code == 403


# -------- admin apartments --------
PLATFORM = "piattaforma@demo.it"   # seed platform manager without an organisation
PLAT_APTS = f"{API}/app/platform/tenants/t-flatsharing-demo/apartments"


def plat(method, url, **kw):
    return requests.request(method, url, headers=hdr(PLATFORM), **kw)


def test_admin_cannot_create_relink_or_delete_apartments_in_mock_mode():
    """D-77: also in staging (INSTANCE_MODE=mock) only the platform creates, relinks and deletes apartments (as D-64)."""
    r = requests.post(f"{API}/app/admin/apartments", headers=hdr(ADMIN),
                      json={"apartment_id": "apt-d77-admin", "name": "x", "instance_url": "mock://builtin"})
    assert r.status_code == 403 and r.json()["error"] == "platform_only", r.text
    for apt_id in ("apt-bologna-01", "apt-inesistente", "apt-altra-01"):   # own, missing, other tenant: same answer
        r = requests.delete(f"{API}/app/admin/apartments/{apt_id}", headers=hdr(ADMIN))
        assert r.status_code == 403 and r.json()["error"] == "platform_only", (apt_id, r.text)
    for change in ({"port": 8100}, {"instance_url": "mock://altro"}):
        r = requests.patch(f"{API}/app/admin/apartments/apt-bologna-01", headers=hdr(ADMIN), json=change)
        assert r.status_code == 403 and r.json()["error"] == "platform_only", (change, r.text)
    # the form resending the same link, with the admin's own fields, still works
    r = requests.patch(f"{API}/app/admin/apartments/apt-bologna-01", headers=hdr(ADMIN),
                       json={"name": "Corso Italia 5 – int. 7", "instance_url": "mock://builtin", "port": None, "enabled": True})
    assert r.status_code == 200 and r.json()["instance_url"] == "mock://builtin"
    assert requests.get(f"{API}/app/apartments/apt-bologna-01", headers=hdr(ADMIN)).status_code == 200


class TestAdminApartments:
    APT_ID = "apt-test-01"

    def test_list_apartments(self):
        r = requests.get(f"{API}/app/admin/apartments", headers=hdr(ADMIN))
        assert r.status_code == 200
        ids = {a["apartment_id"] for a in r.json()}
        assert "apt-rimini-01" in ids and "apt-bologna-01" in ids

    def test_create_apartment(self):
        # D-77: created by the platform, then managed by the organisation's admin
        r = plat("POST", PLAT_APTS, json={"apartment_id": self.APT_ID, "name": "Test Apt",
                                          "instance_url": "mock://builtin", "timezone": "Europe/Rome"})
        assert r.status_code == 201, r.text
        assert self.APT_ID in {a["apartment_id"] for a in requests.get(f"{API}/app/admin/apartments", headers=hdr(ADMIN)).json()}

    def test_duplicate_returns_409(self):
        r = plat("POST", PLAT_APTS, json={"apartment_id": self.APT_ID, "name": "Dup",
                                          "instance_url": "mock://builtin", "timezone": "Europe/Rome"})
        assert r.status_code == 409

    def test_invalid_timezone(self):
        r = plat("POST", PLAT_APTS, json={"apartment_id": "apt-bad-tz", "name": "Bad TZ",
                                          "instance_url": "mock://builtin", "timezone": "Fake/Zone"})
        assert r.status_code == 422
        r = requests.patch(f"{API}/app/admin/apartments/{self.APT_ID}", headers=hdr(ADMIN), json={"timezone": "Fake/Zone"})
        assert r.status_code == 422 and r.json()["error"] == "invalid_timezone"

    def test_patch_apartment(self):
        r = requests.patch(f"{API}/app/admin/apartments/{self.APT_ID}", headers=hdr(ADMIN), json={"name": "Renamed"})
        assert r.status_code == 200 and r.json()["name"] == "Renamed"
        # D-72: the Italianway code is the platform's (ADMIN is also a seed platform manager)
        r = requests.patch(f"{API}/app/admin/apartments/{self.APT_ID}", headers=hdr(ADMIN), json={"italianway_id": "IW-TEST-01"})
        assert r.status_code == 403 and r.json()["error"] == "platform_only"
        r = requests.patch(f"{API}/app/platform/tenants/t-flatsharing-demo/apartments/{self.APT_ID}", headers=hdr(ADMIN),
                           json={"italianway_id": "IW-TEST-01"})
        assert r.status_code == 200 and r.json()["italianway_id"] == "IW-TEST-01"
        rows = requests.get(f"{API}/app/admin/apartments", headers=hdr(ADMIN)).json()
        assert next(a for a in rows if a["apartment_id"] == self.APT_ID)["italianway_id"] == "IW-TEST-01"   # the admin reads it

    def test_verify_rimini(self):
        r = requests.post(f"{API}/app/admin/apartments/apt-rimini-01/verify", headers=hdr(ADMIN))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["health"]["status_code"] == 200
        assert data["version"]["body"].get("contract_version")

    def test_verify_created_apt(self):
        r = requests.post(f"{API}/app/admin/apartments/{self.APT_ID}/verify", headers=hdr(ADMIN))
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_delete_apartment(self):
        assert requests.delete(f"{API}/app/admin/apartments/{self.APT_ID}", headers=hdr(ADMIN)).status_code == 403
        assert plat("DELETE", f"{PLAT_APTS}/{self.APT_ID}").status_code == 204


# -------- instance URL (D-28): the BFF under test runs with INSTANCE_MODE=mock --------
class TestInstanceUrl:
    APT_ID = "apt-test-url"

    def _create(self, url, apt_id=None):
        return plat("POST", PLAT_APTS, json={"apartment_id": apt_id or self.APT_ID, "name": "Url", "instance_url": url})

    def test_real_url_refused_in_mock_mode(self):
        for url in ("https://domotica.esempio.it", "10.198.0.2:8100", "domotica.esempio.it"):
            r = self._create(url, "apt-test-url-bad")
            assert r.status_code == 422, (url, r.text)
            body = r.json()
            assert body["error"] == "invalid_instance_url"
            assert "mock://builtin" in body["message"]

    def test_mock_url_is_normalized(self):
        r = self._create("  MOCK://builtin ")
        assert r.status_code == 201, r.text
        assert r.json()["instance_url"] == "mock://builtin"

    def test_new_apartment_answers(self):
        r = requests.post(f"{API}/app/admin/apartments/{self.APT_ID}/verify", headers=hdr(ADMIN))
        assert r.status_code == 200
        assert r.json()["ok"] is True and r.json()["error"] is None
        r = requests.get(f"{API}/app/apartments/{self.APT_ID}/instance/health", headers=hdr(ADMIN))
        assert r.status_code == 200, r.text

    def test_verify_stores_last_check(self):
        # D-64: the outcome of the last 'Verifica connessione' is kept and shown in the admin list
        apts = {a["apartment_id"]: a for a in requests.get(f"{API}/app/admin/apartments", headers=hdr(ADMIN)).json()}
        lc = apts[self.APT_ID]["last_check"]
        assert lc["ok"] is True and lc["error"] is None and lc["checked_at"]

    def test_patch_to_real_url_refused(self):
        r = plat("PATCH", f"{PLAT_APTS}/{self.APT_ID}", json={"instance_url": "https://domotica.esempio.it"})
        assert r.status_code == 422
        assert r.json()["error"] == "invalid_instance_url"
        r = requests.patch(f"{API}/app/admin/apartments/{self.APT_ID}", headers=hdr(ADMIN),
                           json={"instance_url": "https://domotica.esempio.it"})
        assert r.status_code == 403 and r.json()["error"] == "platform_only"   # D-77: the link is the platform's
        r = requests.patch(f"{API}/app/admin/apartments/{self.APT_ID}", headers=hdr(ADMIN), json={"name": "Solo nome"})
        assert r.status_code == 200 and r.json()["instance_url"] == "mock://builtin"

    def test_secret_name_not_accepted_nor_returned(self):
        # P-36 S3 (D-60): the admin no longer chooses which secret the BFF sends to the instance
        r = requests.patch(f"{API}/app/admin/apartments/{self.APT_ID}", headers=hdr(ADMIN),
                           json={"instance_secret_name": "smtp-app-password"})
        assert r.status_code == 422 and r.json()["error"] == "secret_name_not_allowed"
        r = requests.patch(f"{API}/app/admin/apartments/{self.APT_ID}", headers=hdr(ADMIN),
                           json={"instance_secret_name": None, "name": "Con null"})
        assert r.status_code == 200 and "instance_secret_name" not in r.json()   # null still accepted (PWA form)
        assert all("instance_secret_name" not in a for a in requests.get(f"{API}/app/admin/apartments", headers=hdr(ADMIN)).json())

    def test_cleanup(self):
        assert plat("DELETE", f"{PLAT_APTS}/{self.APT_ID}").status_code == 204


# -------- features --------
class TestFeatures:
    def test_tenant_has_all_features(self):
        r = requests.get(f"{API}/app/admin/tenant", headers=hdr(ADMIN))
        assert r.status_code == 200
        assert "energy" in r.json()["all_features"]

    def test_tenant_disable_energy_and_apartment_override(self):
        # disable energy at tenant
        all_minus_energy = [f for f in ["apartment", "devices", "commands", "schedule",
                                        "rules", "approvals", "decisions", "ask"]]
        r = requests.patch(f"{API}/app/admin/tenant", headers=hdr(ADMIN),
                           json={"enabled_features": all_minus_energy})
        assert r.status_code == 200

        # summary excludes energy
        r = requests.get(f"{API}/app/apartments", headers=hdr(ADMIN))
        for apt in r.json():
            assert "energy" not in apt.get("features", [])

        # instance proxy energy returns 501
        r = requests.get(f"{API}/app/apartments/apt-rimini-01/instance/energy?from=2026-01-01T00:00:00Z&to=2026-01-02T00:00:00Z&bucket=hour",
                         headers=hdr(ADMIN))
        assert r.status_code == 501
        assert r.json()["error"] == "not_implemented"

        # override rimini with full list
        full = ["apartment", "devices", "commands", "energy", "schedule", "rules", "approvals", "decisions", "ask"]
        r = requests.patch(f"{API}/app/admin/apartments/apt-rimini-01", headers=hdr(ADMIN),
                           json={"enabled_features": full})
        assert r.status_code == 200

        # now energy works on rimini
        r = requests.get(f"{API}/app/apartments/apt-rimini-01/instance/energy?from=2026-01-01T00:00:00Z&to=2026-01-02T00:00:00Z&bucket=hour",
                         headers=hdr(ADMIN))
        assert r.status_code == 200, r.text

        # bologna remains disabled
        r = requests.get(f"{API}/app/apartments/apt-bologna-01/instance/energy?from=2026-01-01T00:00:00Z&to=2026-01-02T00:00:00Z&bucket=hour",
                         headers=hdr(ADMIN))
        assert r.status_code == 501

    def test_cleanup_features(self):
        r = requests.patch(f"{API}/app/admin/tenant", headers=hdr(ADMIN), json={"clear_features": True})
        assert r.status_code == 200
        r = requests.patch(f"{API}/app/admin/apartments/apt-rimini-01", headers=hdr(ADMIN),
                           json={"clear_features": True})
        assert r.status_code == 200


# -------- webhook --------
def _sign(raw: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


class TestWebhook:
    def _payload(self, event="reservation.created", ext="IW-DEMO-RIMINI-01", res_id="RES-100"):
        return {
            "event": event,
            "id": f"iw-ev-{event}-{res_id}-{int(time.time()*1000)}",
            "sent_at": "2026-11-01T10:00:00Z",
            "reservation": {
                "id": res_id,
                "apartment_id": ext,
                "checkin": "2026-12-01T15:00:00Z",
                "checkout": "2026-12-05T11:00:00Z",
                "guests": 2,
            },
        }

    def test_valid_signature_accepted(self):
        payload = self._payload(res_id=f"RES-{int(time.time())}")
        raw = json.dumps(payload).encode()
        r = requests.post(f"{API}/webhooks/italianway", data=raw,
                          headers={"X-Signature": _sign(raw), "Content-Type": "application/json"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("accepted") is True
        assert "schedule_ids" in body
        TestWebhook._last_raw = raw

    def test_duplicate_event(self):
        r = requests.post(f"{API}/webhooks/italianway", data=TestWebhook._last_raw,
                          headers={"X-Signature": _sign(TestWebhook._last_raw), "Content-Type": "application/json"})
        assert r.status_code == 200
        assert r.json().get("duplicate") is True

    @pytest.mark.parametrize("incoming", ["iw-12345", "", "12345678123456781234567812345678"])
    def test_correlation_id_not_a_uuid_still_delivers(self, incoming):
        # Fable D-75 note 2: the engine contract wants a UUID; Italianway's own id must not cost a booking
        raw = json.dumps(self._payload(res_id=f"RES-corr-{uuid.uuid4().hex[:8]}")).encode()
        r = requests.post(f"{API}/webhooks/italianway", data=raw,
                          headers={"X-Signature": _sign(raw), "Content-Type": "application/json", "X-Correlation-Id": incoming})
        assert r.status_code == 200, r.text
        assert r.json()["accepted"] is True and str(uuid.UUID(r.json()["correlation_id"])) == r.json()["correlation_id"]

    def test_sha256_prefix(self):
        payload = self._payload(res_id=f"RES-pfx-{int(time.time())}")
        raw = json.dumps(payload).encode()
        r = requests.post(f"{API}/webhooks/italianway", data=raw,
                          headers={"X-Signature": f"sha256={_sign(raw)}", "Content-Type": "application/json"})
        assert r.status_code == 200

    def test_wrong_signature(self):
        payload = self._payload()
        raw = json.dumps(payload).encode()
        r = requests.post(f"{API}/webhooks/italianway", data=raw,
                          headers={"X-Signature": "a" * 64, "Content-Type": "application/json"})
        assert r.status_code == 401
        assert r.json()["error"] == "invalid_signature"

    def test_missing_header(self):
        payload = self._payload()
        raw = json.dumps(payload).encode()
        r = requests.post(f"{API}/webhooks/italianway", data=raw,
                          headers={"Content-Type": "application/json"})
        assert r.status_code == 401

    def test_unknown_apartment(self):
        payload = self._payload(ext="IW-UNKNOWN-999")
        raw = json.dumps(payload).encode()
        r = requests.post(f"{API}/webhooks/italianway", data=raw,
                          headers={"X-Signature": _sign(raw), "Content-Type": "application/json"})
        assert r.status_code == 404
        assert r.json()["error"] == "unknown_apartment"

    def test_unknown_event(self):
        payload = {"event": "reservation.unknown", "id": "x", "sent_at": "2026-11-01T10:00:00Z",
                   "reservation": {"id": "r1", "apartment_id": "IW-DEMO-RIMINI-01",
                                   "checkin": "2026-12-01T15:00:00Z", "checkout": "2026-12-05T11:00:00Z"}}
        raw = json.dumps(payload).encode()
        r = requests.post(f"{API}/webhooks/italianway", data=raw,
                          headers={"X-Signature": _sign(raw), "Content-Type": "application/json"})
        assert r.status_code == 422

    def test_invalid_json_with_valid_signature(self):
        raw = b"{not json"
        r = requests.post(f"{API}/webhooks/italianway", data=raw,
                          headers={"X-Signature": _sign(raw), "Content-Type": "application/json"})
        assert r.status_code == 400


# -------- simulator booking --------
class TestSimulatorBooking:
    def test_admin_can_send(self):
        body = {
            "event_id": f"sim-ev-{int(time.time()*1000)}",
            "type": "booking_created",
            "booking_id": f"BK-{int(time.time())}",
            "checkin_at": "2026-12-10T15:00:00Z",
            "checkout_at": "2026-12-14T11:00:00Z",
            "guests": 3,
            "ts": "2026-11-01T12:00:00Z",
        }
        r = requests.post(f"{API}/app/apartments/apt-rimini-01/simulator/booking",
                          headers=hdr(ADMIN), json=body)
        assert r.status_code == 200, r.text
        assert r.json().get("accepted") is True

    def test_viewer_forbidden(self):
        r = requests.post(f"{API}/app/apartments/apt-rimini-01/simulator/booking",
                          headers=hdr(VIEWER), json={})
        assert r.status_code == 403

    def test_operator_forbidden(self):
        r = requests.post(f"{API}/app/apartments/apt-rimini-01/simulator/booking",
                          headers=hdr(OPERATOR), json={})
        assert r.status_code == 403

    def test_invalid_dates(self):
        body = {
            "event_id": f"sim-bad-{int(time.time()*1000)}",
            "type": "booking_created",
            "booking_id": f"BK-bad-{int(time.time())}",
            "checkin_at": "2026-12-14T11:00:00Z",
            "checkout_at": "2026-12-10T15:00:00Z",
            "guests": 2,
            "ts": "2026-11-01T12:00:00Z",
        }
        r = requests.post(f"{API}/app/apartments/apt-rimini-01/simulator/booking",
                          headers=hdr(ADMIN), json=body)
        assert r.status_code == 422
        assert r.json().get("error") == "invalid_dates"


# -------- push --------
class TestPush:
    TOKEN = "test-token-1234567890"

    def test_status_initial(self):
        r = requests.get(f"{API}/app/push/status", headers=hdr(ADMIN))
        assert r.status_code == 200
        data = r.json()
        assert data["fcm_enabled"] is False
        assert "prefs" in data

    def test_subscribe(self):
        r = requests.post(f"{API}/app/push/subscribe", headers=hdr(ADMIN), json={"token": self.TOKEN})
        assert r.status_code == 200
        data = r.json()
        assert data["subscribed"] is True
        assert data["tokens"] >= 1

    def test_set_prefs(self):
        r = requests.put(f"{API}/app/me/notification-prefs", headers=hdr(ADMIN),
                         json={"approvals": False, "offline": True, "decisions": True})
        assert r.status_code == 200
        data = r.json()
        assert data["approvals"] is False
        assert data["offline"] is True

        # visible in /me
        r = requests.get(f"{API}/app/me", headers=hdr(ADMIN))
        prefs = r.json()["user"]["notification_prefs"]
        assert prefs["approvals"] is False
        assert prefs["offline"] is True

    def test_unsubscribe(self):
        r = requests.delete(f"{API}/app/push/subscribe", headers=hdr(ADMIN), json={"token": self.TOKEN})
        assert r.status_code == 200
        assert r.json()["tokens"] == 0

    def test_restore_prefs(self):
        r = requests.put(f"{API}/app/me/notification-prefs", headers=hdr(ADMIN),
                         json={"approvals": True, "offline": True, "decisions": True})
        assert r.status_code == 200


# -------- energy stay (booking archive in the BFF; the contract has only current_booking_id) --------
class TestEnergyStay:
    def test_rimini_occupied_has_current_booking_id_only(self):
        r = requests.get(f"{API}/app/apartments/apt-rimini-01/instance/apartment", headers=hdr(ADMIN))
        assert r.status_code == 200
        data = r.json()
        assert data.get("occupancy") == "occupied"
        assert data.get("current_booking_id")
        assert "current_checkin" not in data

    def test_bookings_archive_endpoint(self):
        r = requests.get(f"{API}/app/apartments/apt-rimini-01/bookings", headers=hdr(ADMIN))
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list) and r.json()["items"]   # the webhook class above booked here
        # D-90: technical fields nobody shows are not sent
        assert all(not {"event_ids", "last_event_type", "updated_at", "source"} & set(b) for b in r.json()["items"])


# -------- P-18 (D-41, D-43, D-45): apartments per user --------
OWNER = "proprietario@demo.it"  # seeded viewer, only apt-rimini-01
OUTSIDE = "apt-bologna-01"


def _stream_status(email, apt):
    with requests.get(f"{API}/app/apartments/{apt}/stream", headers=hdr(email), stream=True, timeout=10) as r:
        return r.status_code


class TestApartmentScope:
    def test_list_shows_only_own_apartments(self):
        r = requests.get(f"{API}/app/apartments", headers=hdr(OWNER))
        assert r.status_code == 200
        assert [a["apartment_id"] for a in r.json()] == ["apt-rimini-01"]

    def test_outside_apartment_is_404_everywhere(self):
        for path in ("", "/instance/apartment", "/instance/energy?from=2026-10-01T00:00:00.000Z&to=2026-10-02T00:00:00.000Z&bucket=day",
                     "/instance/approvals", "/bookings"):
            r = requests.get(f"{API}/app/apartments/{OUTSIDE}{path}", headers=hdr(OWNER))
            assert r.status_code == 404, (path, r.text)
            assert r.json()["message"] == "Appartamento inesistente"
        assert _stream_status(OWNER, OUTSIDE) == 404

    def test_own_apartment_works(self):
        assert requests.get(f"{API}/app/apartments/apt-rimini-01", headers=hdr(OWNER)).status_code == 200
        assert requests.get(f"{API}/app/apartments/apt-rimini-01/instance/apartment", headers=hdr(OWNER)).status_code == 200
        assert _stream_status(OWNER, "apt-rimini-01") == 200

    def test_me_and_admin_list_show_the_scope(self):
        assert requests.get(f"{API}/app/me", headers=hdr(OWNER)).json()["user"]["apartment_ids"] == ["apt-rimini-01"]
        assert requests.get(f"{API}/app/me", headers=hdr(ADMIN)).json()["user"]["apartment_ids"] == "all"
        by_email = {u["email"]: u["apartment_ids"] for u in requests.get(f"{API}/app/admin/users", headers=hdr(ADMIN)).json()}
        assert by_email[OWNER] == ["apt-rimini-01"] and by_email[VIEWER] == "all" and by_email[ADMIN] == "all"


class TestApartmentScopeAdmin:
    EMAIL = "scope-test@demo.it"
    uid = None

    def _patch(self, body):
        return requests.patch(f"{API}/app/admin/users/{TestApartmentScopeAdmin.uid}", headers=hdr(ADMIN), json=body)

    def test_invite_with_list_and_validation(self):
        r = requests.post(f"{API}/app/admin/users", headers=hdr(ADMIN),
                          json={"email": self.EMAIL, "role": "viewer", "apartment_ids": [OUTSIDE, OUTSIDE]})
        assert r.status_code == 201, r.text
        assert r.json()["apartment_ids"] == [OUTSIDE]  # duplicates removed
        TestApartmentScopeAdmin.uid = r.json()["uid"]
        r = requests.post(f"{API}/app/admin/users", headers=hdr(ADMIN),
                          json={"email": "scope-x@demo.it", "role": "viewer", "apartment_ids": ["apt-altrui"]})
        assert r.status_code == 422 and r.json()["error"] == "unknown_apartment"
        assert r.json()["details"]["apartment_ids"] == ["apt-altrui"]
        r = requests.post(f"{API}/app/admin/users", headers=hdr(ADMIN),
                          json={"email": "scope-y@demo.it", "role": "admin", "apartment_ids": [OUTSIDE]})
        assert r.status_code == 422 and r.json()["error"] == "admin_all_apartments"
        r = requests.post(f"{API}/app/admin/users", headers=hdr(ADMIN), json={"email": "scope-z@demo.it", "role": "viewer"})
        assert r.status_code == 201 and r.json()["apartment_ids"] == "all"

    def test_restriction_applies_at_next_request(self):
        assert [a["apartment_id"] for a in requests.get(f"{API}/app/apartments", headers=hdr(self.EMAIL)).json()] == [OUTSIDE]
        assert self._patch({"apartment_ids": []}).json()["apartment_ids"] == []
        assert requests.get(f"{API}/app/apartments", headers=hdr(self.EMAIL)).json() == []
        assert requests.get(f"{API}/app/apartments/{OUTSIDE}", headers=hdr(self.EMAIL)).status_code == 404

    def test_patch_rules(self):
        r = self._patch({"apartment_ids": None})
        assert r.status_code == 422 and r.json()["error"] == "invalid_apartment_ids"
        assert self._patch({"display_name": "Solo nome"}).json()["apartment_ids"] == []  # missing = no change
        r = self._patch({"role": "admin", "apartment_ids": ["apt-rimini-01"]})
        assert r.status_code == 422 and r.json()["error"] == "admin_all_apartments"
        assert self._patch({"role": "admin"}).json()["apartment_ids"] == "all"  # promotion resets the list
        assert self._patch({"role": "viewer"}).json()["apartment_ids"] == "all"  # demotion does not revive it
        assert self._patch({"apartment_ids": ["apt-rimini-01"]}).json()["apartment_ids"] == ["apt-rimini-01"]
        assert self._patch({"apartment_ids": "all"}).json()["apartment_ids"] == "all"

    def test_deleted_apartment_leaves_lists_but_never_opens_all(self):
        tmp = "apt-scope-tmp"
        r = plat("POST", PLAT_APTS, json={"apartment_id": tmp, "name": "Tmp", "instance_url": "mock://builtin"})
        assert r.status_code == 201, r.text
        assert self._patch({"apartment_ids": [tmp]}).status_code == 200
        r = requests.post(f"{API}/app/admin/users", headers=hdr(ADMIN),
                          json={"email": "scope-two@demo.it", "role": "operator", "apartment_ids": [tmp, "apt-rimini-01"]})
        assert r.status_code == 201
        two = r.json()["uid"]
        assert plat("DELETE", f"{PLAT_APTS}/{tmp}").status_code == 204
        by_uid = {u["uid"]: u["apartment_ids"] for u in requests.get(f"{API}/app/admin/users", headers=hdr(ADMIN)).json()}
        assert by_uid[TestApartmentScopeAdmin.uid] == []        # emptied, NOT "all"
        assert by_uid[two] == ["apt-rimini-01"]
        assert requests.get(f"{API}/app/apartments", headers=hdr(self.EMAIL)).json() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# -------- P-47: the admin's own actions in the organisation's log --------
def test_admin_actions_are_logged():
    email = f"registro-{uuid.uuid4().hex[:6]}@demo.it"
    r = requests.post(f"{API}/app/admin/users", headers=hdr(ADMIN), json={"email": email, "role": "viewer",
                                                                          "apartment_ids": ["apt-rimini-01"]})
    assert r.status_code == 201, r.text
    uid = r.json()["uid"]
    assert requests.patch(f"{API}/app/admin/users/{uid}", headers=hdr(ADMIN), json={"role": "operator"}).status_code == 200
    assert requests.patch(f"{API}/app/admin/users/{uid}", headers=hdr(ADMIN), json={"apartment_ids": "all"}).status_code == 200
    before = requests.get(f"{API}/app/admin/audit", headers=hdr(ADMIN), params={"limit": 100}).json()["items"]
    assert {i["target"]["label"] for i in before if i["target"]["id"] == uid} == {email}      # a member: readable
    assert requests.delete(f"{API}/app/admin/users/{uid}", headers=hdr(ADMIN)).status_code == 204
    r = requests.patch(f"{API}/app/admin/apartments/apt-bologna-01", headers=hdr(ADMIN),
                       json={"address": f"Via Registro {uuid.uuid4().hex[:4]}", "name": "Corso Italia 5 – int. 7"})
    assert r.status_code == 200
    items = requests.get(f"{API}/app/admin/audit", headers=hdr(ADMIN), params={"limit": 100}).json()["items"]
    mine = [i for i in items if i["target"]["id"] == uid]
    assert [i["action"] for i in mine] == ["user_removed", "scope_changed", "role_changed", "invite_sent"]
    sent, role, scope = mine[3], mine[2], mine[1]
    assert sent["details"] == {"role": "viewer", "apartment_ids": ["apt-rimini-01"]}
    # D-91: once removed, the person reads «utente rimosso» in every entry (as in the decisions)
    assert all(i["target"]["removed"] is True and i["target"]["label"] is None for i in mine)
    assert role["details"] == {"from": "viewer", "to": "operator"} and scope["details"] == {"to": "all"}
    assert sent["actor"] == {"kind": "user", "email": ADMIN, "display_name": "Massimiliano Cracchiolo", "removed": False,
                             "role": "admin"}
    updated = next(i for i in items if i["action"] == "apartment_updated" and i["target"]["id"] == "apt-bologna-01")
    assert updated["details"] == {"fields": ["address"]}                       # the name was sent unchanged: not listed


# -------- P-48 (D-87): the engine gets a pseudonym, the app sees the email --------
def test_engine_sees_a_pseudonym_the_app_sees_the_email():
    corr = str(uuid.uuid4())
    base = f"{API}/app/apartments/apt-rimini-01/instance"
    h = {**hdr(ADMIN), "X-Correlation-Id": corr}
    assert requests.post(f"{base}/apartment/hold", headers=h, json={"minutes": 30, "mode": "eco"}).status_code == 202
    # straight from the built-in engine (loopback, the run's fixed key): no email anywhere
    raw = requests.get(f"{API}/mock/apt-rimini-01/api/v1/decisions", params={"correlation_id": corr},
                       headers={"X-API-Key": "dev-key", "X-Actor": "system:prova", "X-Correlation-Id": str(uuid.uuid4())})
    assert raw.status_code == 200, raw.text
    engine = [d["actor"] for d in raw.json()["items"]]
    assert engine and all(a.startswith("user:p-") and a.endswith("@pseudo.hqe.it") for a in engine), engine
    assert ADMIN not in raw.text
    apt_raw = requests.get(f"{API}/mock/apt-rimini-01/api/v1/apartment",
                           headers={"X-API-Key": "dev-key", "X-Actor": "system:prova", "X-Correlation-Id": str(uuid.uuid4())})
    assert apt_raw.json()["hold"]["set_by"].endswith("@pseudo.hqe.it")
    # through the BFF: the email of the member
    shown = requests.get(f"{base}/decisions", headers=hdr(ADMIN), params={"correlation_id": corr}).json()["items"]
    assert {d["actor"] for d in shown} == {f"user:{ADMIN}"}
    assert requests.get(f"{base}/apartment", headers=hdr(ADMIN)).json()["hold"]["set_by"] == ADMIN
    summary = requests.get(f"{API}/app/apartments/apt-rimini-01", headers=hdr(ADMIN)).json()
    assert summary["apartment"]["hold"]["set_by"] == ADMIN
    # a filter by person still works
    by_me = requests.get(f"{base}/decisions", headers=hdr(ADMIN), params={"actor": f"user:{ADMIN}", "correlation_id": corr})
    assert {d["actor"] for d in by_me.json()["items"]} == {f"user:{ADMIN}"}
    # another member of the same organisation sees the same email
    other = requests.get(f"{base}/decisions", headers=hdr("operatore@demo.it"), params={"correlation_id": corr}).json()
    assert {d["actor"] for d in other["items"]} == {f"user:{ADMIN}"}
    requests.post(f"{base}/apartment/hold", headers={**hdr(ADMIN), "X-Correlation-Id": str(uuid.uuid4())}, json={"minutes": 0})


# -------- P-51 (D-90): what each role receives --------
def test_reader_cannot_read_asks_and_only_the_admin_reads_the_version():
    base = f"{API}/app/apartments/apt-rimini-01/instance"
    r = requests.get(f"{base}/ask/ask-qualsiasi", headers=hdr("lettura@demo.it"))
    assert r.status_code == 403 and r.json()["error"] == "forbidden"
    assert requests.get(f"{base}/version", headers=hdr("operatore@demo.it")).status_code == 403
    assert requests.get(f"{base}/version", headers=hdr("lettura@demo.it")).status_code == 403
    assert requests.get(f"{base}/version", headers=hdr(ADMIN)).status_code == 200


def test_unused_fields_are_not_sent():
    s = requests.get(f"{API}/app/apartments/apt-rimini-01", headers=hdr(ADMIN)).json()
    assert not {"instance_features", "reachable"} & set(s)
    gone = {"devices", "uptime_s", "database", "checked_at", "apartment_id"}
    assert s["health"] and not gone & set(s["health"])
    h = requests.get(f"{API}/app/apartments/apt-rimini-01/instance/health", headers=hdr(ADMIN)).json()
    assert h.get("status") and not gone & set(h)
    rows = requests.get(f"{API}/app/admin/apartments", headers=hdr(ADMIN)).json()
    assert all(not {"tenant_id", "created_at", "external_ids"} & set(a) for a in rows)
    items = requests.get(f"{API}/app/admin/audit", headers=hdr(ADMIN)).json()["items"]
    assert items and all("tenant_id" not in i and "uid" not in i["actor"] for i in items)


# -------- P-52 (D-92): the Excel report against the built-in engine --------
def test_energy_export_against_the_engine():
    month = time.strftime("%Y-%m", time.gmtime())
    r = requests.get(f"{API}/app/apartments/apt-rimini-01/energy/export", headers=hdr("lettura@demo.it"), params={"month": month})
    assert r.status_code == 200, r.text
    assert r.headers["Content-Type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert r.content[:2] == b"PK" and f"consumi-apt-rimini-01-{month}.xlsx" in r.headers["Content-Disposition"]
    r = requests.get(f"{API}/app/apartments/apt-bologna-01/energy/export", headers=hdr("proprietario@demo.it"),
                     params={"month": month})
    assert r.status_code == 404                                        # outside the viewer's apartments


# -------- D-97: the reset of a demonstration apartment, against the built-in engine --------
def test_reset_brings_back_the_initial_state():
    base = f"{API}/app/apartments/apt-bologna-01"
    initial = requests.get(f"{base}/instance/apartment", headers=hdr(ADMIN)).json()
    h = {**hdr(ADMIN), "X-Correlation-Id": str(uuid.uuid4())}
    assert requests.post(f"{base}/instance/apartment/hold", headers=h, json={"minutes": 45, "mode": "eco"}).status_code == 202
    assert requests.get(f"{base}/instance/apartment", headers=hdr(ADMIN)).json()["hold"] is not None
    assert requests.post(f"{base}/simulator/reset", headers=hdr("operatore@demo.it")).status_code == 403
    assert requests.post(f"{base}/simulator/reset", headers=hdr(ADMIN)).status_code == 204
    after = requests.get(f"{base}/instance/apartment", headers=hdr(ADMIN)).json()
    assert after["hold"] == initial["hold"] and after["mode"] == initial["mode"]
    assert requests.get(f"{base}/bookings", headers=hdr(ADMIN)).json()["items"] == []
    items = requests.get(f"{API}/app/admin/audit", headers=hdr(ADMIN)).json()["items"]
    assert items[0]["action"] == "simulator_reset" and items[0]["target"]["id"] == "apt-bologna-01"
