"""Rules proposed by the assistant and confirmed by the manager (P-60 step 12, D-151): see bff/rule_proposals.py."""
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
    answer = await ai_gateway.chat(apt.apartment_id, {
        "messages": [{"role": "system", "content": rp.prompt(ruleset)}, {"role": "user", "content": text}],
        "tools": [rp.TOOL], "tool_choice": "auto", "temperature": 0.1})
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
