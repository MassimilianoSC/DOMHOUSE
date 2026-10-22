import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { t } from "@/i18n";
import AssistantPage from "./AssistantPage";

// P-75: after one's own «Sì» the chat says what the click did, also when it is read again («Approvata da te alle
// 12:40», never «Già decisa»); «Già decisa» only when someone else decided; the badge of the answer follows the
// decision instead of staying «richiede approvazione».
const CID = "6b7d0c1e-1f3a-4a1e-8e3f-0c2d9a7b5e44";
const ASK = {
  ask_id: "ask-0007", status: "needs_approval", text: "spegni il clima", correlation_id: CID, approval_id: "apr-0012", actions: [],
  answer: "Spengo climatizzatore soggiorno con ospiti presenti? Rispondi Sì o No qui sotto, oppure dalla pagina Approvazioni.",
};
const approval = (status: string, decided_by: string | null = null) => ({
  approval_id: "apr-0012", status, description: "Spegnere climatizzatore soggiorno", correlation_id: CID, source: "assistant", reason: "ospiti presenti",
  created_at: "2026-10-22T10:12:00.000Z", expires_at: "2026-10-22T10:42:00.000Z", expires_action: "reject",
  decided_by, decided_at: decided_by ? "2026-10-22T10:40:00.000Z" : null,
  proposed_action: { type: "command", device_id: "dev-clima-soggiorno", capability: "climate", action: "turn_off" },
});

const s = vi.hoisted(() => ({ lists: [] as unknown[][], decide: vi.fn() }));

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: true }), useAuth: () => ({ me: { user: { email: "Anna@fs.it" } } }) }));
vi.mock("@/api/instance", () => ({
  instanceApi: () => ({
    listApprovals: vi.fn(async () => ({ items: s.lists.length > 1 ? s.lists.shift() : s.lists[0] })),
    decideApproval: s.decide,
    ask: vi.fn(),
    getAsk: vi.fn(),
  }),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/a/apt-001/assistente"]}>
        <Routes>
          <Route path="/a/:aptId/assistente" element={<AssistantPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  sessionStorage.setItem("assistant.apt-001", JSON.stringify([ASK]));
  Element.prototype.scrollIntoView = vi.fn();
  s.decide.mockImplementation(async () => approval("approved", "anna@fs.it"));
});

describe("Assistente: dopo il proprio «Sì» (P-75)", () => {
  it("resta «Approvato: il comando parte…», mai «Già decisa», e il badge diventa «approvata»", async () => {
    s.lists = [[approval("pending")], [approval("approved", "anna@fs.it")]];
    open();
    expect(screen.getByTestId("ask-status-ask-0007")).toHaveTextContent(t("assistant.status.needs_approval"));
    const yes = await screen.findByTestId("ask-confirm-yes-ask-0007");
    await act(async () => {
      fireEvent.click(yes);
    });
    await waitFor(() => expect(screen.getByTestId("ask-status-ask-0007")).toHaveTextContent("approvata"));
    expect(screen.getByTestId("ask-confirm-result-ask-0007")).toHaveTextContent("Approvato: il comando parte, l'esito arriva nell'app");
    expect(screen.queryByTestId("ask-confirm-closed-ask-0007")).toBeNull();
    expect(screen.getByTestId("ask-message-ask-0007")).not.toHaveTextContent("Già decisa");
    expect(screen.getByTestId("ask-message-ask-0007")).not.toHaveTextContent(t("assistant.status.needs_approval"));
  });

  it("chat riletta (la scheda riaperta): «Approvata da te alle 12:40», anche con l'email scritta diversa", async () => {
    s.lists = [[approval("approved", "anna@fs.it")]];
    open();
    expect(await screen.findByTestId("ask-confirm-closed-ask-0007")).toHaveTextContent("Approvata da te alle 12:40");
    await waitFor(() => expect(screen.getByTestId("ask-status-ask-0007")).toHaveTextContent("approvata"));
  });

  it("respinta da te: «Respinta da te alle 12:40», badge «respinta»", async () => {
    s.lists = [[approval("rejected", "anna@fs.it")]];
    open();
    expect(await screen.findByTestId("ask-confirm-closed-ask-0007")).toHaveTextContent("Respinta da te alle 12:40");
    await waitFor(() => expect(screen.getByTestId("ask-status-ask-0007")).toHaveTextContent("respinta"));
  });

  it("decisa da un'altra persona: «Già decisa: approvata»", async () => {
    s.lists = [[approval("approved", "bruno@fs.it")]];
    open();
    expect(await screen.findByTestId("ask-confirm-closed-ask-0007")).toHaveTextContent("Già decisa: approvata");
  });

  it("scaduta: «Scaduta» e badge «scaduta»", async () => {
    s.lists = [[approval("expired")]];
    open();
    expect(await screen.findByTestId("ask-confirm-closed-ask-0007")).toHaveTextContent("Scaduta");
    await waitFor(() => expect(screen.getByTestId("ask-status-ask-0007")).toHaveTextContent("scaduta"));
  });

  it("ancora da decidere: il badge resta «richiede approvazione»", async () => {
    s.lists = [[approval("pending")]];
    open();
    await screen.findByTestId("ask-confirm-yes-ask-0007");
    expect(screen.getByTestId("ask-status-ask-0007")).toHaveTextContent(t("assistant.status.needs_approval"));
  });
});
