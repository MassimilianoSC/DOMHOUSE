"""P-36 end to end (mock mode): the platform area, D-61a / D-62 / D-66 / D-67. Order matters inside this file: the
classes share one BFF and build on each other (organisation created, then its apartments, then cleanup)."""
import hashlib
import hmac
import json
import os
import uuid

import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = BASE_URL + os.environ.get("BFF_API_PREFIX", "")
PLATFORM_ONLY, PLATFORM_ADMIN = "piattaforma@demo.it", "m.cracchiolo@hqe.it"   # seed managers
A_ADMIN, B_ADMIN = "admin@demo.it", "admin@altra.it"
B_APT = "apt-altra-01"
RUN = uuid.uuid4().hex[:6]
NEW_ADMIN = f"primo-admin-{RUN}@nuova.it"
STATE: dict = {}


def hdr(email):
    return {"X-Dev-User": email, "Content-Type": "application/json"}


def P(method, path, who=PLATFORM_ONLY, **kw):
    return requests.request(method, f"{API}/app/platform{path}", headers=hdr(who), **kw)


class TestAccess:
    def test_platform_routes_refuse_organisation_users(self):
        for who in (A_ADMIN, B_ADMIN, "operatore@demo.it"):
            for method, path in (("GET", "/tenants"), ("POST", "/tenants"), ("GET", "/managers"), ("GET", "/webhook-logs"),
                                 ("GET", "/tenants/t-flatsharing-demo/apartments")):
                r = P(method, path, who, json={})
                assert r.status_code == 403, (who, method, path, r.status_code)

    def test_both_managers_reach_the_platform(self):
        assert P("GET", "/tenants").status_code == 200
        assert P("GET", "/tenants", PLATFORM_ADMIN).status_code == 200


