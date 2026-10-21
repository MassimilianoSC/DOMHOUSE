import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { t } from "@/i18n";
import { useApartmentStore } from "@/store/apartmentStore";
import SummariesPage, { weekRange } from "./SummariesPage";

// «Riepiloghi» (D-150): the weeks from the BFF (routes #36 and #37), the server's sentences as they are, and the
// comparison of consumption at equal occupancy behind them.
const NOW = new Date("2026-10-21T10:00:00Z");
const TZ = "Europe/Rome";

const W42 = { week: "2026-W42", from: "2026-10-11T22:00:00.000Z", to: "2026-10-18T22:00:00.000Z", notable: true, items: 5 };
const W41 = { week: "2026-W41", from: "2026-10-04T22:00:00.000Z", to: "2026-10-11T22:00:00.000Z", notable: false, items: 0 };
const W40 = { week: "2026-W40", from: "2026-09-27T22:00:00.000Z", to: "2026-10-04T22:00:00.000Z", notable: true, items: 1 };

const ITEMS = [
  "Consumi alti per notte con ospiti: 16 kWh contro una mediana di 10 kWh nelle 4 settimane prima.",
  "Misuratore clima: consumi alti per notte con ospiti, 8 kWh contro 5 kWh.",
  "Presa camera è offline da più di 24 ore.",
  "Approvazione scaduta senza risposta: Spegnere la caldaia.",
  "Finestra camera aperta 3 volte con il clima spento dalla regola.",
];

const FULL = {
  apartment_id: "apt-001", week: "2026-W42", from: W42.from, to: W42.to, generated_at: "2026-10-19T06:05:00.000Z",
  energy: {
    available: true,
    occupied: { nights: 3, kwh_per_night: 16.0, median_before: 10.0, status: "anomalous" },
    vacant: { nights: 4, kwh_per_night: 2.0, median_before: 2.0, status: "normal" },
    devices: [{
      device_id: "m1", label: "Misuratore clima",
      occupied: { nights: 1, kwh_per_night: 8.0, median_before: null, status: "not_comparable" },
      vacant: { nights: 0, kwh_per_night: null, median_before: 1.0, status: "no_nights" },
    }],
  },
  offline: { now: [], episodes: [] }, approvals_expired: [], windows: [],
  items: ITEMS, notable: true,
};

const s = vi.hoisted(() => ({ list: [] as unknown[], weeks: {} as Record<string, unknown>, calls: [] as string[] }));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  useApartmentStore.getState().reset("apt-001");
  s.list = [W42, W41, W40];
  s.weeks = { "2026-W42": FULL };
  s.calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const path = new URL(url).pathname;
    s.calls.push(path);
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    if (path === "/app/apartments/apt-001/summaries") return json(s.list);
    const week = path.match(/^\/app\/apartments\/apt-001\/summaries\/(.+)$/)?.[1];
    if (week) return s.weeks[week] ? json(s.weeks[week]) : json({ error: "not_found", message: "Riepilogo inesistente" }, 404);
    return json({ error: "unexpected", message: path }, 500);
  }));
});

afterEach(() => {
  vi.useRealTimers();
});

function open(path: string) {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/a/:aptId/riepiloghi" element={<SummariesPage />} />
          <Route path="/a/:aptId/riepiloghi/:week" element={<SummariesPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Riepiloghi: l'elenco delle settimane", () => {
  it("dalla più recente: periodo in ora locale, quante segnalazioni o «Nessuna novità»", async () => {
    open("/a/apt-001/riepiloghi");
    const list = await screen.findByTestId("summaries-list");
    expect(within(list).getAllByRole("link").map((a) => a.getAttribute("data-testid"))).toEqual(["summary-week-2026-W42", "summary-week-2026-W41", "summary-week-2026-W40"]);
    expect(screen.getByTestId("summary-week-2026-W42")).toHaveTextContent("Settimana dal 12 al 18 ottobre");
    expect(screen.getByTestId("summary-week-2026-W42-count")).toHaveTextContent("5 segnalazioni");
    expect(screen.getByTestId("summary-week-2026-W41-count")).toHaveTextContent("Nessuna novità");
    expect(screen.getByTestId("summary-week-2026-W40-count")).toHaveTextContent("1 segnalazione");
    expect(screen.getByTestId("summary-week-2026-W40")).toHaveTextContent("Settimana dal 28 settembre al 4 ottobre");
  });

  it("nessun riepilogo ancora: lo dice", async () => {
    s.list = [];
    open("/a/apt-001/riepiloghi");
    expect(await screen.findByTestId("summaries-empty")).toHaveTextContent(t("summaries.empty"));
  });

  it("un clic su una settimana apre il suo riepilogo", async () => {
    open("/a/apt-001/riepiloghi");
    const week = await screen.findByTestId("summary-week-2026-W42");
    await act(async () => {
      fireEvent.click(week);
    });
    expect(await screen.findByTestId("summary-items")).toBeInTheDocument();
    expect(s.calls).toContain("/app/apartments/apt-001/summaries/2026-W42");
  });
});

