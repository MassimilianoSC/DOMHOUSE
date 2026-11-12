import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ApprovalsPage from "./ApprovalsPage";

// P-83, D70: an approval past its expiry is still «pending» until the engine's next round (1–2 s with the stream, up to
// 30 s without). Meanwhile its card said «scaduta» with «Approva» and «Rifiuta» still active.
const APPROVAL = {
  approval_id: "apr-1", status: "pending", description: "Spegnere il clima", correlation_id: "c-1", source: "rule", reason: "casa vuota",
  created_at: "2026-11-11T10:00:00.000Z", expires_at: "2026-11-11T10:30:00.000Z", expires_action: "approve",
  decided_by: null, decided_at: null, proposed_action: { type: "apartment_mode", mode: "empty" },
};

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: true }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ listApprovals: async () => ({ items: [APPROVAL] }), decideApproval: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));

async function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/a/apt-001/approvazioni"]}>
        <Routes>
          <Route path="/a/:aptId/approvazioni" element={<ApprovalsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByTestId("approval-card-apr-1");
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date", "setInterval", "clearInterval"], shouldAdvanceTime: true });
});
afterEach(() => vi.useRealTimers());

describe("Approvazioni: scadute, ancora «in attesa» sul motore (P-83, D70)", () => {
  it("prima della scadenza i pulsanti sono attivi; passata la scadenza si disattivano da soli", async () => {
    vi.setSystemTime(new Date("2026-11-11T10:29:58.000Z"));
    await open();
    expect(screen.getByTestId("approve-action-btn-apr-1")).not.toBeDisabled();
    await act(() => vi.advanceTimersByTimeAsync(3000));
    expect(screen.getByTestId("approve-action-btn-apr-1")).toBeDisabled();
    expect(screen.getByTestId("reject-action-btn-apr-1")).toBeDisabled();
  });

  it("aperta già oltre la scadenza: pulsanti disattivati", async () => {
    vi.setSystemTime(new Date("2026-11-11T10:31:00.000Z"));
    await open();
    expect(screen.getByTestId("approve-action-btn-apr-1")).toBeDisabled();
    expect(screen.getByTestId("reject-action-btn-apr-1")).toBeDisabled();
  });
});
