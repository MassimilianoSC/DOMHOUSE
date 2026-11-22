"""Invitation emails for users added from the admin area.

The invite itself is the `inv-*` record in the repository (see auth._from_claims, which migrates it to the Firebase uid
on first sign-in). This module only helps the invited person get in:

* with AUTH_MODE=firebase it makes sure a Firebase Auth account exists for the email (no claims: access still comes
  from the repository record) and generates a password setup link, so users without a Google account can sign in
  with email and password;
* it sends an email over SMTP (SMTP_* settings) with the app URL, the Google sign-in hint and the password link.

Sending never raises: the outcome is reported to the admin as `email_status` (sent | not_configured | failed).
`create_invitation` (P-36) is the one way an invitation record is created, by the admin area and by the platform.
"""
import asyncio
import hashlib
import html
import smtplib
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .config import get_settings
from .logs import info, warn
from .repository import User, get_repository, normalize_email

EmailStatus = Literal["sent", "not_configured", "failed", "deferred"]   # "deferred" never leaves the BFF (see shown)

# P-49: anti-abuse limit on invitation EMAILS (never on invitations): fixed windows, (seconds, max emails). Far above
# normal use; when one is reached the email is not sent, the invitation stays, and the answer is the same as for a
# temporary failure ("riprova più tardi"), so the limit is invisible to the user.
RECIPIENT_LIMITS = ((600, 3), (86_400, 10))
TENANT_LIMITS = ((3_600, 50),)

ROLE_LABELS = {"admin": "amministratore", "operator": "operatore", "viewer": "sola lettura"}
LINK_VALIDITY = "1 ora"
EXPIRED_HINT = "Password dimenticata?"  # same label as the login page link


def _with_lang(link: str, lang: str = "it") -> str:
    parts = urlsplit(link)
    query = dict(parse_qsl(parts.query))
    query["lang"] = lang
    return urlunsplit(parts._replace(query=urlencode(query)))


def _password_link(email: str) -> str | None:
    """Creates the Firebase account if missing and returns a password setup link (None outside firebase mode)."""
    settings = get_settings()
    if settings.auth_mode != "firebase":
        return None
    from firebase_admin import auth as fb_auth

    from .auth import firebase_app

    app = firebase_app()
    try:
        fb_auth.get_user_by_email(email, app=app)
    except fb_auth.UserNotFoundError:
        # rule of answer 1246: no user-written text in Firebase's profile either (its emails may show %DISPLAY_NAME%)
        fb_auth.create_user(email=email, email_verified=False, app=app)
        info("invite: firebase account created", invite=invite_uid(email))
    action = fb_auth.ActionCodeSettings(url=settings.app_public_url) if settings.app_public_url else None
    return _with_lang(fb_auth.generate_password_reset_link(email, action_code_settings=action, app=app))


def _compose(to: str, role: str, tenant_name: str, by_platform: bool, link: str | None) -> EmailMessage:
    """Rule of answer 1246 (the committente, 22 November 2026): only fixed text and fields written by the platform (the
    organisation's name, set only by the platform; the app's address and sender from the manifest); never a name
    written by a user. The invited address stays (a6): the recipient's own."""
    s = get_settings()
    app_url = s.app_public_url or ""
    role_label = ROLE_LABELS.get(role, role)
    greeting = "Ciao,"
    if by_platform:
        org = f" per «{tenant_name}»" if tenant_name else ""
        sentence = f"Il gestore della piattaforma ti ha invitato a usare {s.mail_from_name}{org}, con il ruolo {role_label}."
    else:
        sentence = (f"Un amministratore di «{tenant_name}» ti ha invitato a usare {s.mail_from_name}, con il ruolo "
                    f"{role_label}.")

    text = [
        greeting,
        "",
        sentence,
        "",
        f"Apri l'app: {app_url}",
        f"- Se {to} è un account Google, tocca «Accedi con Google».",
    ]
    if link:
        text += [
            f"- Altrimenti scegli la tua password da questo link (vale {LINK_VALIDITY}), poi accedi con email e password:",
            f"  {link}",
            f"  Se il link è scaduto, nella pagina di accesso usa «{EXPIRED_HINT}».",
        ]
    text += ["", "Se non aspettavi questo invito, ignora questa email."]

    e = html.escape
    link_html = (
        f'<p>Altrimenti scegli la tua password (il link vale {LINK_VALIDITY}), poi accedi con email e password:</p>'
        f'<p><a href="{e(link)}" style="display:inline-block;padding:10px 18px;border-radius:10px;'
        f'background:#c4541f;color:#ffffff;text-decoration:none;font-weight:bold">Scegli la password</a></p>'
        f'<p style="color:#6b7280;font-size:13px">Se il link è scaduto, nella pagina di accesso usa «{EXPIRED_HINT}».</p>'
        if link else ""
    )
    body_html = f"""<!doctype html><html lang="it"><body style="font-family:Arial,sans-serif;color:#1f2937;line-height:1.5">
<p>{e(greeting)}</p>
<p>{e(sentence)}</p>
<p><a href="{e(app_url)}" style="display:inline-block;padding:10px 18px;border-radius:10px;background:#1f2937;color:#ffffff;text-decoration:none;font-weight:bold">Apri l'app</a></p>
<p>Se <strong>{e(to)}</strong> è un account Google, tocca «Accedi con Google».</p>
{link_html}
<p style="color:#6b7280;font-size:13px">Se non aspettavi questo invito, ignora questa email.</p>
</body></html>"""

    msg = EmailMessage()
    msg["Subject"] = f"Invito a {s.mail_from_name}"
    msg["From"] = formataddr((s.mail_from_name, s.smtp_user))
    msg["To"] = to
    msg.set_content("\n".join(text))
    msg.add_alternative(body_html, subtype="html")
    return msg


