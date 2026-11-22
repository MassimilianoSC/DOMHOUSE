import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { ApiError } from "@/api/bff";
import type { CapienzaView } from "@/api/platform";
import { CapacityLine } from "./CapacityLine";

// A7 (docs/proposta-a7.md §2 n. 5, §3; answers 1201, 1203): the free places of the VM in «Nuovo appartamento», from the
// last reading the server keeps; «Aggiorna» sends a new reading, read again every 4 s while it is «inviato».

const s = vi.hoisted(() => ({ capacity: vi.fn(), refreshCapacity: vi.fn() }));
vi.mock("@/api/platform", () => ({ platformApi: { capacity: s.capacity, refreshCapacity: s.refreshCapacity } }));

const OP = "3f9c2a71-0000-4000-8000-000000000007";
const reading = (over: object = {}) => ({
  ambiente: "staging", letta_at: "2026-11-20T14:58:00Z", vecchia: false, posti_liberi: 2, motivo: null,
  motori_ambiente: 2, massimo_motori: 4, mem_available_mb: 900, tetto_nuovo_mb: 120, somma_tetti_mb: 240, budget_mb: 500, ...over,
});
const view = (over: Partial<CapienzaView> = {}): CapienzaView => ({ capienza: reading(), aggiornamento: null, aggiornabile_dal: null, ...over });
const sent = (creato_at = "2026-11-20T15:00:00Z") => ({ op_id: OP, stato: "inviato" as const, codice: null, messaggio: null, creato_at });

const box = () => screen.queryByTestId("new-apt-capacity");
const text = () => screen.getByTestId("new-apt-capacity-text");
const refresh = () => screen.getByTestId("new-apt-capacity-refresh");
// the time, then the answers and React Query's notifications (scheduled with setTimeout 0): a few short steps after
const wait = (ms: number) => act(async () => {
  await vi.advanceTimersByTimeAsync(ms);
  for (let i = 0; i < 5; i++) await vi.advanceTimersByTimeAsync(1);
});

async function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CapacityLine />
    </QueryClientProvider>,
  );
  await wait(0);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
  vi.setSystemTime(new Date("2026-11-20T15:00:00Z")); // 16:00 a Roma
  s.capacity.mockResolvedValue(view());
});

afterEach(() => {
  vi.useRealTimers();
});

describe("i tre casi della riga", () => {
  it("con posti: quanti, con l'ora della lettura, e «Aggiorna»", async () => {
    await open();
    expect(box()).toHaveAttribute("data-kind", "places");
    expect(text()).toHaveTextContent("Posti liberi nello staging: 2 (letto alle 15:58)");
    expect(refresh()).toBeEnabled();
    expect(refresh()).toHaveTextContent("Aggiorna");
    // reading the form sends no order
    expect(s.refreshCapacity).not.toHaveBeenCalled();
  });

  it("senza lettura: «Capienza non ancora letta» con «Aggiorna»", async () => {
    s.capacity.mockResolvedValue(view({ capienza: null }));
    await open();
    expect(box()).toHaveAttribute("data-kind", "unread");
    expect(text()).toHaveTextContent("Capienza non ancora letta");
    expect(refresh()).toBeEnabled();
  });

  it("zero posti: la frase decisa, in giallo", async () => {
    s.capacity.mockResolvedValue(view({ capienza: reading({ posti_liberi: 0, motivo: "staging_pieno" }) }));
    await open();
    expect(box()).toHaveAttribute("data-kind", "zero");
    expect(text()).toHaveTextContent("Nessun posto libero sulla macchina virtuale: per ora non si creano appartamenti. Scrivi all'assistenza HQE. (letto alle 15:58)");
  });

  it("dove la creazione non è disponibile (503): nessuna riga, nessun errore", async () => {
    s.capacity.mockRejectedValue(new ApiError(503, "agent_not_configured", "La creazione degli appartamenti non è disponibile in questo ambiente", "c-1"));
    await open();
    expect(box()).toBeNull();
    expect(screen.queryByText(/non è disponibile/)).toBeNull();
  });

  it("lettura che invecchia a modulo aperto: dopo 10 minuti dice quanto tempo fa", async () => {
    await open();
    await wait(11 * 60_000);
    expect(text()).toHaveTextContent("Posti liberi nello staging: 2 (letto 13 minuti fa)");
  });
});

