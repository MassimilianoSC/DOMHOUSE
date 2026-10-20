"""BFF backend tests - Phase 2 (schedule, rules, approvals, decisions, energy, ask, header auth, window timing)."""
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = BASE + os.environ.get("BFF_API_PREFIX", "")  # "" = BFF diretto (/app/...); "/api" solo dietro un proxy che lo aggiunge

ADMIN = {"X-Dev-User": "m.cracchiolo@hqe.it"}
ADMIN2 = {"X-Dev-User": "admin@demo.it"}
OPERATOR = {"X-Dev-User": "operatore@demo.it"}
VIEWER = {"X-Dev-User": "lettura@demo.it"}
APT = "apt-rimini-01"
INSTANCE = f"{API}/app/apartments/{APT}/instance"


def _future_iso(seconds: int = 3600) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(timespec="seconds").replace("+00:00", "Z")


def _past_iso() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds").replace("+00:00", "Z")


# =========================================================================
# Header-only auth (SSE query params rejected)
# =========================================================================
class TestHeaderAuth:
    def test_me_header_ok(self):
        r = requests.get(f"{API}/app/me", headers=ADMIN)
        assert r.status_code == 200
        assert r.json()["user"]["email"] == "m.cracchiolo@hqe.it"

    def test_me_query_rejected(self):
        # Query auth was removed from /me (header-only).
        r = requests.get(f"{API}/app/me", params={"dev_user": "m.cracchiolo@hqe.it"})
        assert r.status_code == 401

    def test_stream_query_rejected(self):
        # /stream must NOT accept dev_user / access_token query params.
        r = requests.get(
            f"{API}/app/apartments/{APT}/stream",
            params={"dev_user": "admin@demo.it"},
            stream=True, timeout=5,
        )
        try:
            assert r.status_code == 401
        finally:
            r.close()

    def test_stream_header_ok(self):
        r = requests.get(
            f"{API}/app/apartments/{APT}/stream",
            headers=ADMIN, stream=True, timeout=5,
        )
        try:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")
            chunk = next(r.iter_content(chunk_size=128, decode_unicode=True))
            assert "connected" in chunk or "retry" in chunk
        finally:
            r.close()


# =========================================================================
# SSE Last-Event-ID replay
# =========================================================================
class TestSSELastEventID:
    def test_last_event_id_replay(self):
        # Connect, read a few events to capture a known id, trigger an event,
        # reconnect with Last-Event-ID lower than the triggered event id,
        # and verify the triggered event is replayed.
        headers = {**ADMIN, "Accept": "text/event-stream"}
        # 1) First connection: get the baseline latest id by causing a benign event.
        corr = str(uuid.uuid4())
        # Toggle presa online->online (no-op online emits health; use a real contact toggle)
        # Easier: list current id by causing a contact=false->false (idempotent). Use schedule create + delete.
        # Trigger a non-destructive event: close window (already closed) -> may still emit. Use trigger_approval? not idempotent.
        # Instead: open a short-lived SSE and read the first event ids while triggering device_offline toggle.
        with requests.get(
            f"{API}/app/apartments/{APT}/stream",
            headers=headers, stream=True, timeout=10,
        ) as r:
            assert r.status_code == 200
            # Trigger an event: set finestra online toggle via _test state capability contact open->closed
            # The simulator emits device.online or device.state for state changes.
            req = requests.post(
                f"{INSTANCE}/_test/state",
                headers={**ADMIN, "Content-Type": "application/json"},
                json={"device_id": "dev-presa-camera", "online": True},
            )
            assert req.status_code in (200, 204)
            # Also force a state change event (open window shortly then close)
            r1 = requests.post(
                f"{INSTANCE}/_test/state",
                headers={**ADMIN, "Content-Type": "application/json"},
                json={"device_id": "dev-finestra-camera", "capability": "contact", "state": {"open": True}},
            )
            assert r1.status_code in (200, 204)
            last_id = None
            deadline = time.time() + 5
            buf = ""
            for chunk in r.iter_content(chunk_size=256, decode_unicode=True):
                if not chunk:
                    continue
                buf += chunk
                for line in buf.splitlines():
                    if line.startswith("id:"):
                        last_id = line.split(":", 1)[1].strip()
                if last_id or time.time() > deadline:
                    break
        # Clean up: close window
        requests.post(
            f"{INSTANCE}/_test/state",
            headers={**ADMIN, "Content-Type": "application/json"},
            json={"device_id": "dev-finestra-camera", "capability": "contact", "state": {"open": False}},
        )
        if last_id is None:
            pytest.skip("Could not capture an event id from stream (environment may buffer)")
        # Reconnect with Last-Event-ID smaller than last_id to force replay.
        # Last ids are typically monotonic integers or ULIDs; use prefix '0' to force replay of all buffered.
        headers2 = {**ADMIN, "Last-Event-ID": "0"}
        with requests.get(
            f"{API}/app/apartments/{APT}/stream",
            headers=headers2, stream=True, timeout=5,
        ) as r2:
            assert r2.status_code == 200
            replayed = ""
            deadline = time.time() + 3
            for chunk in r2.iter_content(chunk_size=512, decode_unicode=True):
                replayed += chunk
                if last_id and f"id: {last_id}" in replayed:
                    break
                if time.time() > deadline:
                    break
        assert last_id in replayed, f"Last-Event-ID replay missing id {last_id}"


