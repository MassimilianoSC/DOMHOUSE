import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/primitives";
import RulesPage from "./RulesPage";

// P-90 T1 (1104 = a): the rule «Avviso dispositivo offline» drove also the alert «sistema domotico non raggiungibile»
// (D-217), and its description spoke only of «un dispositivo». Now the system's alert is always on, with a fixed threshold
// in the BFF (o1), and the rule drives the single devices only: the description says both.
const s = vi.hoisted(() => ({ enabled: true }));
const offline = () => ({
  rule_id: "offline_alert", label: "Avviso dispositivo offline", enabled: s.enabled, editable: true,
  params: { minutes: 15 }, limits: { minutes: { min: 5, max: 120 } },
});

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: true, isAdmin: false }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getRules: async () => ({ updated_at: "2026-11-12T08:00:00.000Z", rules: [offline()] }), updateRules: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

async function card() {
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
  return screen.findByTestId("rule-card-offline_alert");
}

describe("Avviso dispositivo offline: la regola comanda solo i dispositivi (P-90 T1)", () => {
  it.each([true, false])("regola %s: dice che l'avviso del sistema domotico arriva sempre, dopo 15 minuti", async (enabled) => {
    s.enabled = enabled;
    const c = await card();
    expect(c).toHaveTextContent("Avvisa quando un dispositivo resta offline oltre i minuti indicati.");
    expect(c).toHaveTextContent("L'avviso «sistema domotico non raggiungibile» non dipende da questa regola: arriva sempre dopo 15 minuti.");
  });
});
