"""Final review of lot 9 (Fable, D-91): F2-F4, the minor points, and in-process proofs of behaviours that only the
end-to-end suites covered. In-process, dev auth, memory repository (F1 is in repository_suite_test: Firestore)."""
import asyncio
import dataclasses
import hashlib
import hmac
import json
import smtplib

import httpx
import pytest

from bff import actors, audit, auth, erasure, instances, invites, support
from bff.auth import CurrentUser, Identity, _from_claims
from bff.config import get_settings
from bff.main import app
from bff.repository import PlatformMember, Tenant, User, get_repository
from bff.routes import account, platform, webhooks

TID = "t-altra-demo"
MANAGER = "m.cracchiolo@hqe.it"
ME = Identity(uid="dev-owner", email=MANAGER, display_name="Massimiliano Cracchiolo", user=None, platform_manager=True)
SECRET = "replace-me"


def run(coro):
    return asyncio.run(coro)


async def call(method, path, who, headers=None, **kw):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        return await c.request(method, path, headers={"X-Dev-User": who, **(headers or {})}, **kw)


# -------- F2: obscured by path and type, not by field name --------
def test_guest_data_hidden_whatever_the_field_is_called(monkeypatch):
    monkeypatch.setattr(webhooks, "get_settings", lambda: dataclasses.replace(get_settings(), italianway_webhook_secret=SECRET))
    payload = {"event": "reservation.created", "id": "iw-ev-f2", "sent_at": "2026-11-01T10:00:00Z",
               "reservation": {"id": "RES-F2", "apartment_id": "IW-F2", "checkin": "2026-12-01T15:00:00Z",
                               "checkout": "2026-12-03T10:00:00Z", "status": "confirmed", "guests": ["Giulia Bianchi", "Marco Neri"],
                               "guest": {"id": "CF BNCGLI80A01H501U", "status": "Giulia VIP", "sent_at": "giulia@ospite.it"}},
               "status": "Giulia Bianchi", "guests": "Marco Neri"}
    raw = json.dumps(payload).encode()
    sig = hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    async def go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
            return await c.post("/webhooks/italianway", content=raw, headers={"X-Signature": sig, "Content-Type": "application/json"})
    run(go())
    stored = run(get_repository().list_webhook_logs(None))[0].raw_body
    for personal in ("Giulia", "Marco", "BNCGLI", "giulia@ospite.it", "VIP"):
        assert personal not in stored, (personal, stored)
    body = json.loads(stored)
    assert body["reservation"]["guests"] == "[oscurato]" and body["reservation"]["status"] == "confirmed"
    assert body["reservation"]["checkin"] == "2026-12-01T15:00:00Z" and body["id"] == "iw-ev-f2"
    payload["reservation"]["guests"] = 3
    assert json.loads(webhooks.obscured_body(b"", payload))["reservation"]["guests"] == 3   # an integer only


# -------- F3: an email changed after the invitation leaves no trace --------
def test_erasure_also_covers_the_email_of_the_invitation():
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-f3", name="F3", first_admin_email="prima@f3.it")))
    inv = run(invites.create_invitation("t-f3", "prima@f3.it", "admin"))
    run(audit.record("invite_sent", audit.SYSTEM, "t-f3", audit.user_target(inv)))
    claims = {"uid": "u-f3", "email_verified": True, "tenant_id": "t-f3", "role": "admin"}
    run(_from_claims(repo, {**claims, "email": "prima@f3.it"}))           # the invitation becomes the account
    run(_from_claims(repo, {**claims, "email": "dopo@f3.it"}))            # then the email changes (L6)
    stored = run(repo.get_user("u-f3"))
    assert stored.email == "dopo@f3.it" and "prima@f3.it" in stored.former_emails
    run(erasure.erase_person("u-f3", stored.email, stored.former_emails))
    assert run(repo.get_audit_people([invites.invite_uid("prima@f3.it")])) == {}
    assert run(repo.get_tenant("t-f3")).first_admin_email is None


# -------- F4: no "opened" entry without an access --------
def test_failed_opening_leaves_a_closing_entry(monkeypatch):
    repo = get_repository()

    async def broken(access):
        raise RuntimeError("Firestore non raggiungibile")
    monkeypatch.setattr(repo, "add_support_access", broken)
    r = run(platform.open_support_access(TID, platform.SupportOpen(hours=1, reason="F4"), identity=ME))
    assert r.status_code == 503
    log = run(repo.list_audit(TID, 100))
    opened = next(e for e in log if e.action == "support_access_opened" and e.details.get("reason") == "F4")
    after = [e for e in log if e.target.id == opened.target.id]
    assert [e.action for e in after] == ["support_access_closed", "support_access_opened"]
    assert after[0].actor.kind == "system" and after[0].details == {"not_opened": True}
    assert run(repo.get_support_access(opened.target.id)) is None                 # and indeed nothing was opened


# -------- minor points --------
def test_suspension_closes_the_active_accesses():
    aid = run(platform.open_support_access(TID, platform.SupportOpen(hours=1, reason="Sosp"), identity=ME))["access_id"]
    try:
        run(platform.suspend_tenant(TID, platform.Suspension(reason="prova"), identity=ME))
        assert run(get_repository().get_support_access(aid)).closed_at is not None
    finally:
        run(platform.reactivate_tenant(TID, identity=ME))


