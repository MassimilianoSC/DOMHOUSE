"""P-48 (D-87): the engine never receives a person's email. X-Actor is a random pseudonym with the syntax of an email
(the contract only asks for an email or system:<name>), created once per person; the BFF turns it back into the email
when it passes the engine's answers to the app (decisions, approvals, the apartment's hold, the stream).

The mapping lives only here (actors/{pseudonym} and actor_refs/{uid}, not in the user record that many routes rewrite
whole). Erasing a person's own account removes it: from then on their pseudonym, and any old decision still carrying
their real email, reads "user:removed" / "removed". A pseudonym or email is shown only to the organisation the person
belongs to, or when it is a platform manager (HQE support, real identity by D-86).
"""
import re
import secrets
import time

from .repository import ActorRecord, get_repository

DOMAIN = "pseudo.hqe.it"
REMOVED, REMOVED_PREFIXED = "removed", "user:removed"
FIELDS = ("actor", "decided_by", "set_by")   # where the contract puts who acted (Decision, Approval, Hold)
# D-90: the engine's free texts may quote whoever acted; a pseudonym there is rewritten too
TEXT_FIELDS = ("reasoning", "description", "reason", "note", "answer")
PSEUDONYM_RE = re.compile(r"p-[0-9a-f]{20}@" + re.escape(DOMAIN))
REMOVED_TEXT = "utente rimosso"
MARKERS = tuple(f'"{f}"' for f in FIELDS) + ("@" + DOMAIN,)   # cheap check before parsing a body
CACHE_SECONDS = 30.0
RENEW_SECONDS = 7 * 24 * 3600   # P-54: the mapping's expiry is pushed forward at most once a week per process

_refs: dict[str, tuple[str, str, float]] = {}                   # uid -> (pseudonym, email, written at) in this process
_resolved: dict[tuple[str, str], tuple[float, str | None]] = {}  # (tenant_id, raw identity) -> (when, email | None)


def is_pseudonym(value: str) -> bool:
    return value.startswith("p-") and value.endswith("@" + DOMAIN)


def new_ref() -> str:
    return f"p-{secrets.token_hex(10)}@{DOMAIN}"


async def actor_for(uid: str, email: str) -> str:
    """The X-Actor of this person: created the first time (atomically, a double request cannot make two), then the
    same forever; the email kept next to it follows the person's current address."""
    cached = _refs.get(uid)
    if cached and cached[1] == email and time.monotonic() - cached[2] < RENEW_SECONDS:
        return cached[0]
    repo = get_repository()
    ref = await repo.claim_actor_ref(uid, new_ref())
    await repo.put_actor(ActorRecord(ref=ref, uid=uid, email=email))   # also renews the expiry (P-54)
    _refs[uid] = (ref, email, time.monotonic())
    return ref


async def forget(uid: str) -> None:
    """The person's own account is gone: the pseudonym no longer leads to anyone."""
    _refs.pop(uid, None)
    _resolved.clear()
    await get_repository().forget_actor(uid)


async def _email_in(tenant_id: str, uid: str | None, email: str) -> str | None:
    """The current email when the person belongs to the organisation or is a platform manager, else None."""
    repo = get_repository()
    u = await repo.get_user(uid) if uid else await repo.get_user_by_email(email)
    if u is not None and u.tenant_id == tenant_id:
        return u.email
    return email if await repo.get_platform_member(email) is not None else None


async def _resolve(tenant_id: str, identities: set[str]) -> dict[str, str | None]:
    now, out, todo = time.monotonic(), {}, []
    for raw in identities:
        hit = _resolved.get((tenant_id, raw))
        if hit and now - hit[0] < CACHE_SECONDS:
            out[raw] = hit[1]
        else:
            todo.append(raw)
    records = await get_repository().get_actors([r for r in todo if is_pseudonym(r)])
    for raw in todo:
        if is_pseudonym(raw):
            rec = records.get(raw)
            email = await _email_in(tenant_id, rec.uid, rec.email) if rec else None
        else:   # an older decision with the real email (before D-87)
            email = await _email_in(tenant_id, None, raw)
        _resolved[(tenant_id, raw)] = (now, email)
        out[raw] = email
    return out


def _identity(value: str) -> tuple[str | None, bool]:
    """(the person part, carried "user:") of an actor value; None when it is not a person (rule, brain, system…)."""
    prefixed = value.startswith("user:")
    raw = value[5:] if prefixed else value
    return (raw if "@" in raw else None), prefixed


def _collect(node, found: set[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in FIELDS and isinstance(v, str):
                raw, _ = _identity(v)
                if raw:
                    found.add(raw)
            elif k in TEXT_FIELDS and isinstance(v, str):
                found.update(PSEUDONYM_RE.findall(v))
            else:
                _collect(v, found)
    elif isinstance(node, list):
        for item in node:
            _collect(item, found)


def _apply(node, emails: dict[str, str | None]):
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k in FIELDS and isinstance(v, str):
                raw, prefixed = _identity(v)
                if raw is None:
                    out[k] = v
                else:
                    email = emails.get(raw)
                    if prefixed or k == "actor":
                        out[k] = f"user:{email}" if email else REMOVED_PREFIXED
                    else:
                        out[k] = email or REMOVED
            elif k in TEXT_FIELDS and isinstance(v, str):
                out[k] = PSEUDONYM_RE.sub(lambda m: emails.get(m.group(0)) or REMOVED_TEXT, v)
            else:
                out[k] = _apply(v, emails)
        return out
    if isinstance(node, list):
        return [_apply(item, emails) for item in node]
    return node


async def rewrite(payload, tenant_id: str):
    """The engine's JSON with every actor turned into the email the organisation may see, or the "removed" sentinel."""
    found: set[str] = set()
    _collect(payload, found)
    if not found:
        return payload
    return _apply(payload, await _resolve(tenant_id, found))