def _send(msg: EmailMessage) -> None:
    s = get_settings()
    ctx = ssl.create_default_context()
    if s.smtp_port == 465:
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=ctx, timeout=15) as smtp:
            smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls(context=ctx)
            smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)


def mail_buckets(email: str, tenant_id: str, now: float | None = None) -> list[tuple[str, int]]:
    """Counter keys for this email right now; the recipient is a hash, never the address."""
    t = int(time.time() if now is None else now)
    to = hashlib.sha256(normalize_email(email).encode()).hexdigest()[:16]
    return ([(f"to-{to}-{s}-{t // s}", n) for s, n in RECIPIENT_LIMITS]
            + [(f"tenant-{tenant_id}-{s}-{t // s}", n) for s, n in TENANT_LIMITS])


def shown(status: EmailStatus) -> str:
    """What the caller sees: a deferred email reads as a temporary failure."""
    return "failed" if status == "deferred" else status


async def send_invitation(email: str, role: str, tenant_name: str, tenant_id: str,
                          by_platform: bool = False) -> EmailStatus:
    """by_platform: the platform manager invites (a new organisation's first admin), else an admin of tenant_name."""
    settings = get_settings()
    if not settings.mail_configured:
        info("invite: email not sent, SMTP not configured", invite=invite_uid(email))
        return "not_configured"
    try:
        allowed = await get_repository().take_mail_quota(mail_buckets(email, tenant_id))
    except Exception as exc:  # the counters are a protection, not a dependency: never block a legitimate invitation
        warn("invite: email limit not checked", invite=invite_uid(email), error=str(exc))
        allowed = True
    if not allowed:
        warn("invite: email deferred by the anti-abuse limit", invite=invite_uid(email), tenant_id=tenant_id)
        return "deferred"
    try:
        link = await asyncio.to_thread(_password_link, email)
    except Exception as exc:  # the email still helps Google users
        warn("invite: password link not generated", invite=invite_uid(email), error=str(exc))
        link = None
    try:
        await asyncio.to_thread(_send, _compose(email, role, tenant_name, by_platform, link))
    except Exception as exc:
        # D-91: the type and the SMTP code only; the server's text may quote the address
        warn("invite: email failed", invite=invite_uid(email), error=type(exc).__name__,
             smtp_code=getattr(exc, "smtp_code", None))
        return "failed"
    info("invite: email sent", invite=invite_uid(email), password_link=bool(link))
    return "sent"


class InviteRefused(Exception):
    def __init__(self, message: str, status: int = 409, error: str | None = None):
        super().__init__(message)
        self.message, self.status, self.error = message, status, error


def invite_uid(email: str) -> str:
    """Deterministic per mailbox: a double click or two admins inviting the same address at once create ONE record."""
    return "inv-" + hashlib.sha256(normalize_email(email).encode()).hexdigest()[:16]


async def create_invitation(tenant_id: str, email: str, role: str, display_name: str = "",
                            apartment_ids: list[str] | None = None) -> User:
    """Creates the `inv-*` record (a person belongs to one organisation only). Raises InviteRefused with a message
    that never reveals another organisation (D-63)."""
    repo = get_repository()
    email = normalize_email(email)
    # F5 (D-70): never invite a platform manager (its email is visible to every user) — it could be captured into an
    # organisation, or its Firebase account deleted by cancelling the invite. Same neutral message.
    if await repo.get_platform_member(email):
        raise InviteRefused("Questa email non può essere invitata")
    if existing := await repo.get_user_by_email(email):
        raise InviteRefused("È già un utente della tua organizzazione" if existing.tenant_id == tenant_id
                            else "Questa email non può essere invitata")
    # F-14 (attack-from-outside review, answer 1243): a person enabled in another organisation by claims only (the first
    # admin of set_claims.py, never signed in, so no record) was invited and, at the first sign-in, the invitation won:
    # the other organisation lost the person without deciding it. Refused like a record there, the same neutral words
    from . import accounts
    try:
        claims = await asyncio.to_thread(accounts.env_claims_of_email, email)
    except Exception as exc:
        warn("invite: claims of the email not read", error=type(exc).__name__)
        raise InviteRefused("Controllo dell'accesso non disponibile: riprova tra poco", 503, "auth_unavailable")
    other = claims.get("tenant_id") if claims else None
    if other and other != tenant_id:
        # final rereading R-2 (a6's choice a): only an organisation that exists and is active keeps the person; claims
        # left by one deleted or suspended (people removed before R4-1) do not block. An active one's stale claims are
        # cleared by the platform: scripts/set_claims.py --orphan-claims --apply --email <email>
        held_by = await repo.get_tenant(other)
        if held_by is not None and held_by.status == "active":
            raise InviteRefused("Questa email non può essere invitata")
    user = User(uid=invite_uid(email), email=email, display_name=display_name, tenant_id=tenant_id, role=role,
                apartment_ids=apartment_ids)
    if not await repo.create_user_if_absent(user):  # someone created the same invitation a moment ago
        other = await repo.get_user(user.uid)
        raise InviteRefused("È già un utente della tua organizzazione" if other and other.tenant_id == tenant_id
                            else "Questa email non può essere invitata")
    return user
