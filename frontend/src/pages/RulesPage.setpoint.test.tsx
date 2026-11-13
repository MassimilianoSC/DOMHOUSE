import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/api/bff";
import { TooltipProvider } from "@/components/ui/primitives";
import { useApartmentStore } from "@/store/apartmentStore";
import RulesPage from "./RulesPage";

// Lotto 30 (o1 91bc015): «Limiti del setpoint» gets the temperatures of the modes; the page draws the fields from the
// limits, with their Italian labels, and shows the server's message when the values do not fit together.
// 1098 = b: two ranges, winter (min, max: boiler and climate heating) and summer (summer_min, summer_max: climate cooling
// and drying), the engine's initial values (o1; 1099: summer from 18 to 28, winter from 16 to 24).
const SETPOINT = {
  rule_id: "setpoint_limits", label: "Limiti del setpoint", enabled: true, editable: true,
  params: { min: 16, max: 24, comfort_celsius: 21, eco_celsius: 18, comfort_cool_celsius: 25, summer_min: 18, summer_max: 28 },
  limits: {
    min: { min: 7, max: 20 }, max: { min: 20, max: 28 }, comfort_celsius: { min: 16, max: 26 }, eco_celsius: { min: 10, max: 22 },
    comfort_cool_celsius: { min: 22, max: 28 }, summer_min: { min: 16, max: 28 }, summer_max: { min: 22, max: 30 },
  },
};
const s = vi.hoisted(() => ({ canWrite: false, update: vi.fn(), rules: null as unknown[] | null }));

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: s.canWrite, isAdmin: false }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getRules: async () => ({ updated_at: "2026-10-22T14:00:00.000Z", rules: s.rules ?? [SETPOINT] }), updateRules: s.update }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

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
  await screen.findByTestId("rule-card-setpoint_limits");
}

beforeEach(() => {
  vi.clearAllMocks();
  s.canWrite = false;
  s.rules = null;
});

describe("Regole: le temperature delle modalità (lotto 30)", () => {
  it("i tre campi nuovi con le loro etichette e i limiti, e la descrizione aggiornata", async () => {
    await open();
    const card = screen.getByTestId("rule-card-setpoint_limits");
    expect(card).toHaveTextContent("Temperatura in comfort (°C) (da 16 a 26)");
    expect(card).toHaveTextContent("Temperatura in eco (°C) (da 10 a 22)");
    expect(card).toHaveTextContent("Raffrescamento in comfort (°C) (da 22 a 28)");
    expect(screen.getByTestId("rule-param-setpoint_limits-comfort_cool_celsius")).toHaveValue(25);
    expect(card).toHaveTextContent("in eco la caldaia sta alla temperatura eco");
    // 1096 = a: non «ospiti e app»; il telecomando del climatizzatore e l'antigelo non sono limitati
    expect(card).not.toHaveTextContent("ospiti");
    expect(card).toHaveTextContent("dall'app e dall'assistente, e quella usata da modalità e programmi");
    expect(card).toHaveTextContent("non vale per il telecomando del climatizzatore né per l'antigelo");
  });

  it.each([
    ["eco_celsius=22", "La temperatura eco non può superare quella comfort"],
    // comfort uguale al raffrescamento (25): non più alta, quindi rifiutata
    ["comfort_celsius=25 max=26", "La temperatura di raffrescamento deve essere più alta di quella comfort"],
    ["comfort_celsius=26 max=26", "La temperatura di raffrescamento deve essere più alta di quella comfort"],
    // 1098 = b: inverno minimo ≤ eco ≤ comfort ≤ massimo; estate minimo ≤ raffrescamento ≤ massimo; comfort < raffrescamento
    ["eco_celsius=15", "La temperatura eco non può essere sotto il minimo invernale"],
    ["min=19", "La temperatura eco non può essere sotto il minimo invernale"],
    ["max=20", "La temperatura comfort non può superare il massimo invernale"],
    ["comfort_celsius=24.5", "La temperatura comfort non può superare il massimo invernale"],
    ["summer_min=24 summer_max=23", "Il minimo estivo non può superare il massimo estivo"],
    ["summer_min=26", "La temperatura di raffrescamento deve stare fra il minimo e il massimo estivi"],
    ["summer_max=24", "La temperatura di raffrescamento deve stare fra il minimo e il massimo estivi"],
  ])("prima del salvataggio, %s: «%s», e niente salvataggio", async (changes, message) => {
    s.canWrite = true;
    await open();
    for (const change of changes.split(" ")) {
      const [param, value] = change.split("=");
      fireEvent.change(screen.getByTestId(`rule-param-setpoint_limits-${param}`), { target: { value } });
    }
    expect(screen.getByTestId("rules-range-error")).toHaveTextContent(message);
    expect(screen.getByTestId("rules-save-btn")).toBeDisabled();
    expect(s.update).not.toHaveBeenCalled();
  });

  it("valori coerenti per il sito ma rifiutati dal server (422): il messaggio del server", async () => {
    s.canWrite = true;
    s.update.mockRejectedValueOnce(new ApiError(422, "invalid_range", "La temperatura eco non può superare quella comfort", "c-1"));
    await open();
    fireEvent.change(screen.getByTestId("rule-param-setpoint_limits-comfort_celsius"), { target: { value: "22" } });
    expect(screen.queryByTestId("rules-range-error")).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByTestId("rules-save-btn"));
    });
    expect(await screen.findByTestId("rules-save-error")).toHaveTextContent("La temperatura eco non può superare quella comfort");
  });
});

