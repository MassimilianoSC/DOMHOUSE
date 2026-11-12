import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/api/bff";
import AssistantPage from "./AssistantPage";

// P-83, D23: a question stays «pending» on the engine up to ~28 s. Before, the page followed it only inside send():
// leaving the page (or F5) left it «Sto elaborando…» for ever, and so did ONE failed getAsk.
const PENDING = { ask_id: "ask-1", status: "pending", text: "accendi il clima", correlation_id: "c-1", actions: [], answer: "" };
const ANSWERED = { ...PENDING, status: "answered", answer: "Fatto: clima acceso." };

const s = vi.hoisted(() => ({ ask: vi.fn(), getAsk: vi.fn() }));
vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: true }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ ask: s.ask, getAsk: s.getAsk, listApprovals: vi.fn(async () => ({ items: [] })) }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

function open() {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/a/apt-001/assistente"]}>
        <Routes>
          <Route path="/a/:aptId/assistente" element={<AssistantPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const seconds = (n: number) => act(() => vi.advanceTimersByTimeAsync(n * 1000));

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  s.ask.mockReset();
  s.getAsk.mockReset();
  sessionStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Assistente: una domanda in attesa si segue fino alla risposta (P-83, D23)", () => {
  it("domanda rimasta in attesa (F5, o ritorno sulla pagina): la pagina la rilegge e mostra la risposta", async () => {
    sessionStorage.setItem("assistant.apt-001", JSON.stringify([PENDING]));
    s.getAsk.mockResolvedValue(ANSWERED);
    open();
    expect(screen.getByTestId("ask-pending-ask-1")).toBeInTheDocument();
    await seconds(1.1);
    expect(s.getAsk).toHaveBeenCalledWith("ask-1");
    expect(screen.getByTestId("ask-answer-ask-1")).toHaveTextContent("Fatto: clima acceso.");
  });

  it("domanda mandata, pagina lasciata subito, risposta arrivata nel frattempo: al ritorno c'è la risposta", async () => {
    s.ask.mockResolvedValue(PENDING);
    s.getAsk.mockResolvedValue(PENDING);
    const view = open();
    fireEvent.change(screen.getByTestId("assistant-input"), { target: { value: "accendi il clima" } });
    await act(async () => { fireEvent.submit(screen.getByTestId("assistant-input").closest("form")!); });
    view.unmount();
    s.getAsk.mockResolvedValue(ANSWERED);
    await seconds(3);
    open();
    await seconds(1.1);
    expect(screen.getByTestId("ask-answer-ask-1")).toHaveTextContent("Fatto: clima acceso.");
  });

  it("UNA lettura fallita (rete, 502) non lascia la domanda in attesa: si riprova", async () => {
    sessionStorage.setItem("assistant.apt-001", JSON.stringify([PENDING]));
    s.getAsk
      .mockRejectedValueOnce(new ApiError(502, "instance_unreachable", "Sistema domotico non raggiungibile", null))
      .mockResolvedValue(ANSWERED);
    open();
    await seconds(1.1);
    await seconds(1.1);
    expect(screen.getByTestId("ask-answer-ask-1")).toHaveTextContent("Fatto: clima acceso.");
  });

  it("lettura rifiutata per sempre (403, 404): la domanda risulta non riuscita, non in attesa", async () => {
    sessionStorage.setItem("assistant.apt-001", JSON.stringify([PENDING]));
    s.getAsk.mockRejectedValue(new ApiError(404, "not_found", "Domanda non trovata", null));
    open();
    await seconds(1.1);
    expect(screen.queryByTestId("ask-pending-ask-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("ask-message-ask-1")).toHaveAttribute("data-status", "failed");
  });
});
