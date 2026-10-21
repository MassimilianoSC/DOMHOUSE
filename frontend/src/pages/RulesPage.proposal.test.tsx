import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { TooltipProvider } from "@/components/ui/primitives";
import { t } from "@/i18n";
import RulesPage from "./RulesPage";

// «Chiedi all'assistente» on the Regole page (D-151): the server proposes, the manager sees before and after and
// applies; nothing changes before «Applica». Operators and admins only.
const rule = (rule_id: string, label: string, params: Record<string, number>, limits: Record<string, { min: number; max: number }>, enabled = true) =>
  ({ rule_id, label, enabled, editable: true, params, limits });

const RULES = (minutes = 5) => ({
  updated_at: "2026-10-21T14:00:00.000Z",
  rules: [
    rule("window_open_off", "Finestra aperta spegne il clima", { minutes }, { minutes: { min: 1, max: 30 } }),
    rule("checkout_eco", "Risparmio al check-out", { minutes_after: 30, presence_minutes: 30 }, { minutes_after: { min: 0, max: 240 }, presence_minutes: { min: 5, max: 180 } }),
  ],
});

const PROPOSAL = {
  based_on: "2026-10-21T14:00:00.000Z",
  rules: [{ rule_id: "window_open_off", params: { minutes: 10 } }, { rule_id: "checkout_eco", enabled: false }],
  changes: [
    { rule_id: "window_open_off", label: "Finestra aperta spegne il clima", field: "minutes", old: 5, new: 10 },
    { rule_id: "checkout_eco", label: "Risparmio al check-out", field: "enabled", old: true, new: false },
  ],
  explanation: "Finestra a 10 minuti e risparmio al check-out spento.",
};

const s = vi.hoisted(() => ({
  canWrite: true,
  getRules: vi.fn(),
  answer: { propose: null as unknown, apply: null as unknown },
  calls: [] as { path: string; body: unknown }[],
}));

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: s.canWrite }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getRules: s.getRules }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  vi.clearAllMocks();
  s.canWrite = true;
  s.getRules.mockImplementation(async () => RULES());
  s.answer = { propose: json(PROPOSAL), apply: json(RULES(10)) };
  s.calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    s.calls.push({ path, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (path === "/app/apartments/apt-001/rules/proposal") return s.answer.propose as Response;
    if (path === "/app/apartments/apt-001/rules/proposal/apply") return s.answer.apply as Response;
    return json({ error: "unexpected", message: path }, 500);
  }));
});

async function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/a/apt-001/regole"]}>
          <Routes>
            <Route path="/a/:aptId/regole" element={<RulesPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
  await screen.findByTestId("rule-card-window_open_off");
}

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

async function propose(text = "la finestra aperta spegne dopo 10 minuti") {
  fireEvent.change(screen.getByTestId("rule-proposal-text"), { target: { value: text } });
  await click(screen.getByTestId("rule-proposal-ask"));
}

