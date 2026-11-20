"""Tool A, package A2 (docs/proposta-a2.md; docs/proposta-a2-sito.md): an apartment created from the app.

The flow, driven by the platform manager's calls and by the agent's results (no background task: every step runs
inside a request, the push of a result included):

1. «Nuovo appartamento» (create): checks; ONE transaction reserves the id (never used, D-67), the lowest free port of
   the environment's band, the Italianway code and a place in the organisation's 5 an hour, and saves the apartment
   «in_preparazione» with the label of its secrets (the intention, §3.3); then the two secrets; then «capienza».
2. The capienza result: room on the VM -> «crea_motore» {porta}; otherwise «non_creato».
3. The crea_motore result: the apartment linked to http://10.198.0.2:<porta>, enabled, then «Verifica connessione»
   (instances.verify): ok -> «pronto» and the activity log's apartment_created.
4. «Riprova»: from «non_creato», completes what is missing (a new port first after porta_occupata).
5. «Annulla»: from «non_creato», «annullamento_in_corso» and togli_motore (only if a crea_motore was ever sent);
   after its success the versions of the secrets are destroyed with the delay, the claims released and the apartment
   removed (the id stays used). A success that comes after 20 minutes still closes it, but only if no other order
   was sent for the apartment after that togli_motore (third reading, N8).

The state shown is computed at read time (effective): 20 minutes without progress, or the last order closed without
success, is «non_creato» with its code. Until A10 only the staging creates (503 elsewhere, answer 1162).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from . import agent, audit, capacity, instances
from . import secret_admin
from .logs import warn
from .repository import get_repository
from .repository.base import Apartment, AuditPerson, Creazione, ExternalIds, iso_seconds, now_iso

VM_HOST = "10.198.0.2"                       # the VM's internal address, the one INSTANCE_ALLOWED names (§3.2)
BANDS = {"staging": (8150, 8159), "prod": (8101, 8149)}
LIMIT = 5                                    # answer 1168: 5 creations started an hour per organisation
WINDOW_S = 3600
MAX_WAIT = agent.MAX_WAIT                    # 20 minutes (§6.8 of the project)
OCCUPIED_OWNER = "_occupata_sulla_vm"        # the claim of a port the VM said busy: never chosen again
OPERATIONS = ("capienza", "crea_motore", "togli_motore")
OWN_MESSAGES = {
    "segreti_non_creati": "Le chiavi non sono state create: «Riprova».",
    "secret_conflict": "C'è già un segreto con questo nome: serve un controllo (ID richiesta).",
    "collegamento_fallito": "Il sistema domotico è installato ma l'app non lo raggiunge: «Riprova».",
    "chiavi_non_distrutte": "Il sistema domotico è stato tolto, ma le chiavi no: «Annulla» di nuovo.",
}


class CreationRefused(Exception):
    def __init__(self, status: int, error: str, message: str, **details):
        super().__init__(message)
        self.status, self.error, self.message, self.details = status, error, message, details


def utcnow() -> datetime:
    return agent.utcnow()


def stamp() -> str:
    return utcnow().isoformat(timespec="milliseconds").replace("+00:00", "Z")


def available() -> bool:
    """§2.2 point 24: creation only in the staging with the agent configured (production after A10)."""
    return agent.configured() and agent.get_settings().agent_ambiente == "staging"


def usable(apt: Apartment) -> bool:
    """§2.2 point 25, the single rule: an apartment of the organisation exists for its pages only when «pronto» (or
    linked by hand); in preparation or stopped half-way it is seen only by the platform's routes."""
    return apt.creazione is None or apt.creazione.stato == "pronto"


def message(code: str | None) -> str:
    return OWN_MESSAGES.get(code or "") or agent.MESSAGES.get(code or "", "")


def link_key(port: int) -> str:
    return instances.link_key(f"http://{VM_HOST}", port)


# ---- the state shown ---------------------------------------------------------------------------------------------
def effective(c: Creazione, op) -> tuple[str, str | None]:
    if c.stato in ("in_preparazione", "annullamento_in_corso"):
        if op is not None and op.stato not in ("inviato", "riuscito"):
            return "non_creato", op.codice
        if utcnow().timestamp() - iso_seconds(c.updated_at) > MAX_WAIT.total_seconds():
            return "non_creato", "tempo_scaduto"
    return c.stato, c.codice


async def _op_of(c: Creazione):
    return await get_repository().get_agent_op(c.op["op_id"]) if c.op else None


