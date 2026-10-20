import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, configure, fireEvent, getConfig, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { t } from "@/i18n";
import App from "@/App";

// D-103: no bottom bar on the phone. A three-line button opens a side menu with the logo, every page (general and,
// inside an apartment, the apartment's, with today's visibility rules) and, at the bottom, the person and «Esci».
const s = vi.hoisted(() => ({ me: null as unknown, simulated: false }));

// Every test here mounts the whole app (routes, lazy pages, queries): on a loaded machine that alone took 11 s (P-64,
// D-112). The behaviour checked is the same; only the time allowed grows: 20 s per test, 5 s for each wait on an
// element (findBy..., waitFor), instead of 5 s and 1 s.
vi.setConfig({ testTimeout: 20_000 });
const defaultWait = getConfig().asyncUtilTimeout;
beforeAll(() => configure({ asyncUtilTimeout: 5_000 }));
afterAll(() => configure({ asyncUtilTimeout: defaultWait }));

vi.mock("@/auth/AuthProvider", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/auth/AuthProvider")>();
  return { ...mod, useAuth: () => ({ status: "authenticated", me: s.me, logout: vi.fn(), refreshMe: vi.fn() }), useRole: () => mod.roleOf(s.me as never) };
});
vi.mock("@/hooks/usePushBridge", () => ({ usePushBridge: () => {} }));
vi.mock("@/hooks/useApartmentStream", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/hooks/useApartmentStream")>()), useApartmentStream: () => {} }));

const me = (role: string, platform = false) => ({
  user: { uid: "u1", email: "anna@demo.it", display_name: "", apartment_ids: "all", platform_manager: platform },
  role,
  tenant: { tenant_id: "t1", name: "Demo" },
  env: { app_env: "staging", auth_mode: "dev", fcm_enabled: false, instance_mode: "mock" },
  support: null,
  support_access: [],
});

const SUMMARY = () => ({
  apartment_id: "apt-001", name: "Milano Centro", address: "", timezone: "Europe/Rome", enabled: true, online: true, simulated: s.simulated,
  apartment: null, health: null, contract_version: "1.0.4", features: ["apartment", "devices", "approvals", "decisions", "energy", "schedule", "rules", "ask"],
  pending_approvals: 0, kwh_today: null,
});

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

function open(path: string) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const p = new URL(url).pathname;
    const body = p === "/app/apartments/apt-001" ? SUMMARY() : p === "/app/apartments" ? [SUMMARY()] : [];
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const menuButton = () => screen.getByTestId("mobile-menu-btn");
const drawer = () => screen.getByTestId("mobile-menu");
const openMenu = async () => {
  await act(async () => {
    fireEvent.click(menuButton());
  });
  return drawer();
};
const drawerKeys = () => within(drawer()).queryAllByRole("link").map((a) => a.getAttribute("data-testid"));

beforeEach(() => {
  s.me = me("admin");
  s.simulated = false;
  Element.prototype.scrollIntoView = vi.fn();
});

describe("telefono: niente barra in basso, menu a scomparsa (D-103)", () => {
  it("la barra in basso non c'è più; in alto il pulsante «Apri il menu», chiuso", async () => {
    open("/a/apt-001");
    await screen.findByTestId("mobile-menu-btn");
    expect(screen.queryByTestId("bottom-nav")).not.toBeInTheDocument();
    expect(menuButton()).toHaveAccessibleName(t("nav.openMenu"));
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("mobile-menu")).not.toBeInTheDocument();
  });

  it("aperto dentro un appartamento: logo, tutte le pagine generali e dell'appartamento, la persona con il ruolo, «Esci»", async () => {
    open("/a/apt-001");
    await waitFor(() => expect(within(screen.getByRole("complementary")).queryByTestId("sidebar-nav-energy")).not.toBeNull());
    const menu = await openMenu();
    expect(menuButton()).toHaveAttribute("aria-expanded", "true");
    expect(within(menu).getByTestId("mobile-menu-logo")).toBeInTheDocument();
    expect(drawerKeys()).toEqual([
      "drawer-nav-apartments",
      "drawer-nav-overview", "drawer-nav-approvals", "drawer-nav-decisions", "drawer-nav-energy", "drawer-nav-schedule", "drawer-nav-rules", "drawer-nav-assistant",
      "drawer-nav-admin", "drawer-nav-settings",
    ]);
    expect(within(menu).getByTestId("drawer-user-role")).toHaveTextContent(/^Amministratore · Demo$/);
    expect(within(menu).getByTestId("drawer-logout-btn")).toHaveTextContent(t("nav.logout"));
  });

  it("stesse regole di oggi: Simulatore solo sui dimostrativi; gestore anche con la seconda riga del ruolo", async () => {
    s.simulated = true;
    s.me = me("admin", true);
    open("/a/apt-001");
    await waitFor(() => expect(within(screen.getByRole("complementary")).queryByTestId("sidebar-nav-simulator")).not.toBeNull());
    const menu = await openMenu();
    expect(drawerKeys()).toContain("drawer-nav-simulator");
    expect(drawerKeys()).toContain("drawer-nav-organizations");
    expect(within(menu).getByTestId("drawer-user-platform")).toHaveTextContent(t("roles.platform"));
  });

  it("la pagina aperta è evidenziata (aria-current)", async () => {
    open("/a/apt-001/consumi");
    await waitFor(() => expect(within(screen.getByRole("complementary")).queryByTestId("sidebar-nav-energy")).not.toBeNull());
    const menu = await openMenu();
    expect(within(menu).getByTestId("drawer-nav-energy")).toHaveAttribute("aria-current", "page");
    expect(within(menu).getByTestId("drawer-nav-overview")).not.toHaveAttribute("aria-current");
  });

  it("scelta una pagina: ci va e il menu si chiude", async () => {
    open("/a/apt-001");
    await waitFor(() => expect(within(screen.getByRole("complementary")).queryByTestId("sidebar-nav-energy")).not.toBeNull());
    const menu = await openMenu();
    await act(async () => {
      fireEvent.click(within(menu).getByTestId("drawer-nav-apartments")); // a page already loaded: no lazy chunk to wait for
    });
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/$/);
    await waitFor(() => expect(screen.queryByTestId("mobile-menu")).not.toBeInTheDocument());
    expect(menuButton()).toHaveAttribute("aria-expanded", "false");
  });

  it("Esc chiude il menu e il focus torna al pulsante; da aperto il focus è dentro il menu", async () => {
    open("/");
    await screen.findByTestId("mobile-menu-btn");
    const menu = await openMenu();
    await waitFor(() => expect(menu.contains(document.activeElement)).toBe(true));
    await act(async () => {
      fireEvent.keyDown(document.activeElement ?? menu, { key: "Escape" });
    });
    await waitFor(() => expect(screen.queryByTestId("mobile-menu")).not.toBeInTheDocument());
    await waitFor(() => expect(document.activeElement).toBe(menuButton()));
  });

  it("il pulsante «Chiudi il menu» lo chiude", async () => {
    open("/");
    await screen.findByTestId("mobile-menu-btn");
    const menu = await openMenu();
    await act(async () => {
      fireEvent.click(within(menu).getByRole("button", { name: t("nav.closeMenu") }));
    });
    await waitFor(() => expect(screen.queryByTestId("mobile-menu")).not.toBeInTheDocument());
  });

  it("sul computer resta la barra laterale fissa, con le stesse voci", async () => {
    open("/a/apt-001");
    await waitFor(() => expect(within(screen.getByRole("complementary")).queryByTestId("sidebar-nav-energy")).not.toBeNull());
    expect(within(screen.getByRole("complementary")).getByTestId("sidebar-user-role")).toHaveTextContent(/^Amministratore · Demo$/);
    expect(within(screen.getByRole("complementary")).getByTestId("sidebar-logout-btn")).toBeInTheDocument();
  });
});
