from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette._utils import get_route_path
from starlette.datastructures import MutableHeaders

from engine.log import setup_logging as setup_engine_logging

from . import push
from .config import get_settings
from .logs import setup_logging
from .routes import account, admin, apartments, platform, webhooks
from .routes import ai as ai_routes
from .routes import push as push_routes
from .routes import rules as rules_routes
from .sse_hub import hub_manager


class NoStoreMiddleware:
    """P-36 point 12: the app's JSON answers (/app/*) are per user and per organisation: never kept by the browser or an
    intermediate cache. Pure ASGI, header only, so the SSE stream keeps streaming (and keeps its own no-cache)."""

    def __init__(self, app, root_path: str = ""):
        self.app, self.prefix = app, f"{root_path}/app/"

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith(self.prefix):
            return await self.app(scope, receive, send)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if not headers.get("content-type", "").startswith("text/event-stream"):
                    headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_with_header)


def check_ai_location(settings) -> None:
    """D-180: the BFF does not start with a model outside the European Union (AI_LOCATION not eu nor europe-…)."""
    from .config import european_location
    if not european_location(settings.ai_location):
        from .logs import error
        message = (f"AI_LOCATION «{settings.ai_location}» is not European (D-180: eu or europe-…, never global nor us): "
                   f"the BFF does not start")
        error("model location refused", ai_location=settings.ai_location)
        raise SystemExit(message)


def create_app() -> FastAPI:
    setup_logging()
    setup_engine_logging(None)    # the demonstration apartments' engine logs too, with apartment_id in each line
    settings = get_settings()
    check_ai_location(settings)
    push.register()

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await webhooks.report_demo_codes()   # D-99 F1: a demonstration apartment with an Italianway code, in production
        await push.start_background_hubs()
        from . import summary_job
        summary_job.start()                   # P-60 step 11: the weekly summary's hourly round
        yield
        await hub_manager.stop_all()

    app = FastAPI(title="DOMHOUSE BFF", lifespan=lifespan)
    app.add_middleware(NoStoreMiddleware, root_path=settings.root_path)
    if settings.is_dev:
        app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    elif settings.cors_origins:
        # PWA su Firebase Hosting e BFF su Cloud Run hanno origini diverse: senza CORS nessuna chiamata passa.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Correlation-Id", "Content-Disposition"],   # P-52: the Excel file's name
        )

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"error": "error", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content=detail)

    # /healthz serves only Cloud Run's own startup/liveness probes: from outside, Cloud Run's front end reserves paths
    # ending in "z" and answers 404 itself (https://cloud.google.com/run/docs/known-issues#reserved-url-paths, E-12).
    # /health is the public twin, used by the uptime check.
    @app.get("/healthz")
    @app.get("/health")
    async def healthz():
        return {"status": "ok", "app_env": settings.app_env}

    app.include_router(apartments.router)
    app.include_router(account.router)
    app.include_router(admin.router)
    app.include_router(push_routes.router)
    app.include_router(webhooks.router)
    app.include_router(platform.router)
    app.include_router(ai_routes.router)   # P-60 step 9: engines -> model
    app.include_router(rules_routes.router)   # P-60 step 12: rules proposed by the assistant, copied

    # D-97: the built-in mock is mounted in every mode, also in production, for demonstration apartments (mock://).
    # F2 (D-70) and N1 (D-71) keep it the BFF's own: refused from the internet, its random key checked on loopback.
    from .mock_instance.app import create_mock_app

    @app.middleware("http")
    async def mock_only_from_loopback(request: Request, call_next):
        # F2 (D-70): the mock is for the BFF's own loopback call only. Cloud Run adds X-Forwarded-For to every
        # request from the internet; the BFF's call to 127.0.0.1 has none. Refuse (404) anything forwarded.
        path = get_route_path(request.scope)
        # D-99 N1: "/mock" itself too, which the mount would otherwise answer with a 307 to "/mock/"
        if (path == "/mock" or path.startswith("/mock/")) and "x-forwarded-for" in request.headers:
            return JSONResponse(status_code=404, content={"error": "not_found", "message": "Endpoint inesistente"})
        return await call_next(request)

    model_for = None
    if settings.ai_demos:     # P-60 step 9 (D-132 point 5): the demonstrations ask the real model, on loopback
        from engine.assistant import ModelClient

        def model_for(apartment_id: str) -> ModelClient:
            return ModelClient(f"http://127.0.0.1:{settings.port}", apartment_id, settings.instance_api_key_fallback)
    mock_app = create_mock_app(api_key=settings.instance_api_key_fallback, model_for=model_for)
    app.state.mock_registry = mock_app.state.registry   # the reset of a demonstration apartment (D-97)
    app.mount("/mock", mock_app)
    return app


app = create_app()
