"""Rules proposed by the assistant and confirmed by the manager (P-60 step 12, D-151): see bff/rule_proposals.py."""
import asyncio
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from .. import actors, ai_gateway, audit, instances
from .. import rule_proposals as rp
from ..auth import CurrentUser, get_tenant_apartment, resolve_user
from ..config import get_settings
from ..logs import ctx_apartment, info, warn
from ..repository import get_repository

router = APIRouter(prefix="/app")


def err(status: int, error: str, message: str, **details) -> JSONResponse:
    body = {"error": error, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(body, status_code=status)


async def _writer_apartment(user: CurrentUser, apartment_id: str):
    """The apartment, for an operator or an admin; a JSONResponse to answer otherwise."""
    apt = await get_tenant_apartment(user, apartment_id)
    ctx_apartment.set(apt.apartment_id)
    if not user.can_write:
        return None, err(403, "forbidden", "Il tuo ruolo consente solo la lettura")
    if not apt.enabled:
        return None, err(409, "apartment_disabled", "Appartamento disattivato")
    return apt, None


async def _rules(apt) -> dict:
    resp = await instances.call(apt, "GET", "/rules")
    resp.raise_for_status()
    return resp.json()


async def _put_rules(apt, user, patches: list, correlation_id: str):
    return await instances.call(apt, "PUT", "/rules", actor=await actors.actor_for(user.uid, user.email),
                                correlation_id=correlation_id, json={"rules": patches})


async def _ask_model(apt, ruleset: dict, text: str) -> tuple[list | None, str]:
    s = get_settings()
    if apt.simulated and not s.ai_demos:          # D-151 point 21: the recognizer on the demonstrations
        return rp.recognize(text, ruleset)
    if rp.simple(text):                           # lot 29: one rule, one value: no model call
        patches, said = rp.recognize(text, ruleset)
        if patches is not None:
            return patches, said
    try:
        answer = await asyncio.wait_for(ai_gateway.chat(apt.apartment_id, {
            "messages": [{"role": "system", "content": rp.prompt(ruleset)}, {"role": "user", "content": text}],
            "tools": [rp.TOOL], "tool_choice": "auto", "temperature": 0.1}), timeout=rp.PROPOSAL_TIMEOUT_S)
    except TimeoutError:                          # lot 29: a clear answer within the site's patience
        warn("rule proposal: model call cut", apartment_id=apt.apartment_id, seconds=rp.PROPOSAL_TIMEOUT_S)
        raise ai_gateway.GatewayError(504, "timeout", rp.TIMEOUT_MESSAGE) from None
    return rp.from_answer(answer)


@router.post("/apartments/{apartment_id}/rules/proposal")
async def propose(apartment_id: str, request: Request, user: CurrentUser = Depends(resolve_user)):
    """What the manager wrote -> the proposed changes, with old and new value; nothing changes here."""
    apt, refused = await _writer_apartment(user, apartment_id)
    if refused:
        return refused
    try:
        body = await request.json()
    except ValueError:
        body = None
    text = (body or {}).get("text") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        return err(422, "bad_request", "Scrivi che cosa vuoi cambiare")
    if len(text) > rp.TEXT_MAX:
        return err(422, "text_too_long", f"Al massimo {rp.TEXT_MAX} caratteri")
    try:
        ruleset = await _rules(apt)
    except Exception as exc:
        info("instance unreachable", error=type(exc).__name__, path="rules")
        return err(502, "instance_unreachable", "Istanza non raggiungibile")
    key = f"rule_proposal:{apt.apartment_id}:{rp.local_day(apt.timezone)}"
    if not await get_repository().take_mail_quota([(key, rp.DAILY_LIMIT)]):
        return err(429, "daily_limit", f"Hai già chiesto {rp.DAILY_LIMIT} proposte oggi per questo appartamento: "
                                        "riprova domani o cambia le regole a mano")
    try:
        patches, said = await _ask_model(apt, ruleset, text.strip())
    except ai_gateway.GatewayError as exc:
        return err(exc.status, exc.error, exc.message)
    out = {"based_on": ruleset["updated_at"], "rules": [], "changes": [], "explanation": said}
    if patches is None:
        return out
    try:
        out["rules"], out["changes"] = rp.changes(ruleset, patches)
    except rp.ProposalError as exc:                 # the model went out of the limits: said, not proposed
        out["explanation"] = exc.message
        return out
    if not out["changes"]:
        out["explanation"] = "Le regole sono già così: non c'è niente da cambiare."
    return out


@router.post("/apartments/{apartment_id}/rules/proposal/apply")
async def apply(apartment_id: str, request: Request, user: CurrentUser = Depends(resolve_user)):
    """The manager's «Applica»: checked again, 409 when the rules changed since the proposal, then PUT /rules."""
    apt, refused = await _writer_apartment(user, apartment_id)
    if refused:
        return refused
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or not isinstance(body.get("based_on"), str) or not isinstance(body.get("rules"), list):
        return err(422, "bad_request", "based_on e rules obbligatori")
    try:
        ruleset = await _rules(apt)
    except Exception as exc:
        info("instance unreachable", error=type(exc).__name__, path="rules")
        return err(502, "instance_unreachable", "Istanza non raggiungibile")
    if ruleset["updated_at"] != body["based_on"]:
        return err(409, "rules_changed", "Le regole sono cambiate nel frattempo: rifai la richiesta")
    try:
        patches, changed = rp.changes(ruleset, body["rules"])
    except rp.ProposalError as exc:
        return err(exc.status, exc.error, exc.message)
    if not patches:
        return err(422, "nothing_to_change", "Le regole sono già così: non c'è niente da cambiare")
    resp = await _put_rules(apt, user, patches, str(uuid.uuid4()))
    if resp.status_code != 200:
        return JSONResponse(resp.json(), status_code=resp.status_code)
    await audit.record("rules_changed", audit.by_user(user), user.tenant_id,
                       audit.apartment_target(apt.apartment_id, apt.name), source="assistant", changes=changed)
    return resp.json()


# ---- copy the rules to other apartments (P-60 step 12d, D-151 point 22) -------------------------------------------
COPY_MAX = 100              # destination apartments in one request
COPY_PARALLEL = 5


def _copy_patches(source: dict) -> list[dict]:
    """Every editable rule of the source apartment: on/off and parameters."""
    return [{"rule_id": r["rule_id"], "enabled": r["enabled"], "params": dict(r["params"])}
            for r in source.get("rules") or [] if r["editable"]]


def _for_target(patches: list[dict], target: dict) -> list[dict]:
    """The source's patches restricted to the rules and parameters the destination has (an older engine may lack a
    parameter added later, e.g. presence_minutes)."""
    by_id = {r["rule_id"]: r for r in target.get("rules") or []}
    out = []
    for p in patches:
        rule = by_id.get(p["rule_id"])
        if rule and rule["editable"]:
            out.append({"rule_id": p["rule_id"], "enabled": p["enabled"],
                        "params": {k: v for k, v in p["params"].items() if k in rule["limits"]}})
    return out


async def _copy_request(user: CurrentUser, apartment_id: str, request: Request):
    """(source apartment, destination apartments, body, None) or (None, None, None, the JSONResponse to answer)."""
    apt = await get_tenant_apartment(user, apartment_id)
    ctx_apartment.set(apt.apartment_id)
    if not user.is_admin:
        return None, None, None, err(403, "forbidden", "Solo gli amministratori possono copiare le regole")
    try:
        body = await request.json()
    except ValueError:
        body = None
    to = body.get("to") if isinstance(body, dict) else None
    if not isinstance(to, list) or not to or not all(isinstance(x, str) for x in to):
        return None, None, None, err(422, "bad_request", "Scegli almeno un appartamento di destinazione")
    if len(set(to)) > COPY_MAX:
        return None, None, None, err(422, "too_many", f"Al massimo {COPY_MAX} appartamenti alla volta")
    if apt.apartment_id in to:
        return None, None, None, err(422, "same_apartment",
                                     "L'appartamento di partenza non può essere anche destinazione")
    targets = [await get_tenant_apartment(user, x) for x in dict.fromkeys(to)]   # 404 on one outside the user's list
    return apt, targets, body, None


async def _read_all(targets: list) -> dict:
    """apartment_id -> its RuleSet, None when disabled, the exception when unreachable."""
    gate = asyncio.Semaphore(COPY_PARALLEL)

    async def one(t):
        if not t.enabled:
            return t.apartment_id, None
        async with gate:
            try:
                return t.apartment_id, await _rules(t)
            except Exception as exc:
                return t.apartment_id, exc
    return dict(await asyncio.gather(*(one(t) for t in targets)))


async def _source(apt):
    """The source's RuleSet, or the JSONResponse to answer."""
    if not apt.enabled:
        return None, err(409, "apartment_disabled", "Appartamento disattivato")
    try:
        return await _rules(apt), None
    except Exception as exc:
        info("instance unreachable", error=type(exc).__name__, path="rules")
        return None, err(502, "instance_unreachable", "Istanza non raggiungibile")


@router.post("/apartments/{apartment_id}/rules/copy/preview")
async def copy_preview(apartment_id: str, request: Request, user: CurrentUser = Depends(resolve_user)):
    """D-151 point 22 (b, d): which apartments the copy touches and how, before the confirmation."""
    apt, targets, _body, refused = await _copy_request(user, apartment_id, request)
    if refused:
        return refused
    source, refused = await _source(apt)
    if refused:
        return refused
    patches = _copy_patches(source)
    read = await _read_all(targets)
    out = []
    for t in targets:
        row = {"apartment_id": t.apartment_id, "name": t.name, "based_on": None, "changes": [], "customized": []}
        got = read[t.apartment_id]
        if got is None:
            row.update(status="disabled", message="Appartamento disattivato")
        elif isinstance(got, Exception):
            row.update(status="unreachable", message="Istanza non raggiungibile")
        else:
            row["based_on"] = got["updated_at"]
            try:
                _clean, row["changes"] = rp.changes(got, _for_target(patches, got))
            except rp.ProposalError as exc:
                row.update(status="refused", message=exc.message)
            else:
                row["status"] = "changes" if row["changes"] else "same"
                if row["changes"]:
                    row["customized"] = rp.customized(got)
        out.append(row)
    return {"from": {"apartment_id": apt.apartment_id, "name": apt.name, "based_on": source["updated_at"]},
            "rules": patches, "targets": out}


@router.post("/apartments/{apartment_id}/rules/copy")
async def copy_rules(apartment_id: str, request: Request, user: CurrentUser = Depends(resolve_user)):
    """D-151 point 22 (c): one PUT /rules per destination, under the admin's pseudonym and its own correlation id (one
    decision in each engine), one «rules_changed» in the activity log for each; the outcome per apartment."""
    apt, targets, body, refused = await _copy_request(user, apartment_id, request)
    if refused:
        return refused
    based_on = body.get("based_on")
    if not isinstance(based_on, dict) or not isinstance(body.get("from_based_on"), str):
        return err(422, "bad_request", "based_on e from_based_on obbligatori, dall'anteprima")
    source, refused = await _source(apt)
    if refused:
        return refused
    if source["updated_at"] != body["from_based_on"]:
        return err(409, "rules_changed", "Le regole dell'appartamento di partenza sono cambiate: rifai l'anteprima")
    patches = _copy_patches(source)
    read = await _read_all(targets)
    actor = await actors.actor_for(user.uid, user.email)
    gate = asyncio.Semaphore(COPY_PARALLEL)

    async def one(t) -> dict:
        row = {"apartment_id": t.apartment_id, "name": t.name, "changes": []}
        got = read[t.apartment_id]
        if got is None:
            return {**row, "outcome": "disabled", "message": "Appartamento disattivato"}
        if isinstance(got, Exception):
            return {**row, "outcome": "unreachable", "message": "Istanza non raggiungibile"}
        if got["updated_at"] != based_on.get(t.apartment_id):
            return {**row, "outcome": "changed_meanwhile", "message": "Regole cambiate dopo l'anteprima: non toccato"}
        try:
            clean, changed = rp.changes(got, _for_target(patches, got))
        except rp.ProposalError as exc:
            return {**row, "outcome": "refused", "message": exc.message}
        if not clean:
            return {**row, "outcome": "same", "message": "Già uguale, nessuna modifica"}
        async with gate:
            try:
                resp = await instances.call(t, "PUT", "/rules", actor=actor, correlation_id=str(uuid.uuid4()),
                                            json={"rules": clean})
            except Exception as exc:
                info("instance unreachable", error=type(exc).__name__, path="rules")
                return {**row, "outcome": "unreachable", "message": "Istanza non raggiungibile"}
        if resp.status_code != 200:
            try:
                message = resp.json().get("message") or "Rifiutato dall'istanza"
            except ValueError:
                message = "Rifiutato dall'istanza"
            return {**row, "outcome": "refused", "message": message}
        await audit.record("rules_changed", audit.by_user(user), user.tenant_id,
                           audit.apartment_target(t.apartment_id, t.name), source="copy",
                           from_apartment={"id": apt.apartment_id, "name": apt.name}, changes=changed)
        return {**row, "outcome": "applied", "message": "Regole copiate", "changes": changed}
    results = await asyncio.gather(*(one(t) for t in targets))
    info("rules copied", targets=len(targets), applied=sum(r["outcome"] == "applied" for r in results))
    return {"from": {"apartment_id": apt.apartment_id, "name": apt.name}, "results": list(results)}
