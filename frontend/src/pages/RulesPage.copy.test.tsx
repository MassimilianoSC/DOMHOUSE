import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { toast } from "sonner";
import { TooltipProvider } from "@/components/ui/primitives";
import { t } from "@/i18n";
import RulesPage from "./RulesPage";

// «Applica le stesse regole ad altri appartamenti» (D-151 point 6, routes #40 and #41): admins only; the apartments to
// touch, a preview with the changes and the warning on customized rules, then the outcome per apartment.
const RULES = {
  updated_at: "2026-10-21T14:00:00.000Z",
  rules: [{ rule_id: "window_open_off", label: "Finestra aperta spegne il clima", enabled: true, editable: true, params: { minutes: 12 }, limits: { minutes: { min: 1, max: 30 } } }],
};

const apt = (apartment_id: string, name: string) => ({ apartment_id, name, address: "", timezone: "Europe/Rome", enabled: true, online: true, apartment: null, health: null, contract_version: "1.0.5", features: [], pending_approvals: 0, kwh_today: null });
const APARTMENTS = [apt("apt-bologna-01", "Bologna"), apt("apt-rimini-01", "Rimini"), apt("apt-roma-01", "Roma"), apt("apt-pisa-01", "Pisa")];

const WINDOW = { rule_id: "window_open_off", label: "Finestra aperta spegne il clima", field: "minutes", old: 5, new: 12 };
const PREVIEW = {
  from: { apartment_id: "apt-bologna-01", name: "Bologna", based_on: "2026-10-21T14:00:00.000Z" },
  rules: [{ rule_id: "window_open_off", enabled: true, params: { minutes: 12 } }],
  targets: [
    { apartment_id: "apt-rimini-01", name: "Rimini", based_on: "2026-10-20T09:00:00.000Z", status: "changes", changes: [WINDOW],
      customized: [{ rule_id: "offline_alert", label: "Avviso dispositivo offline", field: "minutes", value: 60, default: 15 }] },
    { apartment_id: "apt-roma-01", name: "Roma", based_on: "2026-10-19T09:00:00.000Z", status: "same", changes: [], customized: [] },
    { apartment_id: "apt-pisa-01", name: "Pisa", based_on: null, status: "unreachable", changes: [], customized: [] },
  ],
};
const RESULTS = {
  from: PREVIEW.from,
  results: [
    { apartment_id: "apt-rimini-01", name: "Rimini", outcome: "applied", message: null, changes: [WINDOW] },
    { apartment_id: "apt-roma-01", name: "Roma", outcome: "same", message: null, changes: [] },
    { apartment_id: "apt-pisa-01", name: "Pisa", outcome: "changed_meanwhile", message: "Regole cambiate dopo l'anteprima: non toccato", changes: [] },
  ],
};

const s = vi.hoisted(() => ({ role: { canWrite: true, isAdmin: true }, answer: { preview: null as unknown, copy: null as unknown }, calls: [] as { path: string; body: unknown }[] }));

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => s.role }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getRules: async () => RULES }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  vi.clearAllMocks();
  s.role = { canWrite: true, isAdmin: true };
  s.answer = { preview: json(PREVIEW), copy: json(RESULTS) };
  s.calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    s.calls.push({ path, body: init?.body ? JSON.parse(String(init.body)) : null });
    if (path === "/app/apartments") return json(APARTMENTS);
    if (path === "/app/apartments/apt-bologna-01/rules/copy/preview") return s.answer.preview as Response;
    if (path === "/app/apartments/apt-bologna-01/rules/copy") return s.answer.copy as Response;
    return json({ error: "unexpected", message: path }, 500);
  }));
});

async function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/a/apt-bologna-01/regole"]}>
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

async function previewOf(ids: string[]) {
  await open();
  for (const id of ids) await click(await screen.findByTestId(`rules-copy-target-${id}`));
  await click(screen.getByTestId("rules-copy-preview"));
}

