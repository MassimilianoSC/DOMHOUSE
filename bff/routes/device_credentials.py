"""Tool A, package A3 (docs/proposta-a3-server.md §2, §5, §8): the routes of the devices' credentials.

- /app/apartments/{apt}/device-credentials: the organisation's administrators (require_admin). A platform manager
  inside through a support access is an operator, so not here: the password of a device is seen by who answers for it.
- /app/platform/apartments/{apt}/device-credentials: the same calls for the platform managers, only in staging (and
  in dev) and only for lab- and test- apartments (answer 1170); 404 otherwise.

GET the list; POST «Registra» (201, the password once); POST …/{device}/rigenera (200, a new password);
POST …/{device}/revoca and …/riprova (202). Every change goes to the VM as ONE order aggiorna_broker with the
complete list of fingerprints, signed (bff/agent.py), taken in the same transaction as the change.
"""
import re
from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse

from .. import agent, audit, device_alarms, device_refusals
from .. import device_credentials as dc
from ..auth import CurrentUser, Identity, get_tenant_apartment, require_admin, require_platform
from ..logs import warn
from ..repository import AgentOp, get_repository

tenant = APIRouter(prefix="/app/apartments/{apartment_id}/device-credentials")
platform = APIRouter(prefix="/app/platform/apartments/{apartment_id}/device-credentials",
                     dependencies=[Depends(require_platform)])

HOURLY_LIMIT = 30                        # §8.3: actions an hour per organisation, a counter of its own (review 15)
PLATFORM_ENVS = ("dev", "staging")
LAB_RE = re.compile(r"^(lab|test)-")
NOT_SENT = "Ordine non inviato al sistema domotico: copia comunque la password, poi usa «Riprova»"
NO_STORE = {"Cache-Control": "no-store"}
WITH_PASSWORD = {"Cache-Control": "no-store", "Pragma": "no-cache"}
AUDIT = {"registra": "device_credential_registered", "rigenera": "device_credential_regenerated",
         "revoca": "device_credential_revoked", "riprova": "device_credential_retried"}


def err(status: int, error: str, message: str, **details) -> JSONResponse:
    body = {"error": error, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content=body, headers=NO_STORE)


def _now_iso() -> str:
    return agent.utcnow().isoformat(timespec="milliseconds").replace("+00:00", "Z")


# ---- what the site sees ---------------------------------------------------------------------------------------------
def _op_view(op: AgentOp | None) -> dict | None:
    if op is None:
        return None
    stato, codice = op.stato, op.codice
    if agent._too_old(op):
        stato, codice = "fallito", "tempo_scaduto"
    return {"op_id": op.op_id, "stato": stato, "codice": codice,
            "messaggio": agent.MESSAGES.get(codice or "") or agent.STATE_MESSAGES.get(stato, "")}


def describe(apartment_id: str, doc: dict, op: AgentOp | None, ultima: int, names: dict, now: datetime,
             refusals: dict | None = None) -> dict:
    """§2.1: never the fingerprint, never an uid or an email. A5: «rifiuti», null when not known."""
    state = dc.state_of(doc, op, ultima, now)
    device = doc["device_id"]
    return {"device_id": device, "name": None, "stato": state, "version": doc.get("version"),
            "updated_at": doc.get("updated_at"), "updated_by": names.get(doc.get("updated_by")),
            "azione": dc.shown_action(doc, state), "engine_device_id": None, "op": _op_view(op),
            "connection": {"server": agent.get_settings().device_broker_address or None, "ssl_ca": "ca.pem",
                           "client_id": f"{apartment_id}.{device}", "user": f"{apartment_id}.{device}",
                           "topic_prefix": f"{apartment_id}/{device}"},
            "rifiuti": device_refusals.view_of(refusals, device)}


async def _names(uids) -> dict:
    """The visible names from the activity log's people (P-48: a person removed is no name, never an email)."""
    refs = sorted({u for u in uids if isinstance(u, str)})
    people = await get_repository().get_audit_people(refs) if refs else {}
    return {ref: (p.display_name or None) for ref, p in people.items()}


async def _listing(apartment_id: str) -> dict:
    docs, ultima, ops = await get_repository().device_credentials_view(apartment_id)
    names, now = await _names(d.get("updated_by") for d in docs), datetime.now(UTC)
    refusals = await device_refusals.for_apartment(apartment_id)
    return {"items": [describe(apartment_id, d, ops.get(d.get("op_id")), ultima, names, now, refusals) for d in docs]}