describe("«Aggiorna»", () => {
  it("manda l'ordine, dice «Lettura in corso…», rilegge ogni 4 s e si ferma con la lettura nuova", async () => {
    s.refreshCapacity.mockResolvedValue(view({ aggiornamento: sent(), aggiornabile_dal: "2026-11-20T15:00:30Z" }));
    await open();
    s.capacity.mockClear();
    s.capacity.mockResolvedValue(view({ aggiornamento: sent(), aggiornabile_dal: "2026-11-20T15:00:30Z" }));
    await act(async () => {
      fireEvent.click(refresh());
    });
    expect(s.refreshCapacity).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("new-apt-capacity-running")).toHaveTextContent("Lettura in corso…");
    expect(refresh()).toBeDisabled();
    // the last good reading stays in sight
    expect(text()).toHaveTextContent("Posti liberi nello staging: 2");
    await wait(4_000);
    expect(s.capacity).toHaveBeenCalledTimes(1);
    s.capacity.mockResolvedValue(view({ capienza: reading({ letta_at: "2026-11-20T15:00:07Z", posti_liberi: 1 }), aggiornamento: { ...sent(), stato: "riuscito" } }));
    await wait(4_000);
    expect(s.capacity).toHaveBeenCalledTimes(2);
    expect(screen.queryByTestId("new-apt-capacity-running")).toBeNull();
    expect(text()).toHaveTextContent("Posti liberi nello staging: 1 (letto alle 16:00)");
    expect(refresh()).toBeEnabled();
    await wait(60_000);
    expect(s.capacity).toHaveBeenCalledTimes(2);
  });

  it("lettura ancora in corso dopo i 30 s: «Aggiorna» resta spento, senza la spiegazione dei 30 s", async () => {
    s.capacity.mockResolvedValue(view({ aggiornamento: sent("2026-11-20T14:59:00Z"), aggiornabile_dal: null }));
    await open();
    expect(screen.getByTestId("new-apt-capacity-running")).toBeInTheDocument();
    expect(refresh()).toBeDisabled();
    expect(screen.getByTestId("new-apt-capacity-refresh-wrap")).not.toHaveAttribute("title");
  });

  it("spento per 30 s dopo l'ultimo, con la spiegazione; poi si riaccende da solo", async () => {
    s.capacity.mockResolvedValue(view({ aggiornabile_dal: "2026-11-20T15:00:20Z" }));
    await open();
    expect(refresh()).toBeDisabled();
    expect(screen.getByTestId("new-apt-capacity-refresh-wrap")).toHaveAttribute("title", "Di nuovo fra pochi secondi");
    await wait(21_000);
    expect(refresh()).toBeEnabled();
    expect(screen.getByTestId("new-apt-capacity-refresh-wrap")).not.toHaveAttribute("title");
  });

  it("429: resta spento fino all'ora che dice il server", async () => {
    s.refreshCapacity.mockRejectedValue(new ApiError(429, "rate_limited", "La capienza è appena stata chiesta: riprova fra qualche secondo.", "c-1", { riprova_dal: "2026-11-20T15:00:25Z" }));
    await open();
    await act(async () => {
      fireEvent.click(refresh());
    });
    expect(refresh()).toBeDisabled();
    expect(screen.queryByTestId("new-apt-capacity-failed")).toBeNull();
    await wait(26_000);
    expect(refresh()).toBeEnabled();
  });

  it("502: «Lettura non riuscita» con il messaggio e l'ID richiesta copiabile; sotto resta l'ultima lettura buona", async () => {
    s.refreshCapacity.mockRejectedValue(new ApiError(502, "agent_publish_failed", "Ordine non inviato all'agente", "c-2", { op: { op_id: OP } }));
    await open();
    await act(async () => {
      fireEvent.click(refresh());
    });
    expect(screen.getByTestId("new-apt-capacity-failed")).toHaveTextContent("Lettura non riuscita: Ordine non inviato all'agente");
    expect(screen.getByTestId("new-apt-capacity-failed-id")).toHaveTextContent(OP.slice(0, 8));
    expect(text()).toHaveTextContent("Posti liberi nello staging: 2 (letto alle 15:58)");
    expect(refresh()).toBeEnabled();
  });

  it("l'ordine non riuscito che il server ricorda, più nuovo dell'ultima lettura: si dice", async () => {
    s.capacity.mockResolvedValue(view({ aggiornamento: { op_id: OP, stato: "fallito", codice: "tempo_scaduto", messaggio: "L'agente non ha risposto", creato_at: "2026-11-20T14:59:00Z" } }));
    await open();
    expect(screen.getByTestId("new-apt-capacity-failed")).toHaveTextContent("Lettura non riuscita: L'agente non ha risposto");
    expect(text()).toHaveTextContent("Posti liberi nello staging: 2");
  });

  it("un ordine rimasto «inviato» da più di 20 minuti: non si rilegge più, «non riuscita»", async () => {
    // the last good reading is older than the order: it is the order that went unanswered
    s.capacity.mockResolvedValue(view({ capienza: reading({ letta_at: "2026-11-20T14:30:00Z" }), aggiornamento: sent("2026-11-20T14:39:00Z") }));
    await open();
    expect(screen.getByTestId("new-apt-capacity-failed")).toHaveTextContent("nessuna risposta dalla macchina virtuale in 20 minuti");
    s.capacity.mockClear();
    await wait(60_000);
    expect(s.capacity).not.toHaveBeenCalled();
  });
});
