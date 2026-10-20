"""P-49: an anti-abuse limit on invitation EMAILS, invisible to the user. Invitations are never limited: past the limit
the invitation is created, the email is not sent, the answer is the usual "failed" ("riprova più tardi") and the
organisation's log says why (invite_email_deferred). In-process, memory repository, SMTP replaced by a stub."""
import asyncio
import dataclasses

import pytest

from bff import invites
from bff.auth import CurrentUser
from bff.config import get_settings
from bff.repository import Tenant, User, get_repository
from bff.routes import admin

TENANT = "t-mail-limits"
ADMIN = CurrentUser("u-mail-admin", "admin@limiti.it", TENANT, "admin")


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def smtp(monkeypatch):
    sent = []
    configured = dataclasses.replace(get_settings(), smtp_user="mittente@esempio.it", smtp_password="x")
    monkeypatch.setattr(invites, "get_settings", lambda: configured)
    monkeypatch.setattr(invites, "_password_link", lambda email, name: None)
    monkeypatch.setattr(invites, "_send", lambda msg: sent.append(msg["To"]))
    get_repository().mail_counts.clear()
    run(get_repository().upsert_tenant(Tenant(tenant_id=TENANT, name="Limiti")))
    return sent


def send(email, tenant=TENANT, now=None):
    if now is not None:
        return run(_at(now, email, tenant))
    return run(invites.send_invitation(email, "", "viewer", "Limiti", "Admin", tenant))


async def _at(now, email, tenant):
    real = invites.mail_buckets
    invites.mail_buckets = lambda e, t: real(e, t, now)
    try:
        return await invites.send_invitation(email, "", "viewer", "Limiti", "Admin", tenant)
    finally:
        invites.mail_buckets = real


def test_same_recipient_three_emails_per_ten_minutes_then_ten_per_day(smtp):
    t0 = 1_800_000_000 - 1_800_000_000 % 86_400                        # start of a day: windows aligned
    assert [send("bersaglio@esempio.it", now=t0 + i) for i in range(4)] == ["sent"] * 3 + ["deferred"]
    assert smtp == ["bersaglio@esempio.it"] * 3                           # the fourth never reached SMTP
    assert send("altro@esempio.it", now=t0) == "sent"                     # another recipient is not affected
    later = [send("bersaglio@esempio.it", now=t0 + 600 * k + 1) for k in range(1, 5)]
    assert later == ["sent"] * 4                                          # each new 10-minute window opens again…
    day = [send("bersaglio@esempio.it", now=t0 + 600 * k + 2) for k in range(5, 12)]
    assert day == ["sent"] * 3 + ["deferred"] * 4                         # …up to 10 in the same day
    assert smtp.count("bersaglio@esempio.it") == 10
    assert send("bersaglio@esempio.it", now=t0 + 86_400) == "sent"       # a new day


def test_fifty_emails_per_hour_per_organisation(smtp):
    t0 = 1_800_000_000 - 1_800_000_000 % 3_600
    results = [send(f"p{i}@esempio.it", now=t0 + i) for i in range(51)]
    assert results[:50] == ["sent"] * 50 and results[50] == "deferred"
    assert send("p99@esempio.it", tenant="t-other-org", now=t0) == "sent"   # never another organisation's quota


def test_limit_is_invisible_and_logged(smtp, monkeypatch):
    repo = get_repository()
    run(repo.upsert_user(User(uid="inv-limiti-1", email="ripetuto@esempio.it", tenant_id=TENANT, role="viewer")))
    monkeypatch.setattr(invites, "RECIPIENT_LIMITS", ((600, 1),))
    assert run(admin.resend_invite("inv-limiti-1", ADMIN))["email_status"] == "sent"
    out = run(admin.resend_invite("inv-limiti-1", ADMIN))
    assert out["email_status"] == "failed"                                # same as a temporary failure
    assert run(repo.get_user("inv-limiti-1")) is not None                 # the invitation stays
    actions = [e.action for e in run(repo.list_audit(TENANT, 10))]
    assert actions[:2] == ["invite_email_deferred", "invite_resent"]


def test_a_broken_counter_never_blocks_an_invitation(smtp, monkeypatch):
    async def broken(buckets):
        raise RuntimeError("Firestore non raggiungibile")
    monkeypatch.setattr(get_repository(), "take_mail_quota", broken)
    assert send("comunque@esempio.it") == "sent"


def test_buckets_never_contain_the_address():
    keys = [k for k, _ in invites.mail_buckets("Mario.Rossi@Esempio.it", "t-x", 1_800_000_000)]
    assert keys and all("mario" not in k.lower() and "@" not in k for k in keys)
    assert keys == [k for k, _ in invites.mail_buckets("mario.rossi@esempio.it", "t-x", 1_800_000_000)]
