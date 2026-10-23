import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { t } from "@/i18n";
import SchedulePage from "./SchedulePage";

// Programmazione (design lot 2): one list with rows, the time in a fixed column, the booking code only in the tooltip,
// the history with a normal title and «Ultimi 7 giorni» under it.
const item = (id: string, status: string, run_at: string, booking_id: string | null = null) => ({
  schedule_id: id,
  run_at,
  status,
  kind: "prearrival",
  source: booking_id ? "booking" : "manual",
  booking_id,
  action: { type: "set_mode", mode: "comfort" },
});

vi.mock("@/api/instance", () => ({
  instanceApi: () => ({
    listSchedule: async () => ({
      items: [
        item("s-1", "planned", "2026-10-26T13:00:00Z", "bk-90210"),
        item("s-2", "done", "2026-10-20T13:00:00Z"),
      ],
    }),
  }),
}));
vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: true, isAdmin: true }) }));

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/a/apt-001/programmazione"]}>
        <Routes>
          <Route path="/a/:aptId/programmazione" element={<SchedulePage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Programmazione: un elenco a righe (design, lotto 2)", () => {
  it("le azioni in programma in un solo elenco; il codice della prenotazione solo al passaggio", async () => {
    open();
    const list = await screen.findByTestId("schedule-planned-list");
    const row = within(list).getByTestId("schedule-item-s-1");
    expect(row).not.toHaveTextContent("bk-90210");
    expect(row.querySelector('[title="bk-90210"]')).not.toBeNull();
    expect(within(row).getByTestId("schedule-cancel-btn-s-1")).toBeInTheDocument();
  });

  it("lo storico ha un titolo normale e «Ultimi 7 giorni» sotto, senza pulsanti", async () => {
    open();
    const history = await screen.findByTestId("schedule-history-list");
    expect(screen.getByRole("heading", { name: t("schedule.history") })).not.toHaveClass("text-muted-foreground");
    expect(screen.getByText(t("schedule.historyHint"))).toBeInTheDocument();
    expect(within(history).queryByTestId("schedule-cancel-btn-s-2")).not.toBeInTheDocument();
  });
});
