import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { markAutoLogout } from "@/lib/sharedDevice";
import LoginPage from "./LoginPage";

// F-15 (answer 1244 = a) on the sign-in page: the box, off at first, with its line; what the next sign-in takes; the
// notice after an automatic exit, once.

vi.mock("@/lib/utils", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/utils")>();
  return { ...mod, env: { ...mod.env, authMode: "dev", bffUrl: "" } };
});
vi.mock("@/auth/AuthProvider", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/AuthProvider")>()),
  useAuth: () => ({ status: "anonymous", problem: undefined, devLogin: vi.fn() }),
}));

/** In StrictMode, as main.tsx: React renders twice in development, a side effect in the render would show here. */
function show() {
  return render(
    <StrictMode>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </QueryClientProvider>
    </StrictMode>,
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })));
});

describe("pagina «Accedi»: dispositivo condiviso (F-15)", () => {
  it("la casella, spenta all'inizio, con la sua riga", () => {
    show();
    const box = screen.getByTestId("login-shared-device-box") as HTMLInputElement;
    expect(box.checked).toBe(false);
    expect(screen.getByTestId("login-shared-device")).toHaveTextContent("Questo è un dispositivo condiviso");
    expect(screen.getByTestId("login-shared-device")).toHaveTextContent("Dopo 30 minuti senza usare l'app l'uscita è automatica, e alla riapertura serve di nuovo l'accesso. Lasciala spenta sul tuo telefono o computer personale.");
    expect(box).toHaveAccessibleName(/Questo è un dispositivo condiviso/);
  });

  it("il prossimo accesso prende lo stato della casella: spenta all'apertura, poi come la lascia la persona", () => {
    show();
    expect(localStorage.getItem("domotica.sharedPending")).toBe("0");
    fireEvent.click(screen.getByTestId("login-shared-device-box"));
    expect(localStorage.getItem("domotica.sharedPending")).toBe("1");
    fireEvent.click(screen.getByTestId("login-shared-device-box"));
    expect(localStorage.getItem("domotica.sharedPending")).toBe("0");
  });

  it("dopo un'uscita automatica l'avviso, una volta sola", () => {
    markAutoLogout();
    const first = show();
    expect(screen.getByTestId("login-auto-logout")).toHaveTextContent("Uscita automatica: l'app non è stata usata per 30 minuti su un dispositivo condiviso. Accedi di nuovo per continuare.");
    first.unmount();
    show();
    expect(screen.queryByTestId("login-auto-logout")).toBeNull();
  });

  it("senza uscita automatica nessun avviso", () => {
    show();
    expect(screen.queryByTestId("login-auto-logout")).toBeNull();
  });
});
