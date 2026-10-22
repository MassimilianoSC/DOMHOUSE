import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import SettingsPage from "./SettingsPage";

// A platform manager without an organization (P-36): Settings makes no call to the organization routes, which would
// only answer 403 and leave two lines in the server's log at every opening; with an organization nothing changes.
const s = vi.hoisted(() => ({ me: null as unknown, calls: [] as string[] }));

vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ me: s.me, logout: vi.fn() }) }));
vi.mock("@/components/settings/AccountSettings", () => ({ AccountSettings: () => null }));

const ENV = { app_env: "staging", auth_mode: "firebase", fcm_enabled: false, instance_mode: "real" };
const PLATFORM_ONLY = { user: { uid: "p1", email: "piattaforma@hqe.it", display_name: "", platform_manager: true }, role: null, tenant: null, env: ENV };
const ADMIN = { user: { uid: "u1", email: "anna@fs.it", display_name: "", apartment_ids: "all" }, role: "admin", tenant: { tenant_id: "t1", name: "Demo" }, env: ENV };

beforeEach(() => {
  s.calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const path = new URL(url).pathname;
    s.calls.push(path);
    const body = path === "/app/push/status" ? { fcm_enabled: false, tokens: 0, prefs: { approvals: true, offline: true, decisions: false, bookings: true, summary: true } } : [];
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

describe("Impostazioni senza organizzazione (P-36)", () => {
  it("gestore della piattaforma senza organizzazione: nessuna chiamata agli appartamenti né alle notifiche", async () => {
    s.me = PLATFORM_ONLY;
    open();
    expect(await screen.findByTestId("settings-platform")).toBeInTheDocument();
    expect(screen.queryByTestId("settings-notifications")).toBeNull();
    await new Promise((r) => setTimeout(r, 50));
    expect(s.calls).not.toContain("/app/apartments");
    expect(s.calls).not.toContain("/app/push/status");
  });

  it("con un'organizzazione tutto come prima: appartamenti e notifiche", async () => {
    s.me = ADMIN;
    open();
    expect(await screen.findByTestId("settings-notifications")).toBeInTheDocument();
    await waitFor(() => expect(s.calls).toEqual(expect.arrayContaining(["/app/apartments", "/app/push/status"])));
  });
});
