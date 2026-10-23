"""The contract's HTTP API (1.0.5) over the apartment engine (engine/core.py), in two shapes:
- one apartment, at /api/v1: the engine as a service of its own (python -m engine, P-60 step 2);
- many apartments, at /{apartment_id}/api/v1: the BFF's demonstration apartments (mounted at /mock) and
  python -m bff.mock_instance."""
import asyncio
import json
import re
from collections.abc import Callable

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette._utils import get_route_path

from .core import CONTRACT_VERSION, ApartmentEngine, MockError, parse_dt
from .features import feature_for

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SYSTEM_RE = re.compile(r"^system:[A-Za-z0-9_.-]+$")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
NO_AUTH = {"health", "version"}


def error(status: int, code: str, message: str, details=None) -> JSONResponse:
    body = {"error": code, "message": message}
    if details:
        body["details"] = details
    return JSONResponse(status_code=status, content=body)


def create_contract_app(engine_of: Callable[[str], ApartmentEngine], api_key: str, *, features: list[str],
                        simulated: bool, implementation: dict, ping_seconds: float, apartment_id: str | None = None,
                        title: str = "DOMHOUSE engine (contract 1.0.5)", lifespan=None) -> FastAPI:
    """engine_of(apartment_id) gives the apartment's engine, started. With apartment_id the app serves that apartment
    only, at /api/v1; without, any apartment at /{apartment_id}/api/v1."""
    enabled = list(features)
    ping = ping_seconds
    app = FastAPI(title=title, lifespan=lifespan)
    single = apartment_id
    router = APIRouter(prefix="/api/v1" if single else "/{apartment_id}/api/v1")
    contract_path = re.compile(r"^/api/v1(/.*)?$" if single else r"^/[^/]+/api/v1(/.*)?$")

    def apartment_of(request: Request) -> str:
        return single or request.path_params["apartment_id"]

    @app.middleware("http")
    async def contract_guard(request: Request, call_next):
        # N1 (D-71): when mounted (e.g. under /mock) Starlette keeps the full path in the request; match the part
        # relative to the mount (and to any root path), or "mock" is read as the apartment and nothing is checked
        m = contract_path.match(get_route_path(request.scope))
        if not m:
            return await call_next(request)
        path = (m.group(1) or "/").rstrip("/") or "/"
        top = path.strip("/").split("/")[0]
        if top in NO_AUTH:
            return await call_next(request)
        if request.headers.get("X-API-Key") != api_key:
            return error(401, "unauthorized", "Chiave API mancante o non valida")
        actor = request.headers.get("X-Actor", "")
        corr = request.headers.get("X-Correlation-Id", "")
        if not (EMAIL_RE.match(actor) or SYSTEM_RE.match(actor)) or not UUID_RE.match(corr):
            return error(400, "bad_request", "Header X-Actor o X-Correlation-Id mancante o non valido")
        if top == "_test" and not simulated:
            return error(404, "not_found", "Endpoint disponibile solo in modalità simulata")
        feature = feature_for(request.method, path)
        if feature and feature not in enabled:
            return error(501, "not_implemented", "Funzione non disponibile per questo appartamento")
        return await call_next(request)

    async def body_of(request: Request):
        raw = await request.body()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            raise MockError(400, "bad_request", "JSON non valido")

    def ctx(request: Request):
        return request.headers["X-Actor"], request.headers["X-Correlation-Id"]

    async def run(fn, status: int = 200):
        try:
            result = fn()
            if status == 204:
                return Response(status_code=204)
            return JSONResponse(status_code=status, content=result)
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())

    async def run_idempotent(request: Request, sim, fn, status: int):
        actor, corr = ctx(request)
        key = f"{request.method} {request.url.path} {corr}"
        hit = sim.idempotent(key)
        if hit:
            return JSONResponse(status_code=hit[0], content=hit[1])
        try:
            result = fn()
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        sim.remember(key, status, result)
        return JSONResponse(status_code=status, content=result)

    @router.get("/version")
    async def version(apartment_id: str = Depends(apartment_of)):
        return {"contract_version": CONTRACT_VERSION, "implementation": dict(implementation), "features": list(enabled)}

    @router.get("/health")
    async def health(apartment_id: str = Depends(apartment_of)):
        code, body = engine_of(apartment_id).health()
        return JSONResponse(status_code=code, content=body)

    @router.get("/apartment")
    async def get_apartment(apartment_id: str = Depends(apartment_of)):
        return engine_of(apartment_id).apartment()

    @router.post("/apartment/mode")
    async def set_mode(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        actor, corr = ctx(request)
        try:
            body = await body_of(request)
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        mode = (body or {}).get("mode") if isinstance(body, dict) else None
        return await run_idempotent(request, sim, lambda: {
            "mode": mode, "command_ids": sim.set_mode(mode, actor, corr, "Modalità impostata dall'app")}, 202)

    @router.post("/apartment/hold")
    async def hold(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        actor, corr = ctx(request)
        try:
            body = await body_of(request) or {}
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        if not isinstance(body, dict):
            return error(400, "bad_request", "Corpo non valido")
        return await run_idempotent(request, sim, lambda: sim.set_hold(body.get("minutes"), body.get("mode"), actor, corr), 202)

    @router.get("/devices")
    async def devices(apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        return {"apartment_id": apartment_id, "rooms": sim.rooms, "devices": list(sim.devices.values())}

    @router.patch("/devices/{device_id}")
    async def patch_device(device_id: str, request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        actor, corr = ctx(request)
        try:
            body = await body_of(request)
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        return await run(lambda: sim.update_device(device_id, body, actor, corr))

    @router.post("/devices/{device_id}/commands")
    async def command(device_id: str, request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        actor, corr = ctx(request)
        try:
            body = await body_of(request)
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        return await run_idempotent(request, sim, lambda: sim.create_command(device_id, body, actor, corr), 202)

    @router.get("/commands/{command_id}")
    async def get_command(command_id: str, apartment_id: str = Depends(apartment_of)):
        cmd = engine_of(apartment_id).commands.get(command_id)
        return cmd if cmd else error(404, "not_found", "Comando inesistente")

    @router.get("/energy")
    async def energy(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        return await run(lambda: sim.energy(request.query_params))

    @router.get("/schedule")
    async def schedule(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        q = request.query_params

        def go():
            try:
                frm = parse_dt(q["from"]) if q.get("from") else None
                to = parse_dt(q["to"]) if q.get("to") else None
            except ValueError:
                raise MockError(400, "bad_request", "from/to non validi")
            return sim.list_schedule(frm, to)

        return await run(go)

    @router.post("/schedule")
    async def create_schedule(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        actor, corr = ctx(request)
        try:
            body = await body_of(request)
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        return await run_idempotent(request, sim, lambda: sim.create_schedule(body, actor, corr), 201)

    @router.patch("/schedule/{schedule_id}")
    async def move_schedule(schedule_id: str, request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        actor, corr = ctx(request)
        try:
            body = await body_of(request)
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        return await run(lambda: sim.move_schedule(schedule_id, body, actor, corr))

    @router.delete("/schedule/{schedule_id}")
    async def delete_schedule(schedule_id: str, request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        actor, corr = ctx(request)
        return await run(lambda: sim.cancel_schedule(schedule_id, actor, corr), 204)

    @router.get("/rules")
    async def rules(apartment_id: str = Depends(apartment_of)):
        return engine_of(apartment_id).ruleset()

    @router.put("/rules")
    async def put_rules(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        actor, corr = ctx(request)
        try:
            body = await body_of(request)
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        return await run(lambda: sim.update_rules(body, actor, corr))

    @router.get("/approvals")
    async def approvals(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        return await run(lambda: sim.list_approvals(request.query_params.get("status", "pending")))

    @router.post("/approvals/{approval_id}/decision")
    async def decide(approval_id: str, request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        actor, corr = ctx(request)
        try:
            body = await body_of(request)
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        return await run_idempotent(request, sim, lambda: sim.decide(approval_id, body, actor, corr), 200)

    @router.get("/decisions")
    async def decisions(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        return await run(lambda: sim.list_decisions(request.query_params))

    @router.post("/ask")
    async def ask(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        actor, corr = ctx(request)
        try:
            body = await body_of(request)
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        return await run_idempotent(request, sim, lambda: sim.create_ask(body, actor, corr), 202)

    @router.get("/ask/{ask_id}")
    async def get_ask(ask_id: str, apartment_id: str = Depends(apartment_of)):
        a = engine_of(apartment_id).asks.get(ask_id)
        return a if a else error(404, "not_found", "Richiesta inesistente")

    @router.post("/bookings")
    async def bookings(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        _, corr = ctx(request)
        try:
            body = await body_of(request)
            status, result = sim.ingest_booking(body, corr)
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        return JSONResponse(status_code=status, content=result)

    @router.post("/_test/state")
    async def test_state(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        actor, corr = ctx(request)
        try:
            body = await body_of(request)
        except MockError as exc:
            return JSONResponse(status_code=exc.status, content=exc.body())
        return await run(lambda: sim.test_state(body, actor, corr), 204)

    @router.get("/stream")
    async def stream(request: Request, apartment_id: str = Depends(apartment_of)):
        sim = engine_of(apartment_id)
        last_id = request.headers.get("Last-Event-ID")
        queue: asyncio.Queue = asyncio.Queue()
        for env in sim.events_after(last_id):
            queue.put_nowait(env)
        sim.subscribers.add(queue)

        async def gen():
            try:
                yield ": connected\n\n"
                while True:
                    try:
                        env = await asyncio.wait_for(queue.get(), timeout=ping)
                    except TimeoutError:
                        if await request.is_disconnected():
                            break
                        yield ": ping\n\n"
                        continue
                    payload = {k: v for k, v in env.items() if k != "_t"}
                    yield f"id: {env['id']}\nevent: {env['event']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            finally:
                sim.subscribers.discard(queue)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    app.include_router(router)
    return app
