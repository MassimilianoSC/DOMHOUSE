import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { WebhookLog } from "@/api/admin";
import { t } from "@/i18n";
import { fmtDate } from "@/lib/format";
import { AdminWebhookLogs } from "./AdminWebhookLogs";

// «Prenotazioni ricevute» (D-79): one sentence per call, the outcome in green or red, the technical details on request.
const s = vi.hoisted(() => ({ logs: [] as unknown[], apartments: vi.fn() }));

vi.mock("@/api/admin", () => ({ adminApi: { webhookLogs: async () => s.logs, apartments: s.apartments } }));

const body = (event: string, apartmentId: string) =>
  JSON.stringify({ event, id: "iw-ev-1", sent_at: "2026-11-01T10:00:00Z", reservation: { id: "RES-100", apartment_id: apartmentId, checkin: "2026-12-01T15:00:00Z", checkout: "2026-12-03T10:00:00Z" } });

const recent = (hoursAgo: number) => new Date(Date.now() - hoursAgo * 3600 * 1000).toISOString();

const log = (over: Partial<WebhookLog>): WebhookLog => ({
  log_id: "wh-1", source: "italianway", received_at: recent(1), tenant_id: "t-1", apartment_id: "apt-001", signature_ok: true, status_code: 200,
  outcome: "accepted", event_id: "iw-ev-1", booking_id: "RES-100", correlation_id: "corr-123", forward_status: 200, forward_attempts: 1,
  raw_body: body("reservation.created", "IW-7"), ...over,
});

const MILANO = { apartment_id: "apt-001", name: "Milano Centro", italianway_id: "IW-7" };
const RIMINI = { apartment_id: "apt-002", name: "Rimini Mare", italianway_id: "IW-9" };
const DATES = t("admin.bookingsReceived.dates", { checkin: fmtDate("2026-12-01T15:00:00Z"), checkout: fmtDate("2026-12-03T10:00:00Z") });

function open(props: Parameters<typeof AdminWebhookLogs>[0] = {}) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AdminWebhookLogs {...props} />
    </QueryClientProvider>,
  );
}

// The apartment names arrive with their own list: wait until the sentence no longer says "…".
async function sentence(id: string) {
  const el = await screen.findByTestId(`webhook-log-sentence-${id}`);
  await waitFor(() => expect(el).not.toHaveTextContent("…"));
  return el;
}
const result = (id: string) => screen.getByTestId(`webhook-log-result-${id}`);

beforeEach(() => {
  vi.clearAllMocks();
  s.apartments.mockResolvedValue([MILANO, RIMINI]);
  s.logs = [];
});

