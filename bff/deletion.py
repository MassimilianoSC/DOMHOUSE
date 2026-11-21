"""Tool A, package A6 (docs/proposta-a6.md; bff/API.md «Eliminazione di un appartamento»; answers 1210): switch an
apartment off, wait 7 days, delete it with its name.

- ONE state of «switched off»: the platform's «Disattiva» and the administrator's «Attivo» both write enabled false,
  disattivato_at and disattivato_da (bff/routes/admin.py calls on_admin_enabled). It does what it did before A6 (the
  engine's automations go on; notifications, summaries, bookings, Excel stop). The 7 days count from disattivato_at,
  whoever switched it off; switching on clears it. Switched off before A6 (no time): not deletable until «Disattiva»
  writes the time.
- Who deletes: only the platform manager (answer 1210, point 1, provisional): can_delete, the one place to change with
  D-232.
- «Elimina» by origine: «app» (made with A2) goes through togli_motore (the agent acts only with its creation mark),
  then the two secrets destroyed with the delay, then the database (the devices' credentials, then remove_apartment:
  record, users' lists, link, Italianway code; the id stays used, D-67). Never a record removed with the engine still
  there. «a_mano» and «dimostrativo»: only the record, at once. «dev»: never (D-118).
- State computed at read time, as the creation's: 20 minutes without progress, or the order closed without success, is
  «non_riuscita» with its code; «Riprova» goes on from the step that stopped.
- Emails to the organisation's administrators and the platform managers at every switch-off and switch-on (whoever
  did it: risk 1 of the proposal is a compromised administrator) and when a deletion starts; at most MAIL_PER_HOUR an
  hour per apartment for the switches, a quota of its own for the deletion (A6 review, point 5).
- At most DAILY_LIMIT deletions a day per organisation (answer 1210, point 6), counted only once a deletion really
  starts (review, point 4); «Riprova» does not count.
- The administrator never switches on what the platform switched off (review, point 1, the prudent road until the
  committente decides): 409 disabled_by_platform.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr

from . import agent, audit, instances, secret_admin
from .config import get_settings
from .logs import warn
from .repository import get_repository
from .repository.base import Apartment, AuditPerson, Disattivazione, Eliminazione, iso_seconds

WAIT = timedelta(days=7)                       # answer 1210, point 2
DAILY_LIMIT = 2                                # answer 1210, point 6
MAIL_PER_HOUR = 4                              # emails about one apartment an hour (a switch toggled again and again)
MAX_WAIT = agent.MAX_WAIT                      # 20 minutes, as the creation
OWN_MESSAGES = {
    "chiavi_non_distrutte": "Il sistema domotico è stato tolto, ma le chiavi no: «Riprova».",
    "errore_database": "Il sistema domotico e le chiavi sono stati tolti, ma l'appartamento è ancora nell'elenco: «Riprova».",
}


class DeletionRefused(Exception):
    def __init__(self, status: int, error: str, message: str, **details):
        super().__init__(message)
        self.status, self.error, self.message, self.details = status, error, message, details


def utcnow() -> datetime:
    return agent.utcnow()


def stamp(t: datetime | None = None) -> str:
    return (t or utcnow()).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse(value: str) -> datetime:
    return datetime.fromtimestamp(iso_seconds(value), UTC)


def can_delete(identity) -> bool:
    """Answer 1210, point 1 (provisional): only the platform managers delete. With D-232 the administrators too: here."""
    return getattr(identity, "platform_manager", False) is True


def origine(apt: Apartment) -> str:
    if apt.apartment_id == "dev":
        return "dev"
    if apt.creazione is not None:
        return "app"
    if instances.is_mock(apt.instance_url):
        return "dimostrativo"
    return "a_mano"


def eliminabile_dal(apt: Apartment) -> str | None:
    if apt.enabled or not apt.disattivato_at or origine(apt) == "dev" or apt.eliminazione is not None:
        return None
    return stamp(parse(apt.disattivato_at) + WAIT)


def message(code: str | None) -> str:
    return OWN_MESSAGES.get(code or "") or agent.MESSAGES.get(code or "", "")


# ---- what the site sees ------------------------------------------------------------------------------------------
async def _op_of(e: Eliminazione):
    return await get_repository().get_agent_op(e.op["op_id"]) if e.op else None


def effective(e: Eliminazione, op) -> tuple[str, str | None]:
    if e.stato == "in_corso":
        if op is not None and op.stato not in ("inviato", "riuscito"):
            return "non_riuscita", op.codice
        if utcnow().timestamp() - iso_seconds(e.updated_at) > MAX_WAIT.total_seconds():
            return "non_riuscita", "tempo_scaduto"
    return e.stato, e.codice


async def _names(uids) -> dict:
    refs = sorted({u for u in uids if isinstance(u, str)})
    people = await get_repository().get_audit_people(refs) if refs else {}
    return {ref: (p.display_name or None) for ref, p in people.items()}


def who_view(apt: Apartment, names: dict) -> dict | None:
    d = apt.disattivato_da
    return None if d is None else {"ruolo": d.ruolo, "nome": names.get(d.uid)}


async def eliminazione_view(apt: Apartment, names: dict | None = None) -> dict | None:
    e = apt.eliminazione
    if e is None:
        return None
    names = names if names is not None else await _names([e.updated_by])
    op = await _op_of(e)
    stato, codice = effective(e, op)
    return {"stato": stato, "passo": e.passo, "codice": codice if stato == "non_riuscita" else None,
            "messaggio": message(codice) if stato == "non_riuscita" else None,
            "op": None if op is None else {"op_id": op.op_id, "operazione": op.operazione, "stato": op.stato,
                                           "codice": op.codice, "messaggio": agent.describe(op)["messaggio"]},
            "version": e.version, "iniziata_at": e.iniziata_at, "updated_at": e.updated_at,
            "updated_by": names.get(e.updated_by)}


async def views(apartments) -> dict[str, dict]:
    """The A6 fields of each platform row (bff/API.md)."""
    uids = [a.disattivato_da.uid for a in apartments if a.disattivato_da]
    uids += [a.eliminazione.updated_by for a in apartments if a.eliminazione]
    names = await _names(uids)
    out = {}
    for a in apartments:
        out[a.apartment_id] = {"disattivato_at": a.disattivato_at, "disattivato_da": who_view(a, names),
                               "eliminabile_dal": eliminabile_dal(a), "origine": origine(a),
                               "eliminazione": await eliminazione_view(a, names)}
    return out


async def admin_names(apartments) -> dict:
    return await _names(a.disattivato_da.uid for a in apartments if a.disattivato_da)


# ---- emails ------------------------------------------------------------------------------------------------------
def _mail_ready() -> bool:
    return get_settings().mail_configured


async def _deliver(to: str, subject: str, text: str) -> None:
    """One email, one recipient (nobody sees the others' addresses). Replaced in the tests."""
    from .invites import _send
    s = get_settings()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((s.mail_from_name, s.smtp_user))
    msg["To"] = to
    msg.set_content(text)
    await asyncio.to_thread(_send, msg)


async def _recipients(tenant_id: str) -> list[str]:
    repo = get_repository()
    admins = [u.email for u in await repo.list_users(tenant_id) if u.role == "admin" and u.email]
    managers = [m.email for m in await repo.list_platform_members() if m.email]
    return sorted({e.strip().lower() for e in admins + managers})


async def notify(apt: Apartment, what: str, who: str | None) -> None:
    """«disattivato» or «eliminazione»: never blocks the change; a failure is a log line."""
    try:
        if not _mail_ready():
            warn("deletion mail not sent", apartment_id=apt.apartment_id, motivo="posta_non_configurata")
            return
        hour = utcnow().strftime("%Y%m%d%H")
        kind = "eliminazione" if what == "eliminazione" else "interruttore"     # review, point 5: two quotas
        if not await get_repository().take_mail_quota([(f"deletion_mail:{kind}:{apt.apartment_id}:{hour}",
                                                        MAIL_PER_HOUR)]):
            warn("deletion mail not sent", apartment_id=apt.apartment_id, motivo="limite_orario")
            return
        when = utcnow().strftime("%d/%m/%Y %H:%M UTC")
        if what == "disattivato":
            subject = f"Appartamento disattivato: {apt.name}"
            lines = [f"L'appartamento «{apt.name}» ({apt.apartment_id}) è stato disattivato il {when}"
                     f"{' da ' + who if who else ''}.",
                     "Gli automatismi del sistema domotico continuano; notifiche, riepiloghi, prenotazioni ed export "
                     "Excel sono fermi finché non viene riattivato."]
            if origine(apt) != "dev":
                lines.append(f"Da {stamp(utcnow() + WAIT)[:10]} il gestore della piattaforma potrà eliminarlo.")
        elif what == "riattivato":
            subject = f"Appartamento riattivato: {apt.name}"
            lines = [f"L'appartamento «{apt.name}» ({apt.apartment_id}) è stato riattivato il {when}"
                     f"{' da ' + who if who else ''}.", "Notifiche, riepiloghi, prenotazioni ed export Excel ripartono."]
        else:
            subject = f"Eliminazione avviata: {apt.name}"
            lines = [f"L'eliminazione dell'appartamento «{apt.name}» ({apt.apartment_id}) è stata avviata il {when}"
                     f"{' da ' + who if who else ''}.", "Non si può annullare: resta solo il recupero dello storico."]
        lines.append("Se non te lo aspettavi, avvisa subito il gestore della piattaforma.")
        for to in await _recipients(apt.tenant_id):
            try:
                await _deliver(to, subject, "\n\n".join(lines))
            except Exception as exc:                             # noqa: BLE001 - the others still get theirs
                warn("deletion mail not sent", apartment_id=apt.apartment_id, error=type(exc).__name__)
    except Exception as exc:                                     # noqa: BLE001 - an email never stops the change
        warn("deletion mail not sent", apartment_id=apt.apartment_id, error=type(exc).__name__)


# ---- switching off and on ----------------------------------------------------------------------------------------
async def _person(identity) -> None:
    await get_repository().put_audit_person(AuditPerson(ref=identity.uid, email=identity.email,
                                                        display_name=identity.display_name))


async def disable(apt: Apartment, identity) -> Apartment:
    """The platform's «Disattiva»; also writes the time of one switched off before A6."""
    def change(a: Apartment):
        if a.eliminazione is not None:
            raise DeletionRefused(409, "deletion_in_progress", "L'eliminazione di questo appartamento è in corso.")
        if a.creazione is not None and a.creazione.stato != "pronto":          # review, point 3
            raise DeletionRefused(409, "creation_not_ready", "La creazione non è finita: usa «Annulla».")
        if not a.enabled and a.disattivato_at:
            raise DeletionRefused(409, "already_disabled", "L'appartamento è già disattivato.")
        a.enabled = False
        a.disattivato_at = stamp()
        a.disattivato_da = Disattivazione(ruolo="gestore", uid=identity.uid)
        return a
    saved = await get_repository().change_apartment(apt.apartment_id, change)
    await _after_switch(saved)
    await _person(identity)
    await audit.record("apartment_disabled", audit.by_platform(identity), saved.tenant_id,
                       audit.apartment_target(saved.apartment_id, saved.name), da="gestore")
    await notify(saved, "disattivato", identity.display_name or None)
    return saved


async def enable(apt: Apartment, identity) -> Apartment:
    def change(a: Apartment):
        if a.eliminazione is not None:
            raise DeletionRefused(409, "deletion_in_progress", "L'eliminazione di questo appartamento è in corso.")
        if a.enabled:
            raise DeletionRefused(409, "not_disabled", "L'appartamento è già attivo.")
        a.enabled, a.disattivato_at, a.disattivato_da = True, None, None
        return a
    saved = await get_repository().change_apartment(apt.apartment_id, change)
    await _after_switch(saved)
    await _person(identity)
    await audit.record("apartment_reenabled", audit.by_platform(identity), saved.tenant_id,
                       audit.apartment_target(saved.apartment_id, saved.name))
    await notify(saved, "riattivato", identity.display_name or None)          # review, point 1
    return saved


async def _after_switch(saved: Apartment) -> None:
    from .sse_hub import hub_manager
    instances.invalidate_version(saved.apartment_id)
    hub_manager.hub(saved)


def on_admin_enabled(apt: Apartment, wanted: bool, user) -> str | None:
    """The administrator's «Attivo» (PATCH): the same state as «Disattiva». Changes apt in place before it is saved;
    «disabled», «enabled» or None (no change). Raises while a deletion runs."""
    if apt.eliminazione is not None:
        raise DeletionRefused(409, "deletion_in_progress", "L'eliminazione di questo appartamento è in corso.")
    if apt.enabled and not wanted:
        apt.disattivato_at = stamp()
        apt.disattivato_da = Disattivazione(ruolo="amministratore", uid=user.uid)
        return "disabled"
    if not apt.enabled and wanted:
        if apt.disattivato_da is not None and apt.disattivato_da.ruolo == "gestore":     # review, point 1
            raise DeletionRefused(409, "disabled_by_platform",
                                  "L'ha disattivato il gestore della piattaforma: solo lui può riattivarlo.")
        apt.disattivato_at, apt.disattivato_da = None, None
        return "enabled"
    return None


async def after_admin_switch(saved: Apartment, what: str | None, user) -> None:
    if what == "disabled":
        await audit.record("apartment_disabled", audit.by_user(user), saved.tenant_id,
                           audit.apartment_target(saved.apartment_id, saved.name), da="amministratore")
        await notify(saved, "disattivato", getattr(user, "display_name", None) or None)
    elif what == "enabled":
        await audit.record("apartment_reenabled", audit.by_user(user), saved.tenant_id,
                           audit.apartment_target(saved.apartment_id, saved.name))
        await notify(saved, "riattivato", getattr(user, "display_name", None) or None)


# ---- «Elimina» ---------------------------------------------------------------------------------------------------
def _same_name(given, saved: str) -> bool:
    return isinstance(given, str) and given.strip() == saved.strip() and given.strip() != ""


def _tomorrow() -> str:
    now = utcnow()
    return stamp(datetime(now.year, now.month, now.day, tzinfo=UTC) + timedelta(days=1))


async def start(apt: Apartment, nome, identity) -> tuple[int, dict]:
    """(status, body). The checks in the order of bff/API.md, all before anything is touched."""
    kind = origine(apt)
    if kind == "dev":
        raise DeletionRefused(409, "not_deletable", "Questo appartamento non si può eliminare.")
    if apt.creazione is not None and apt.creazione.stato != "pronto":
        raise DeletionRefused(409, "creation_not_ready", "La creazione non è finita: usa «Annulla».")
    if apt.enabled:
        raise DeletionRefused(409, "not_disabled", "Prima disattiva l'appartamento.")
    if apt.eliminazione is None:
        when = eliminabile_dal(apt)
        if when is None or parse(when) > utcnow():
            raise DeletionRefused(409, "too_early", "Si può eliminare solo dopo 7 giorni di disattivazione.",
                                  eliminabile_dal=when)
    if not _same_name(nome, apt.name):
        raise DeletionRefused(422, "name_mismatch", "Il nome non corrisponde")
    if apt.eliminazione is not None:
        raise DeletionRefused(409, "deletion_in_progress", "L'eliminazione di questo appartamento è in corso.")
    if kind == "app" and not agent.configured():
        raise DeletionRefused(503, "agent_not_configured", "L'agente sulla VM non è configurato in questo ambiente")
    # review, point 4: the deletion is written first, in the apartment's transaction (a double click or two managers:
    # the second is refused here), and only then the place of the day is taken; without a place it is taken back
    now = stamp()

    def change(a: Apartment):
        if a.enabled or a.eliminazione is not None:
            raise DeletionRefused(409, "deletion_in_progress", "L'eliminazione di questo appartamento è in corso.")
        a.eliminazione = Eliminazione(iniziata_da=identity.uid, updated_by=identity.uid, iniziata_at=now, updated_at=now,
                                      passo="motore" if kind == "app" else "database")
        return a
    saved = await get_repository().change_apartment(apt.apartment_id, change)
    if saved is None:
        raise DeletionRefused(404, "not_found", "Appartamento inesistente")
    day = utcnow().strftime("%Y%m%d")
    if not await get_repository().take_mail_quota([(f"deletions:{apt.tenant_id}:{day}", DAILY_LIMIT)]):
        def undo(a: Apartment):
            if a.eliminazione is None or a.eliminazione.iniziata_at != now or a.eliminazione.iniziata_da != identity.uid:
                return None
            a.eliminazione = None
            return a
        await get_repository().change_apartment(apt.apartment_id, undo)
        raise DeletionRefused(429, "rate_limited", "Oggi sono già state fatte le eliminazioni possibili: riprova domani.",
                              riprova_dal=_tomorrow())
    await _person(identity)
    target = audit.apartment_target(apt.apartment_id, apt.name)
    if kind != "app":                                # only the record (answer 1210, point 4)
        await audit.record("apartment_deletion_started", audit.by_platform(identity), apt.tenant_id, target,
                           origine=kind)
        await notify(saved, "eliminazione", identity.display_name or None)
        try:
            await _remove(saved)
        except Exception as exc:                                 # noqa: BLE001 - second reading: «Riprova», never a 500
            warn("deletion database step failed", apartment_id=apt.apartment_id, error=type(exc).__name__)
            await _fail(apt.apartment_id, "database", "errore_database")
            return 202, {"eliminazione": await eliminazione_view(await get_repository().get_apartment(apt.apartment_id))}
        await audit.record("apartment_deleted", audit.by_platform(identity), apt.tenant_id, target)
        return 200, {"eliminazione": {"stato": "eliminato"}}
    await audit.record("apartment_deletion_started", audit.by_platform(identity), apt.tenant_id, target, origine=kind)
    await notify(saved, "eliminazione", identity.display_name or None)
    await _send_togli(saved)                         # AgentError (502) goes up, saved «non_riuscita: non_inviato»
    return 202, {"eliminazione": await eliminazione_view(await get_repository().get_apartment(apt.apartment_id))}


async def _save(apartment_id: str, expect_version: int | None = None, expect_op: str | None = None,
                uid: str | None = None, **changes) -> Apartment | None:
    def change(a: Apartment):
        e = a.eliminazione
        if e is None or (expect_version is not None and e.version != expect_version) \
                or (expect_op is not None and (e.op or {}).get("op_id") != expect_op):
            return None
        for k, v in changes.items():
            setattr(e, k, v)
        e.version += 1
        e.updated_at = stamp()
        if uid:
            e.updated_by = uid
        return a
    return await get_repository().change_apartment(apartment_id, change)


async def _fail(apartment_id: str, passo: str, codice: str | None, expect_op: str | None = None) -> None:
    saved = await _save(apartment_id, expect_op=expect_op, stato="non_riuscita", passo=passo,
                        codice=codice or "errore_interno")
    if saved is not None:
        await audit.record("apartment_deletion_failed", audit.SYSTEM, saved.tenant_id,
                           audit.apartment_target(apartment_id, saved.name), passo=passo, codice=codice)


async def _send_togli(apt: Apartment) -> None:
    e = apt.eliminazione
    op, body = await agent.new_order("togli_motore", apt.apartment_id, e.updated_by, {})
    if await _save(apt.apartment_id, expect_version=e.version, op={"op_id": op.op_id, "operazione": "togli_motore"},
                   stato="in_corso", passo="motore", codice=None) is None:
        raise DeletionRefused(409, "version_changed", "Qualcuno ha appena cambiato questa eliminazione: ricarica.")
    try:
        await agent.publish_op(op, body)
    except agent.AgentError:
        await _fail(apt.apartment_id, "motore", "non_inviato", expect_op=op.op_id)
        raise


async def _remove(apt: Apartment) -> None:
    from .routes.admin import remove_apartment
    await get_repository().delete_device_credentials(apt.apartment_id)
    await remove_apartment(apt)


async def _finish(apartment_id: str) -> str:
    """After the engine is gone: the secrets, then the database. «eliminato» or «non_riuscita»."""
    repo = get_repository()
    apt = await repo.get_apartment(apartment_id)
    if apt is None or apt.eliminazione is None:
        return "gia_eliminato"
    e = apt.eliminazione
    if origine(apt) == "app":
        # second reading of A6: only an apartment made from the app loses its secrets; one linked by hand (lab-01, a
        # demonstration) loses only its record (answer 1210, point 4), also through «Riprova»
        apt = await _save(apartment_id, expect_version=e.version, stato="in_corso", passo="segreti", codice=None)
        if apt is None:
            return "stato_diverso"
        try:
            await secret_admin.destroy_pair(secret_admin.get_secret_admin(), apartment_id)
        except secret_admin.SecretError as exc:
            warn("deletion secrets not destroyed", apartment_id=apartment_id, error=str(exc))
            await _fail(apartment_id, "segreti", "chiavi_non_distrutte")
            return "non_riuscita"
    apt = await _save(apartment_id, expect_version=apt.eliminazione.version, stato="in_corso", passo="database",
                      codice=None)
    if apt is None:
        return "stato_diverso"
    try:
        await _remove(apt)
    except Exception as exc:                                     # noqa: BLE001 - «Riprova» completes it
        warn("deletion database step failed", apartment_id=apartment_id, error=type(exc).__name__)
        await _fail(apartment_id, "database", "errore_database")
        return "non_riuscita"
    who = audit.Who(audit.AuditActor(kind="platform", ref=e.iniziata_da))
    await audit.record("apartment_deleted", who, apt.tenant_id, audit.apartment_target(apartment_id, apt.name))
    return "eliminato"


async def retry(apt: Apartment, version, identity) -> tuple[int, dict]:
    e = apt.eliminazione
    if e is None:
        raise DeletionRefused(404, "not_found", "Nessuna eliminazione in corso per questo appartamento.")
    if not isinstance(version, int) or isinstance(version, bool):
        raise DeletionRefused(422, "invalid_version", "Versione mancante o non valida.")
    stato, _ = effective(e, await _op_of(e))
    if stato != "non_riuscita":
        raise DeletionRefused(409, "invalid_state", "Con lo stato di adesso questa azione non si può fare.")
    if version != e.version:
        raise DeletionRefused(409, "version_changed", "Qualcuno ha appena cambiato questa eliminazione: ricarica.")
    # review, point 6: no order until the new one is saved, so a second «Riprova» meanwhile reads «in corso»
    saved = await _save(apt.apartment_id, expect_version=version, uid=identity.uid, stato="in_corso", codice=None,
                        op=None)
    if saved is None:
        raise DeletionRefused(409, "version_changed", "Qualcuno ha appena cambiato questa eliminazione: ricarica.")
    await _person(identity)
    if e.passo == "motore":
        if not agent.configured():
            raise DeletionRefused(503, "agent_not_configured", "L'agente sulla VM non è configurato in questo ambiente")
        await _send_togli(saved)
        return 202, {"eliminazione": await eliminazione_view(await get_repository().get_apartment(apt.apartment_id))}
    if await _finish(apt.apartment_id) in ("eliminato", "gia_eliminato"):
        return 200, {"eliminazione": {"stato": "eliminato"}}
    return 202, {"eliminazione": await eliminazione_view(await get_repository().get_apartment(apt.apartment_id))}


# ---- the agent's result ------------------------------------------------------------------------------------------
async def owns(op) -> bool:
    apt = await get_repository().get_apartment(op.apartment_id) if op.apartment_id else None
    return apt is not None and apt.eliminazione is not None and (apt.eliminazione.op or {}).get("op_id") == op.op_id


async def after_result(op, esito: str, codice: str, late: bool = False) -> str:
    """togli_motore of a deletion (bff/creation.after_result sends it here). Safe to run twice."""
    repo = get_repository()
    apt = await repo.get_apartment(op.apartment_id) if op.apartment_id else None
    e = apt.eliminazione if apt else None
    if e is None or (e.op or {}).get("op_id") != op.op_id:
        return "ordine_successivo"
    if e.stato != "in_corso" or e.passo != "motore":
        return "stato_diverso"
    if late:
        if await repo.apartment_seq(op.apartment_id) != op.seq:
            return "ordine_successivo"
    else:
        stored = await repo.get_agent_op(op.op_id)
        if stored is None or stored.stato != esito:
            return "chiuso_diverso"
    if esito != "riuscito":
        await _fail(op.apartment_id, "motore", codice, expect_op=op.op_id)
        return "non_riuscita"
    return await _finish(op.apartment_id)