async def _names(uids) -> dict:
    refs = sorted({u for u in uids if isinstance(u, str)})
    people = await get_repository().get_audit_people(refs) if refs else {}
    return {ref: (p.display_name or None) for ref, p in people.items()}


async def views(apartments) -> dict[str, dict | None]:
    """The `creazione` of each apartment (§2.1), None for one linked by hand."""
    made = [a for a in apartments if a.creazione is not None]
    names = await _names(a.creazione.updated_by for a in made)
    out: dict[str, dict | None] = {a.apartment_id: None for a in apartments}
    for a in made:
        c = a.creazione
        op = await _op_of(c)
        stato, codice = effective(c, op)
        out[a.apartment_id] = {
            "stato": stato, "passo": c.passo, "version": c.version, "porta": c.porta,
            "op": None if op is None else {"op_id": op.op_id, "operazione": op.operazione, "stato": op.stato,
                                           "codice": op.codice, "messaggio": agent.describe(op)["messaggio"]},
            "codice": codice, "messaggio": message(codice) if stato == "non_creato" else None,
            "fatti": list(c.fatti), "updated_at": c.updated_at, "updated_by": names.get(c.updated_by)}
    return out


async def view(apt: Apartment) -> dict | None:
    return (await views([apt]))[apt.apartment_id]


async def counts(tenant_id: str) -> dict:
    """§2.2 point 22: the creations stopped half-way and in progress of one organisation."""
    found = {"non_creato": 0, "in_preparazione": 0}
    for v in (await views(await get_repository().list_apartments(tenant_id))).values():
        if v and v["stato"] in ("non_creato", "in_preparazione", "annullamento_in_corso"):
            found["non_creato" if v["stato"] == "non_creato" else "in_preparazione"] += 1
    return {"appartamenti_non_creati": found["non_creato"], "appartamenti_in_preparazione": found["in_preparazione"]}


def _window(times: list[str], now: float) -> list[str]:
    return sorted(t for t in times if now - iso_seconds(t) < WINDOW_S)


def _free_from(oldest: str) -> str:
    when = datetime.fromtimestamp(iso_seconds(oldest), UTC) + timedelta(seconds=WINDOW_S)
    return when.isoformat(timespec="milliseconds").replace("+00:00", "Z")


async def last_hour(tenant_id: str) -> dict:
    """§2.2 point 20: {usate, limite, libera_dal}; libera_dal only when the limit is reached."""
    times = _window(await get_repository().creation_times(tenant_id), utcnow().timestamp())
    return {"usate": len(times), "limite": LIMIT,
            "libera_dal": _free_from(times[-LIMIT]) if len(times) >= LIMIT else None}


# ---- saving ------------------------------------------------------------------------------------------------------
async def _save(apartment_id: str, uid: str | None = None, expect_op: str | None = None,
                expect_version: int | None = None, expect_stato: str | None = None, **changes) -> Apartment | None:
    """The creation changed in one transaction, version + 1; with expect_op / expect_version / expect_stato only if
    the creation is still at that order / version / state (a newer action wins: None, nothing written). Fields of the
    apartment go in `apartment`."""
    apartment_fields = changes.pop("apartment", {})

    def change(apt: Apartment):
        c = apt.creazione
        if c is None or (expect_op is not None and (c.op or {}).get("op_id") != expect_op) \
                or (expect_version is not None and c.version != expect_version) \
                or (expect_stato is not None and c.stato != expect_stato):
            return None
        for k, v in changes.items():
            setattr(c, k, v)
        for k, v in apartment_fields.items():
            setattr(apt, k, v)
        c.version += 1
        c.updated_at = stamp()
        if uid:
            c.updated_by = uid
        return apt
    return await get_repository().change_apartment(apartment_id, change)


async def _fail(apartment_id: str, code: str | None, expect_op: str | None = None,
                expect_stato: str | None = None) -> None:
    await _save(apartment_id, expect_op=expect_op, expect_stato=expect_stato, stato="non_creato",
                codice=code or "errore_interno")


def _added(c: Creazione, *items: str) -> list[str]:
    return c.fatti + [i for i in items if i not in c.fatti]


