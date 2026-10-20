"""Idempotent forwarding of BookingEvents to the instance (POST /bookings) with retries."""
import asyncio
import uuid

from .. import instances
from ..logs import info, warn
from ..repository import Apartment, apply_booking_event, get_repository
from .translator import BookingEvent

RETRIES = 3
BACKOFF_S = (0.5, 1.5, 3.0)


async def _archive(apartment_id: str, ev: BookingEvent) -> None:
    """Keeps the latest state of every forwarded booking: the contract only exposes current_booking_id."""
    repo = get_repository()
    existing = await repo.get_booking(apartment_id, ev.booking_id)
    await repo.upsert_booking(apply_booking_event(existing, apartment_id, ev.model_dump()))


class ForwardError(Exception):
    def __init__(self, status: int, body: dict):
        super().__init__(body.get("message", "forward failed"))
        self.status = status
        self.body = body


async def forward(apt: Apartment, ev: BookingEvent, correlation_id: str | None = None, stats: dict | None = None) -> dict:
    """event_id is the idempotency key on the instance, so a retry after a timeout is safe. `stats` gets attempts/status."""
    correlation_id = correlation_id or str(uuid.uuid4())
    stats = stats if stats is not None else {}
    last_exc: Exception | None = None
    for attempt in range(RETRIES):
        stats["attempts"] = attempt + 1
        try:
            resp = await instances.call(apt, "POST", "/bookings", actor="system:bff", correlation_id=correlation_id,
                                        json=ev.model_dump())
            stats["status"] = resp.status_code
            if resp.status_code < 500:
                body = resp.json()
                if resp.status_code >= 400:
                    raise ForwardError(resp.status_code, body)
                await _archive(apt.apartment_id, ev)
                info("booking forwarded", apartment_id=apt.apartment_id, event_id=ev.event_id, duplicate=body.get("duplicate"))
                return body
            last_exc = ForwardError(resp.status_code, resp.json() if resp.content else {"message": "errore istanza"})
        except ForwardError:
            raise
        except Exception as exc:
            last_exc = exc
        warn("booking forward retry", apartment_id=apt.apartment_id, event_id=ev.event_id, attempt=attempt + 1, error=str(last_exc))
        if attempt < RETRIES - 1:
            await asyncio.sleep(BACKOFF_S[attempt])
    raise ForwardError(502, {"error": "instance_unreachable", "message": "Istanza non raggiungibile dopo 3 tentativi"})