describe("Regole: «Chiedi all'assistente» (D-151)", () => {
  it("la proposta: prima e dopo per ogni valore, con la frase dell'assistente; niente cambia prima di «Applica»", async () => {
    await open();
    await propose();
    expect(s.calls).toEqual([{ path: "/app/apartments/apt-001/rules/proposal", body: { text: "la finestra aperta spegne dopo 10 minuti" } }]);
    expect(screen.getByTestId("rule-proposal-change-window_open_off-minutes")).toHaveTextContent("Finestra aperta spegne il clima · Minuti: 5 → 10");
    expect(screen.getByTestId("rule-proposal-change-checkout_eco-enabled")).toHaveTextContent("Risparmio al check-out · Stato: attiva → spenta");
    expect(screen.getByTestId("rule-proposal-explanation")).toHaveTextContent(PROPOSAL.explanation);
    expect(screen.getByTestId("rule-param-window_open_off-minutes")).toHaveValue(5);
  });

  it("«Applica»: manda la proposta così com'è e la pagina mostra le regole nuove", async () => {
    await open();
    await propose();
    await click(screen.getByTestId("rule-proposal-apply"));
    expect(s.calls[1]).toEqual({ path: "/app/apartments/apt-001/rules/proposal/apply", body: { based_on: PROPOSAL.based_on, rules: PROPOSAL.rules } });
    expect(toast.success).toHaveBeenCalledWith(t("rules.proposal.applied"));
    await waitFor(() => expect(screen.getByTestId("rule-param-window_open_off-minutes")).toHaveValue(10));
    expect(screen.queryByTestId("rule-proposal-result")).toBeNull();
    expect(screen.getByTestId("rule-proposal-text")).toHaveValue("");
  });

  it("nessuna modifica possibile: solo la frase del server, niente «Applica»", async () => {
    s.answer.propose = json({ ...PROPOSAL, rules: [], changes: [], explanation: "Il valore deve essere tra 1 e 30 minuti." });
    await open();
    await propose("finestra 90 minuti");
    expect(screen.getByTestId("rule-proposal-none")).toHaveTextContent("Il valore deve essere tra 1 e 30 minuti.");
    expect(screen.queryByTestId("rule-proposal-apply")).toBeNull();
  });

  it("regole cambiate nel frattempo (409): il messaggio, la proposta sparisce e le regole si rileggono", async () => {
    s.answer.apply = json({ error: "rules_changed", message: "Le regole sono cambiate nel frattempo: rifai la richiesta" }, 409);
    await open();
    await propose();
    const before = s.getRules.mock.calls.length;
    await click(screen.getByTestId("rule-proposal-apply"));
    expect(toast.error).toHaveBeenCalledWith("Le regole sono cambiate nel frattempo: rifai la richiesta", expect.anything());
    expect(screen.queryByTestId("rule-proposal-result")).toBeNull();
    await waitFor(() => expect(s.getRules.mock.calls.length).toBeGreaterThan(before));
  });

  it("limite giornaliero (429): il messaggio del server, nessuna proposta", async () => {
    s.answer.propose = json({ error: "daily_limit", message: "Hai già fatto 20 richieste oggi per questo appartamento" }, 429);
    await open();
    await propose();
    expect(toast.error).toHaveBeenCalledWith("Hai già fatto 20 richieste oggi per questo appartamento", expect.anything());
    expect(screen.queryByTestId("rule-proposal-result")).toBeNull();
  });

  it("modifiche fatte a mano non salvate: «Applica» aspetta, con la spiegazione", async () => {
    await open();
    fireEvent.change(screen.getByTestId("rule-param-window_open_off-minutes"), { target: { value: "7" } });
    await propose();
    expect(screen.getByTestId("rule-proposal-unsaved")).toHaveTextContent(t("rules.proposal.unsaved"));
    expect(screen.getByTestId("rule-proposal-apply")).toBeDisabled();
  });

  it("testo vuoto o oltre 500 caratteri: «Proponi» disattivato, il contatore lo dice", async () => {
    await open();
    expect(screen.getByTestId("rule-proposal-ask")).toBeDisabled();
    fireEvent.change(screen.getByTestId("rule-proposal-text"), { target: { value: "x".repeat(501) } });
    expect(screen.getByTestId("rule-proposal-counter")).toHaveTextContent("501/500 caratteri");
    expect(screen.getByTestId("rule-proposal-ask")).toBeDisabled();
  });

  it("chi legge soltanto: il riquadro non c'è", async () => {
    s.canWrite = false;
    await open();
    expect(screen.queryByTestId("rule-proposal")).toBeNull();
  });

  it("il parametro nuovo di «Risparmio al check-out» con la sua etichetta", async () => {
    await open();
    expect(screen.getByTestId("rule-card-checkout_eco")).toHaveTextContent("Minuti di presenza dopo il check-out");
    expect(screen.getByTestId("rule-card-checkout_eco")).toHaveTextContent(t("rules.desc.checkout_eco"));
  });
});
