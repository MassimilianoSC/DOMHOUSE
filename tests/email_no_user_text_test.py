"""Rule of answer 1246 (the committente, 22 November 2026): the app's emails carry only fixed text and fields written
by the platform manager (HQE), never a text written by a user (people's names, names and addresses of apartments
written by a client's admin, notes...). Every user-written field gets a marker; no email composed by the server may
contain one: the invitation and its resending (by an admin and by the platform), the three emails of A6's deletion
(switched off, back on, deletion started) and the assistant's spending alert. In-process, memory repository, dev
auth; the emails are captured, never sent."""
import dataclasses

import pytest

from bff import ai_gateway, deletion, invites
from bff.config import get_settings
from bff.repository import get_repository
from bff.repository.seed import DEMO_TENANT
from tests.creation_test import ADMIN, PLATFORM, call, run, to_ready, world  # noqa: F401  (world is the fixture)

MARKERS = {"invited": "MarcatoreInvitato", "first_admin": "MarcatorePrimoAdmin", "admin": "MarcatoreAdmin",
           "manager": "MarcatoreGestore", "apartment": "MarcatoreAppartamento", "address": "MarcatoreIndirizzo"}
APT = "lab-a2-71"


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    s = dataclasses.replace(get_settings(), smtp_user="mittente@esempio.it", smtp_password="x", smtp_host="smtp.x")
    monkeypatch.setattr(invites, "get_settings", lambda: s)
    monkeypatch.setattr(invites, "_password_link", lambda email: None)
    monkeypatch.setattr(invites, "_send", lambda msg: sent.append(_text(msg)))

    async def deliver(to, subject, text):
        sent.append(f"{subject}\n{text}")
    monkeypatch.setattr(deletion, "_deliver", deliver)
    monkeypatch.setattr(deletion, "_mail_ready", lambda: True)
    repo = get_repository()
    repo.mail_counts.clear()
    admin = run(repo.get_user_by_email("admin@demo.it"))
    run(repo.upsert_user(admin.model_copy(update={"display_name": MARKERS["admin"]})))
    manager = run(repo.get_platform_member("piattaforma@demo.it"))
    run(repo.add_platform_member(manager.model_copy(update={"display_name": MARKERS["manager"]})))
    yield sent
    run(repo.upsert_user(admin))
    run(repo.add_platform_member(manager))
    repo.mail_counts.clear()


def _text(msg) -> str:
    parts = [msg["Subject"] or ""]
    parts += [p.get_content() for p in msg.walk() if p.get_content_type().startswith("text/")]
    return "\n".join(parts)


def _no_marker(sent: list[str], at_least: int):
    assert len(sent) >= at_least, sent
    for text in sent:
        found = [k for k, m in MARKERS.items() if m in text]
        assert not found, (found, text[:400])


def test_invitations_and_their_resending_carry_no_user_written_text(world, outbox):
    r = call("POST", "/app/admin/users", headers=ADMIN, json={"email": "marcatore-invitato@esempio.it", "role": "viewer",
                                                             "display_name": MARKERS["invited"]})
    assert r.status_code == 201, r.text
    uid = r.json()["uid"]
    assert call("POST", f"/app/admin/users/{uid}/invite", headers=ADMIN).status_code == 200
    r = call("POST", "/app/platform/tenants", json={"name": "Organizzazione F-1246", "admin_email": "marcatore-primo@esempio.it",
                                                   "admin_display_name": MARKERS["first_admin"]})
    assert r.status_code == 201, r.text
    assert call("POST", f"/app/platform/tenants/{r.json()['tenant_id']}/invite").status_code == 200
    _no_marker(outbox, 4)
    assert any("Un amministratore di «Flatsharing" in t for t in outbox)                # the fixed sender line
    assert any("Il gestore della piattaforma ti ha invitato" in t for t in outbox)
    assert all("marcatore-" in t for t in outbox)                                        # the invited address stays


def test_the_three_deletion_emails_carry_no_user_written_text(world, outbox):
    to_ready(world, APT)
    r = call("PATCH", f"/app/admin/apartments/{APT}", headers=ADMIN,
             json={"name": MARKERS["apartment"], "address": MARKERS["address"]})
    assert r.status_code == 200, r.text
    assert call("PATCH", f"/app/admin/apartments/{APT}", headers=ADMIN, json={"enabled": False}).status_code == 200
    assert call("PATCH", f"/app/admin/apartments/{APT}", headers=ADMIN, json={"enabled": True}).status_code == 200
    base = f"/app/platform/tenants/{DEMO_TENANT}/apartments/{APT}"
    assert call("POST", f"{base}/disattiva").status_code == 200
    from datetime import timedelta
    world.now = world.now + timedelta(days=7, seconds=1)
    r = call("POST", f"{base}/elimina", json={"nome": MARKERS["apartment"]})
    assert r.status_code in (200, 202), r.text
    _no_marker(outbox, 4)
    assert all(APT in t for t in outbox)                                                 # the technical id instead
    assert all("Apri DOMHOUSE per vedere di quale appartamento si tratta:" in t for t in outbox)


def test_the_spending_alert_carries_no_user_written_text():
    msg = ai_gateway._alert_email(["gestore@esempio.it"], "2026-11", 16.5)
    _no_marker([_text(msg)], 1)


def test_the_firebase_account_made_for_an_invitation_carries_no_name(monkeypatch):
    """Firebase's own emails may show %DISPLAY_NAME%: the account the server makes has no name (answer 1246, point 2)."""
    from firebase_admin import auth as fb_auth
    made = []

    def missing(email, app=None):
        raise fb_auth.UserNotFoundError("nessuno")
    monkeypatch.setattr(fb_auth, "get_user_by_email", missing)
    monkeypatch.setattr(fb_auth, "create_user", lambda **kw: made.append(kw))
    monkeypatch.setattr(fb_auth, "generate_password_reset_link", lambda email, action_code_settings=None, app=None:
                        "https://x.example/reset?oobCode=1")
    import bff.auth
    monkeypatch.setattr(bff.auth, "firebase_app", lambda: None)
    s = dataclasses.replace(get_settings(), auth_mode="firebase")
    monkeypatch.setattr(invites, "get_settings", lambda: s)
    assert invites._password_link("senza-nome@esempio.it")
    assert made and "display_name" not in made[0] and made[0]["email"] == "senza-nome@esempio.it"