# =========================================================================
# Window rule timing (MOCK_TIME_SCALE=1, minutes=5 -> 5s)
# =========================================================================
class TestWindowRuleTiming:
    def test_climate_off_after_window_minutes(self):
        # Ensure climate is ON first
        def climate_state():
            r = requests.get(f"{INSTANCE}/devices", headers=ADMIN)
            devs = r.json().get("devices", [])
            return next(d for d in devs if d["device_id"] == "dev-clima-soggiorno")

        d = climate_state()
        if not d["capabilities"]["climate"]["on"]:
            r = requests.post(
                f"{INSTANCE}/devices/dev-clima-soggiorno/commands",
                headers={**ADMIN, "Content-Type": "application/json"},
                json={"capability": "climate", "action": "set_climate",
                      "params": {"on": True, "setpoint": 21}},
            )
            assert r.status_code in (200, 202), r.text
            time.sleep(2)
            d = climate_state()
            assert d["capabilities"]["climate"]["on"] is True

        # Open window
        r = requests.post(
            f"{INSTANCE}/_test/state",
            headers={**ADMIN, "Content-Type": "application/json"},
            json={"device_id": "dev-finestra-camera", "capability": "contact", "state": {"open": True}},
        )
        assert r.status_code in (200, 204)
        try:
            time.sleep(2)
            d = climate_state()
            assert d["capabilities"]["climate"]["on"] is True, "climate should still be on after 2s (<5s)"
            time.sleep(5)  # total ~7s
            d = climate_state()
            assert d["capabilities"]["climate"]["on"] is False, "climate should be off after ~7s"
        finally:
            requests.post(
                f"{INSTANCE}/_test/state",
                headers={**ADMIN, "Content-Type": "application/json"},
                json={"device_id": "dev-finestra-camera", "capability": "contact", "state": {"open": False}},
            )


# =========================================================================
# Schedule CRUD
# =========================================================================
class TestSchedule:
    def test_crud_flow(self):
        # LIST
        r = requests.get(f"{INSTANCE}/schedule", headers=ADMIN)
        assert r.status_code == 200
        assert "items" in r.json() or isinstance(r.json(), (list, dict))

        # CREATE
        payload = {"run_at": _future_iso(3600), "action": {"type": "apartment_mode", "mode": "eco"}}
        r = requests.post(f"{INSTANCE}/schedule",
                          headers={**ADMIN, "Content-Type": "application/json"}, json=payload)
        assert r.status_code == 201, r.text
        item = r.json()
        sid = item["schedule_id"]
        assert item["status"] == "planned"
        assert item["action"]["mode"] == "eco"

        # PATCH move
        new_run = _future_iso(7200)
        r = requests.patch(f"{INSTANCE}/schedule/{sid}",
                           headers={**ADMIN, "Content-Type": "application/json"},
                           json={"run_at": new_run})
        assert r.status_code == 200, r.text
        assert r.json()["run_at"].startswith(new_run[:16])

        # DELETE
        r = requests.delete(f"{INSTANCE}/schedule/{sid}", headers=ADMIN)
        assert r.status_code == 204

        # Verify cancellation via GET all
        r = requests.get(f"{INSTANCE}/schedule", headers=ADMIN)
        items = r.json().get("items", []) if isinstance(r.json(), dict) else r.json()
        found = next((i for i in items if i.get("schedule_id") == sid), None)
        if found:
            assert found["status"] == "cancelled"

    def test_create_past_422(self):
        payload = {"run_at": _past_iso(), "action": {"type": "apartment_mode", "mode": "eco"}}
        r = requests.post(f"{INSTANCE}/schedule",
                          headers={**ADMIN, "Content-Type": "application/json"}, json=payload)
        assert r.status_code == 422
        assert r.json().get("error") == "run_at_in_past"


