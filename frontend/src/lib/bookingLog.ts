import type { WebhookLog } from "@/api/admin";

// «Prenotazioni ricevute» (D-79): reads a webhook call for a non-technical admin, from the data the BFF already logs.
// No new field: the event and the dates come from raw_body, the outcome from signature_ok, status_code, outcome and
// forward_attempts.

export const BOOKING_TYPES = ["booking_created", "booking_changed", "booking_cancelled", "checkin", "checkout"] as const;
export type BookingType = (typeof BOOKING_TYPES)[number];

/** Event names of the stub Italianway translator (bff/bookings/translator.py, ItalianwayTranslator.TYPE_MAP). */
const ITALIANWAY_TYPES: Record<string, BookingType> = {
  "reservation.created": "booking_created",
  "reservation.updated": "booking_changed",
  "reservation.cancelled": "booking_cancelled",
  "reservation.checkin": "checkin",
  "reservation.checkout": "checkout",
};

export interface ReadEvent {
  type: BookingType;
  /** Apartment code of the booking platform (Italianway id); null when the body does not carry it. */
  externalId: string | null;
  checkin: string | null;
  checkout: string | null;
}

const obj = (v: unknown): Record<string, unknown> | null => (v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : null);
const str = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : typeof v === "number" ? String(v) : null);

/**
 * The two formats the BFF knows today: the stub Italianway one ({event, reservation: {apartment_id, checkin, checkout}})
 * and our own BookingEvent, used by the bookings simulator ({type, checkin_at, checkout_at, apartment_external_id or
 * apartment_id}). The real Italianway format is not known yet (P-10): anything else is null, "formato non riconosciuto".
 */
export function readEvent(raw: string): ReadEvent | null {
  let body: Record<string, unknown> | null;
  try {
    body = obj(JSON.parse(raw));
  } catch {
    return null;
  }
  if (!body) return null;
  const iw = ITALIANWAY_TYPES[String(body.event)];
  if (iw) {
    const res = obj(body.reservation) ?? {};
    return { type: iw, externalId: str(res.apartment_id) ?? str(body.apartment_id), checkin: str(res.checkin), checkout: str(res.checkout) };
  }
  const type = BOOKING_TYPES.find((x) => x === body.type);
  if (type) return { type, externalId: str(body.apartment_external_id) ?? str(body.apartment_id), checkin: str(body.checkin_at), checkout: str(body.checkout_at) };
  return null;
}

/**
 * The event of a logged call. The BFF reads it into structured fields and obscures the body (P-51, D-90): when those
 * fields are there they are the only source, and an unknown or missing event_type is "formato non riconosciuto". An
 * older BFF without them falls back to reading the body.
 */
export function eventOf(log: Pick<WebhookLog, "raw_body" | "event_type" | "external_id" | "checkin_at" | "checkout_at">): ReadEvent | null {
  if (log.event_type === undefined) return readEvent(log.raw_body);
  const type = log.event_type ? ITALIANWAY_TYPES[log.event_type] ?? BOOKING_TYPES.find((x) => x === log.event_type) : undefined;
  if (!type) return null;
  return { type, externalId: log.external_id ?? null, checkin: log.checkin_at ?? null, checkout: log.checkout_at ?? null };
}

export type OutcomeKind = "forwarded" | "signature" | "engine" | "unknownApartment" | "disabled" | "unreadable" | "other";

export interface Outcome {
  kind: OutcomeKind;
  ok: boolean;
  /** Only for "engine": attempts after the first one (the BFF tries up to 3 times). */
  retries: number;
}

/** Outcome of a call, in the order the BFF decides it (bff/routes/webhooks.py). */
export function outcomeOf(log: Pick<WebhookLog, "signature_ok" | "status_code" | "outcome" | "forward_attempts">): Outcome {
  const kind: OutcomeKind = !log.signature_ok
    ? "signature"
    : log.status_code === 200
      ? "forwarded"
      : log.outcome === "unknown_apartment" || log.outcome === "ambiguous_apartment"
        ? "unknownApartment"
        : log.outcome === "bad_request" || log.outcome === "untranslatable"
          ? "unreadable"
          : log.outcome === "apartment_disabled"
            ? "disabled"
            : log.forward_attempts > 0
              ? "engine"
              : "other";
  return { kind, ok: kind === "forwarded", retries: kind === "engine" ? Math.max(0, log.forward_attempts - 1) : 0 };
}

/** Calls of the last 24 hours: received, forwarded to the engine, with a problem (all the others). */
export function summary24h(logs: WebhookLog[], now = Date.now()) {
  const recent = logs.filter((l) => {
    const at = Date.parse(l.received_at);
    return !Number.isNaN(at) && now - at <= 24 * 3600 * 1000;
  });
  const sent = recent.filter((l) => outcomeOf(l).ok).length;
  return { received: recent.length, sent, problems: recent.length - sent };
}
