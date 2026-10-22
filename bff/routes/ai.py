"""POST /internal/ai/chat: the engines' way to the model (P-60 step 9, bff/ai_gateway.py). Not a route of the PWA:
the caller is an engine, with X-Apartment-Id and its instance key in X-API-Key."""
from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from .. import ai_gateway
from ..config import get_settings

router = APIRouter(prefix="/internal/ai")


@router.post("/chat")
async def chat(body: dict = Body(...), x_apartment_id: str | None = Header(default=None),
               x_api_key: str | None = Header(default=None)):
    location = {"X-AI-Location": get_settings().ai_location}   # D-181: the engine checks it on every answer
    try:
        apt = await ai_gateway.authenticate(x_apartment_id, x_api_key)
        return JSONResponse(await ai_gateway.chat(apt.apartment_id, body), headers=location)
    except ai_gateway.GatewayError as exc:
        return JSONResponse(status_code=exc.status, content={"error": exc.error, "message": exc.message},
                            headers=location)
