"""Phase 4 regression: booking archive + current_checkin removal + webhook archive."""
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import UTC, datetime, timedelta

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = BASE_URL + os.environ.get("BFF_API_PREFIX", "")  # "" = BFF diretto (/app/...); "/api" solo dietro un proxy che lo aggiunge
ADMIN = "m.cracchiolo@hqe.it"
VIEWER = "lettura@demo.it"
OPERATOR = "operatore@demo.it"
SECRET = "replace-me"


def _hdr(user: str = ADMIN) -> dict:
    return {"X-Dev-User": user, "Content-Type": "application/json"}


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# Shared ids for cleanup across tests
STATE = {}


@pytest.fixture(scope="module", autouse=True)
def _cleanup():
    yield
    # Cancel what we created on bologna
    now = datetime.now(UTC)
    for bid in (STATE.get("cur"), STATE.get("prev"), STATE.get("iw")):
        if not bid:
            continue
        payload = {
            "event_id": f"cleanup-{bid}-{secrets.token_hex(4)}",
            "type": "booking_cancelled",
            "booking_id": bid,
            "checkin_at": _iso(now - timedelta(days=1)),
            "checkout_at": _iso(now + timedelta(days=1)),
            "guests": 1,
            "source": "simulator",
            "ts": _iso(now),
        }
        try:
            requests.post(f"{API}/app/apartments/apt-bologna-01/simulator/booking",
                          headers=_hdr(), json=payload, timeout=10)
        except Exception:
            pass


