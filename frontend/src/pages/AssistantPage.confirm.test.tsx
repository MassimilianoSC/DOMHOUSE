import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { t } from "@/i18n";
import AssistantPage from "./AssistantPage";

// D-154: with guests present the assistant asks «Spengo …? Sì o No» and the click is the same call as the Approvazioni
// page (POST …/approvals/{id}/decision), so the same entry and expiry. One open approval at a time per question.
const CID = "6b7d0c1e-1f3a-4a1e-8e3f-0c2d9a7b5e44";
const ASK = {
  ask_id: "ask-0007", status: "needs_approval", text: "spegni il clima", correlation_id: CID, approval_id: "apr-0012", actions: [],
  answer: "Chiedo di spegnere il clima. Spengo climatizzatore soggiorno con ospiti presenti? Rispondi Sì o No qui sotto, oppure dalla pagina Approvazioni.",
};
const approval = (approval_id: string, status: string, description: string, correlation_id = CID) => ({
  approval_id, status, description, correlation_id, source: "assistant", reason: "ospiti presenti", created_at: "2026-10-22T10:12:00.000Z",
  expires_at: "2026-10-22T10:42:00.000Z", expires_action: "reject", proposed_action: { type: "command", device_id: "dev-clima-soggiorno", capability: "climate", action: "turn_off" },
});

