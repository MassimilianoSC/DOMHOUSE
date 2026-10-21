import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { Apartment } from "@/api/types";
import { TooltipProvider } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { fmtDayMonth } from "@/lib/format";
import { useApartmentStore } from "@/store/apartmentStore";
import EnergyPage from "./EnergyPage";

// D-130: under the chart, since when the server has measured consumption (energy_since of the apartment summary),
// as day and month in the apartment's time zone; nothing while there is no data yet.
const s = vi.hoisted(() => ({ summary: {} as Record<string, unknown> }));

vi.mock("@/hooks/useFeatures", () => ({ useApartmentSummary: () => ({ data: s.summary }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getEnergy: async () => ({ total_kwh: 5, avoided_hvac_hours: null, series: [], by_device: [] }) }) }));
vi.mock("@/hooks/useStays", () => ({ useCurrentStay: () => ({ current: undefined, previous: undefined, loading: false }), usePreviousStayEnergy: () => ({ data: undefined }) }));

const NOW = new Date("2026-10-21T10:00:00Z");

async function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/a/apt-001/consumi"]}>
          <Routes>
            <Route path="/a/:aptId/consumi" element={<EnergyPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
  await screen.findByTestId("energy-chart");
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  useApartmentStore.getState().reset("apt-001");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Consumi: «Consumi disponibili dal …» (D-130)", () => {
  it("con la data: la frase sotto il grafico, giorno e mese in ora locale (mezzanotte di Roma = 23:00 UTC del giorno prima)", async () => {
    s.summary = { energy_since: "2025-12-31T23:00:00Z" };
    await open();
    expect(screen.getByTestId("energy-since")).toHaveTextContent("Consumi disponibili dal 1 gennaio");
    expect(screen.getByTestId("energy-since")).not.toHaveTextContent("2026");
    expect(screen.getByTestId("energy-chart")).toContainElement(screen.getByTestId("energy-since"));
  });

  it("anno diverso da quello corrente: c'è anche l'anno", async () => {
    s.summary = { energy_since: "2025-03-14T09:00:00Z" };
    await open();
    expect(screen.getByTestId("energy-since")).toHaveTextContent(t("energy.since", { date: "14 marzo 2025" }));
  });

  it("il fuso è quello dell'appartamento, non del browser", async () => {
    useApartmentStore.getState().setSnapshot({ apartment: { timezone: "America/New_York" } as unknown as Apartment });
    s.summary = { energy_since: "2026-04-01T02:00:00Z" };
    await open();
    expect(screen.getByTestId("energy-since")).toHaveTextContent("Consumi disponibili dal 31 marzo");
  });

  it("energy_since null (nessun dato ancora): la frase non compare", async () => {
    s.summary = { energy_since: null };
    await open();
    expect(screen.queryByTestId("energy-since")).toBeNull();
  });

  it("server di prima del passo 6, senza il campo: la frase non compare", async () => {
    s.summary = {};
    await open();
    expect(screen.queryByTestId("energy-since")).toBeNull();
  });
});

describe("fmtDayMonth", () => {
  it("giorno e mese nel fuso indicato, l'anno solo se diverso da quello corrente in quel fuso", () => {
    expect(fmtDayMonth("2026-03-31T22:30:00Z", "Europe/Rome", NOW)).toBe("1 aprile");
    expect(fmtDayMonth("2026-03-31T22:30:00Z", "UTC", NOW)).toBe("31 marzo");
    expect(fmtDayMonth("2025-12-31T23:00:00Z", "UTC", NOW)).toBe("31 dicembre 2025");
    expect(fmtDayMonth("2025-12-31T23:00:00Z", "Europe/Rome", NOW)).toBe("1 gennaio");
    expect(fmtDayMonth("2026-12-31T23:30:00Z", "Europe/Rome", NOW)).toBe("1 gennaio 2027");
  });

  it("data assente o illeggibile: stringa vuota", () => {
    expect(fmtDayMonth(null)).toBe("");
    expect(fmtDayMonth(undefined)).toBe("");
    expect(fmtDayMonth("non una data")).toBe("");
  });
});
