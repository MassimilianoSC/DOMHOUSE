import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { t } from "@/i18n";
import DecisionsPage from "./DecisionsPage";

// Decisioni page with the search on the whole log (P-32): status line, "Cerca più indietro", pasted request ID, period.
type Q = { cursor?: string; correlation_id?: string; from?: string; limit?: number };
const s = vi.hoisted(() => ({ calls: [] as Q[] }));

const dec = (n: number, reasoning: string) => ({ decision_id: `d-${n}`, ts: new Date(Date.UTC(2026, 9, 16, 12) - n * 60_000).toISOString(), actor: "brain", target: { type: "apartment" }, action: n === 0 ? "booking_cancel_reset" : "mode", old_value: null, new_value: null, reasoning, outcome: n === 2 ? "failed" : "applied", correlation_id: n === 1500 ? "3f2a9c1e-7b4d-4e8a-9c0f-1a2b3c4d5e6f" : `c-${n}`, command_id: n === 2 ? "cmd-2222" : null, approval_id: null });

vi.mock("@/api/instance", () => ({
  instanceApi: () => ({
    getRules: async () => ({ rules: [] }),
    listDecisions: async (q: Q) => {
      s.calls.push(q);
      // 3,000 decisions; only n = 1500 talks about a "finestra".
      const all = Array.from({ length: 3000 }, (_, n) => dec(n, n === 1500 ? "Finestra aperta, clima spento" : "altro"));
      if (q.correlation_id) return { items: all.filter((d) => d.correlation_id === q.correlation_id), next_cursor: null };
      const start = q.cursor ? Number(q.cursor) : 0;
      const items = all.slice(start, start + (q.limit ?? 30));
      return { items, next_cursor: start + items.length < all.length ? String(start + items.length) : null };
    },
  }),
}));

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/a/apt-001/decisioni"]}>
        <Routes>
          <Route path="/a/:aptId/decisioni" element={<DecisionsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const status = () => screen.getByTestId("decisions-search-status");

beforeEach(() => {
  s.calls = [];
});

describe("Decisioni: ricerca in tutto lo storico", () => {
  it("una parola che non è nelle prime righe: il primo lotto dice fin dove ha cercato, «Cerca più indietro» la trova", async () => {
    open();
    await screen.findByTestId("decisions-list");
    fireEvent.change(screen.getByTestId("decisions-search-input"), { target: { value: "finestra" } });
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "ready"), { timeout: 3000 });
    expect(status()).toHaveTextContent("Risultati: 0");
    expect(status()).toHaveTextContent("1000 decisioni esaminate");
    expect(screen.queryByTestId("decision-row-d-1500")).not.toBeInTheDocument();
    expect(screen.queryByTestId("decisions-load-more-btn")).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByTestId("decisions-search-more-btn"));
    });
    await waitFor(() => expect(screen.getByTestId("decision-row-d-1500")).toBeInTheDocument(), { timeout: 3000 });
    await waitFor(() => expect(status()).toHaveTextContent("Risultati: 1"));
    expect(s.calls.filter((c) => c.limit === 200).map((c) => c.cursor)).toEqual([undefined, "200", "400", "600", "800", "1000", "1200", "1400", "1600", "1800"]);
  });

  it("fine dello storico: «cercato in tutto lo storico disponibile», niente più pulsante", async () => {
    open();
    await screen.findByTestId("decisions-list");
    fireEvent.change(screen.getByTestId("decisions-search-input"), { target: { value: "parola-che-non-esiste" } });
    for (const scanned of [1000, 2000]) {
      await waitFor(() => expect(status()).toHaveTextContent(`(${scanned} decisioni esaminate)`), { timeout: 3000 });
      await act(async () => {
        fireEvent.click(screen.getByTestId("decisions-search-more-btn"));
      });
    }
    await waitFor(() => expect(status()).toHaveTextContent(t("decisions.searchedAll", { found: 0, count: 3000 })), { timeout: 3000 });
    expect(screen.queryByTestId("decisions-search-more-btn")).not.toBeInTheDocument();
  });

  it("ID richiesta incollato: una sola richiesta con il filtro esatto, risultato da tutto lo storico", async () => {
    open();
    await screen.findByTestId("decisions-list");
    s.calls = [];
    fireEvent.change(screen.getByTestId("decisions-search-input"), { target: { value: "3f2a9c1e-7b4d-4e8a-9c0f-1a2b3c4d5e6f" } });
    expect(await screen.findByTestId("decision-row-d-1500", undefined, { timeout: 3000 })).toBeInTheDocument();
    expect(status()).toHaveTextContent(t("decisions.searchCorrelation", { found: 1 }));
    expect(s.calls).toEqual([{ correlation_id: "3f2a9c1e-7b4d-4e8a-9c0f-1a2b3c4d5e6f", limit: 200 }]);
  });

  it("togliendo la parola torna il registro con «Carica altri»", async () => {
    open();
    await screen.findByTestId("decisions-list");
    fireEvent.change(screen.getByTestId("decisions-search-input"), { target: { value: "finestra" } });
    await waitFor(() => expect(status()).toHaveAttribute("data-status", "ready"), { timeout: 3000 });
    fireEvent.change(screen.getByTestId("decisions-search-input"), { target: { value: "" } });
    await waitFor(() => expect(screen.queryByTestId("decisions-search-status")).not.toBeInTheDocument(), { timeout: 3000 });
    expect(screen.getByTestId("decisions-load-more-btn")).toBeInTheDocument();
    expect(screen.getByTestId("decision-row-d-0")).toBeInTheDocument();
  });

  it("Periodo: il registro si richiede al motore con «from»", async () => {
    open();
    await screen.findByTestId("decisions-list");
    s.calls = [];
    fireEvent.change(screen.getByTestId("decisions-period-select"), { target: { value: "7" } });
    await waitFor(() => expect(s.calls.at(-1)?.from).toBeDefined());
    const from = new Date(s.calls.at(-1)!.from!).getTime();
    expect(Math.abs(Date.now() - 7 * 86_400_000 - from)).toBeLessThan(60_000);
    expect(screen.getByTestId("decisions-period-select")).toHaveDisplayValue(t("decisions.period7"));
  });
});

describe("Decisioni: il tipo di azione (D-125)", () => {
  it("azione nota: l'etichetta italiana nel riquadro; azione sconosciuta: il codice", async () => {
    open();
    expect(await screen.findByTestId("decision-action-d-0")).toHaveTextContent(/^Disdetta dopo il pre-arrivo$/);
    expect(screen.getByTestId("decision-action-d-0")).toHaveAttribute("title", "booking_cancel_reset");
    expect(screen.getByTestId("decision-action-d-1")).toHaveTextContent(/^mode$/);
  });
});

describe("Decisioni: la riga (design, lotto 2)", () => {
  it("esito come badge a colore pieno (lotto 34); il codice del comando dietro «Dettagli»", async () => {
    open();
    expect(await screen.findByTestId("decision-outcome-d-1")).toHaveClass("bg-positive-bg");
    expect(screen.getByTestId("decision-outcome-d-2")).toHaveClass("bg-negative-bg");
    expect(screen.getByTestId("decision-row-d-2")).not.toHaveTextContent("cmd-2222");
    expect(screen.queryByTestId("decision-details-toggle-d-1")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("decision-details-toggle-d-2"));
    expect(screen.getByTestId("decision-details-d-2")).toHaveTextContent("cmd-2222");
    expect(screen.getByTestId("decision-correlation-d-2")).toBeInTheDocument();
  });
});
