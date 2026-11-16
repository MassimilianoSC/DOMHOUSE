import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { Device } from "@/api/types";
import { can } from "@/auth/permissions";
import { roleOf } from "@/auth/AuthProvider";
import { apartmentNav } from "@/components/layout/navItems";
import { fmtShortDateTime } from "@/lib/format";
import { useApartmentStore } from "@/store/apartmentStore";
import App from "@/App";
import DeviceStatusPage from "./DeviceStatusPage";

// «Stato dei dispositivi», first step (activation by the client §5, the committente's go of 15 Nov): one row per
// device with its state (in linea, offline da…, mai collegato), the last time seen and what to check. Only the data
// the site already gets; refused logins come later as one more column. Admins only, through the permission
// devices.status (one place: src/auth/permissions.ts).
const s = vi.hoisted(() => ({ me: null as unknown }));

vi.mock("@/auth/AuthProvider", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/auth/AuthProvider")>();
  return { ...mod, useAuth: () => ({ status: "authenticated", me: s.me, logout: vi.fn(), refreshMe: vi.fn() }), useRole: () => mod.roleOf(s.me as never) };
});
vi.mock("@/hooks/usePushBridge", () => ({ usePushBridge: () => {} }));
vi.mock("@/hooks/useApartmentStream", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/hooks/useApartmentStream")>()), useApartmentStream: () => {} }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const me = (role: string, suspended = false) => ({
  user: { uid: "u1", email: "anna@demo.it", display_name: "", apartment_ids: "all" },
  role,
  tenant: { tenant_id: "t1", name: "Demo", suspended },
  env: { app_env: "prod", auth_mode: "firebase", fcm_enabled: true, instance_mode: "real" },
  support: null,
  support_access: [],
});

const SUMMARY = { apartment_id: "apt-001", name: "Milano Centro", address: "", timezone: "Europe/Rome", enabled: true, online: true, simulated: false, apartment: null, health: null, contract_version: "1.0.5", features: ["apartment", "devices"], pending_approvals: 0, kwh_today: null };

function openApp(path: string) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const p = new URL(url).pathname;
    const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
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
  useApartmentStore.getState().reset("apt-001");
});

describe("Stato dei dispositivi: chi lo vede", () => {
  it("amministratore: voce «Stato dei dispositivi» nel menu dell'appartamento e pagina aperta", async () => {
    openApp("/a/apt-001/stato-dispositivi");
    expect(await screen.findByTestId("device-status-header")).toHaveTextContent("Stato dei dispositivi");
    await waitFor(() => expect(sidebarHas("deviceStatus")).toBe(true));
  });

  it.each(["operator", "viewer"])("%s: niente voce, e l'indirizzo dà «Pagina non trovata»", async (role) => {
    s.me = me(role);
    openApp("/a/apt-001/stato-dispositivi");
    expect(await screen.findByTestId("not-found")).toBeInTheDocument();
    expect(sidebarHas("deviceStatus")).toBe(false);
  });

  it("il permesso in un punto solo: amministratore sì; operatore, sola lettura e organizzazione sospesa no", () => {
    expect(can(roleOf(me("admin") as never), "devices.status")).toBe(true);
    expect(can(roleOf(me("operator") as never), "devices.status")).toBe(false);
    expect(can(roleOf(me("viewer") as never), "devices.status")).toBe(false);
    expect(can(roleOf(me("admin", true) as never), "devices.status")).toBe(false);
    expect(apartmentNav("x", false, true).map((i) => i.key)).toContain("deviceStatus");
    expect(apartmentNav("x", false, false).map((i) => i.key)).not.toContain("deviceStatus");
  });
});

const ago = (min: number) => new Date(Date.now() - min * 60_000).toISOString();
const ROOMS = [{ room_id: "soggiorno", name: "Soggiorno" }, { room_id: "camera", name: "Camera" }];
const device = (device_id: string, label: string, room_id: string, online: boolean, last_seen: string | null, capabilities: object) =>
  ({ device_id, label, room_id, online, last_seen, capabilities }) as Device;
const CALDAIA = device("caldaia", "Caldaia", "soggiorno", true, ago(1), { heating: { on: false, setpoint: 20 } });
const PRESA = device("presa", "Presa stufetta", "camera", false, ago(125), { switch: { on: false } });
const FINESTRA = device("finestra", "Finestra camera", "camera", false, null, { contact: { open: false, since: null } });
const HEALTH = (connector: "up" | "down") => ({ status: "ok", connector: { status: connector, connected_devices: 1, last_event_at: null }, database: { status: "ok" }, model_provider: { status: "ok", provider: "x" } }) as never;

function openPage(devices: Device[], health: unknown = HEALTH("up")) {
  useApartmentStore.getState().setSnapshot({ apartment: { timezone: "Europe/Rome" } as never, rooms: ROOMS as never, devices, health: health as never });
  render(<DeviceStatusPage />);
}