describe("Riepiloghi: la settimana (il link del push)", () => {
  it("le frasi del server così come sono, in ordine, con periodo e ora del calcolo", async () => {
    open("/a/apt-001/riepiloghi/2026-W42");
    await screen.findByTestId("summary-items");
    expect(screen.getAllByTestId("summary-item").map((li) => li.textContent)).toEqual(ITEMS);
    expect(screen.getByTestId("summary-header")).toHaveTextContent("Settimana dal 12 al 18 ottobre");
    expect(screen.getByTestId("summary-back")).toHaveAttribute("href", "/a/apt-001/riepiloghi");
  });

  it("consumi a parità di occupazione: notti, kWh per notte, mediana prima e stato", async () => {
    open("/a/apt-001/riepiloghi/2026-W42");
    const occupied = await screen.findByTestId("summary-energy-occupied");
    expect(occupied).toHaveTextContent("Notti con ospiti");
    expect(occupied).toHaveTextContent("3 notti · 16 kWh per notte · mediana prima 10 kWh");
    expect(occupied).toHaveTextContent("Alto");
    expect(screen.getByTestId("summary-energy-vacant")).toHaveTextContent("4 notti · 2 kWh per notte · mediana prima 2 kWh");
    expect(screen.getByTestId("summary-energy-vacant")).toHaveTextContent("Nella norma");
    // per dispositivo: confronto non disponibile (mai un allarme, niente mediana) e nessuna notte di quel tipo
    expect(screen.getByTestId("summary-device-m1")).toHaveTextContent("Misuratore clima");
    const nc = screen.getByTestId("summary-device-m1-occupied");
    expect(nc).toHaveTextContent("1 notte · 8 kWh per notte");
    expect(nc).not.toHaveTextContent("mediana");
    expect(nc).toHaveTextContent("Confronto non disponibile");
    expect(screen.getByTestId("summary-device-m1-vacant")).toHaveTextContent("nessuna notte di questo tipo nella settimana");
    expect(screen.getByTestId("summary-device-m1-vacant")).toHaveTextContent("Nessuna notte");
  });

  it("settimana senza novità: lo dice, e i consumi restano visibili", async () => {
    s.weeks = { "2026-W41": { ...FULL, week: "2026-W41", from: W41.from, to: W41.to, items: [], notable: false } };
    open("/a/apt-001/riepiloghi/2026-W41");
    expect(await screen.findByTestId("summary-no-news")).toHaveTextContent("Settimana senza novità");
    expect(screen.queryAllByTestId("summary-item")).toHaveLength(0);
    expect(screen.getByTestId("summary-energy")).toBeInTheDocument();
  });

  it("dati insufficienti (i dimostrativi all'inizio): la frase del server così com'è", async () => {
    const reason = "dati insufficienti: servono 5 settimane di consumi veri, disponibili dal 01/10/2026";
    s.weeks = { "2026-W42": { ...FULL, energy: { available: false, since: "2026-09-30T22:00:00.000Z", reason } } };
    open("/a/apt-001/riepiloghi/2026-W42");
    expect(await screen.findByTestId("summary-energy-unavailable")).toHaveTextContent(reason);
    expect(screen.queryByTestId("summary-energy-occupied")).toBeNull();
  });

  it("settimana inesistente: il messaggio del server", async () => {
    open("/a/apt-001/riepiloghi/2025-W01");
    expect(await screen.findByTestId("summary-error")).toHaveTextContent("Riepilogo inesistente");
  });
});

describe("weekRange", () => {
  it("lunedì-domenica nel fuso dell'appartamento, l'anno solo se diverso dal corrente", () => {
    expect(weekRange(W42.from, W42.to, TZ, NOW)).toBe("dal 12 al 18 ottobre");
    expect(weekRange(W40.from, W40.to, TZ, NOW)).toBe("dal 28 settembre al 4 ottobre");
    expect(weekRange("2025-12-28T23:00:00.000Z", "2026-01-04T23:00:00.000Z", TZ, NOW)).toBe("dal 29 dicembre 2025 al 4 gennaio");
  });
});