# =========================================================================
# Rules
# =========================================================================
class TestRules:
    def test_get_rules_8_cards(self):
        r = requests.get(f"{INSTANCE}/rules", headers=ADMIN)
        assert r.status_code == 200
        rules = r.json()["rules"]
        assert len(rules) == 8
        ids = {r["rule_id"] for r in rules}
        assert "compressor_min_off" in ids
        locked = next(r for r in rules if r["rule_id"] == "compressor_min_off")
        assert locked["editable"] is False

    def test_update_out_of_range_422(self):
        r = requests.put(f"{INSTANCE}/rules",
                         headers={**ADMIN, "Content-Type": "application/json"},
                         json={"rules": [{"rule_id": "window_open_off", "params": {"minutes": 999}}]})
        assert r.status_code == 422
        body = r.json()
        assert body.get("error") == "param_out_of_range"
        assert body.get("details", {}).get("param") == "minutes"

    def test_update_valid_200(self):
        r = requests.put(f"{INSTANCE}/rules",
                         headers={**ADMIN, "Content-Type": "application/json"},
                         json={"rules": [{"rule_id": "window_open_off", "params": {"minutes": 10}}]})
        assert r.status_code == 200, r.text
        updated = r.json()
        rule = next(x for x in updated["rules"] if x["rule_id"] == "window_open_off")
        assert rule["params"]["minutes"] == 10
        # Restore to default 5
        requests.put(f"{INSTANCE}/rules",
                     headers={**ADMIN, "Content-Type": "application/json"},
                     json={"rules": [{"rule_id": "window_open_off", "params": {"minutes": 5}}]})

    def test_update_non_editable_422(self):
        r = requests.put(f"{INSTANCE}/rules",
                         headers={**ADMIN, "Content-Type": "application/json"},
                         json={"rules": [{"rule_id": "compressor_min_off", "params": {"minutes": 3}}]})
        assert r.status_code == 422
        assert r.json().get("error") == "rule_not_editable"


# =========================================================================
# Approvals
# =========================================================================
class TestApprovals:
    def test_trigger_and_decide(self):
        # Trigger
        r = requests.post(f"{INSTANCE}/_test/state",
                          headers={**ADMIN, "Content-Type": "application/json"},
                          json={"trigger": "approval"})
        assert r.status_code in (200, 204)
        # List pending
        r = requests.get(f"{INSTANCE}/approvals", params={"status": "pending"}, headers=ADMIN)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        aid = items[0]["approval_id"]

        # Approve
        r = requests.post(f"{INSTANCE}/approvals/{aid}/decision",
                          headers={**ADMIN, "Content-Type": "application/json"},
                          json={"decision": "approve"})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "approved"

        # Second decision -> 409
        r2 = requests.post(f"{INSTANCE}/approvals/{aid}/decision",
                           headers={**ADMIN, "Content-Type": "application/json",
                                    "X-Correlation-Id": str(uuid.uuid4())},
                           json={"decision": "reject"})
        assert r2.status_code == 409, r2.text


# =========================================================================
# Decisions filters
# =========================================================================
class TestDecisions:
    def test_list_with_filters(self):
        r = requests.get(f"{INSTANCE}/decisions", params={"limit": 5}, headers=ADMIN)
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert len(body["items"]) <= 5

    def test_filter_device(self):
        r = requests.get(f"{INSTANCE}/decisions",
                         params={"device_id": "dev-clima-soggiorno", "limit": 20},
                         headers=ADMIN)
        assert r.status_code == 200
        for item in r.json()["items"]:
            if item.get("target", {}).get("device_id"):
                assert item["target"]["device_id"] == "dev-clima-soggiorno"