describe("Prenotazioni ricevute: una frase per riga", () => {
  it("trasmessa: evento, nome dell'appartamento (non il codice), date, esito in verde", async () => {
    s.logs = [log({})];
    open();
    expect(await sentence("wh-1")).toHaveTextContent(`${t("admin.bookingsReceived.events.booking_created")} · Milano Centro · ${DATES}`);
    expect(screen.getByTestId("webhook-log-sentence-wh-1")).not.toHaveTextContent("IW-7");
    expect(result("wh-1")).toHaveTextContent(t("admin.bookingsReceived.outcomes.forwarded"));
    expect(screen.getByTestId("webhook-log-wh-1")).toHaveAttribute("data-ok", "true");
  });

  it("senza apartment_id nel log, il nome viene dal codice Italianway del corpo", async () => {
    s.logs = [log({ apartment_id: null, raw_body: body("reservation.cancelled", "IW-9"), status_code: 409, outcome: "apartment_disabled", forward_status: null, forward_attempts: 0 })];
    open();
    expect(await sentence("wh-1")).toHaveTextContent(`${t("admin.bookingsReceived.events.booking_cancelled")} · Rimini Mare`);
    expect(result("wh-1")).toHaveTextContent(t("admin.bookingsReceived.outcomes.disabled"));
  });

  it("codice che non corrisponde a nessun appartamento: «appartamento non riconosciuto»", async () => {
    s.logs = [log({ apartment_id: null, raw_body: body("reservation.checkin", "IW-404"), status_code: 404, outcome: "unknown_apartment", forward_status: null, forward_attempts: 0 })];
    open();
    expect(await sentence("wh-1")).toHaveTextContent(`${t("admin.bookingsReceived.events.checkin")} · ${t("admin.bookingsReceived.unknownApartment")}`);
    expect(result("wh-1")).toHaveTextContent(t("admin.bookingsReceived.outcomes.unknownApartment"));
    expect(screen.getByTestId("webhook-log-wh-1")).toHaveAttribute("data-ok", "false");
  });

  it("motore irraggiungibile dopo 3 tentativi: «riprovato 2 volte», in rosso", async () => {
    s.logs = [log({ status_code: 502, outcome: "instance_unreachable", forward_status: 503, forward_attempts: 3 })];
    open();
    await sentence("wh-1");
    expect(result("wh-1")).toHaveTextContent(t("admin.bookingsReceived.outcomes.engineRetried", { count: 2 }));
    expect(result("wh-1")).toHaveClass("text-destructive");
  });

  it("rifiutata dal motore al primo tentativo: senza «riprovato»; con 2 tentativi «riprovato 1 volta»", async () => {
    s.logs = [
      log({ log_id: "wh-1", status_code: 422, outcome: "invalid_booking", forward_status: 422, forward_attempts: 1 }),
      log({ log_id: "wh-2", status_code: 502, outcome: "instance_unreachable", forward_status: 503, forward_attempts: 2 }),
    ];
    open();
    await sentence("wh-2");
    expect(result("wh-1")).toHaveTextContent(t("admin.bookingsReceived.outcomes.engine"));
    expect(result("wh-1")).not.toHaveTextContent("riprovato");
    expect(result("wh-2")).toHaveTextContent(t("admin.bookingsReceived.outcomes.engineRetriedOnce"));
  });

  it("firma non valida", async () => {
    s.logs = [log({ signature_ok: false, status_code: 401, outcome: "invalid_signature", apartment_id: null, forward_status: null, forward_attempts: 0 })];
    open();
    await sentence("wh-1");
    expect(result("wh-1")).toHaveTextContent(t("admin.bookingsReceived.outcomes.signature"));
  });

  it("corpo in un formato sconosciuto: «Evento ricevuto, formato non riconosciuto», il corpo resta nei dettagli", async () => {
    s.logs = [log({ raw_body: '{"booking":{"status":"new"}}', status_code: 422, outcome: "untranslatable", apartment_id: null, forward_status: null, forward_attempts: 0 })];
    open();
    expect(await sentence("wh-1")).toHaveTextContent(t("admin.bookingsReceived.unreadable"));
    expect(result("wh-1")).toHaveTextContent(t("admin.bookingsReceived.outcomes.unreadable"));
    fireEvent.click(screen.getByTestId("webhook-log-toggle-wh-1"));
    expect(screen.getByTestId("webhook-log-body-wh-1")).toHaveTextContent('{"booking":{"status":"new"}}');
  });
});