def test_closings_in_other_organisations_are_support_actions():
    repo = get_repository()
    run(repo.upsert_user(User(uid="u-mgr-member", email="mgr.member@hqe.it", tenant_id="t-flatsharing-demo", role="viewer")))
    run(repo.add_platform_member(PlatformMember(email="mgr.member@hqe.it")))
    who = Identity(uid="u-mgr-member", email="mgr.member@hqe.it", display_name="", user=None, platform_manager=True)
    aid = run(platform.open_support_access(TID, platform.SupportOpen(hours=1, reason="Altrove"), identity=who))["access_id"]
    me = CurrentUser("u-mgr-member", "mgr.member@hqe.it", "t-flatsharing-demo", "viewer")
    out = run(account.delete_account(Identity(uid=me.uid, email=me.email, display_name="", user=me, platform_manager=True)))
    assert getattr(out, "status_code", 204) == 204
    closed = next(e for e in run(repo.list_audit(TID, 100)) if e.target.id == aid and e.action == "support_access_closed")
    assert closed.actor.kind == "support" and closed.actor.support_access_id == aid


def test_people_no_longer_members_read_removed_in_the_log():
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-gone", name="Gone")))
    u = User(uid="u-gone", email="gone@gone.it", tenant_id="t-gone", role="operator")
    run(repo.upsert_user(u))
    run(audit.record("invite_resent", audit.by_user(CurrentUser("u-gone", "gone@gone.it", "t-gone", "operator")),
                     "t-gone", audit.user_target(u)))
    assert run(audit.page("t-gone", 10, None, viewer="admin"))["items"][0]["actor"]["email"] == "gone@gone.it"
    run(repo.delete_user("u-gone"))                                        # removed by an admin: not a member any more
    item = run(audit.page("t-gone", 10, None, viewer="admin"))["items"][0]
    assert item["actor"]["removed"] is True and item["actor"]["email"] is None and item["target"]["label"] is None


def test_smtp_errors_never_log_the_address(monkeypatch):
    seen = []
    configured = dataclasses.replace(get_settings(), smtp_user="mittente@esempio.it", smtp_password="x")
    monkeypatch.setattr(invites, "get_settings", lambda: configured)
    monkeypatch.setattr(invites, "_password_link", lambda e, n: None)

    def refuse(msg):
        raise smtplib.SMTPRecipientsRefused({"segreto@destinatario.it": (550, b"5.1.1 segreto@destinatario.it unknown")})
    monkeypatch.setattr(invites, "_send", refuse)
    monkeypatch.setattr(invites, "warn", lambda msg, **f: seen.append((msg, f)))
    run(get_repository().upsert_tenant(Tenant(tenant_id="t-smtp", name="Smtp")))
    assert run(invites.send_invitation("segreto@destinatario.it", "", "viewer", "S", "A", "t-smtp")) == "failed"
    assert seen and "destinatario" not in json.dumps(seen) and "SMTPRecipientsRefused" in json.dumps(seen)


# -------- behaviours so far proven only end to end --------
def test_platform_never_reads_the_organisation_s_emails_in_the_log():
    repo = get_repository()
    run(repo.upsert_tenant(Tenant(tenant_id="t-hide", name="Hide")))
    u = User(uid="u-hide", email="nascosta@hide.it", tenant_id="t-hide", role="admin")
    run(repo.upsert_user(u))
    run(audit.record("role_changed", audit.by_user(CurrentUser("u-hide", "nascosta@hide.it", "t-hide", "admin")), "t-hide",
                     audit.user_target(u), **{"from": "operator", "to": "admin"}))
    page = run(audit.page("t-hide", 10, None, viewer="platform"))
    assert "nascosta@hide.it" not in json.dumps(page)
    assert page["items"][0]["actor"]["role"] == "admin" and page["items"][0]["target"]["role"] == "admin"


@pytest.mark.parametrize("who, path, status", [
    ("lettura@demo.it", "ask/ask-1", 403), ("operatore@demo.it", "version", 403), ("lettura@demo.it", "version", 403),
])
def test_ask_and_version_by_role(who, path, status):
    r = run(call("GET", f"/app/apartments/apt-rimini-01/instance/{path}", who))
    assert r.status_code == status and r.json()["error"] == "forbidden"


def test_suspended_member_me_and_opening_on_a_suspended_organisation():
    run(platform.suspend_tenant(TID, platform.Suspension(reason="prova"), identity=ME))
    try:
        r = run(call("GET", "/app/me", "operatore@altra.it"))
        assert r.status_code == 403 and r.json()["error"] == "tenant_suspended"
        r = run(platform.open_support_access(TID, platform.SupportOpen(hours=1, reason="x"), identity=ME))
        assert r.status_code == 409 and b"tenant_suspended" in r.body
    finally:
        run(platform.reactivate_tenant(TID, identity=ME))


def test_actor_filter_reaches_the_engine_as_the_pseudonym(monkeypatch):
    sent = []

    async def fake_call(apt, method, path, **kw):
        sent.append(kw["params"])
        return httpx.Response(200, json={"items": []}, request=httpx.Request("GET", "http://x"))
    monkeypatch.setattr(instances, "call", fake_call)
    r = run(call("GET", "/app/apartments/apt-rimini-01/instance/decisions", "admin@demo.it",
                 params={"actor": "user:operatore@demo.it", "limit": "5"}))
    assert r.status_code == 200
    params = dict(sent[0])
    operator = run(get_repository().get_user_by_email("operatore@demo.it"))
    assert params["actor"] == "user:" + run(actors.actor_for(operator.uid, operator.email)) and params["limit"] == "5"
    run(call("GET", "/app/apartments/apt-rimini-01/instance/decisions", "admin@demo.it", params={"actor": "user:estraneo@x.it"}))
    assert dict(sent[1])["actor"] == "user:estraneo@x.it"                    # not a member: sent as is, finds nothing
