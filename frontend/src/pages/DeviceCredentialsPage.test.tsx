import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { DeviceCredential } from "@/api/deviceCredentials";
import { can } from "@/auth/permissions";
import { roleOf } from "@/auth/AuthProvider";
import { apartmentNav } from "@/components/layout/navItems";
import { useApartmentStore } from "@/store/apartmentStore";
import App from "@/App";

// A3, «Credenziali dei dispositivi» (docs/proposta-a3-sito.md §1–§3, screens approved by the committente, 1182): the
// page of an apartment, for admins only (permission devices.credentials), with the registered devices and their state;
// the revoked ones in a closed section at the bottom.
const s = vi.hoisted(() => ({ me: null as unknown, items: [] as unknown[] }));

vi.mock("@/auth/AuthProvider", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/auth/AuthProvider")>();
  return { ...mod, useAuth: () => ({ status: "authenticated", me: s.me, logout: vi.fn(), refreshMe: vi.fn() }), useRole: () => mod.roleOf(s.me as never) };
});
vi.mock("@/hooks/usePushBridge", () => ({ usePushBridge: () => {} }));
vi.mock("@/hooks/useApartmentStream", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/hooks/useApartmentStream")>()), useApartmentStream: () => {} }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const me = (role: string, suspended = false) => ({
  user: { uid: "u1", email: "anna@esempio.it", display_name: "", apartment_ids: "all" },
  role,
  tenant: { tenant_id: "t1", name: "Prova", suspended },
  env: { app_env: "prod", auth_mode: "firebase", fcm_enabled: true, instance_mode: "real" },
  support: null,
  support_access: [],
});

const SUMMARY = { apartment_id: "apt-001", name: "Milano Centro", address: "", timezone: "Europe/Rome", enabled: true, online: true, simulated: false, apartment: null, health: null, contract_version: "1.0.5", features: ["apartment", "devices"], pending_approvals: 0, kwh_today: null };

const cred = (device_id: string, stato: DeviceCredential["stato"], azione: DeviceCredential["azione"] = null, extra: Partial<DeviceCredential> = {}): DeviceCredential => ({
  device_id,
  name: null,
  stato,
  version: 2,
  updated_at: "2026-11-19T15:12:00Z",
  updated_by: "Giulia Rossi",
  azione,
  engine_device_id: null,
  op: null,
  connection: { server: "mqtt.example.test:8883", ssl_ca: "ca.pem", client_id: `apt-001.${device_id}`, user: `apt-001.${device_id}`, topic_prefix: `apt-001/${device_id}` },
  ...extra,
});

function openApp(path: string) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const p = new URL(url).pathname;
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
    if (p === "/app/apartments/apt-001/device-credentials") return json({ items: s.items });
    if (p === "/app/apartments/apt-001") return json(SUMMARY);
    if (p === "/app/apartments") return json([SUMMARY]);
    return json([]);
  }));
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
  s.items = [];
  useApartmentStore.getState().reset("apt-001");
});

describe("Credenziali dei dispositivi: chi le vede", () => {
  it("amministratore: voce nel menu dell'appartamento e pagina aperta", async () => {
    openApp("/a/apt-001/credenziali");
    expect(await screen.findByTestId("credentials-header")).toHaveTextContent("Credenziali dei dispositivi");
    await waitFor(() => expect(sidebarHas("credentials")).toBe(true));
  });

  it.each(["operator", "viewer"])("%s (anche il gestore con l'accesso di assistenza, che è un operatore): niente voce e «Pagina non trovata»", async (role) => {
    s.me = me(role);
    openApp("/a/apt-001/credenziali");
    expect(await screen.findByTestId("not-found")).toBeInTheDocument();
    expect(sidebarHas("credentials")).toBe(false);
  });

  it("il permesso in un punto solo: amministratore sì; operatore, sola lettura e organizzazione sospesa no", () => {
    expect(can(roleOf(me("admin") as never), "devices.credentials")).toBe(true);
    expect(can(roleOf(me("operator") as never), "devices.credentials")).toBe(false);
    expect(can(roleOf(me("viewer") as never), "devices.credentials")).toBe(false);
    expect(can(roleOf(me("admin", true) as never), "devices.credentials")).toBe(false);
    expect(apartmentNav("x", false, false, true).map((i) => i.key)).toContain("credentials");
    expect(apartmentNav("x", false, false, false).map((i) => i.key)).not.toContain("credentials");
  });
});

