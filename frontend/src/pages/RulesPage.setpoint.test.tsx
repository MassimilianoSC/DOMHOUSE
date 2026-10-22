import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ApiError } from "@/api/bff";
import { TooltipProvider } from "@/components/ui/primitives";
import RulesPage from "./RulesPage";

// Lotto 30 (o1 91bc015): «Limiti del setpoint» gets the temperatures of the modes; the page draws the fields from the
// limits, with their Italian labels, and shows the server's message when the values do not fit together.
const SETPOINT = {
  rule_id: "setpoint_limits", label: "Limiti del setpoint", enabled: true, editable: true,
  params: { min: 16, max: 24, comfort_celsius: 21, eco_celsius: 18, comfort_cool_celsius: 25 },
  limits: { min: { min: 7, max: 20 }, max: { min: 20, max: 28 }, comfort_celsius: { min: 16, max: 26 }, eco_celsius: { min: 10, max: 22 }, comfort_cool_celsius: { min: 22, max: 28 } },
};
const s = vi.hoisted(() => ({ canWrite: false, update: vi.fn() }));

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: s.canWrite, isAdmin: false }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getRules: async () => ({ updated_at: "2026-10-22T14:00:00.000Z", rules: [SETPOINT] }), updateRules: s.update }) }));
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
});

describe("Regole: le temperature delle modalità (lotto 30)", () => {
  it("i tre campi nuovi con le loro etichette e i limiti, e la descrizione aggiornata", async () => {
    await open();
    const card = screen.getByTestId("rule-card-setpoint_limits");
    expect(card).toHaveTextContent("Temperatura in comfort (°C) (da 16 a 26)");
    expect(card).toHaveTextContent("Temperatura in eco (°C) (da 10 a 22)");
    expect(card).toHaveTextContent("Raffrescamento in comfort (°C) (da 22 a 28)");
    expect(screen.getByTestId("rule-param-setpoint_limits-comfort_cool_celsius")).toHaveValue(25);
    expect(card).toHaveTextContent("In eco la caldaia sta alla temperatura eco.");
  });

  it.each([
    ["eco_celsius", "22", "La temperatura eco non può superare quella comfort"],
    // comfort uguale al raffrescamento (25): non più alta, quindi rifiutata
    ["comfort_celsius", "25", "La temperatura di raffrescamento deve essere più alta di quella comfort"],
    ["comfort_celsius", "26", "La temperatura di raffrescamento deve essere più alta di quella comfort"],
  ])("prima del salvataggio, %s a %s: «%s», e niente salvataggio", async (param, value, message) => {
    s.canWrite = true;
    await open();
    fireEvent.change(screen.getByTestId(`rule-param-setpoint_limits-${param}`), { target: { value } });
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