describe("Dettagli tecnici: chiusi finché non si aprono", () => {
  it("firma, codice di risposta, event_id, correlation_id copiabile, inoltro e corpo grezzo", async () => {
    s.logs = [log({ status_code: 502, outcome: "instance_unreachable", forward_status: 503, forward_attempts: 3 })];
    open();
    await sentence("wh-1");
    expect(screen.queryByTestId("webhook-log-details-wh-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("webhook-log-toggle-wh-1")).toHaveTextContent(t("admin.bookingsReceived.details"));
    fireEvent.click(screen.getByTestId("webhook-log-toggle-wh-1"));
    expect(screen.getByTestId("webhook-log-signature-wh-1")).toHaveTextContent(t("admin.bookingsReceived.hmacOk"));
    expect(screen.getByTestId("webhook-log-outcome-wh-1")).toHaveTextContent("502 · instance_unreachable");
    expect(screen.getByTestId("webhook-log-event-wh-1")).toHaveTextContent("iw-ev-1");
    expect(screen.getByTestId("webhook-log-correlation-wh-1")).toHaveTextContent("corr-123");
    expect(screen.getByTestId("webhook-log-forward-wh-1")).toHaveTextContent(`503 · ${t("admin.bookingsReceived.attempts", { count: 3 })}`);
    expect(screen.getByTestId("webhook-log-body-wh-1")).toHaveTextContent("RES-100");
    fireEvent.click(screen.getByTestId("webhook-log-toggle-wh-1"));
    expect(screen.queryByTestId("webhook-log-details-wh-1")).not.toBeInTheDocument();
  });
});

describe("riga di sintesi in cima", () => {
  it("«Ultime 24 ore: N ricevute, N trasmesse, N con problemi»; le chiamate più vecchie non contano", async () => {
    s.logs = [
      log({ log_id: "wh-1" }),
      log({ log_id: "wh-2", status_code: 502, outcome: "instance_unreachable", forward_status: 503, forward_attempts: 3 }),
      log({ log_id: "wh-3", received_at: recent(30) }),
    ];
    open();
    expect(await screen.findByTestId("admin-webhooks-summary")).toHaveTextContent(/^Ultime 24 ore: 2 ricevute, 1 trasmessa, 1 con problemi$/);
  });

  it("singolare quando il numero è 1: «1 ricevuta, 1 trasmessa»; «con problemi» non cambia", async () => {
    s.logs = [log({ log_id: "wh-1", status_code: 502, outcome: "instance_unreachable", forward_status: 503, forward_attempts: 3 })];
    open();
    expect(await screen.findByTestId("admin-webhooks-summary")).toHaveTextContent(/^Ultime 24 ore: 1 ricevuta, 0 trasmesse, 1 con problemi$/);
  });

  it("una sola chiamata trasmessa: «1 ricevuta, 1 trasmessa, 0 con problemi»", async () => {
    s.logs = [log({ log_id: "wh-2" })];
    open();
    expect(await screen.findByTestId("admin-webhooks-summary")).toHaveTextContent(/^Ultime 24 ore: 1 ricevuta, 1 trasmessa, 0 con problemi$/);
  });

  it("nessuna chiamata: sintesi a zero e lo stato vuoto", async () => {
    open();
    expect(await screen.findByTestId("admin-webhooks-empty")).toHaveTextContent(t("admin.bookingsReceived.empty"));
    expect(screen.getByTestId("admin-webhooks-summary")).toHaveTextContent(/^Ultime 24 ore: 0 ricevute, 0 trasmesse, 0 con problemi$/);
  });
});

describe("area piattaforma (Webhook non attribuiti): stesse righe, senza elenco appartamenti", () => {
  it("mostra il codice Italianway al posto del nome e non chiede l'elenco degli appartamenti", async () => {
    s.logs = [log({ apartment_id: null, tenant_id: null, raw_body: body("reservation.created", "IW-404"), status_code: 404, outcome: "unknown_apartment", forward_status: null, forward_attempts: 0 })];
    open({ apartmentNames: false, hint: "piattaforma" });
    expect(await sentence("wh-1")).toHaveTextContent(t("admin.bookingsReceived.externalCode", { code: "IW-404" }));
    expect(s.apartments).not.toHaveBeenCalled();
    expect(screen.getByTestId("admin-webhooks-hint")).toHaveTextContent("piattaforma");
  });
});

describe("campi strutturati del server, corpo oscurato (P-51, D-90)", () => {
  const structured = (over: Partial<WebhookLog>) => log({
    raw_body: JSON.stringify({ event: "reservation.cancelled", id: "[oscurato]", reservation: { apartment_id: "IW-9", checkin: "[oscurato]", guest_name: "[oscurato]" } }),
    event_type: "reservation.cancelled", external_id: "IW-9", checkin_at: "2026-12-01T15:00:00Z", checkout_at: "2026-12-03T10:00:00Z", guests: 3,
    apartment_id: null, ...over,
  });

  it("la frase viene dai campi strutturati, non dal corpo", async () => {
    s.logs = [structured({})];
    open();
    expect(await sentence("wh-1")).toHaveTextContent(`${t("admin.bookingsReceived.events.booking_cancelled")} · Rimini Mare · ${DATES}`);
  });

  it("anche con un corpo non JSON (oscurato) la frase c'è, se i campi ci sono", async () => {
    s.logs = [structured({ raw_body: "[corpo non JSON, 120 byte]" })];
    open();
    expect(await sentence("wh-1")).toHaveTextContent(t("admin.bookingsReceived.events.booking_cancelled"));
  });

  it("tipo di evento assente o sconosciuto: «formato non riconosciuto», anche se il corpo sembrerebbe leggibile", async () => {
    s.logs = [structured({ event_type: null, raw_body: body("reservation.created", "IW-7") }), structured({ log_id: "wh-2", event_type: "reservation.moved" })];
    open();
    expect(await sentence("wh-1")).toHaveTextContent(t("admin.bookingsReceived.unreadable"));
    expect(screen.getByTestId("webhook-log-sentence-wh-2")).toHaveTextContent(t("admin.bookingsReceived.unreadable"));
  });

  it("«Dettagli tecnici»: codice Italianway, ospiti e il corpo così com'è (oscurato)", async () => {
    s.logs = [structured({})];
    open();
    await sentence("wh-1");
    fireEvent.click(screen.getByTestId("webhook-log-toggle-wh-1"));
    expect(screen.getByTestId("webhook-log-external-wh-1")).toHaveTextContent("IW-9");
    expect(screen.getByTestId("webhook-log-guests-wh-1")).toHaveTextContent("3");
    expect(screen.getByTestId("webhook-log-body-wh-1")).toHaveTextContent("[oscurato]");
  });

  it("piattaforma: il codice dal campo strutturato", async () => {
    s.logs = [structured({ tenant_id: null, status_code: 404, outcome: "unknown_apartment", forward_status: null, forward_attempts: 0 })];
    open({ apartmentNames: false });
    expect(await sentence("wh-1")).toHaveTextContent(t("admin.bookingsReceived.externalCode", { code: "IW-9" }));
  });
});
