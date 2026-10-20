"""Booking translators: platform payload -> contract BookingEvent (our internal format)."""
from typing import Protocol

from pydantic import BaseModel, ValidationError, field_validator

BOOKING_TYPES = ("booking_created", "booking_changed", "booking_cancelled", "checkin", "checkout")
SOURCES = ("italianway", "ical", "simulator", "manual")


class BookingEvent(BaseModel):
    event_id: str
    type: str
    booking_id: str
    checkin_at: str
    checkout_at: str
    guests: int | None = None
    source: str
    ts: str

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        if v not in BOOKING_TYPES:
            raise ValueError("type non valido")
        return v

    @field_validator("source")
    @classmethod
    def _source(cls, v):
        if v not in SOURCES:
            raise ValueError("source non valido")
        return v


class TranslationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class BookingTranslator(Protocol):
    source: str

    def translate(self, payload: dict) -> tuple[str, BookingEvent]:
        """Returns (external_apartment_id, event). Raises TranslationError."""
        ...


class SimulatorTranslator:
    """Accepts our own BookingEvent as-is; `apartment_external_id` or `apartment_id` selects the apartment."""

    source = "simulator"

    def translate(self, payload: dict) -> tuple[str, BookingEvent]:
        if not isinstance(payload, dict):
            raise TranslationError("Corpo non valido")
        ext = payload.get("apartment_external_id") or payload.get("apartment_id")
        if not ext:
            raise TranslationError("apartment_id mancante")
        try:
            ev = BookingEvent(**{k: v for k, v in payload.items() if k in BookingEvent.model_fields})
        except ValidationError as exc:
            raise TranslationError("; ".join(e["msg"] for e in exc.errors()))
        return str(ext), ev


class ItalianwayTranslator:
    """STUB — the real Italianway webhook payload is not known yet (see contract 'Domande aperte').

    Current best guess maps a flat payload with `event`, `reservation.{id,checkin,checkout,guests,apartment_id}`
    and `sent_at`. Replace `translate` once the real payload is documented; keep the BookingEvent output stable.
    """

    source = "italianway"
    TYPE_MAP = {
        "reservation.created": "booking_created",
        "reservation.updated": "booking_changed",
        "reservation.cancelled": "booking_cancelled",
        "reservation.checkin": "checkin",
        "reservation.checkout": "checkout",
    }

    def translate(self, payload: dict) -> tuple[str, BookingEvent]:
        if not isinstance(payload, dict):
            raise TranslationError("Corpo non valido")
        res = payload.get("reservation") or {}
        ev_type = self.TYPE_MAP.get(str(payload.get("event", "")))
        if not ev_type:
            raise TranslationError(f"Evento Italianway non riconosciuto: {payload.get('event')!r} (stub)")
        ext = res.get("apartment_id") or payload.get("apartment_id")
        if not ext:
            raise TranslationError("apartment_id mancante nel payload Italianway")
        try:
            ev = BookingEvent(
                event_id=str(payload.get("id") or f"iw-{res.get('id')}-{ev_type}-{payload.get('sent_at')}"),
                type=ev_type,
                booking_id=str(res.get("id", "")),
                checkin_at=str(res.get("checkin", "")),
                checkout_at=str(res.get("checkout", "")),
                guests=res.get("guests"),
                source="italianway",
                ts=str(payload.get("sent_at", "")),
            )
        except ValidationError as exc:
            raise TranslationError("; ".join(e["msg"] for e in exc.errors()))
        return str(ext), ev
