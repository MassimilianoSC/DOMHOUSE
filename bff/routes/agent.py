"""Tool A, package A1: the routes of the order receiver (bff/agent.py).

- POST /internal/agent/risultati: Pub/Sub's push of the results. Not a route of the PWA and not of the engines: only
  Google's signature for this environment's push account opens it (401 otherwise). Every result it can read is
  acknowledged (204), applied or ignored, so that Pub/Sub never retries it.
- POST /app/platform/agent/prova and GET /app/platform/agent/ops/{op_id}: the button «Prova l'agente» of the platform
  page, for the platform managers only (require_platform): an order «stato» for one apartment, then its outcome.
"""
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse, Response

from .. import agent
from ..auth import Identity, require_platform
from ..logs import warn

internal = APIRouter(prefix="/internal/agent")
platform = APIRouter(prefix="/app/platform/agent", dependencies=[Depends(require_platform)])


def err(status: int, error: str, message: str, **details) -> JSONResponse:
    body = {"error": error, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content=body)


@internal.post("/risultati")
async def results(request: Request):
    if not await agent.authorised(request.headers.get("authorization")):
        return Response(status_code=401)
    try:
        body = await request.json()
    except Exception:                                            # noqa: BLE001 - R2: any body is acknowledged
        body = None
    try:
        outcome = await agent.receive(body)
    except Exception as exc:                                     # noqa: BLE001 - N2: the repository failed
        warn("agent result not saved", error=type(exc).__name__)
        return Response(status_code=503)                         # Pub/Sub delivers it again
    if outcome != "chiuso":
        warn("agent result ignored", reason=outcome)
    return Response(status_code=204)


@platform.post("/prova", status_code=202)
async def test_the_agent(payload: dict = Body(...), identity: Identity = Depends(require_platform)):
    apartment_id = payload.get("apartment_id") if isinstance(payload, dict) else None
    try:
        op = await agent.send("stato", apartment_id, identity.uid)
    except agent.AgentError as exc:
        details = {"op": agent.describe(exc.op)} if exc.op else {}
        return err(exc.status, exc.error, exc.message, **details)
    return JSONResponse(status_code=202, content=agent.describe(op))


@platform.get("/ops/{op_id}")
async def operation(op_id: str):
    seen = await agent.view(op_id)
    if seen is None:
        return err(404, "not_found", "Operazione inesistente")
    return seen
