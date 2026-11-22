"""POST /internal/ai/chat: the engines' way to the model (P-60 step 9, bff/ai_gateway.py). Not a route of the PWA:
the caller is an engine, with X-Apartment-Id and its instance key in X-API-Key."""
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from .. import ai_gateway
from ..config import get_settings
from ..logs import warn
from ..repository import get_repository

router = APIRouter(prefix="/internal/ai")
# F-4 (attack-from-outside review): the server's own count per apartment and UTC day on the engines' way, for a stolen
# key that skips the engine's 50 questions a day (ASK_DAILY_LIMIT, per local day: a UTC day can hold up to 100 of them).
# Over it 429, which the engine answers with the quick assistant
ENGINE_DAILY_CALLS = 100


@router.post("/chat")
async def chat(request: Request, x_apartment_id: str | None = Header(default=None),
               x_api_key: str | None = Header(default=None), x_ask_id: str | None = Header(default=None)):
    location = {"X-AI-Location": get_settings().ai_location}   # D-181: the engine checks it on every answer
    try:
        apt = await ai_gateway.authenticate(x_apartment_id, x_api_key)
        day = datetime.now(UTC).strftime("%Y-%m-%d")
        if not await get_repository().take_mail_quota([(f"ai_engine:{apt.apartment_id}:{day}", ENGINE_DAILY_CALLS)]):
            warn("assistant engine daily calls over", apartment_id=apt.apartment_id, limit=ENGINE_DAILY_CALLS)
            raise ai_gateway.GatewayError(429, "daily_limit", "Limite giornaliero dell'assistente raggiunto per questo "
                                                              "appartamento")
        # F-2: the body is parsed only after the key (a typed `Body(...)` was parsed before it); its size is limited
        # before it is read (bff/body_limit.py, 256 KiB). Not JSON, or nested too deep: 422, as the typed body gave
        try:
            body = json.loads(await request.body())
        except (ValueError, RecursionError):
            raise ai_gateway.GatewayError(422, "bad_request", "JSON non valido")
        return JSONResponse(await ai_gateway.chat(apt.apartment_id, body, ask_id=(x_ask_id or "")[:64]),
                            headers=location)
    except ai_gateway.GatewayError as exc:
        return JSONResponse(status_code=exc.status, content={"error": exc.error, "message": exc.message},
                            headers=location)
