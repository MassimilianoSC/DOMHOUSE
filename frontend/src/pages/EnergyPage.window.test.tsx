import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/primitives";
import { useApartmentStore } from "@/store/apartmentStore";
import EnergyPage from "./EnergyPage";

// P-83, D22: the page re-reads every minute, but the window from/to was computed once when it opened: two hours later
// «Oggi» still stopped at the opening hour, and after midnight it still showed yesterday. Now every request computes it.
const s = vi.hoisted(() => ({ getEnergy: vi.fn(async (_p: { from: string; to: string; bucket: string }) => ({ total_kwh: 5, avoided_hvac_hours: null, series: [], by_device: [] })) }));

vi.mock("@/hooks/useFeatures", () => ({ useApartmentSummary: () => ({ data: {} }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getEnergy: s.getEnergy }) }));
vi.mock("@/hooks/useStays", () => ({ useCurrentStay: () => ({ current: undefined, previous: undefined, loading: false }), usePreviousStayEnergy: () => ({ data: undefined }) }));

let client: QueryClient;

async function open() {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
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

/** What the minute's re-read (or the return to the window) does: the same query, asked again. */
async function reread() {
  await act(async () => {
    await client.refetchQueries({ queryKey: ["energy"] });
  });
}

const last = () => s.getEnergy.mock.calls.at(-1)![0];

beforeEach(() => {
  s.getEnergy.mockClear();
  vi.useFakeTimers({ toFake: ["Date"] });
  useApartmentStore.getState().reset("apt-001");
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Consumi: la finestra dei dati segue l'orologio (P-83, D22)", () => {
  it("«Oggi» aperta alle 09:05 di Roma: due ore dopo la rilettura arriva fino alle 11:05 passate", async () => {
    vi.setSystemTime(new Date("2026-11-11T08:05:00Z")); // 09:05 a Roma
    await open();
    expect(last().from).toBe("2026-11-10T23:00:00.000Z");
    expect(last().to).toBe("2026-11-11T09:05:00.000Z");
    vi.setSystemTime(new Date("2026-11-11T10:05:00Z"));
    await reread();
    expect(last().to).toBe("2026-11-11T11:05:00.000Z");
    expect(last().from).toBe("2026-11-10T23:00:00.000Z");
  });

  it("dopo mezzanotte «Oggi» è il giorno nuovo", async () => {
    vi.setSystemTime(new Date("2026-11-11T21:00:00Z")); // 22:00 a Roma
    await open();
    vi.setSystemTime(new Date("2026-11-11T23:30:00Z")); // 00:30 del 12 a Roma
    await reread();
    expect(last().from).toBe("2026-11-11T23:00:00.000Z");
    expect(last().to).toBe("2026-11-12T00:30:00.000Z");
  });
});