describe("Regole: inverno ed estate, due intervalli (1096/1097 = a, 1098 = b)", () => {
  const WINDOW = { rule_id: "window_open_off", label: "Finestra aperta spegne il clima", enabled: true, editable: true, params: { minutes: 5 }, limits: { minutes: { min: 1, max: 30 } } };
  const OLD = { ...SETPOINT, params: { ...SETPOINT.params, max: 20 } };   // salvata prima: comfort 21 sopra il massimo invernale 20

  it("due gruppi chiari: «Inverno (riscaldamento)» con minimo, massimo, eco e comfort; «Estate (raffrescamento)» con minimo, massimo e raffrescamento", async () => {
    await open();
    const winter = screen.getByTestId("rule-group-setpoint_limits-winter");
    const summer = screen.getByTestId("rule-group-setpoint_limits-summer");
    expect(winter).toHaveTextContent("Inverno (riscaldamento)");
    expect(summer).toHaveTextContent("Estate (raffrescamento)");
    for (const k of ["min", "max", "eco_celsius", "comfort_celsius"]) expect(winter).toContainElement(screen.getByTestId(`rule-param-setpoint_limits-${k}`));
    for (const k of ["summer_min", "summer_max", "comfort_cool_celsius"]) expect(summer).toContainElement(screen.getByTestId(`rule-param-setpoint_limits-${k}`));
    expect(summer).toHaveTextContent("Minimo (°C) (da 16 a 28)");
    expect(summer).toHaveTextContent("Massimo (°C) (da 22 a 30)");
    expect(screen.getByTestId("rule-param-setpoint_limits-summer_max")).toHaveValue(28);
    const card = screen.getByTestId("rule-card-setpoint_limits");
    expect(card).toHaveTextContent("Estate: il clima che raffresca o deumidifica resta fra minimo e massimo estivi");
  });

  it("regole salvate già incoerenti, modificata un'altra regola: avviso, ma si salva (il motore controlla solo chi tocca la regola)", async () => {
    s.canWrite = true;
    s.rules = [WINDOW, OLD];
    s.update.mockResolvedValue({ updated_at: "2026-11-13T08:00:00.000Z", rules: [WINDOW, OLD] });
    await open();
    expect(screen.getByTestId("rules-range-warning")).toHaveTextContent("La temperatura comfort non può superare il massimo invernale");
    expect(screen.queryByTestId("rules-range-error")).toBeNull();
    fireEvent.click(screen.getByTestId("rule-toggle-window_open_off"));
    expect(screen.getByTestId("rules-save-btn")).not.toBeDisabled();
    await act(async () => { fireEvent.click(screen.getByTestId("rules-save-btn")); });
    expect(s.update).toHaveBeenCalled();
  });

  it.each([
    ["un parametro", () => fireEvent.change(screen.getByTestId("rule-param-setpoint_limits-comfort_celsius"), { target: { value: "22" } })],
    ["l'interruttore", () => fireEvent.click(screen.getByTestId("rule-toggle-setpoint_limits"))],
  ])("regole salvate già incoerenti, toccato %s di «Limiti del setpoint»: blocca finché non si corregge", async (_what, touch) => {
    s.canWrite = true;
    s.rules = [WINDOW, OLD];
    await open();
    touch();
    expect(screen.getByTestId("rules-range-error")).toHaveTextContent("La temperatura comfort non può superare il massimo invernale");
    expect(screen.queryByTestId("rules-range-warning")).toBeNull();
    expect(screen.getByTestId("rules-save-btn")).toBeDisabled();
    fireEvent.change(screen.getByTestId("rule-param-setpoint_limits-max"), { target: { value: "24" } });
    expect(screen.queryByTestId("rules-range-error")).toBeNull();
    expect(screen.getByTestId("rules-save-btn")).not.toBeDisabled();
  });
});

describe("Regole: «Ultima modifica» nell'ora dell'appartamento (P-83, D71)", () => {
  afterEach(() => useApartmentStore.getState().reset("apt-001"));

  it("appartamento a New York: l'ora di New York, non quella di Roma", async () => {
    useApartmentStore.getState().reset("apt-001");
    useApartmentStore.getState().setSnapshot({ apartment: { timezone: "America/New_York" } as never });
    await open();
    // 14:00 UTC del 22 ottobre 2026 = 10:00 a New York (16:00 a Roma)
    expect(screen.getByTestId("rules-updated-at")).toHaveTextContent("10:00");
    expect(screen.getByTestId("rules-updated-at")).not.toHaveTextContent("16:00");
  });
});
