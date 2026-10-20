import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { TooltipProvider } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { recentMonths } from "@/lib/energyExport";
import { DEFAULT_TZ } from "@/lib/format";
import EnergyPage from "./EnergyPage";

// «Scarica Excel» (P-52, D-92): the monthly report with the month chosen, and one button per stay where stays show.
const s = vi.hoisted(() => ({ download: vi.fn(async (..._args: unknown[]) => "consumi.xlsx") }));

vi.mock("@/lib/energyExport", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/energyExport")>()), downloadEnergyReport: s.download }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getEnergy: async () => ({ total_kwh: 5, avoided_hvac_hours: null, series: [], by_device: [] }) }) }));
vi.mock("@/hooks/useStays", () => ({
  useCurrentStay: () => ({
    current: { apartment_id: "apt-001", booking_id: "RES-2", checkin_at: "2026-10-14T15:00:00Z", checkout_at: "2026-10-18T10:00:00Z", guests: 2, status: "checked_in" },
    previous: { apartment_id: "apt-001", booking_id: "RES-1", checkin_at: "2026-10-01T15:00:00Z", checkout_at: "2026-10-05T10:00:00Z", guests: 3, status: "checked_out" },
    loading: false,
  }),
  usePreviousStayEnergy: () => ({ data: { total_kwh: 4 } }),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

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

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe("Consumi: rendiconto in Excel", () => {
  it("mese: si parte dal mese in corso, se ne sceglie un altro e si scarica quello", async () => {
    const months = recentMonths(DEFAULT_TZ);
    open();
    const select = screen.getByTestId("energy-export-month") as HTMLSelectElement;
    expect(select.value).toBe(months[0]);
    expect(select.options).toHaveLength(12);
    fireEvent.change(select, { target: { value: months[1] } });
    await click(screen.getByTestId("energy-export-btn"));
    expect(s.download).toHaveBeenCalledWith("apt-001", { month: months[1] }, expect.any(String));
  });

  it("soggiorno in corso e precedente: ognuno con il suo «Excel del soggiorno»", async () => {
    open();
    await click(screen.getByTestId("energy-period-stay"));
    await click(await screen.findByTestId("energy-export-stay"));
    expect(s.download).toHaveBeenLastCalledWith("apt-001", { booking_id: "RES-2" }, expect.any(String));
    await click(await screen.findByTestId("energy-export-previous-stay"));
    expect(s.download).toHaveBeenLastCalledWith("apt-001", { booking_id: "RES-1" }, expect.any(String));
    expect(screen.getByTestId("energy-export-stay")).toHaveTextContent(t("energy.exportStay"));
  });

  it("rifiuto del server (funzione non attiva, motore irraggiungibile): il suo messaggio", async () => {
    s.download.mockRejectedValueOnce(new ApiError(502, "instance_unreachable", "Istanza non raggiungibile", "c-1"));
    open();
    await click(screen.getByTestId("energy-export-btn"));
    expect(toast.error).toHaveBeenCalledWith("Istanza non raggiungibile", expect.anything());
  });
});
