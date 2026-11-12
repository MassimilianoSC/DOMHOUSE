import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/primitives";
import RulesPage from "./RulesPage";

// P-83, D31 (1086 = a): «Con la casa vuota mantiene almeno questa temperatura» made one believe that switching the rule
// off left the boiler off in an empty apartment. «Casa vuota» sends the boiler to this temperature with the rule off too;
// the rule on keeps it even when someone switches the boiler off or lowers it, writes its switches in the Decisions and
// warns when the room's sensor is missing (engine/core.py thermostat() and mode_commands()).
const s = vi.hoisted(() => ({ enabled: true }));
const frost = () => ({
  rule_id: "frost_protection", label: "Antigelo a casa vuota", enabled: s.enabled, editable: true,
  params: { celsius: 8 }, limits: { celsius: { min: 5, max: 12 } },
});

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: true, isAdmin: false }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getRules: async () => ({ updated_at: "2026-11-12T08:00:00.000Z", rules: [frost()] }), updateRules: vi.fn() }) }));
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
  return screen.findByTestId("rule-card-frost_protection");
}

describe("Antigelo a casa vuota: la descrizione dice che cosa resta con la regola spenta (P-83, D31)", () => {
  it.each([true, false])("regola %s: la temperatura resta anche spenta; accesa vale anche contro lo spegnimento a mano", async (enabled) => {
    s.enabled = enabled;
    const c = await card();
    expect(c).toHaveAttribute("data-enabled", String(enabled));
    expect(c).toHaveTextContent("Con la casa vuota la caldaia va a questa temperatura anche con la regola spenta.");
    expect(c).toHaveTextContent("anche se qualcuno spegne la caldaia o abbassa la temperatura");
    expect(c).toHaveTextContent("avvisa se manca il sensore della stanza");
    expect(c).not.toHaveTextContent("mantiene almeno questa temperatura.");
  });
});
