import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";
import { t } from "@/i18n";
import App from "@/App";

// Simulatore (D-97): it follows the apartment, not the environment: admins only, on a simulated apartment, in
// production too. The reset needs the built-in engine; after it everything of the apartment is read again.
const s = vi.hoisted(() => ({ me: null as unknown, simulated: true, url: "mock://builtin", calls: [] as string[], resetStatus: 204, resync: vi.fn(async () => {}) }));

vi.mock("@/auth/AuthProvider", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/auth/AuthProvider")>();
  return { ...mod, useAuth: () => ({ status: "authenticated", me: s.me, logout: vi.fn(), refreshMe: vi.fn() }), useRole: () => mod.roleOf(s.me as never) };
});
vi.mock("@/hooks/usePushBridge", () => ({ usePushBridge: () => {} }));
vi.mock("@/hooks/useApartmentStream", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/hooks/useApartmentStream")>()), useApartmentStream: () => {}, resync: s.resync }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const me = (role: string) => ({
  user: { uid: "u1", email: "anna@demo.it", display_name: "", apartment_ids: "all" },
  role,
  tenant: { tenant_id: "t1", name: "Demo" },
  env: { app_env: "prod", auth_mode: "firebase", fcm_enabled: true, instance_mode: "real" },
  support: null,
  support_access: [],
});

const SUMMARY = () => ({ apartment_id: "apt-001", name: "Milano Centro", address: "", timezone: "Europe/Rome", enabled: true, online: true, simulated: s.simulated, apartment: null, health: null, contract_version: "1.0.4", features: ["apartment", "devices"], pending_approvals: 0, kwh_today: null });

function bff() {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    s.calls.push(`${init?.method ?? "GET"} ${path}`);
    const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
    if (path === "/app/apartments/apt-001") return json(SUMMARY());
    if (path === "/app/apartments") return json([SUMMARY()]);
    if (path === "/app/admin/apartments") return json([{ apartment_id: "apt-001", name: "Milano Centro", address: "", timezone: "Europe/Rome", instance_url: s.url, port: null, enabled: true, italianway_id: null, enabled_features: null, simulated: s.simulated }]);
    if (path === "/app/apartments/apt-001/simulator/reset") return s.resetStatus === 204 ? new Response(null, { status: 204 }) : json({ error: "reset_not_available", message: "Ripristino non disponibile" }, s.resetStatus);
    return json([]);
  }));
}

function open(path: string) {
  bff();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const sidebarHas = (key: string) => within(screen.getByRole("complementary")).queryByTestId(`sidebar-nav-${key}`) !== null;

beforeEach(() => {
  vi.clearAllMocks();
  s.me = me("admin");
  s.simulated = true;
  s.url = "mock://builtin";
  s.calls = [];
  s.resetStatus = 204;
  Element.prototype.scrollIntoView = vi.fn();
});

describe("Simulatore: chi lo vede", () => {
  it("admin, appartamento simulato, anche in produzione: voce nel menu e pagina aperta con l'etichetta «Dimostrativo»", async () => {
    open("/a/apt-001/simulatore");
    expect(await screen.findByTestId("simulator-header")).toBeInTheDocument();
    expect(screen.getByTestId("simulator-demo-badge")).toHaveTextContent(t("apartments.demo"));
    await waitFor(() => expect(sidebarHas("simulator")).toBe(true));
  });

  it("appartamento reale: nessuna voce, e l'indirizzo dà «Pagina non trovata»", async () => {
    s.simulated = false;
    open("/a/apt-001/simulatore");
    expect(await screen.findByTestId("not-found")).toBeInTheDocument();
    expect(sidebarHas("simulator")).toBe(false);
  });

  it("operatore su un appartamento simulato: niente Simulatore", async () => {
    s.me = me("operator");
    open("/a/apt-001/simulatore");
    expect(await screen.findByTestId("not-found")).toBeInTheDocument();
    expect(sidebarHas("simulator")).toBe(false);
  });
});

describe("Simulatore: ripristino dello stato iniziale", () => {
  async function openReset() {
    open("/a/apt-001/simulatore");
    const btn = await screen.findByTestId("sim-reset-btn");
    await waitFor(() => expect(btn).toBeEnabled());
    await act(async () => {
      fireEvent.click(btn);
    });
    return screen.getByTestId("sim-reset-dialog");
  }

  it("conferma esplicita con quello che torna com'era e quello che resta; annullando non parte niente", async () => {
    const dialog = await openReset();
    expect(dialog).toHaveTextContent(t("simulator.resetTitle", { name: "Milano Centro" }));
    expect(dialog).toHaveTextContent(t("simulator.resetText"));
    // N5: every archived stay of the apartment goes, also the ones from Italianway; never "test stays only"
    expect(dialog).toHaveTextContent("anche quelli arrivati da Italianway");
    expect(dialog).not.toHaveTextContent("soggiorni di prova");
    await act(async () => {
      fireEvent.click(screen.getByTestId("sim-reset-cancel"));
    });
    expect(s.calls).not.toContain("POST /app/apartments/apt-001/simulator/reset");
  });

  it("confermato: POST del ripristino, avviso, e l'appartamento viene riletto come dopo una riconnessione", async () => {
    await openReset();
    const before = s.calls.filter((c) => c === "GET /app/apartments/apt-001").length;
    await act(async () => {
      fireEvent.click(screen.getByTestId("sim-reset-confirm"));
    });
    expect(s.calls).toContain("POST /app/apartments/apt-001/simulator/reset");
    expect(toast.success).toHaveBeenCalledWith(t("simulator.resetDone"));
    await waitFor(() => expect(s.resync).toHaveBeenCalledWith("apt-001"));
    await waitFor(() => expect(s.calls.filter((c) => c === "GET /app/apartments/apt-001").length).toBeGreaterThan(before));
  });

  it("simulato su un motore vero: pulsante disattivato, con la spiegazione", async () => {
    s.url = "http://10.198.0.2:8101";
    open("/a/apt-001/simulatore");
    expect(await screen.findByTestId("sim-reset-unavailable")).toHaveTextContent(t("simulator.resetUnavailable"));
    expect(screen.getByTestId("sim-reset-btn")).toBeDisabled();
  });

  it("rifiuto del server: il suo messaggio, nessuna rilettura", async () => {
    s.resetStatus = 409;
    await openReset();
    await act(async () => {
      fireEvent.click(screen.getByTestId("sim-reset-confirm"));
    });
    expect(toast.error).toHaveBeenCalledWith("Ripristino non disponibile", expect.anything());
    expect(s.resync).not.toHaveBeenCalled();
  });
});
