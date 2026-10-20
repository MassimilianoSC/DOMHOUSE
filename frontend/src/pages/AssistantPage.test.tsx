import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import AssistantPage from "./AssistantPage";

// The assistant for a reader (P-51, D-90): no question is ever sent, so no ask and no getAsk (the server answers 403).
const s = vi.hoisted(() => ({ canWrite: false, ask: vi.fn(async () => ({ ask_id: "a1", status: "answered", question: "x", answer: "y", actions: [] })), getAsk: vi.fn() }));

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: s.canWrite }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ ask: s.ask, getAsk: s.getAsk }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

function open() {
  render(
    <QueryClientProvider client={new QueryClient()}>
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
  Element.prototype.scrollIntoView = vi.fn(); // not in jsdom
});

describe("Assistente: il lettore non manda domande", () => {
  it("anche forzando il modulo, nessuna chiamata all'assistente", async () => {
    s.canWrite = false;
    open();
    const input = screen.getByTestId("assistant-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "accendi il clima" } });
    await act(async () => {
      fireEvent.submit(input.closest("form")!);
    });
    expect(s.ask).not.toHaveBeenCalled();
    expect(s.getAsk).not.toHaveBeenCalled();
  });

  it("l'operatore manda la domanda come prima", async () => {
    s.canWrite = true;
    open();
    const input = screen.getByTestId("assistant-input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "accendi il clima" } });
    await act(async () => {
      fireEvent.submit(input.closest("form")!);
    });
    expect(s.ask).toHaveBeenCalledTimes(1);
  });
});