# ---- one action -----------------------------------------------------------------------------------------------------
async def _act(action: str, apt, device_id, version, uid: str, who) -> JSONResponse:
    s = agent.get_settings()
    try:
        dc.check_device_id(device_id)
        if action != "registra":
            dc.check_version(version)
    except dc.DeviceError as exc:
        return err(exc.status, exc.error, exc.message)
    if apt.apartment_id == "dev" or not agent.apartment_allowed(apt.apartment_id, s.agent_ambiente or "staging"):
        return err(422, "invalid_apartment", "Nome dell'appartamento non valido per questo ambiente")
    hour = datetime.now(UTC).strftime("%Y%m%d%H")
    if not await get_repository().take_mail_quota([(f"device_credentials:{apt.tenant_id}:{hour}", HOURLY_LIMIT)]):
        return err(429, "rate_limited", "Troppe operazioni in poco tempo: riprova fra qualche minuto.")
    if not agent.configured():
        return err(503, "agent_not_configured", "L'agente sulla VM non è configurato in questo ambiente")
    password = None
    if action in ("registra", "rigenera"):
        if not s.device_broker_address:          # §5.1: before the password exists
            return err(503, "broker_address_missing",
                       "Indirizzo del sistema domotico per i dispositivi non configurato in questo ambiente.")
        password = dc.new_password()
    impronta = dc.hash_password(password) if password else None
    built = {}

    def build(op: AgentOp, docs: list[dict]):
        built["body"], sha = agent.signed_order(op, {"dispositivi": dc.broker_list(docs)})
        return built["body"], sha
    template = AgentOp(op_id=agent.new_op_id(), operazione="aggiorna_broker", apartment_id=apt.apartment_id,
                       ambiente=s.agent_ambiente, richiesto_da=uid, creato_at=_now_iso())
    try:
        doc, op, body = await get_repository().device_credential_change(
            apt.apartment_id, device_id, dc.decide(action, device_id, version, impronta, uid), template, build)
    except dc.DeviceError as exc:
        return err(exc.status, exc.error, exc.message)
    # code review, point 7: from here the change is saved; nothing after it may lose the password or the order
    try:
        await audit.record(AUDIT[action], who, apt.tenant_id, audit.apartment_target(apt.apartment_id, apt.name),
                           device_id=device_id)
    except Exception as exc:                                     # noqa: BLE001 - the activity log failed, not the change
        warn("device credential not in the activity log", apartment_id=apt.apartment_id, error=type(exc).__name__)
    failed = None
    try:
        await agent.publish_op(op, body)
    except agent.AgentError as exc:
        failed = exc
        op = exc.op or op
    try:
        names = await _names([uid])
    except Exception:                                            # noqa: BLE001 - a name is not worth the password
        names = {}
    credential = describe(apt.apartment_id, doc, op, 0, names, datetime.now(UTC),
                          device_refusals.cached(apt.apartment_id))    # A5: the copy, never a read here
    if failed is not None and password is None:
        if action == "revoca":                   # N2: a revocation not applied, also from here
            try:
                await revoke_not_applied(apt, device_id, op)
            except Exception as exc:                             # noqa: BLE001 - the hourly round writes it later
                warn("agent alarm codice=revoca_non_applicata", apartment_id=apt.apartment_id, op_id=op.op_id,
                     error=type(exc).__name__)
        return err(502, failed.error, failed.message, op=agent.describe(op))
    if failed is not None:
        credential["op"]["messaggio"] = NOT_SENT           # §5.3: the password is not lost, only the order
    content = {"credential": credential}
    if password is not None:
        content["password"] = password
    status = {"registra": 201, "rigenera": 200}.get(action, 202)
    return JSONResponse(status_code=status, content=content, headers=WITH_PASSWORD if password else NO_STORE)


async def revoke_not_applied(apt, device_id: str, op: AgentOp) -> None:
    """§8.4 (answer 1175, N2): the system's row and the alarm, once per order (bff/device_alarms.py)."""
    await device_alarms.not_applied(apt, device_id, "revoca", op.seq, op.op_id)


def _payload(payload) -> dict:
    return payload if isinstance(payload, dict) else {}


# ---- the organisation's administrators ----------------------------------------------------------------------------
@tenant.get("")
async def list_for_admin(apartment_id: str, user: CurrentUser = Depends(require_admin)):
    apt = await get_tenant_apartment(user, apartment_id)
    return JSONResponse(content=await _listing(apt.apartment_id), headers=NO_STORE)


@tenant.post("")
async def register_for_admin(apartment_id: str, payload=Body(None), user: CurrentUser = Depends(require_admin)):
    apt = await get_tenant_apartment(user, apartment_id)
    return await _act("registra", apt, _payload(payload).get("device_id"), None, user.uid, audit.by_user(user))


@tenant.post("/{device_id}/{action}")
async def act_for_admin(apartment_id: str, device_id: str, action: str, payload=Body(None),
                        user: CurrentUser = Depends(require_admin)):
    apt = await get_tenant_apartment(user, apartment_id)
    if action not in ("rigenera", "revoca", "riprova"):
        return err(404, "not_found", "Azione inesistente")
    return await _act(action, apt, device_id, _payload(payload).get("version"), user.uid, audit.by_user(user))


# ---- the platform managers (staging, lab- and test-) -----------------------------------------------------------------
async def _platform_apartment(apartment_id: str):
    if agent.get_settings().app_env not in PLATFORM_ENVS or not LAB_RE.match(apartment_id or ""):
        return None
    return await get_repository().get_apartment(apartment_id)


@platform.get("")
async def list_for_platform(apartment_id: str):
    apt = await _platform_apartment(apartment_id)
    if apt is None:
        return err(404, "not_found", "Appartamento inesistente")
    return JSONResponse(content=await _listing(apt.apartment_id), headers=NO_STORE)


@platform.post("")
async def register_for_platform(apartment_id: str, request: Request, payload=Body(None),
                                identity: Identity = Depends(require_platform)):
    apt = await _platform_apartment(apartment_id)
    if apt is None:
        return err(404, "not_found", "Appartamento inesistente")
    return await _act("registra", apt, _payload(payload).get("device_id"), None, identity.uid,
                      audit.by_platform(identity))


@platform.post("/{device_id}/{action}")
async def act_for_platform(apartment_id: str, device_id: str, action: str, payload=Body(None),
                           identity: Identity = Depends(require_platform)):
    apt = await _platform_apartment(apartment_id)
    if apt is None or action not in ("rigenera", "revoca", "riprova"):
        return err(404, "not_found", "Appartamento inesistente" if apt is None else "Azione inesistente")
    return await _act(action, apt, device_id, _payload(payload).get("version"), identity.uid,
                      audit.by_platform(identity))
