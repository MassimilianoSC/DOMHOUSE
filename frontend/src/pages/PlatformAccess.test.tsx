import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { t } from "@/i18n";
import App from "@/App";

// Platform role (P-36, D-61a): "Organizzazioni" only for platform managers, a separate guard from AdminOnly, and a
// manager outside any organization sees only Organizzazioni and Impostazioni. A normal admin sees the app as before.
const s = vi.hoisted(() => ({ me: null as unknown }));

vi.mock("@/auth/AuthProvider", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/auth/AuthProvider")>();
  return { ...mod, useAuth: () => ({ status: "authenticated", me: s.me, logout: vi.fn(), refreshMe: vi.fn() }), useRole: () => mod.roleOf(s.me as never) };
});
vi.mock("@/hooks/usePushBridge", () => ({ usePushBridge: () => {} }));

const me = (role: string | null, platform: boolean, tenant = true) => ({
  user: { uid: "u1", email: "gestore@demo.it", display_name: "", platform_manager: platform, apartment_ids: "all" },
  role,
  tenant: tenant ? { tenant_id: "t1", name: "Demo" } : null,
  env: { app_env: "dev", auth_mode: "dev", fcm_enabled: false, simulator: true, instance_mode: "mock" },
});

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}

const TENANTS = [{ tenant_id: "t1", name: "Demo", created_at: "2026-10-01T08:00:00Z", first_admin: null }];

function open(path: string) {
  // The organizations list answers one organization, any other call an empty list.
  const answer = (url: string) => (url.endsWith("/app/platform/tenants") ? TENANTS : []);
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => new Response(JSON.stringify(answer(String(input))), { status: 200, headers: { "Content-Type": "application/json" } })));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <App />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const sidebarKeys = () => within(screen.getByRole("complementary")).queryAllByRole("link").map((a) => a.getAttribute("data-testid"));

describe("ruolo di piattaforma: menu e accesso", () => {
  it("amministratore normale: nessuna voce «Organizzazioni», l'indirizzo scritto a mano dà «Pagina non trovata»", async () => {
    s.me = me("admin", false);
    open("/organizzazioni");
    expect(await screen.findByTestId("not-found")).toHaveTextContent(t("errors.notFound"));
    expect(screen.queryByTestId("organizations-header")).not.toBeInTheDocument();
    expect(sidebarKeys()).toEqual(["sidebar-nav-apartments", "sidebar-nav-admin", "sidebar-nav-settings"]);
    expect(screen.getByTestId("sidebar-user-role")).toHaveTextContent(/^Amministratore · Demo$/);
    expect(screen.queryByTestId("sidebar-user-platform")).not.toBeInTheDocument(); // one role, one line (D-82)
  });

  it("gestore della piattaforma che è anche amministratore: vede «Organizzazioni», anche nel menu del telefono", async () => {
    s.me = me("admin", true);
    open("/organizzazioni");
    expect(await screen.findByTestId("organizations-header")).toHaveTextContent(t("platform.title"));
    // D-82: both roles in the sidebar, the organization's on the first line, the platform's below
    expect(screen.getByTestId("sidebar-user-role")).toHaveTextContent(/^Amministratore · Demo$/);
    expect(screen.getByTestId("sidebar-user-platform")).toHaveTextContent(/^Gestore della piattaforma$/);
    expect(sidebarKeys()).toEqual(["sidebar-nav-apartments", "sidebar-nav-admin", "sidebar-nav-organizations", "sidebar-nav-settings"]);
    // D-103: on the phone the same entry is in the side menu (no bottom bar any more)
    await act(async () => {
      fireEvent.click(screen.getByTestId("mobile-menu-btn"));
    });
    expect(within(screen.getByTestId("mobile-menu")).getByTestId("drawer-nav-organizations")).toHaveAttribute("href", "/organizzazioni");
    // D-78: the tab says «Elenco organizzazioni», the menu entry stays «Organizzazioni».
    expect(screen.getByTestId("platform-tab-tenants")).toHaveTextContent("Elenco organizzazioni");
    expect(screen.getByTestId("sidebar-nav-organizations")).toHaveTextContent(t("nav.organizations"));
    expect(t("nav.organizations")).toBe("Organizzazioni");
  });

  it("gestore senza organizzazione: solo Organizzazioni e Impostazioni; «/» porta a Organizzazioni", async () => {
    s.me = me(null, true, false);
    open("/");
    expect(await screen.findByTestId("organizations-header")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/organizzazioni");
    expect(sidebarKeys()).toEqual(["sidebar-nav-organizations", "sidebar-nav-settings"]);
    expect(screen.getByTestId("sidebar-user-role")).toHaveTextContent(t("roles.platform"));
    expect(screen.queryByTestId("sidebar-user-platform")).not.toBeInTheDocument(); // not twice (D-82)
  });

  it("lettore con il ruolo di piattaforma: «Organizzazioni» sì, Amministrazione no", async () => {
    s.me = me("viewer", true);
    open("/organizzazioni");
    expect(await screen.findByTestId("organizations-header")).toBeInTheDocument();
    expect(sidebarKeys()).toEqual(["sidebar-nav-apartments", "sidebar-nav-organizations", "sidebar-nav-settings"]);
  });
});

describe("«+ Appartamento» del gestore: Organizzazioni con gli appartamenti della sua organizzazione già aperti (D-77)", () => {
  it("arrivando con ?appartamenti=t1 la lista di quell'organizzazione è aperta, e l'indirizzo torna pulito", async () => {
    s.me = me("admin", true);
    open("/organizzazioni?appartamenti=t1");
    expect(await screen.findByTestId("platform-apartments-empty-t1")).toBeInTheDocument();
    expect(screen.getByTestId("tenant-apartments-btn-t1")).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/organizzazioni$/);
  });

  it("senza il parametro le liste restano chiuse", async () => {
    s.me = me("admin", true);
    open("/organizzazioni");
    expect(await screen.findByTestId("tenant-apartments-btn-t1")).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("platform-apartments-empty-t1")).not.toBeInTheDocument();
  });
});

describe("gestore della piattaforma con la propria organizzazione sospesa (P-50, D-85)", () => {
  it("«/» porta a Organizzazioni; niente Appartamenti né Amministrazione; avviso e «sospesa» nella barra laterale", async () => {
    s.me = { ...me("admin", true), tenant: { tenant_id: "t1", name: "Demo", suspended: true } };
    open("/");
    expect(await screen.findByTestId("organizations-header")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("/organizzazioni");
    expect(sidebarKeys()).toEqual(["sidebar-nav-organizations", "sidebar-nav-settings"]);
    expect(screen.getByTestId("own-tenant-suspended")).toHaveTextContent(t("platform.ownSuspended", { name: "Demo" }));
    expect(screen.getByTestId("sidebar-user-role")).toHaveTextContent(t("platform.suspendedBadge").toLowerCase());
  });

  it("l'indirizzo di Amministrazione scritto a mano non apre la pagina", async () => {
    s.me = { ...me("admin", true), tenant: { tenant_id: "t1", name: "Demo", suspended: true } };
    open("/admin");
    expect(await screen.findByTestId("where")).toHaveTextContent(/^\/(organizzazioni)?$/);
    expect(screen.queryByTestId("admin-header")).not.toBeInTheDocument();
  });
});