const s = vi.hoisted(() => ({ canWrite: true, lists: [] as unknown[][], decide: vi.fn() }));

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: s.canWrite }), useAuth: () => ({ me: { user: { email: "anna@fs.it" } } }) }));
vi.mock("@/api/instance", () => ({
  instanceApi: () => ({
    // every read gives the next state of the list; the last one stays
    listApprovals: vi.fn(async () => ({ items: s.lists.length > 1 ? s.lists.shift() : s.lists[0] })),
    decideApproval: s.decide,
    ask: vi.fn(),
    getAsk: vi.fn(),
  }),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

function open() {
  sessionStorage.setItem("assistant.apt-001", JSON.stringify([ASK]));
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

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  Element.prototype.scrollIntoView = vi.fn();
  s.canWrite = true;
  s.decide.mockImplementation(async (id: string, body: { decision: string }) => ({ ...approval(id, body.decision === "approve" ? "approved" : "rejected", "x") }));
});

describe("Assistente: conferma nella chat con ospiti presenti (D-154)", () => {
  it("«Sì» e «No» sotto la domanda, con l'ora di scadenza nell'ora dell'appartamento", async () => {
    s.lists = [[approval("apr-0012", "pending", "Spegnere climatizzatore soggiorno")]];
    open();
    expect(await screen.findByTestId("ask-confirm-yes-ask-0007")).toHaveTextContent("Sì");
    expect(screen.getByTestId("ask-confirm-no-ask-0007")).toHaveTextContent("No");
    expect(screen.getByTestId("ask-confirm-expiry-ask-0007")).toHaveTextContent("Scade alle 12:42");
  });

  it("«Sì»: la stessa chiamata della pagina Approvazioni, poi «Approvato: il comando parte…» e niente pulsanti", async () => {
    s.lists = [[approval("apr-0012", "pending", "Spegnere climatizzatore soggiorno")], [approval("apr-0012", "approved", "Spegnere climatizzatore soggiorno")]];
    open();
    await click(await screen.findByTestId("ask-confirm-yes-ask-0007"));
    expect(s.decide).toHaveBeenCalledWith("apr-0012", { decision: "approve" }, expect.stringMatching(/^[0-9a-f-]{36}$/));
    await waitFor(() => expect(screen.getByTestId("ask-confirm-result-ask-0007")).toHaveTextContent("Approvato: il comando parte, l'esito arriva nell'app"));
    expect(screen.queryByTestId("ask-confirm-yes-ask-0007")).toBeNull();
  });

  it("«No»: «Respinto»", async () => {
    s.lists = [[approval("apr-0012", "pending", "Spegnere climatizzatore soggiorno")], [approval("apr-0012", "rejected", "Spegnere climatizzatore soggiorno")]];
    open();
    await click(await screen.findByTestId("ask-confirm-no-ask-0007"));
    expect(s.decide).toHaveBeenCalledWith("apr-0012", { decision: "reject" }, expect.any(String));
    await waitFor(() => expect(screen.getByTestId("ask-confirm-result-ask-0007")).toHaveTextContent("Respinto"));
  });

  it("più azioni nella stessa domanda: dopo il clic i pulsanti passano alla successiva", async () => {
    s.lists = [
      [approval("apr-0012", "pending", "Spegnere climatizzatore soggiorno")],
      [approval("apr-0012", "approved", "Spegnere climatizzatore soggiorno"), approval("apr-0013", "pending", "Modalità eco")],
    ];
    open();
    await click(await screen.findByTestId("ask-confirm-yes-ask-0007"));
    await waitFor(() => expect(screen.getByTestId("ask-confirm-ask-0007")).toHaveAttribute("data-approval", "apr-0013"));
    expect(screen.getByTestId("ask-confirm-ask-0007")).toHaveTextContent("Approvato: il comando parte");
    expect(screen.getByTestId("ask-confirm-ask-0007")).toHaveTextContent("Ora: Modalità eco");
    await click(screen.getByTestId("ask-confirm-yes-ask-0007"));
    expect(s.decide).toHaveBeenLastCalledWith("apr-0013", { decision: "approve" }, expect.any(String));
  });

  it("in coda dietro un'approvazione di un'altra fonte: «In attesa…» con il link alle Approvazioni", async () => {
    s.lists = [[approval("apr-0009", "pending", "Consumo a casa vuota", "altra-correlazione")]];
    open();
    const queued = await screen.findByTestId("ask-confirm-queued-ask-0007");
    expect(queued).toHaveTextContent("In attesa: prima va decisa l'approvazione aperta.");
    expect(queued.querySelector("a")).toHaveAttribute("href", "/a/apt-001/approvazioni");
    expect(screen.queryByTestId("ask-confirm-yes-ask-0007")).toBeNull();
  });

  it.each([
    ["approved", "Già decisa: approvata"],
    ["rejected", "Già decisa: respinta"],
    ["expired", "Scaduta"],
  ])("già chiusa (%s): «%s», niente pulsanti", async (status, text) => {
    s.lists = [[approval("apr-0012", status, "Spegnere climatizzatore soggiorno")]];
    open();
    expect(await screen.findByTestId("ask-confirm-closed-ask-0007")).toHaveTextContent(text);
    expect(screen.queryByTestId("ask-confirm-yes-ask-0007")).toBeNull();
  });

  it("decisa altrove nel frattempo (409 already_closed): nessun errore, dice com'è andata", async () => {
    s.lists = [[approval("apr-0012", "pending", "Spegnere climatizzatore soggiorno")], [approval("apr-0012", "approved", "Spegnere climatizzatore soggiorno")]];
    s.decide.mockRejectedValueOnce(new ApiError(409, "already_closed", "Approvazione già chiusa", "c-1"));
    open();
    await click(await screen.findByTestId("ask-confirm-yes-ask-0007"));
    expect(toast.error).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByTestId("ask-confirm-closed-ask-0007")).toHaveTextContent(t("assistant.confirm.alreadyApproved")));
  });

  it("chi legge soltanto: la domanda sì, i pulsanti no", async () => {
    s.canWrite = false;
    s.lists = [[approval("apr-0012", "pending", "Spegnere climatizzatore soggiorno")]];
    open();
    expect(await screen.findByTestId("ask-answer-ask-0007")).toHaveTextContent("Spengo climatizzatore soggiorno con ospiti presenti?");
    expect(screen.queryByTestId("ask-confirm-ask-0007")).toBeNull();
  });
});