# ---- the orders --------------------------------------------------------------------------------------------------
async def _send(apt: Apartment, operazione: str, passo: str, parametri: dict) -> None:
    """The order saved, the creation pointed at it, then published. A failed publish: «non_creato» (non_inviato) and
    the AgentError (502) goes up to the route."""
    c = apt.creazione
    capacity = operazione == "capienza"
    # code review A2, point 1: an order only in the state it belongs to (a «Annulla» in between wins)
    wanted = "annullamento_in_corso" if operazione == "togli_motore" else "in_preparazione"
    op, body = await agent.new_order(operazione, None if capacity else apt.apartment_id, c.updated_by, parametri,
                                     per_appartamento=apt.apartment_id if capacity else None)
    extra = {"crea_inviato": True} if operazione == "crea_motore" else {}
    if await _save(apt.apartment_id, expect_stato=wanted, op={"op_id": op.op_id, "operazione": operazione},
                   passo=passo, codice=None, **extra) is None:
        warn("creation order not sent", apartment_id=apt.apartment_id, operazione=operazione, motivo="stato_cambiato")
        raise CreationRefused(409, "invalid_state", "Con lo stato di adesso questa azione non si può fare.")
    try:
        await agent.publish_op(op, body)
    except agent.AgentError:
        await _fail(apt.apartment_id, "non_inviato", expect_op=op.op_id)
        raise


async def _advance(apartment_id: str) -> None:
    """From what exists: the secrets, then capienza (or, with the engine already there, the link again)."""
    apt = await get_repository().get_apartment(apartment_id)
    c = apt.creazione
    if "segreti" not in c.fatti:
        apt = await _save(apartment_id, expect_stato="in_preparazione", passo="segreti")
        if apt is None:
            return                                     # the state changed meanwhile: nothing more to do here
        try:
            await secret_admin.ensure_pair(secret_admin.get_secret_admin(), agent.get_settings().agent_ambiente,
                                           apartment_id, c.segreti_op)
        except secret_admin.SecretConflict as exc:
            warn("agent alarm codice=secret_conflict", apartment_id=apartment_id, secret=exc.name)
            await _fail(apartment_id, "secret_conflict", expect_stato="in_preparazione")
            raise CreationRefused(409, "secret_conflict", OWN_MESSAGES["secret_conflict"],
                                  apartment_id=apartment_id) from None
        except secret_admin.SecretError as exc:
            warn("creation secrets failed", apartment_id=apartment_id, error=str(exc))
            await _fail(apartment_id, "segreti_non_creati", expect_stato="in_preparazione")
            return
        apt = await _save(apartment_id, expect_stato="in_preparazione", fatti=_added(apt.creazione, "segreti"))
        if apt is None:
            return
    if "motore" in apt.creazione.fatti and "broker" in apt.creazione.fatti:
        await _link(apartment_id)
        return
    await _send(apt, "capienza", "capienza", {})


async def _link(apartment_id: str) -> None:
    """The engine answered: linked, enabled, verified; «pronto» or «non_creato: collegamento_fallito»."""
    apt = await get_repository().get_apartment(apartment_id)
    apt = await _save(apartment_id, expect_stato="in_preparazione", passo="collegamento", apartment={
        "instance_url": f"http://{VM_HOST}", "port": apt.creazione.porta, "enabled": True})
    if apt is None:
        return
    full = await instances.verify(apt, "system")
    if not full.get("ok"):
        warn("creation link failed", apartment_id=apartment_id, error=full.get("error"))
        await _fail(apartment_id, "collegamento_fallito", expect_stato="in_preparazione")
        return
    saved = await _save(apartment_id, expect_stato="in_preparazione", stato="pronto", codice=None)
    if saved is None:
        return
    instances.invalidate_version(apartment_id)
    c = saved.creazione
    who = audit.Who(audit.AuditActor(kind="platform", ref=c.avviata_da))
    await audit.record("apartment_created", who, saved.tenant_id, audit.apartment_target(apartment_id, saved.name))


async def _finish_cancel(apartment_id: str) -> None:
    """After togli_motore (or with nothing on the VM): secrets destroyed with the delay, claims released, apartment
    removed. A refusal of Secret Manager leaves «non_creato: chiavi_non_distrutte» (the engine is gone already)."""
    repo = get_repository()
    apt = await repo.get_apartment(apartment_id)
    try:
        await secret_admin.destroy_pair(secret_admin.get_secret_admin(), apartment_id)
    except secret_admin.SecretError as exc:
        warn("creation secrets not destroyed", apartment_id=apartment_id, error=str(exc))
        await _save(apartment_id, stato="non_creato", codice="chiavi_non_distrutte", crea_inviato=False,
                    fatti=[f for f in apt.creazione.fatti if f not in ("motore", "broker")])
        return
    await repo.release_external_id("link", link_key(apt.creazione.porta), apartment_id)
    if apt.external_ids.italianway:
        await repo.release_external_id("italianway", apt.external_ids.italianway, apartment_id)
    await repo.delete_apartment(apartment_id)
    warn("creation cancelled", apartment_id=apartment_id)