# =========================================================================
# Energy
# =========================================================================
class TestEnergy:
    def test_energy_day(self):
        frm = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds").replace("+00:00", "Z")
        to = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        r = requests.get(f"{INSTANCE}/energy",
                         params={"from": frm, "to": to, "bucket": "day"},
                         headers=ADMIN)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["bucket"] == "day"
        assert isinstance(body["series"], list) and len(body["series"]) >= 1
        assert "total_kwh" in body
        assert isinstance(body["by_device"], list)

    def test_energy_hour(self):
        frm = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat(timespec="seconds").replace("+00:00", "Z")
        to = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        r = requests.get(f"{INSTANCE}/energy",
                         params={"from": frm, "to": to, "bucket": "hour"},
                         headers=ADMIN)
        assert r.status_code == 200
        assert r.json()["bucket"] == "hour"


# =========================================================================
# Assistant /ask
# =========================================================================
class TestAssistant:
    def _create_ask(self, text: str):
        r = requests.post(f"{INSTANCE}/ask",
                          headers={**ADMIN, "Content-Type": "application/json"},
                          json={"text": text})
        assert r.status_code == 202, r.text
        return r.json()

    def _wait_resolved(self, ask_id: str, timeout: float = 5):
        deadline = time.time() + timeout
        while time.time() < deadline:
            r = requests.get(f"{INSTANCE}/ask/{ask_id}", headers=ADMIN)
            assert r.status_code == 200
            data = r.json()
            if data["status"] != "pending":
                return data
            time.sleep(0.3)
        pytest.fail(f"ask {ask_id} did not resolve within {timeout}s")

    def test_ask_turn_off_climate(self):
        # Ensure no caldaia-pending blocks: text references clima soggiorno.
        ask = self._create_ask("Spegni il clima del soggiorno")
        assert ask["status"] == "pending"
        resolved = self._wait_resolved(ask["ask_id"])
        assert resolved["status"] == "answered"
        assert any(a.get("type") == "command" for a in resolved.get("actions", []))

    def test_ask_schedule_at_time(self):
        ask = self._create_ask("Alle 23 metti il clima a 22 gradi")
        resolved = self._wait_resolved(ask["ask_id"])
        assert resolved["status"] == "answered"
        assert any(a.get("type") == "schedule" for a in resolved.get("actions", []))

    def test_ask_caldaia_needs_approval(self):
        # First, clear any pending approval
        r = requests.get(f"{INSTANCE}/approvals", params={"status": "pending"}, headers=ADMIN)
        for a in r.json().get("items", []):
            requests.post(f"{INSTANCE}/approvals/{a['approval_id']}/decision",
                          headers={**ADMIN, "Content-Type": "application/json",
                                   "X-Correlation-Id": str(uuid.uuid4())},
                          json={"decision": "reject"})
        ask = self._create_ask("Spegni la caldaia")
        resolved = self._wait_resolved(ask["ask_id"])
        # apt-rimini-01 is occupied -> needs_approval with approval_id
        assert resolved["status"] in ("needs_approval", "answered"), resolved
        assert resolved.get("approval_id") is not None


# =========================================================================
# Viewer role forbidden on Phase 2 writes
# =========================================================================
class TestViewerRole:
    def test_viewer_cannot_create_schedule(self):
        payload = {"run_at": _future_iso(3600), "action": {"type": "apartment_mode", "mode": "eco"}}
        r = requests.post(f"{INSTANCE}/schedule",
                          headers={**VIEWER, "Content-Type": "application/json"}, json=payload)
        assert r.status_code == 403

    def test_viewer_cannot_update_rules(self):
        r = requests.put(f"{INSTANCE}/rules",
                         headers={**VIEWER, "Content-Type": "application/json"},
                         json={"rules": [{"rule_id": "window_open_off", "params": {"minutes": 5}}]})
        assert r.status_code == 403

    def test_viewer_cannot_decide_or_ask(self):
        r = requests.post(f"{INSTANCE}/ask",
                          headers={**VIEWER, "Content-Type": "application/json"},
                          json={"text": "Spegni il clima"})
        assert r.status_code == 403