class TestTenants:
    def test_create_with_first_admin(self):
        r = P("POST", "/tenants", json={"name": f"Nuova  Org {RUN}", "admin_email": NEW_ADMIN, "admin_display_name": "Primo"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["tenant_id"].startswith("t-") and len(body["tenant_id"]) == 12
        assert body["name"] == f"Nuova Org {RUN}"                                   # spaces normalised
        assert body["first_admin"] == {"email": NEW_ADMIN, "pending": True}
        assert body["email_status"] == "not_configured"
        STATE["tid"] = body["tenant_id"]

    def test_double_click_and_case_do_not_duplicate(self):
        for name in (f"Nuova Org {RUN}", f"  nuova ORG {RUN} "):
            r = P("POST", "/tenants", json={"name": name, "admin_email": f"altro-{RUN}@nuova.it"})
            assert r.status_code == 409 and r.json()["error"] == "name_taken"
            assert r.json()["details"]["tenant_id"] == STATE["tid"]
        r = P("POST", "/tenants", json={"name": "Flatsharing demo", "admin_email": f"altro2-{RUN}@nuova.it"})
        assert r.status_code == 409 and r.json()["details"]["tenant_id"] == "t-flatsharing-demo"   # older record, no index

    def test_used_email_refused_and_name_not_consumed(self):
        r = P("POST", "/tenants", json={"name": f"Org email {RUN}", "admin_email": A_ADMIN})
        assert r.status_code == 409 and r.json() == {"error": "email_taken", "message": "Questa email non può essere invitata"}
        r = P("POST", "/tenants", json={"name": f"Org email {RUN}", "admin_email": f"libera-{RUN}@nuova.it"})
        assert r.status_code == 201                                                # the name was released

    def test_list_and_get_show_only_the_registry(self):
        rows = P("GET", "/tenants").json()
        assert all(set(r) == {"tenant_id", "name", "created_at", "first_admin", "suspended", "suspended_at",
                              "suspended_reason", "support_access"} for r in rows)
        assert {"t-flatsharing-demo", "t-altra-demo", STATE["tid"]} <= {r["tenant_id"] for r in rows}
        legacy = next(r for r in rows if r["tenant_id"] == "t-flatsharing-demo")
        assert legacy["first_admin"] is None
        assert P("GET", f"/tenants/{STATE['tid']}").json()["first_admin"]["email"] == NEW_ADMIN
        assert P("GET", "/tenants/t-inesistente").status_code == 404

    def test_rename(self):
        r = P("PATCH", f"/tenants/{STATE['tid']}", json={"name": f"Rinominata {RUN}"})
        assert r.status_code == 200 and r.json()["name"] == f"Rinominata {RUN}"
        r = P("PATCH", f"/tenants/{STATE['tid']}", json={"name": "altra organizzazione DEMO"})
        assert r.status_code == 409 and r.json()["details"]["tenant_id"] == "t-altra-demo"
        assert P("PATCH", f"/tenants/{STATE['tid']}", json={"name": "   "}).status_code == 422

    def test_resend_invite(self):
        r = P("POST", f"/tenants/{STATE['tid']}/invite")
        assert r.status_code == 200 and r.json()["email_status"] == "not_configured"
        assert P("POST", "/tenants/t-flatsharing-demo/invite").json()["error"] == "no_first_admin"

    def test_first_admin_gets_an_empty_organisation(self):
        me = requests.get(f"{API}/app/me", headers=hdr(NEW_ADMIN)).json()
        assert me["tenant"]["tenant_id"] == STATE["tid"] and me["role"] == "admin" and me["user"]["platform_manager"] is False
        assert requests.get(f"{API}/app/apartments", headers=hdr(NEW_ADMIN)).json() == []
        assert [u["email"] for u in requests.get(f"{API}/app/admin/users", headers=hdr(NEW_ADMIN)).json()] == [NEW_ADMIN]


class TestApartments:
    def row_keys(self):
        return {"apartment_id", "name", "instance_url", "port", "enabled", "timezone", "italianway_id", "simulated", "last_check"}

    def test_create_link_verify(self):
        aid = STATE["aid"] = f"apt-plat-{RUN}"
        r = P("POST", f"/tenants/{STATE['tid']}/apartments", json={"apartment_id": aid, "name": "Collegato", "instance_url": "MOCK://builtin"})
        assert r.status_code == 201, r.text
        assert set(r.json()) == self.row_keys() and r.json()["instance_url"] == "mock://builtin" and r.json()["enabled"] is True
        v = P("POST", f"/tenants/{STATE['tid']}/apartments/{aid}/verify").json()
        assert v["ok"] is True
        rows = P("GET", f"/tenants/{STATE['tid']}/apartments").json()
        assert [x["apartment_id"] for x in rows] == [aid] and rows[0]["last_check"]["ok"] is True

    def test_refusals(self):
        tid = STATE["tid"]
        r = P("POST", f"/tenants/{tid}/apartments", json={"apartment_id": "apt-rimini-01", "name": "x", "instance_url": "mock://builtin"})
        assert r.status_code == 409 and r.json()["message"] == "Identificativo non disponibile"
        r = P("POST", f"/tenants/{tid}/apartments", json={"apartment_id": f"apt-url-{RUN}", "name": "x", "instance_url": "https://esempio.it"})
        assert r.status_code == 422 and r.json()["error"] == "invalid_instance_url"      # mock mode: mock:// only (D-28)
        assert P("POST", "/tenants/t-inesistente/apartments", json={"apartment_id": f"apt-x-{RUN}", "name": "x",
                                                                     "instance_url": "mock://builtin"}).status_code == 404
        # an apartment of ANOTHER organisation through this organisation's path: as if it did not exist
        assert P("PATCH", f"/tenants/{tid}/apartments/apt-rimini-01", json={"port": 8101}).status_code == 404
        assert P("DELETE", f"/tenants/{tid}/apartments/apt-rimini-01").status_code == 404
        assert P("POST", f"/tenants/{tid}/apartments/apt-rimini-01/verify").status_code == 404

    def test_organisation_admin_uses_it_platform_does_not_see_inside(self):
        aid = STATE["aid"]
        assert requests.get(f"{API}/app/apartments/{aid}/instance/apartment", headers=hdr(NEW_ADMIN)).status_code == 200
        assert requests.get(f"{API}/app/apartments/{aid}/instance/apartment", headers=hdr(PLATFORM_ONLY)).status_code in (401, 403)
        assert requests.get(f"{API}/app/apartments/{aid}/instance/apartment", headers=hdr(PLATFORM_ADMIN)).status_code == 404
        assert requests.get(f"{API}/app/apartments/{aid}/bookings", headers=hdr(PLATFORM_ADMIN)).status_code == 404
        with requests.get(f"{API}/app/apartments/{aid}/stream", headers=hdr(PLATFORM_ADMIN), stream=True, timeout=10) as r:
            assert r.status_code == 404
        admin_view = next(a for a in requests.get(f"{API}/app/admin/apartments", headers=hdr(NEW_ADMIN)).json() if a["apartment_id"] == aid)
        assert admin_view["last_check"]["ok"] is True                              # the admin sees the outcome too

    def test_relink_only_the_link(self):
        r = P("PATCH", f"/tenants/{STATE['tid']}/apartments/{STATE['aid']}", json={"port": 8123, "name": "ignorato"})
        assert r.status_code == 200 and r.json()["port"] == 8123 and r.json()["name"] == "Collegato"
        r = P("PATCH", f"/tenants/{STATE['tid']}/apartments/{STATE['aid']}", json={"instance_url": "https://esempio.it"})
        assert r.status_code == 422

    def test_italianway_code_is_set_by_the_platform(self):
        """D-72 (F6): the platform sets, changes and removes the code; the organisation admin only reads it."""
        tid, aid, code = STATE["tid"], STATE["aid"], f"IW-PLAT-{RUN}"
        assert P("PATCH", f"/tenants/{tid}/apartments/{aid}", json={"italianway_id": "IW-DEMO-ALTRA-01"}).json()["error"] == "external_id_in_use"
        r = P("PATCH", f"/tenants/{tid}/apartments/{aid}", json={"italianway_id": f" {code} "})
        assert r.status_code == 200 and r.json()["italianway_id"] == code
        admin_apts = f"{API}/app/admin/apartments"
        assert next(a for a in requests.get(admin_apts, headers=hdr(NEW_ADMIN)).json() if a["apartment_id"] == aid)["italianway_id"] == code
        r = requests.patch(f"{admin_apts}/{aid}", headers=hdr(NEW_ADMIN), json={"italianway_id": None})
        assert r.status_code == 403 and r.json()["error"] == "platform_only"
        assert P("PATCH", f"/tenants/{tid}/apartments/{aid}", json={"port": 8124}).json()["italianway_id"] == code   # absent: unchanged
        assert P("PATCH", f"/tenants/{tid}/apartments/{aid}", json={"italianway_id": None}).json()["italianway_id"] is None
        other = f"apt-iw2-{RUN}"
        r = P("POST", f"/tenants/{tid}/apartments", json={"apartment_id": other, "name": "x", "instance_url": "mock://builtin", "italianway_id": code})
        assert r.status_code == 201 and r.json()["italianway_id"] == code               # freed by the removal
        assert P("DELETE", f"/tenants/{tid}/apartments/{other}").status_code == 204

    def test_delete_and_id_never_reused(self):
        tid, aid = STATE["tid"], STATE["aid"]
        assert P("DELETE", f"/tenants/{tid}/apartments/{aid}").status_code == 204
        assert requests.get(f"{API}/app/apartments/{aid}", headers=hdr(NEW_ADMIN)).status_code == 404
        r = P("POST", f"/tenants/{tid}/apartments", json={"apartment_id": aid, "name": "Di nuovo", "instance_url": "mock://builtin"})
        assert r.status_code == 409 and r.json()["message"] == "Identificativo non disponibile"         # D-67
        r = requests.post(f"{API}/app/admin/apartments", headers=hdr(NEW_ADMIN),
                          json={"apartment_id": aid, "name": "Di nuovo", "instance_url": "mock://builtin"})
        assert r.status_code == 403 and r.json()["error"] == "platform_only"         # D-77: never the admin, also in mock


class TestWebhookLogs:
    def test_unattributed_calls_only_for_the_platform(self):
        raw = json.dumps({"event": "reservation.created", "id": f"iw-ev-{RUN}", "reservation": {"id": f"RES-{RUN}"}}).encode()
        r = requests.post(f"{API}/webhooks/italianway", data=raw, headers={"X-Signature": "sbagliata", "Content-Type": "application/json"})
        assert r.status_code == 401
        mine = lambda logs: [l for l in logs if l["outcome"] == "invalid_signature" and f"RES-{RUN}" in l["raw_body"]]
        assert len(mine(P("GET", "/webhook-logs").json())) == 1
        for admin in (A_ADMIN, B_ADMIN):
            assert mine(requests.get(f"{API}/app/admin/webhook-logs", headers=hdr(admin)).json()) == []


class TestManagers:
    def test_list_add_remove_last(self):
        rows = P("GET", "/managers").json()
        assert all(set(r) == {"email", "display_name", "active"} for r in rows)
        assert {PLATFORM_ONLY, PLATFORM_ADMIN} <= {r["email"] for r in rows}
        assert next(r for r in rows if r["email"] == PLATFORM_ONLY)["active"] is True   # it signed in during this run
        new = f"Nuovo.Gestore-{RUN}@Esempio.it"
        r = P("POST", "/managers", json={"email": new})
        assert r.status_code == 201 and r.json() == {"email": new.lower(), "display_name": "", "active": False}
        assert P("POST", "/managers", json={"email": new.upper()}).status_code == 409
        # P-71 (D-142): the email in the body, never in the path; the old DELETE /managers/{email} is gone
        assert P("DELETE", f"/managers/{new}").status_code in (404, 405)
        for bad in ({}, {"email": ""}, {"email": 3}):
            r = P("POST", "/managers/remove", json=bad)
            assert r.status_code == 422 and r.json()["error"] == "bad_request", bad
        assert P("POST", "/managers/remove", json={"email": new}).status_code == 204
        assert P("POST", "/managers/remove", json={"email": "nessuno@esempio.it"}).status_code == 404
        assert P("POST", "/managers/remove", json={"email": PLATFORM_ADMIN}).status_code == 204
        r = P("POST", "/managers/remove", json={"email": PLATFORM_ONLY})
        assert r.status_code == 409 and r.json()["error"] == "last_manager"
        assert requests.get(f"{API}/app/me", headers=hdr(PLATFORM_ADMIN)).json()["user"]["platform_manager"] is False


class TestManagerNotCapturable:
    def test_cannot_invite_a_platform_manager(self):
        # F5 (D-70): the manager's email is visible; an admin must not be able to invite (capture) or delete it
        r = requests.post(f"{API}/app/admin/users", headers=hdr(A_ADMIN),
                          json={"email": PLATFORM_ONLY, "role": "viewer"})
        assert r.status_code == 409 and r.json()["message"] == "Questa email non può essere invitata"

    def test_me_and_tenant_do_not_leak_platform_fields(self):
        # created_by / first_admin_email live only in the platform area
        for who in (A_ADMIN, NEW_ADMIN):
            me = requests.get(f"{API}/app/me", headers=hdr(who))
            if me.json().get("tenant"):
                assert set(me.json()["tenant"]) <= {"tenant_id", "name", "enabled_features", "suspended", "energy_price_eur_kwh"}
        t = requests.get(f"{API}/app/admin/tenant", headers=hdr(A_ADMIN)).json()
        assert "created_by" not in t and "first_admin_email" not in t

    def test_admin_tenant_patch_ignores_name(self):
        # L1 (D-70): the name is set only by the platform; the admin PATCH no longer carries it
        before = requests.get(f"{API}/app/admin/tenant", headers=hdr(A_ADMIN)).json()["name"]
        r = requests.patch(f"{API}/app/admin/tenant", headers=hdr(A_ADMIN), json={"name": "Nome Cambiato", "enabled_features": ["devices"]})
        assert r.status_code == 200 and r.json()["name"] == before and "name" not in str(r.json().get("created_by", ""))
        assert requests.get(f"{API}/app/admin/tenant", headers=hdr(A_ADMIN)).json()["name"] == before
        requests.patch(f"{API}/app/admin/tenant", headers=hdr(A_ADMIN), json={"clear_features": True})


class TestAudit:
    """P-47: what the classes above did is in the organisation's log and in the platform's, newest first."""

    def _all(self, url, who):
        items, cursor = [], None
        while True:
            r = requests.get(url, headers=hdr(who), params={"limit": 2, **({"before": cursor} if cursor else {})})
            assert r.status_code == 200, r.text
            body = r.json()
            assert len(body["items"]) <= 2
            items += body["items"]
            if not (cursor := body["next"]):
                return items

    def test_platform_sees_the_organisation_log_page_by_page(self):
        items = self._all(f"{API}/app/platform/audit?tenant_id={STATE['tid']}", PLATFORM_ONLY)
        assert [i["at"] for i in items] == sorted((i["at"] for i in items), reverse=True)
        assert len({i["audit_id"] for i in items}) == len(items)                         # no entry twice across pages
        actions = [i["action"] for i in items]
        for a in ("tenant_created", "invite_sent", "tenant_renamed", "invite_resent", "apartment_created",
                  "apartment_relinked", "italianway_changed", "apartment_deleted"):
            assert a in actions, (a, actions)
        invite = next(i for i in items if i["action"] == "invite_sent")
        # D-90: the platform sees the role of the organisation's people, never their email
        assert invite["target"]["type"] == "user" and invite["target"]["label"] is None and invite["target"]["role"] == "admin"
        assert invite["details"] == {"role": "admin", "apartment_ids": "all"}
        assert invite["actor"]["kind"] == "platform" and invite["actor"]["email"] == PLATFORM_ONLY
        deleted = next(i for i in items if i["action"] == "apartment_deleted")
        assert deleted["target"] == {"type": "apartment", "id": STATE["aid"], "label": "Collegato", "removed": False,
                                     "role": None}
        renamed = next(i for i in items if i["action"] == "tenant_renamed")
        assert set(renamed["details"]) == {"from", "to"}

    def test_the_admin_sees_the_same_log_without_the_manager_identity(self):
        items = self._all(f"{API}/app/admin/audit", NEW_ADMIN)
        assert all("tenant_id" not in i for i in items)                               # D-90: not sent any more
        assert next(i for i in items if i["action"] == "invite_sent")["target"]["label"] == NEW_ADMIN
        assert "tenant_created" in [i["action"] for i in items]
        for i in items:
            if i["actor"]["kind"] == "platform":   # "Gestore della piattaforma (HQE)": not which manager
                assert i["actor"]["email"] is None and "uid" not in i["actor"] and i["actor"]["display_name"] is None

    def test_platform_sees_roles_not_the_organisation_s_people(self):
        """D-90 (1): in an organisation's log the platform sees what was done and the ROLE of who did it, never emails."""
        email = f"ruolo-{RUN}@nuova.it"
        r = requests.post(f"{API}/app/admin/users", headers=hdr(NEW_ADMIN), json={"email": email, "role": "viewer"})
        assert r.status_code == 201, r.text
        items = self._all(f"{API}/app/platform/audit?tenant_id={STATE['tid']}", PLATFORM_ONLY)
        sent = next(i for i in items if i["action"] == "invite_sent" and i["actor"]["kind"] == "user")
        assert sent["actor"] == {"kind": "user", "email": None, "display_name": None, "removed": False, "role": "admin"}
        assert sent["target"]["label"] is None and sent["target"]["role"] == "viewer"
        assert email not in json.dumps(items) and NEW_ADMIN not in json.dumps(items)
        mine = self._all(f"{API}/app/admin/audit", NEW_ADMIN)                      # the organisation still sees them
        seen = next(i for i in mine if i["action"] == "invite_sent" and i["target"]["label"] == email)
        assert seen["actor"]["email"] == NEW_ADMIN and seen["actor"]["role"] == "admin"

    def test_platform_level_actions(self):
        items = self._all(f"{API}/app/platform/audit?scope=platform", PLATFORM_ONLY)
        actions = [i["action"] for i in items]
        assert "manager_added" in actions and "manager_removed" in actions
        added = next(i for i in items if i["action"] == "manager_added")
        assert added["target"]["type"] == "manager" and "@" in added["target"]["label"]   # HQE people: shown

    def test_refusals_and_isolation(self):
        assert P("GET", "/audit").status_code == 422                                     # tenant_id or scope
        assert P("GET", f"/audit?tenant_id={STATE['tid']}&scope=platform").status_code == 422
        assert P("GET", "/audit?tenant_id=t-inesistente").status_code == 404
        assert P("GET", f"/audit?tenant_id={STATE['tid']}&limit=0").status_code == 422
        assert P("GET", "/audit?scope=platform", A_ADMIN).status_code == 403            # organisation users: never
        assert requests.get(f"{API}/app/admin/audit", headers=hdr("operatore@demo.it")).status_code == 403
        other = requests.get(f"{API}/app/admin/audit", headers=hdr(B_ADMIN)).json()["items"]
        assert all(i["target"]["id"] != STATE["tid"] and i["target"]["label"] != NEW_ADMIN for i in other)


class TestSuspension:
    """P-50 (D-85): the platform suspends and reactivates an organisation; the app stops for its people, a platform
    manager who is also a member keeps /app/me and the platform to bring it back."""

    def test_suspend_then_reactivate(self):
        tid = "t-flatsharing-demo"   # PLATFORM_ADMIN (m.cracchiolo@hqe.it) is an admin here and a platform manager
        if not requests.get(f"{API}/app/me", headers=hdr(PLATFORM_ADMIN)).json()["user"]["platform_manager"]:
            assert P("POST", "/managers", json={"email": PLATFORM_ADMIN}).status_code == 201   # TestManagers removed it
        try:
            r = P("POST", f"/tenants/{tid}/suspend", json={"reason": "Contratto in revisione"})
            assert r.status_code == 200, r.text
            assert r.json()["suspended"] is True and r.json()["suspended_reason"] == "Contratto in revisione"
            assert P("POST", f"/tenants/{tid}/suspend", json={"reason": "di nuovo"}).json()["error"] == "already_suspended"
            for who in (A_ADMIN, "operatore@demo.it"):
                for path in ("/app/me", "/app/apartments", "/app/apartments/apt-rimini-01/instance/devices"):
                    r = requests.get(f"{API}{path}", headers=hdr(who))
                    assert r.status_code == 403 and r.json()["error"] == "tenant_suspended", (who, path, r.text)
            assert requests.get(f"{API}/app/admin/users", headers=hdr(A_ADMIN)).json()["error"] == "tenant_suspended"
            me = requests.get(f"{API}/app/me", headers=hdr(PLATFORM_ADMIN))
            assert me.status_code == 200 and me.json()["tenant"]["suspended"] is True
            assert me.json()["user"]["platform_manager"] is True
            r = requests.get(f"{API}/app/apartments", headers=hdr(PLATFORM_ADMIN))
            assert r.status_code == 403 and r.json()["error"] == "tenant_suspended"   # organisation routes: closed
            assert P("GET", "/tenants", PLATFORM_ADMIN).status_code == 200            # the platform: open
            assert requests.get(f"{API}/app/me", headers=hdr(B_ADMIN)).json()["tenant"]["suspended"] is False
            row = next(t for t in P("GET", "/tenants").json() if t["tenant_id"] == tid)
            assert row["suspended"] is True and row["suspended_at"]
        finally:
            r = P("POST", f"/tenants/{tid}/reactivate", PLATFORM_ADMIN)
        assert r.status_code == 200 and r.json()["suspended"] is False and r.json()["suspended_reason"] is None
        assert requests.get(f"{API}/app/apartments", headers=hdr(A_ADMIN)).status_code == 200
        assert P("POST", f"/tenants/{tid}/reactivate").json()["error"] == "not_suspended"
        assert P("POST", f"/tenants/{tid}/suspend", json={"reason": " "}).json()["error"] == "invalid_reason"
        items = requests.get(f"{API}/app/admin/audit", headers=hdr(A_ADMIN)).json()["items"]
        assert [i["action"] for i in items[:2]] == ["tenant_reactivated", "tenant_suspended"]
        assert items[1]["details"] == {"reason": "Contratto in revisione"} and items[1]["actor"]["email"] is None

    def test_refused_to_organisation_users(self):
        assert P("POST", "/tenants/t-altra-demo/suspend", B_ADMIN, json={"reason": "x"}).status_code == 403
        assert P("POST", "/tenants/t-inesistente/suspend", json={"reason": "x"}).status_code == 404


class TestSupportAccess:
    """P-50 (D-86): HQE opens an access (1-24 h) and works inside the organisation as an operator; the admins see it and
    close it; outside the window the manager gets nothing from the organisation."""
    TID = "t-altra-demo"

    def S(self, method, path, who=PLATFORM_ONLY, tenant=TID, headers_extra=None, **kw):
        headers = {**hdr(who), "X-Support-Tenant": tenant, **(headers_extra or {})}
        return requests.request(method, f"{API}{path}", headers=headers, **kw)

    def test_open_refusals(self):
        base = f"/tenants/{self.TID}/support-access"
        for hours in (0, 25):
            r = P("POST", base, json={"hours": hours, "reason": "x"})
            assert r.status_code == 422 and r.json()["error"] == "invalid_hours"
        assert P("POST", base, json={"hours": 2, "reason": "  "}).json()["error"] == "invalid_reason"
        assert P("POST", base, B_ADMIN, json={"hours": 2, "reason": "x"}).status_code == 403
        assert P("POST", "/tenants/t-inesistente/support-access", json={"hours": 2, "reason": "x"}).status_code == 404
        tid = STATE["tid"]
        assert P("POST", f"/tenants/{tid}/suspend", json={"reason": "prova"}).status_code == 200
        try:
            r = P("POST", f"/tenants/{tid}/support-access", json={"hours": 2, "reason": "x"})
            assert r.status_code == 409 and r.json()["error"] == "tenant_suspended"
        finally:
            assert P("POST", f"/tenants/{tid}/reactivate").status_code == 200

    def test_work_inside_then_the_admin_closes_it(self):
        r = P("POST", f"/tenants/{self.TID}/support-access", json={"hours": 2, "reason": "Caldaia che non risponde"})
        assert r.status_code == 201, r.text
        access = r.json()
        assert access["status"] == "active" and access["operator_email"] == PLATFORM_ONLY and access["closed_at"] is None
        r = P("POST", f"/tenants/{self.TID}/support-access", json={"hours": 2, "reason": "di nuovo"})
        assert r.status_code == 409 and r.json()["error"] == "support_active"
        row = next(t for t in P("GET", "/tenants").json() if t["tenant_id"] == self.TID)
        assert row["support_access"]["access_id"] == access["access_id"] and row["support_access"]["mine"] is True

        # inside, as an operator
        me = self.S("GET", "/app/me").json()
        assert me["tenant"]["tenant_id"] == self.TID and me["role"] == "operator" and me["user"]["platform_manager"] is True
        assert me["support"] == {"access_id": access["access_id"], "tenant_id": self.TID, "expires_at": access["expires_at"],
                                 "reason": "Caldaia che non risponde"}
        assert [a["apartment_id"] for a in self.S("GET", "/app/apartments").json()] == [B_APT]
        assert self.S("GET", f"/app/apartments/{B_APT}/instance/devices").status_code == 200
        assert self.S("GET", "/app/apartments/apt-rimini-01/instance/devices").status_code == 404   # never another tenant
        # what the manager does inside reaches the engine as their pseudonym and reads as their real identity (D-86)
        corr = str(uuid.uuid4())
        r = self.S("POST", f"/app/apartments/{B_APT}/instance/apartment/hold", json={"minutes": 15, "mode": "eco"},
                   headers_extra={"X-Correlation-Id": corr})
        assert r.status_code == 202, r.text
        for who, path in ((None, None), (B_ADMIN, None)):
            got = (self.S("GET", f"/app/apartments/{B_APT}/instance/decisions", params={"correlation_id": corr}) if who is None
                   else requests.get(f"{API}/app/apartments/{B_APT}/instance/decisions", headers=hdr(who),
                                     params={"correlation_id": corr}))
            assert {d["actor"] for d in got.json()["items"]} == {f"user:{PLATFORM_ONLY}"}
        self.S("POST", f"/app/apartments/{B_APT}/instance/apartment/hold", json={"minutes": 0})
        assert self.S("GET", "/app/admin/users").status_code == 403                                 # operator rights only
        assert self.S("PATCH", f"/app/admin/apartments/{B_APT}", json={"name": "x"}).status_code == 403
        # only the manager who opened it can enter
        r = self.S("GET", "/app/me", PLATFORM_ADMIN)
        assert r.status_code == 403 and r.json()["error"] == "support_expired"
        # own account routes ignore the header: nothing is ever tied to the assisted organisation
        assert self.S("GET", "/app/push/status").status_code in (401, 403)   # PLATFORM_ONLY has no organisation of its own
        assert all(u["email"] not in (PLATFORM_ONLY, PLATFORM_ADMIN)
                   for u in requests.get(f"{API}/app/admin/users", headers=hdr(B_ADMIN)).json())

        # the organisation sees it
        me_admin = requests.get(f"{API}/app/me", headers=hdr(B_ADMIN)).json()
        assert [a["access_id"] for a in me_admin["support_access"]] == [access["access_id"]]
        assert me_admin["support_access"][0]["operator_email"] == PLATFORM_ONLY
        assert requests.get(f"{API}/app/me", headers=hdr("operatore@altra.it")).json()["support_access"] == []
        r = requests.delete(f"{API}/app/admin/support-access/{access['access_id']}", headers=hdr(A_ADMIN))
        assert r.status_code == 404                                          # another organisation's admin

        # closed by the admin: effective at the next request
        assert requests.delete(f"{API}/app/admin/support-access/{access['access_id']}", headers=hdr(B_ADMIN)).status_code == 204
        for path in ("/app/me", "/app/apartments", f"/app/apartments/{B_APT}/instance/devices"):
            r = self.S("GET", path)
            assert r.status_code == 403 and r.json()["error"] == "support_expired", path
        history = requests.get(f"{API}/app/admin/support-access", headers=hdr(B_ADMIN)).json()
        assert history[0]["access_id"] == access["access_id"] and history[0]["status"] == "closed"
        items = requests.get(f"{API}/app/admin/audit", headers=hdr(B_ADMIN)).json()["items"]
        assert [i["action"] for i in items[:2]] == ["support_access_closed", "support_access_opened"]
        opened, closed = items[1], items[0]
        assert opened["details"] == {"hours": 2, "expires_at": access["expires_at"], "reason": "Caldaia che non risponde"}
        assert opened["target"] == {"type": "support_access", "id": access["access_id"], "label": "Altra organizzazione demo",
                                    "removed": False, "role": None}
        assert closed["actor"]["kind"] == "user" and closed["actor"]["email"] == B_ADMIN

    def test_the_manager_closes_it(self):
        r = P("POST", f"/tenants/{self.TID}/support-access", json={"hours": 1, "reason": "Verifica"})
        assert r.status_code == 201
        aid = r.json()["access_id"]
        assert P("DELETE", f"/tenants/{self.TID}/support-access/{aid}").status_code == 204
        assert P("DELETE", f"/tenants/{self.TID}/support-access/{aid}").status_code == 204   # already closed: nothing to do
        assert P("DELETE", f"/tenants/t-flatsharing-demo/support-access/{aid}").status_code == 404
        assert self.S("GET", "/app/me").json()["error"] == "support_expired"
        rows = P("GET", f"/tenants/{self.TID}/support-access").json()
        assert rows[0]["access_id"] == aid and rows[0]["status"] == "closed"
        assert next(t for t in P("GET", "/tenants").json() if t["tenant_id"] == self.TID)["support_access"] is None