describe("Regole: copia su altri appartamenti (D-151)", () => {
  it("gli altri appartamenti dell'organizzazione, non quello di partenza; senza scelta niente anteprima", async () => {
    await open();
    expect(await screen.findByTestId("rules-copy-target-apt-rimini-01")).toBeInTheDocument();
    expect(screen.queryByTestId("rules-copy-target-apt-bologna-01")).toBeNull();
    expect(screen.getByTestId("rules-copy-preview")).toBeDisabled();
    await click(screen.getByTestId("rules-copy-all"));
    expect(screen.getByTestId("rules-copy-preview")).toBeEnabled();
  });

  it("anteprima: per ogni appartamento che cosa cambia, «già uguale», non raggiungibile, e l'avviso sulle regole personalizzate", async () => {
    await previewOf(["apt-rimini-01", "apt-roma-01", "apt-pisa-01"]);
    expect(s.calls.find((c) => c.path.endsWith("/copy/preview"))?.body).toEqual({ to: ["apt-rimini-01", "apt-roma-01", "apt-pisa-01"] });
    expect(screen.getByTestId("rules-copy-changes-apt-rimini-01")).toHaveTextContent("Finestra aperta spegne il clima · Minuti: 5 → 12");
    expect(screen.getByTestId("rules-copy-customized-apt-rimini-01")).toHaveTextContent("Ha regole personalizzate che verranno sovrascritte: Avviso dispositivo offline, minuti 60 (predefinito 15)");
    expect(screen.getByTestId("rules-copy-row-apt-roma-01")).toHaveTextContent("Già uguale, nessuna modifica");
    expect(screen.getByTestId("rules-copy-row-apt-pisa-01")).toHaveTextContent("Motore non raggiungibile: non verrà toccato");
    expect(screen.queryByTestId("rules-copy-customized-apt-roma-01")).toBeNull();
    expect(screen.getByTestId("rules-copy-confirm")).toHaveTextContent("Copia su 1 appartamento");
    expect(s.calls.some((c) => c.path === "/app/apartments/apt-bologna-01/rules/copy")).toBe(false);
  });

  it("conferma: manda quello che ha dato l'anteprima e mostra l'esito per appartamento", async () => {
    await previewOf(["apt-rimini-01", "apt-roma-01", "apt-pisa-01"]);
    await click(screen.getByTestId("rules-copy-confirm"));
    expect(s.calls.find((c) => c.path === "/app/apartments/apt-bologna-01/rules/copy")?.body).toEqual({
      to: ["apt-rimini-01", "apt-roma-01", "apt-pisa-01"],
      from_based_on: "2026-10-21T14:00:00.000Z",
      based_on: { "apt-rimini-01": "2026-10-20T09:00:00.000Z", "apt-roma-01": "2026-10-19T09:00:00.000Z", "apt-pisa-01": null },
    });
    expect(screen.getByTestId("rules-copy-result-apt-rimini-01")).toHaveTextContent("Rimini · Regole copiate");
    expect(screen.getByTestId("rules-copy-result-changes-apt-rimini-01")).toHaveTextContent("Minuti: 5 → 12");
    expect(screen.getByTestId("rules-copy-result-apt-roma-01")).toHaveTextContent("Già uguale, nessuna modifica");
    expect(screen.getByTestId("rules-copy-result-apt-pisa-01")).toHaveTextContent("Regole cambiate dopo l'anteprima: non toccato");
    await click(screen.getByTestId("rules-copy-close"));
    expect(screen.queryByTestId("rules-copy-results")).toBeNull();
  });

  it("niente da cambiare in nessun appartamento: la conferma è disattivata", async () => {
    s.answer.preview = json({ ...PREVIEW, targets: [PREVIEW.targets[1]] });
    await previewOf(["apt-roma-01"]);
    expect(screen.getByTestId("rules-copy-confirm")).toBeDisabled();
  });

  it("regole di partenza cambiate dopo l'anteprima (409): il messaggio, si torna alla scelta", async () => {
    s.answer.copy = json({ error: "rules_changed", message: "Le regole sono cambiate nel frattempo: rifai la richiesta" }, 409);
    await previewOf(["apt-rimini-01"]);
    await click(screen.getByTestId("rules-copy-confirm"));
    expect(toast.error).toHaveBeenCalledWith("Le regole sono cambiate nel frattempo: rifai la richiesta", expect.anything());
    expect(screen.queryByTestId("rules-copy-preview-result")).toBeNull();
    expect(screen.getByTestId("rules-copy-preview")).toBeInTheDocument();
  });

  it("modifiche fatte a mano non salvate: l'anteprima aspetta, con la spiegazione", async () => {
    await open();
    await click(await screen.findByTestId("rules-copy-target-apt-rimini-01"));
    fireEvent.change(screen.getByTestId("rule-param-window_open_off-minutes"), { target: { value: "7" } });
    expect(screen.getByTestId("rules-copy-unsaved")).toHaveTextContent(t("rules.proposal.unsaved"));
    expect(screen.getByTestId("rules-copy-preview")).toBeDisabled();
  });

  it("operatore: niente copia (la proposta dell'assistente sì)", async () => {
    s.role = { canWrite: true, isAdmin: false };
    await open();
    expect(screen.queryByTestId("rules-copy")).toBeNull();
    expect(screen.getByTestId("rule-proposal")).toBeInTheDocument();
  });

  it("nessun altro appartamento: lo dice", async () => {
    vi.mocked(fetch).mockImplementation(async () => json([APARTMENTS[0]]));
    await open();
    expect(await screen.findByTestId("rules-copy-none")).toHaveTextContent(t("rules.copy.noOthers"));
  });
});