# -----------------------------------------------------------
# 1) GET /apartment must NOT contain current_checkin (contract 1.0.4)
# -----------------------------------------------------------
class TestApartmentContract:
    def test_rimini_apartment_no_current_checkin(self):
        r = requests.get(f"{API}/app/apartments/apt-rimini-01/instance/apartment", headers=_hdr(), timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "current_checkin" not in data, f"current_checkin must be removed in contract 1.0.4, got {list(data.keys())}"
        assert "current_booking_id" in data
        assert data["occupancy"] in ("occupied", "reserved", "vacant")


# -----------------------------------------------------------
# 2) Booking archive endpoint
# -----------------------------------------------------------
class TestBookingArchiveAccess:
    def test_viewer_can_read(self):
        r = requests.get(f"{API}/app/apartments/apt-bologna-01/bookings", headers=_hdr(VIEWER), timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body and isinstance(body["items"], list)

    def test_unknown_apartment_404(self):
        r = requests.get(f"{API}/app/apartments/apt-does-not-exist/bookings", headers=_hdr(), timeout=10)
        assert r.status_code == 404


# -----------------------------------------------------------
# 3) Archive flow: previous + current stay with checkin event
# -----------------------------------------------------------
class TestArchiveFlow:
    def test_full_flow(self):
        now = datetime.now(UTC)
        prev_id = f"bk-prev-{secrets.token_hex(3)}"
        cur_id = f"bk-cur-{secrets.token_hex(3)}"
        STATE["prev"] = prev_id
        STATE["cur"] = cur_id

        prev_ci = now - timedelta(days=5)
        prev_ci = prev_ci.replace(hour=15, minute=0, second=0, microsecond=0)
        prev_co = now - timedelta(days=3)
        prev_co = prev_co.replace(hour=10, minute=0, second=0, microsecond=0)
        cur_ci = now - timedelta(days=1)
        cur_ci = cur_ci.replace(hour=15, minute=0, second=0, microsecond=0)
        cur_co = now + timedelta(days=2)
        cur_co = cur_co.replace(hour=10, minute=0, second=0, microsecond=0)

        def send(evtype, bid, ci, co, extra_evid=""):
            evid = f"evt-{bid}-{evtype}-{extra_evid or secrets.token_hex(3)}"
            payload = {
                "event_id": evid, "type": evtype, "booking_id": bid,
                "checkin_at": _iso(ci), "checkout_at": _iso(co),
                "guests": 2, "source": "simulator", "ts": _iso(now),
            }
            r = requests.post(f"{API}/app/apartments/apt-bologna-01/simulator/booking",
                              headers=_hdr(), json=payload, timeout=10)
            assert r.status_code in (200, 202), f"{evtype} {bid}: {r.status_code} {r.text}"
            return evid, r.json()

        # Previous booking: create + checkout
        send("booking_created", prev_id, prev_ci, prev_co)
        send("checkout", prev_id, prev_ci, prev_co)

        # Current booking: create + checkin
        send("booking_created", cur_id, cur_ci, cur_co)
        checkin_evid, _ = send("checkin", cur_id, cur_ci, cur_co)

        # Archive query by booking_id
        r = requests.get(f"{API}/app/apartments/apt-bologna-01/bookings",
                         params={"booking_id": cur_id}, headers=_hdr(), timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1, items
        cur = items[0]
        assert cur["booking_id"] == cur_id
        assert cur["status"] == "checked_in"
        # D-90: event_ids, last_event_type, updated_at and source stay inside the BFF
        assert not {"event_ids", "last_event_type", "updated_at", "source"} & set(cur), cur

        # Previous archived with checked_out
        r = requests.get(f"{API}/app/apartments/apt-bologna-01/bookings",
                         params={"booking_id": prev_id}, headers=_hdr(), timeout=10)
        prev = r.json()["items"][0]
        assert prev["status"] == "checked_out"

        # GET /apartment now occupied with current_booking_id matching
        r = requests.get(f"{API}/app/apartments/apt-bologna-01/instance/apartment", headers=_hdr(), timeout=10)
        apt = r.json()
        assert apt["occupancy"] == "occupied", apt
        assert apt["current_booking_id"] == cur_id
        assert "current_checkin" not in apt

        # Idempotency: resending same event_id with duplicate flag
        payload = {
            "event_id": checkin_evid, "type": "checkin", "booking_id": cur_id,
            "checkin_at": _iso(cur_ci), "checkout_at": _iso(cur_co),
            "guests": 2, "source": "simulator", "ts": _iso(now),
        }
        r = requests.post(f"{API}/app/apartments/apt-bologna-01/simulator/booking",
                          headers=_hdr(), json=payload, timeout=10)
        assert r.status_code in (200, 202)
        body = r.json()
        assert body.get("duplicate") is True, body

        # archive unchanged
        r = requests.get(f"{API}/app/apartments/apt-bologna-01/bookings",
                         params={"booking_id": cur_id}, headers=_hdr(), timeout=10)
        cur2 = r.json()["items"][0]
        assert cur2 == cur


# -----------------------------------------------------------
# 4) Webhook HMAC → archived with source italianway
# -----------------------------------------------------------
class TestWebhookArchive:
    def test_italianway_reservation_archived(self):
        now = datetime.now(UTC)
        ci = (now - timedelta(hours=6)).replace(microsecond=0)
        co = (now + timedelta(days=1)).replace(microsecond=0)
        res_id = f"RES-ARCH-{secrets.token_hex(3)}"
        STATE["iw"] = res_id
        payload = {
            "event": "reservation.created",
            "id": f"iw-evt-{secrets.token_hex(4)}",
            "reservation": {
                "id": res_id,
                "apartment_id": "IW-DEMO-BOLOGNA-01",
                "checkin": _iso(ci),
                "checkout": _iso(co),
                "guests": 2,
            },
            "sent_at": _iso(now),
        }
        raw = json.dumps(payload).encode()
        sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
        r = requests.post(f"{API}/webhooks/italianway", data=raw,
                          headers={"X-Signature": sig, "Content-Type": "application/json"},
                          timeout=10)
        assert r.status_code in (200, 202), r.text

        # Should appear in archive with source italianway
        r = requests.get(f"{API}/app/apartments/apt-bologna-01/bookings",
                         params={"booking_id": res_id}, headers=_hdr(), timeout=10)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1, f"Expected to find {res_id} in archive: {items}"
        assert items[0]["status"] == "booked" and "source" not in items[0]   # D-90: the source stays inside