# ---- the calls of the platform manager -----------------------------------------------------------------------------
async def _ports(apartment_id: str, exclude: set[int] = frozenset()) -> list[tuple[int, str]]:
    """The band of this environment, lowest first, without the ports of any apartment (read check, like link_in_use)."""
    low, high = BANDS[agent.get_settings().agent_ambiente]
    used = {instances.link_key(a.instance_url, a.port) for a in await get_repository().list_apartments()
            if a.apartment_id != apartment_id}
    return [(p, link_key(p)) for p in range(low, high + 1) if p not in exclude and link_key(p) not in used]


LOAD_NAMES = ("test-carico-", "carico-")       # A7 review, point 1: the load test's names, never created here


def _check_id(apartment_id: str) -> bool:
    return agent.apartment_allowed(apartment_id, "staging") and apartment_id != "dev" \
        and not apartment_id.startswith(LOAD_NAMES)


async def create(tenant_id: str, apartment_id: str, name: str, timezone: str, code: str | None, identity) -> Apartment:
    """§4.1: raises CreationRefused (or agent.AgentError for a publish that failed); returns the apartment."""
    repo = get_repository()
    if not available():
        raise CreationRefused(503, "agent_not_configured",
                              "La creazione degli appartamenti non è disponibile in questo ambiente")
    if not _check_id(apartment_id):
        raise CreationRefused(422, "invalid_apartment_id",
                              "Id non valido: nello staging lab-… o test-…, lettere minuscole, cifre e trattini.")
    when = stamp()
    apt = Apartment(apartment_id=apartment_id, tenant_id=tenant_id, name=name, timezone=timezone, instance_url="",
                    enabled=False, external_ids=ExternalIds(italianway=code),
                    creazione=Creazione(porta=0, fatti=["id", "porta"], segreti_op=str(uuid.uuid4()),
                                        avviata_da=identity.uid, updated_by=identity.uid, updated_at=when))
    if code and any(a.apartment_id != apartment_id for a in await repo.find_apartments_by_external_id("italianway", code)):
        raise CreationRefused(409, "external_id_in_use", "Codice Italianway già in uso")
    got = await repo.reserve_creation(apt, await _ports(apartment_id), code, when, LIMIT, WINDOW_S)
    if got["esito"] == "exists":
        raise CreationRefused(409, "already_exists", "Identificativo non disponibile")
    if got["esito"] == "external":
        raise CreationRefused(409, "external_id_in_use", "Codice Italianway già in uso")
    if got["esito"] == "no_port":
        raise CreationRefused(409, "no_free_port", "Non c'è più posto per un motore nuovo in questo ambiente.")
    if got["esito"] == "rate":
        free = _free_from(got["times"][-LIMIT])
        raise CreationRefused(429, "rate_limited", "Si possono creare al massimo 5 appartamenti l'ora per "
                              "organizzazione. Il prossimo si può creare più tardi.", limite=LIMIT, riprova_dal=free)
    await repo.put_audit_person(AuditPerson(ref=identity.uid, email=identity.email,
                                            display_name=identity.display_name))
    warn("creation started", apartment_id=apartment_id, porta=got["porta"])
    await _advance(apartment_id)
    return await repo.get_apartment(apartment_id)


async def _checked(apt: Apartment, version) -> Creazione:
    c = apt.creazione
    if c is None:
        raise CreationRefused(404, "not_found", "Appartamento inesistente")
    if not isinstance(version, int) or isinstance(version, bool) or version != c.version:
        raise CreationRefused(409, "version_changed", "Qualcuno ha appena cambiato questa creazione: ricarica.")
    if effective(c, await _op_of(c))[0] != "non_creato":
        raise CreationRefused(409, "invalid_state", "Con lo stato di adesso questa azione non si può fare.")
    return c


