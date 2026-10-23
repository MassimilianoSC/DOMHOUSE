import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { t } from "@/i18n";
import AssistantPage from "./AssistantPage";

// Design lot 2: no state for an ordinary answer, what was done in words, the codes behind «Dettagli»; one container
// with the form at its bottom.
const ANSWERED = {
  ask_id: "ask-0001", status: "answered", text: "spegni la presa", correlation_id: "c-0001", approval_id: null,
  actions: [{ type: "command", command_id: "cmd-7f3a9c1e" }], answer: "Spengo la presa della camera.",
};

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: true }), useAuth: () => ({ me: { user: { email: "anna@fs.it" } } }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ ask: vi.fn(), getAsk: vi.fn(), listApprovals: vi.fn(async () => ({ items: [] })) }) }));

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
  sessionStorage.clear();
  sessionStorage.setItem("assistant.apt-001", JSON.stringify([ANSWERED]));
  Element.prototype.scrollIntoView = vi.fn();
});

describe("Assistente: la risposta (design, lotto 2)", () => {
  it("risposta normale: nessun badge di stato, «Comando inviato» a parole, il codice solo in «Dettagli»", () => {
    open();
    expect(screen.queryByTestId("ask-status-ask-0001")).not.toBeInTheDocument();
    expect(screen.getByTestId("ask-action-ask-0001-0")).toHaveTextContent(t("assistant.commandSent"));
    expect(screen.getByTestId("ask-message-ask-0001")).not.toHaveTextContent("cmd-7f3a9c1e");
    fireEvent.click(screen.getByTestId("ask-details-toggle-ask-0001"));
    expect(screen.getByTestId("ask-details-ask-0001")).toHaveTextContent("cmd-7f3a9c1e");
  });

  it("un solo contenitore: il modulo sta dentro la conversazione", () => {
    open();
    expect(screen.getByTestId("assistant-thread")).toContainElement(screen.getByTestId("assistant-form"));
  });
});