describe("Stato dei dispositivi: cosa mostra", () => {
  it("tutti in linea: «In linea», l'ultima volta visto e «Niente da fare»", () => {
    openPage([CALDAIA]);
    expect(screen.getByTestId("device-status-summary")).toHaveTextContent("In linea: 1 · Offline: 0 · Mai collegati: 0");
    expect(screen.getByTestId("device-status-caldaia-status")).toHaveTextContent("In linea");
    expect(screen.getByTestId("device-status-caldaia-last-seen")).toHaveTextContent(fmtShortDateTime(CALDAIA.last_seen, "Europe/Rome"));
    expect(screen.getByTestId("device-status-caldaia-advice")).toHaveTextContent("Niente da fare");
    expect(screen.getByTestId("device-status-caldaia-room")).toHaveTextContent("Soggiorno");
  });

  it("uno offline e uno mai collegato: prima loro, con lo stato, «Mai» e il «Cosa fare» giusto per Shelly e sensore", () => {
    openPage([CALDAIA, PRESA, FINESTRA]);
    expect(screen.getByTestId("device-status-summary")).toHaveTextContent("In linea: 1 · Offline: 1 · Mai collegati: 1");
    const rows = within(screen.getByTestId("device-status-list")).getAllByRole("listitem");
    expect(rows.map((r) => r.getAttribute("data-status"))).toEqual(["never", "offline", "online"]);
    expect(screen.getByTestId("device-status-finestra-status")).toHaveTextContent("Mai collegato");
    expect(screen.getByTestId("device-status-finestra-last-seen")).toHaveTextContent("Mai");
    expect(screen.getByTestId("device-status-finestra-advice")).toHaveTextContent("Non si è mai fatto sentire. Controlla che abbia la batteria");
    expect(screen.getByTestId("device-status-presa-status")).toHaveTextContent("Offline da 2 ore");
    expect(screen.getByTestId("device-status-presa-advice")).toHaveTextContent("Prima funzionava, ora non risponde. Controlla che abbia corrente");
    expect(screen.queryByTestId("device-status-connector-down")).toBeNull();
    expect(screen.queryByTestId("device-status-unreachable")).toBeNull();
  });

  it("collegamento ai dispositivi fermo: lo dice in alto, e su ogni dispositivo che non è colpa sua", () => {
    openPage([PRESA, FINESTRA], HEALTH("down"));
    expect(screen.getByTestId("device-status-connector-down")).toHaveTextContent("Il collegamento fra il sistema domotico e i dispositivi è fermo");
    for (const id of ["presa", "finestra"]) expect(screen.getByTestId(`device-status-${id}-advice`)).toHaveTextContent("Non è un problema di questo dispositivo");
  });

  it("sistema domotico che non risponde: l'ultimo stato ricevuto, detto in alto", () => {
    useApartmentStore.getState().setSnapshot({ rooms: ROOMS as never, devices: [PRESA], health: HEALTH("up") });
    useApartmentStore.getState().setUnreachable("apt-001");
    render(<DeviceStatusPage />);
    expect(screen.getByTestId("device-status-unreachable")).toHaveTextContent("Il sistema domotico dell'appartamento non risponde");
    expect(screen.queryByTestId("device-status-connector-down")).toBeNull();
    expect(screen.getByTestId("device-status-presa-advice")).toHaveTextContent("Non è un problema di questo dispositivo");
  });

  it("nessun dispositivo: lo dice", () => {
    openPage([]);
    expect(screen.getByTestId("device-status-empty")).toHaveTextContent("Nessun dispositivo in questo appartamento.");
  });

  it("batteria: colonna «Batteria», «—» per lo Shelly, giallo sotto il 20 %, conteggio nel riepilogo e prima in elenco", () => {
    const withBattery = (d: Device, battery_percent: number | null) => ({ ...d, battery_percent }) as Device;
    const BAGNO = withBattery(device("bagno", "Sensore bagno", "soggiorno", true, ago(1), { temperature: { celsius: 21 } }), 15);
    const SALA = withBattery(device("sala", "Sensore sala", "soggiorno", true, ago(1), { temperature: { celsius: 20 } }), 78);
    openPage([CALDAIA, SALA, BAGNO]);
    expect(screen.getByTestId("device-status-summary")).toHaveTextContent("In linea: 3 · Offline: 0 · Mai collegati: 0 · Batterie da cambiare: 1");
    expect(screen.getByTestId("device-status-bagno-battery")).toHaveTextContent("15 %, da cambiare presto");
    expect(screen.getByTestId("device-status-bagno-battery").querySelector("[data-battery='low']")).not.toBeNull();
    expect(screen.getByTestId("device-status-sala-battery")).toHaveTextContent("78 %");
    expect(screen.getByTestId("device-status-sala-battery").querySelector("[data-battery='low']")).toBeNull();
    expect(screen.getByTestId("device-status-caldaia-battery")).toHaveTextContent("—");
    expect(screen.getByTestId("device-status-bagno-advice")).toHaveTextContent("Batteria quasi scarica: cambiala presto");
    const rows = within(screen.getByTestId("device-status-list")).getAllByRole("listitem");
    expect(rows[0]).toHaveAttribute("data-testid", "device-status-row-bagno");
  });

  it("batteria: senza il dato (motore che non lo manda ancora) «non nota», e nel riepilogo nessun conteggio", () => {
    openPage([device("x", "Sensore", "camera", true, ago(1), { temperature: { celsius: 18 } })]);
    expect(screen.getByTestId("device-status-x-battery")).toHaveTextContent("non nota");
    expect(screen.getByTestId("device-status-summary")).not.toHaveTextContent("Batterie");
  });

  it("stanza che non c'è più: «Senza stanza», come nella Panoramica", () => {
    openPage([device("x", "Sensore", "cantina", true, ago(1), { temperature: { celsius: 18 } })]);
    expect(screen.getByTestId("device-status-x-room")).toHaveTextContent("Senza stanza");
  });
});