async def retry(apt: Apartment, version, identity) -> Apartment:
    repo = get_repository()
    c = await _checked(apt, version)
    stato, codice = effective(c, await _op_of(c))
    changes = {}
    if codice == "porta_occupata":                     # §3.2 point 4: that port stays marked, the next one is taken
        free = await _ports(apt.apartment_id, exclude={c.porta})
        new = None
        for port, key in free:
            if await repo.claim_external_id("link", key, apt.apartment_id) is None:
                new = port
                break
        if new is None:
            raise CreationRefused(409, "no_free_port", "Non c'è più posto per un motore nuovo in questo ambiente.")
        await repo.release_external_id("link", link_key(c.porta), apt.apartment_id)
        await repo.claim_external_id("link", link_key(c.porta), OCCUPIED_OWNER)
        changes["porta"] = new
    # code review A2, point 1: «in_preparazione» and no order together, so that until the new order is saved the
    # state read is «in preparazione» (not the old order's failure, which would allow «Annulla» at once)
    saved = await _save(apt.apartment_id, uid=identity.uid, expect_version=c.version, stato="in_preparazione",
                        codice=None, op=None, **changes)
    if saved is None:
        raise CreationRefused(409, "version_changed", "Qualcuno ha appena cambiato questa creazione: ricarica.")
    await repo.put_audit_person(AuditPerson(ref=identity.uid, email=identity.email,
                                            display_name=identity.display_name))
    await audit.record("apartment_creation_retried", audit.by_platform(identity), apt.tenant_id,
                       audit.apartment_target(apt.apartment_id, apt.name), passo=c.passo, codice=codice)
    await _advance(apt.apartment_id)
    return await repo.get_apartment(apt.apartment_id)


async def cancel(apt: Apartment, version, identity) -> Apartment | None:
    """None when it is already gone (nothing was on the VM)."""
    repo = get_repository()
    c = await _checked(apt, version)
    saved = await _save(apt.apartment_id, uid=identity.uid, expect_version=c.version, stato="annullamento_in_corso",
                        codice=None)
    if saved is None:
        raise CreationRefused(409, "version_changed", "Qualcuno ha appena cambiato questa creazione: ricarica.")
    await repo.put_audit_person(AuditPerson(ref=identity.uid, email=identity.email,
                                            display_name=identity.display_name))
    await audit.record("apartment_creation_cancelled", audit.by_platform(identity), apt.tenant_id,
                       audit.apartment_target(apt.apartment_id, apt.name), passo=c.passo)
    if not c.crea_inviato:                             # nothing was ever sent to install: nothing to remove there
        await _finish_cancel(apt.apartment_id)
        return await repo.get_apartment(apt.apartment_id)
    await _send(saved, "togli_motore", saved.creazione.passo, {})
    return await repo.get_apartment(apt.apartment_id)


# ---- the agent's results -----------------------------------------------------------------------------------------
async def after_result(op, esito: str, codice: str, dati: dict, late: bool = False) -> str:
    """Called by the receiver for capienza (of a creation), crea_motore and togli_motore, after the operation was
    closed (or found closed: Pub/Sub delivers again after a 503). What it did, for the log line."""
    repo = get_repository()
    if op.operazione == "togli_motore":
        from . import deletion
        if await deletion.owns(op):                    # A6: the togli_motore of a deletion, not of a cancellation
            return await deletion.after_result(op, esito, codice, late)
    apartment_id = op.apartment_id or op.per_appartamento
    apt = await repo.get_apartment(apartment_id) if apartment_id else None
    c = apt.creazione if apt else None
    if c is None or (c.op or {}).get("op_id") != op.op_id:
        return "ordine_successivo"                     # another order since: this result changes nothing
    # code review A2, point 1: capienza and crea_motore count only «in preparazione», togli_motore only «annullamento»
    if c.stato != ("annullamento_in_corso" if op.operazione == "togli_motore" else "in_preparazione"):
        return "stato_diverso"
    if not late:
        stored = await repo.get_agent_op(op.op_id)
        if stored is None or stored.stato != esito:
            return "chiuso_diverso"                    # expired at 20 minutes meanwhile: the result is ignored
    if esito != "riuscito":
        await _fail(apartment_id, codice, expect_op=op.op_id)
        return "non_creato"
    if op.operazione == "capienza":
        problem = capacity.room_problem(dati, op.ambiente)           # A7: the VM's rule, the real caps (1196)
        if problem is not None:
            await _fail(apartment_id, problem, expect_op=op.op_id)
        else:
            try:
                await _send(apt, "crea_motore", "motore", {"porta": c.porta})
            except agent.AgentError:
                pass                                   # saved «non_creato: non_inviato»
            except CreationRefused:
                return "stato_diverso"
            return "crea_motore"
        return "non_creato"
    if op.operazione == "crea_motore":
        await _save(apartment_id, expect_op=op.op_id, fatti=_added(c, "motore", "broker"))
        await _link(apartment_id)
        return "collegato"
    # togli_motore
    if late and await repo.apartment_seq(apartment_id) != op.seq:
        warn("agent result ignored", op_id=op.op_id, motivo="ordine_successivo")
        return "ordine_successivo"
    await _finish_cancel(apartment_id)
    return "annullato"
