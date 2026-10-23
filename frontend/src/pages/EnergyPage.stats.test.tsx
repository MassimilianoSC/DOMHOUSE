import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/primitives";
import { t } from "@/i18n";
import EnergyPage from "./EnergyPage";

// Design lot 2: the indicators in one strip; «Ore di clima evitate» only when computed; the peak of the period;
// the comparison with the previous stay as one line, in red only when it is worse.
const s = vi.hoisted(() => ({
  avoided: null as number | null,
  series: [
    { ts: "2026-10-20T00:00:00Z", kwh: 1.5 },
    { ts: "2026-10-21T00:00:00Z", kwh: 4.25 },
    { ts: "2026-10-22T00:00:00Z", kwh: 2 },
  ],
}));

vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getEnergy: async () => ({ total_kwh: 7.75, avoided_hvac_hours: s.avoided, series: s.series, by_device: [] }) }) }));
vi.mock("@/hooks/useFeatures", () => ({ useApartmentSummary: () => ({ data: undefined }) }));
vi.mock("@/hooks/useStays", () => ({
  useCurrentStay: () => ({
    current: { apartment_id: "apt-001", booking_id: "RES-2", checkin_at: "2026-10-14T15:00:00Z", checkout_at: "2026-10-18T10:00:00Z", guests: 2, status: "checked_in" },
    previous: { apartment_id: "apt-001", booking_id: "RES-1", checkin_at: "2026-10-01T15:00:00Z", checkout_at: "2026-10-05T10:00:00Z", guests: 3, status: "checked_out" },
    loading: false,
  }),
  usePreviousStayEnergy: () => ({ data: { total_kwh: 5 } }),
}));

function open() {
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
}

// recharts' ResponsiveContainer needs ResizeObserver, which jsdom does not have
class NoResize {
  observe() {}
  unobserve() {}
  disconnect() {}
}
beforeEach(() => {
  vi.stubGlobal("ResizeObserver", NoResize);
  s.avoided = null;
});

describe("Consumi: striscia degli indicatori (design, lotto 2)", () => {
  it("totale e picco; «Ore di clima evitate» non c'è finché il motore non le calcola", async () => {
    open();
    expect(await screen.findByTestId("energy-total")).toHaveTextContent("7,75");
    expect(screen.getByTestId("energy-peak")).toHaveTextContent("4,25");
    expect(screen.getByTestId("energy-peak")).toHaveTextContent(t("energy.peakHour"));
    expect(screen.queryByTestId("energy-avoided")).not.toBeInTheDocument();
  });

  it("con le ore calcolate compare la terza casella", async () => {
    s.avoided = 6;
    open();
    expect(await screen.findByTestId("energy-avoided")).toHaveTextContent(t("energy.avoided"));
  });

  it("soggiorno in corso: il confronto è una riga, in rosso solo se peggiora", async () => {
    open();
    await screen.findByTestId("energy-total");
    await act(async () => {
      fireEvent.click(screen.getByTestId("energy-period-stay"));
    });
    const delta = await screen.findByTestId("energy-stay-delta");
    expect(delta).toHaveTextContent("+55%");
    expect(delta).toHaveClass("text-negative-fg");
    expect(screen.getByTestId("energy-stay-comparison")).toHaveTextContent(t("energy.guests", { count: 3 }));
    expect(screen.getByTestId("energy-export-previous-stay")).toHaveTextContent(t("energy.exportPreviousStay"));
  });
});
