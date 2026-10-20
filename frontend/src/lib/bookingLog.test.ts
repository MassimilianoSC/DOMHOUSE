import type { WebhookLog } from "@/api/admin";
import { outcomeOf, readEvent, summary24h } from "./bookingLog";

// «Prenotazioni ricevute» (D-79): what the tab can read from a logged webhook call, without new fields from the BFF.
const ITALIANWAY = {
  event: "reservation.created",
  id: "iw-ev-1",
  sent_at: "2026-11-01T10:00:00Z",
  reservation: { id: "RES-100", apartment_id: "IW-7", checkin: "2026-12-01T15:00:00Z", checkout: "2026-12-03T10:00:00Z", guests: 2 },
};

describe("lettura del corpo: solo i formati che il BFF conosce oggi", () => {
  it("formato del traduttore stub Italianway: tipo, codice dell'appartamento e date", () => {
    expect(readEvent(JSON.stringify(ITALIANWAY))).toEqual({ type: "booking_created", externalId: "IW-7", checkin: "2026-12-01T15:00:00Z", checkout: "2026-12-03T10:00:00Z" });
  });

  it.each([
    ["reservation.updated", "booking_changed"],
    ["reservation.cancelled", "booking_cancelled"],
    ["reservation.checkin", "checkin"],
    ["reservation.checkout", "checkout"],
  ])("evento %s → %s", (event, type) => {
    expect(readEvent(JSON.stringify({ ...ITALIANWAY, event }))?.type).toBe(type);
  });

  it("formato del simulatore (BookingEvent): tipo, date e apartment_external_id", () => {
    const sim = { event_id: "e1", type: "booking_cancelled", booking_id: "b1", checkin_at: "2026-12-01T15:00:00+01:00", checkout_at: "2026-12-04T10:00:00+01:00", source: "simulator", ts: "", apartment_external_id: "IW-9" };
    expect(readEvent(JSON.stringify(sim))).toEqual({ type: "booking_cancelled", externalId: "IW-9", checkin: "2026-12-01T15:00:00+01:00", checkout: "2026-12-04T10:00:00+01:00" });
  });

  it("codice dell'appartamento assente: null, le date restano", () => {
    const { apartment_id: _code, ...reservation } = ITALIANWAY.reservation;
    expect(readEvent(JSON.stringify({ ...ITALIANWAY, reservation }))).toMatchObject({ externalId: null, checkin: "2026-12-01T15:00:00Z" });
  });

  it.each([
    ["JSON non valido", "{non json"],
    ["corpo vuoto", ""],
    ["un elenco", "[1,2]"],
    ["evento sconosciuto", JSON.stringify({ ...ITALIANWAY, event: "reservation.unknown" })],
    ["tipo sconosciuto", JSON.stringify({ type: "booking_moved", checkin_at: "x" })],
    ["altro formato", JSON.stringify({ booking: { status: "new" } })],
  ])("%s → formato non riconosciuto (null)", (_label, raw) => {
    expect(readEvent(raw)).toBeNull();
  });
});

const log = (over: Partial<WebhookLog>): WebhookLog => ({
  log_id: "wh-1", source: "italianway", received_at: "2026-10-16T08:00:00Z", tenant_id: "t-1", apartment_id: "apt-001", signature_ok: true,
  status_code: 200, outcome: "accepted", event_id: "e1", booking_id: "b1", correlation_id: "c1", forward_status: 200, forward_attempts: 1, raw_body: "", ...over,
});

describe("esito: tabella di corrispondenza", () => {
  it.each([
    ["accettata", { status_code: 200, outcome: "accepted" }, "forwarded", true, 0],
    ["già ricevuta prima (duplicate)", { status_code: 200, outcome: "duplicate" }, "forwarded", true, 0],
    ["firma non valida", { signature_ok: false, status_code: 401, outcome: "invalid_signature", forward_status: null, forward_attempts: 0 }, "signature", false, 0],
    ["codice Italianway sconosciuto", { status_code: 404, outcome: "unknown_apartment", forward_status: null, forward_attempts: 0 }, "unknownApartment", false, 0],
    ["codice su più appartamenti", { status_code: 409, outcome: "ambiguous_apartment", forward_status: null, forward_attempts: 0 }, "unknownApartment", false, 0],
    ["JSON non valido", { status_code: 400, outcome: "bad_request", forward_status: null, forward_attempts: 0 }, "unreadable", false, 0],
    ["non traducibile", { status_code: 422, outcome: "untranslatable", forward_status: null, forward_attempts: 0 }, "unreadable", false, 0],
    ["appartamento disattivato", { status_code: 409, outcome: "apartment_disabled", forward_status: null, forward_attempts: 0 }, "disabled", false, 0],
    ["rifiutata dal motore al primo tentativo", { status_code: 422, outcome: "invalid_booking", forward_status: 422, forward_attempts: 1 }, "engine", false, 0],
    ["motore irraggiungibile dopo 3 tentativi", { status_code: 502, outcome: "instance_unreachable", forward_status: 503, forward_attempts: 3 }, "engine", false, 2],
    ["esito mai visto, senza inoltro", { status_code: 500, outcome: "boh", forward_status: null, forward_attempts: 0 }, "other", false, 0],
  ] as const)("%s", (_label, over, kind, ok, retries) => {
    expect(outcomeOf(log(over))).toEqual({ kind, ok, retries });
  });

  it("la firma non valida vale più di tutto il resto", () => {
    expect(outcomeOf(log({ signature_ok: false, status_code: 200 })).kind).toBe("signature");
  });
});

describe("sintesi delle ultime 24 ore", () => {
  it("conta le ricevute, le trasmesse e le altre; fuori dalle 24 ore non conta", () => {
    const now = Date.parse("2026-10-16T12:00:00Z");
    const logs = [
      log({ log_id: "a", received_at: "2026-10-16T11:00:00Z" }),
      log({ log_id: "b", received_at: "2026-10-16T02:00:00Z", status_code: 200, outcome: "duplicate" }),
      log({ log_id: "c", received_at: "2026-10-15T13:00:00Z", status_code: 502, outcome: "instance_unreachable", forward_attempts: 3 }),
      log({ log_id: "d", received_at: "2026-10-15T11:59:00Z" }),
    ];
    expect(summary24h(logs, now)).toEqual({ received: 3, sent: 2, problems: 1 });
  });
});