describe("l'elenco", () => {
  it("vuoto: dice di registrare ogni Shelly prima di montarlo", async () => {
    openApp("/a/apt-001/credenziali");
    expect(await screen.findByTestId("credentials-empty")).toHaveTextContent("Nessun dispositivo registrato");
    expect(screen.getByTestId("credentials-register-btn")).toHaveTextContent("Registra un dispositivo");
  });

  it("ogni stato con la sua etichetta e la sua riga; prima i non applicati, poi in corso, poi i pronti", async () => {
    s.items = [
      cred("shellyplugmg3-pronto", "pronto"),
      cred("shelly1pm-attesa", "in_attesa", "registra"),
      cred("shellyhtg3-cambio", "cambio_in_corso", "rigenera"),
      cred("shellyi4-ko", "non_applicato", "revoca", { op: { op_id: "7c41e9a2-0000-4000-8000-000000000001", stato: "scartato", messaggio: "Ordine scartato dal sistema domotico" } }),
    ];
    openApp("/a/apt-001/credenziali");
    const rows = await screen.findAllByTestId(/^credential-row-/);
    expect(rows.map((r) => r.dataset.testid)).toEqual(["credential-row-shellyi4-ko", "credential-row-shelly1pm-attesa", "credential-row-shellyhtg3-cambio", "credential-row-shellyplugmg3-pronto"]);
    expect(screen.getByTestId("credential-state-shellyplugmg3-pronto")).toHaveTextContent("Pronto");
    expect(screen.getByTestId("credential-row-shellyplugmg3-pronto")).toHaveTextContent("Può collegarsi.");
    expect(screen.getByTestId("credential-state-shelly1pm-attesa")).toHaveTextContent("In preparazione");
    expect(screen.getByTestId("credential-state-shellyhtg3-cambio")).toHaveTextContent("Cambio password in corso");
    expect(screen.getByTestId("credential-row-shellyhtg3-cambio")).toHaveTextContent("vale ancora la password vecchia");
    const ko = screen.getByTestId("credential-row-shellyi4-ko");
    expect(screen.getByTestId("credential-state-shellyi4-ko")).toHaveTextContent("Non applicato");
    expect(ko).toHaveTextContent("La revoca non è arrivata al sistema domotico: il dispositivo può ancora collegarsi.");
    expect(ko).toHaveTextContent("Ordine scartato dal sistema domotico");
    expect(within(ko).getByTestId("credential-op-shellyi4-ko")).toHaveAttribute("data-correlation-id", "7c41e9a2-0000-4000-8000-000000000001");
    // chi e quando
    expect(screen.getByTestId("credential-row-shellyplugmg3-pronto")).toHaveTextContent("Giulia Rossi");
  });

  it("«Non applicato» dice cosa non è stato applicato, secondo l'azione in attesa", async () => {
    s.items = [cred("d-reg", "non_applicato", "registra"), cred("d-rig", "non_applicato", "rigenera")];
    openApp("/a/apt-001/credenziali");
    expect(await screen.findByTestId("credential-row-d-reg")).toHaveTextContent("La registrazione non è arrivata al sistema domotico: il dispositivo non può ancora collegarsi.");
    expect(screen.getByTestId("credential-row-d-rig")).toHaveTextContent("La password nuova non è arrivata al sistema domotico: vale ancora quella vecchia.");
  });

  it("i revocati stanno in una sezione chiusa in fondo, con il numero; aperta mostra data e «Registra di nuovo»", async () => {
    s.items = [cred("d-attivo", "pronto"), cred("d-rev-1", "revocato", null, { updated_at: "2026-11-12T09:00:00Z" }), cred("d-rev-2", "revocato")];
    openApp("/a/apt-001/credenziali");
    const toggle = await screen.findByTestId("credentials-revoked-toggle");
    expect(toggle).toHaveTextContent("Revocati (2)");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("credential-row-d-rev-1")).toBeNull();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const row = screen.getByTestId("credential-row-d-rev-1");
    expect(row).toHaveTextContent("Revocato il 12 nov 2026");
    expect(within(row).getByTestId("credential-reregister-d-rev-1")).toHaveTextContent("Registra di nuovo");
  });

  it("nessun revocato: nessuna sezione", async () => {
    s.items = [cred("d-attivo", "pronto")];
    openApp("/a/apt-001/credenziali");
    await screen.findByTestId("credential-row-d-attivo");
    expect(screen.queryByTestId("credentials-revoked-toggle")).toBeNull();
  });

  it("i pulsanti della riga seguono lo stato: «Riprova» solo sui non applicati, «Dati di collegamento» sempre", async () => {
    s.items = [cred("d-ko", "non_applicato", "revoca"), cred("d-ok", "pronto"), cred("d-rev", "revocato")];
    openApp("/a/apt-001/credenziali");
    await screen.findByTestId("credential-row-d-ko");
    expect(screen.getByTestId("credential-retry-d-ko")).toBeInTheDocument();
    expect(screen.queryByTestId("credential-retry-d-ok")).toBeNull();
    expect(screen.getByTestId("credential-connection-d-ko")).toBeInTheDocument();
    expect(screen.getByTestId("credential-connection-d-ok")).toBeInTheDocument();
    // a revoked notApplied revoke has no «⋯» menu: only «Riprova» closes it
    expect(screen.queryByTestId("credential-menu-d-ko")).toBeNull();
    expect(screen.getByTestId("credential-menu-d-ok")).toBeInTheDocument();
  });
});
