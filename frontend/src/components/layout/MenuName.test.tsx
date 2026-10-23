import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { create } from "zustand";
import App from "@/App";

// D-170, staging test 1 of lot 31: the name saved in Settings › Account shows in the menu right after «Salva», without
// reloading (the site rereads /app/me). The signed-in person lives in a small store, so refreshMe re-renders both
// the menu and the form, as the real AuthProvider does.
const me0 = {
  user: { uid: "u1", email: "m.cracchiolo@hqe.it", display_name: "", apartment_ids: "all", platform_manager: false },
  role: "operator",
  tenant: { tenant_id: "t1", name: "Flatsharing" },
  env: { app_env: "staging", auth_mode: "firebase", fcm_enabled: false, instance_mode: "real" },
  support: null,
  support_access: [],
};
const useMe = create<{ me: typeof me0; saved: string }>(() => ({ me: me0, saved: "" }));

vi.mock("@/auth/AuthProvider", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/auth/AuthProvider")>();
  const useAuth = () => {
    const me = useMe((s) => s.me);
    return {
      status: "authenticated",
      me,
      providers: ["google.com"],
      logout: vi.fn(),
      // the server answers with what was saved, as GET /app/me does after PATCH
      refreshMe: async () => useMe.setState((s) => ({ me: { ...s.me, user: { ...s.me.user, display_name: s.saved } } })),
    };
  };
  return { ...mod, useAuth, useRole: () => mod.roleOf(useMe.getState().me as never) };
});
vi.mock("@/hooks/usePushBridge", () => ({ usePushBridge: () => {} }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

beforeEach(() => {
  useMe.setState({ me: me0, saved: "" });
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    if (path === "/app/me" && init?.method === "PATCH") {
      useMe.setState({ saved: JSON.parse(String(init.body)).display_name });
      return new Response(JSON.stringify({ display_name: useMe.getState().saved }), { status: 200, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify(path === "/app/push/status" ? { fcm_enabled: false, tokens: 0, prefs: { approvals: true, offline: true, bookings: true, summary: true } } : []), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});

describe("il nome salvato compare nel menu subito (D-170)", () => {
  it("«MAXX» in Impostazioni › Account › Salva: nel menu il nome in grassetto e sotto l'email, senza ricaricare", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/impostazioni"]}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const aside = within(screen.getByRole("complementary"));
    expect(aside.queryByTestId("sidebar-user-name")).toBeNull();
    fireEvent.change(await screen.findByTestId("account-name-input"), { target: { value: "MAXX" } });
    await act(async () => {
      fireEvent.submit(screen.getByTestId("account-name-form"));
    });
    await waitFor(() => expect(aside.getByTestId("sidebar-user-name")).toHaveTextContent("MAXX"));
    expect(aside.getByTestId("sidebar-user-email")).toHaveTextContent("m.cracchiolo@hqe.it");
  });
});
