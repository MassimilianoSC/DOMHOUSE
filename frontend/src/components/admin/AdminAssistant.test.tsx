import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { AdminAssistant } from "./AdminAssistant";

// Amministrazione › Assistente (decision 120, D-183): questions, timeouts and quick answers per week, for the whole
// organization; a week above 10 % highlighted; two complete weeks in a row above it reopen the choice of the model.
const s = vi.hoisted(() => ({ answer: null as unknown, calls: [] as string[] }));

const week = (n: number, asks: number, timeouts: number, quick = { timeout: timeouts, model_unavailable: 0, monthly_cap: 0, json_invalid: 0 }) => {
  const monday = new Date(Date.UTC(2026, 9, 18, 22) - n * 7 * 86_400_000); // Monday 00:00 in Rome (19 Oct 2026, CEST)
  return { week: `2026-W${43 - n}`, from: monday.toISOString(), to: new Date(monday.getTime() + 7 * 86_400_000).toISOString(), asks, timeouts, twins: 0, quick };
};

beforeEach(() => {
  s.calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const u = new URL(url);
    s.calls.push(u.pathname + u.search);
    return new Response(JSON.stringify(s.answer), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AdminAssistant />
    </QueryClientProvider>,
  );
}

describe("Amministrazione › Assistente (decisione 120)", () => {
  it("le ultime 8 settimane dalla più recente, con domande, timeout, risposte rapide e percentuale", async () => {
    s.answer = { weeks: [week(0, 10, 0), week(1, 40, 2, { timeout: 2, model_unavailable: 0, monthly_cap: 0, json_invalid: 1 })], threshold_percent: 10, over_threshold: false };
    open();
    const row = await screen.findByTestId("admin-assistant-week-2026-W42");
    expect(s.calls).toEqual(["/app/admin/assistant-stats?weeks=8"]);
    expect(row).toHaveTextContent("dal 12 al 18 ottobre");
    expect(row).toHaveTextContent("40");
    expect(row).toHaveTextContent("3"); // quick answers: 2 timeouts + 1 invalid answer
    expect(row).toHaveTextContent("5 %");
    expect(row).toHaveAttribute("data-over", "false");
    expect(screen.getByTestId("admin-assistant-week-2026-W43")).toHaveTextContent("in corso");
    expect(screen.getByTestId("admin-assistant-causes")).toHaveTextContent("tempo scaduto 2 · assistente non raggiungibile 0 · limite mensile 0 · risposta non valida 1");
    expect(screen.queryByTestId("admin-assistant-alert")).toBeNull();
  });

  it("una settimana sopra il 10 %: evidenziata; due di fila (secondo il server): l'avviso sul modello", async () => {
    s.answer = { weeks: [week(0, 5, 0), week(1, 20, 3), week(2, 30, 4)], threshold_percent: 10, over_threshold: true };
    open();
    expect(await screen.findByTestId("admin-assistant-week-2026-W42")).toHaveAttribute("data-over", "true");
    expect(screen.getByTestId("admin-assistant-week-2026-W42")).toHaveTextContent("15 %");
    expect(screen.getByTestId("admin-assistant-week-2026-W43")).toHaveAttribute("data-over", "false");
    expect(screen.getByTestId("admin-assistant-alert")).toHaveTextContent("Timeout oltre il 10 % per due settimane di fila: va riaperta la scelta del modello dell'assistente.");
  });

  it("nessuna domanda nelle settimane mostrate: lo dice, niente tabella", async () => {
    s.answer = { weeks: [week(0, 0, 0), week(1, 0, 0)], threshold_percent: 10, over_threshold: false };
    open();
    expect(await screen.findByTestId("admin-assistant-empty")).toHaveTextContent("Nessuna domanda all'assistente nelle ultime settimane.");
    expect(screen.queryByTestId("admin-assistant-table")).toBeNull();
  });
});
