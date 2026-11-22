import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom";
import { disablePush } from "@/lib/push";
import { isShared, SHARED_IDLE_MS } from "@/lib/sharedDevice";
import LoginPage from "@/pages/LoginPage";
import { AuthProvider, useAuth } from "./AuthProvider";

// F-15 (answer 1244 = a) in the app: on a shared device, 30 minutes without using the app is «Esci» by itself, also
// after a reload and on coming back from the background; signing in without the box removes the choice; two people on
// the same device each keep their own. Review (RILETTURA-SITO-O2.md): S-1 the sign-in page never writes the box while
// a session loads (integration test with the real page), S-2 reading the profile is not a use, S-6 the key goes at the
// exit, S-7 scrolling is a use. Development sign-in (the same exit as Firebase's, without Firebase).

vi.mock("@/lib/utils", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/utils")>();
  return { ...mod, env: { ...mod.env, authMode: "dev", bffUrl: "" } };
});
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() } }));
vi.mock("@/lib/push", () => ({ disablePush: vi.fn(async () => {}), forgetPushResume: vi.fn() }));

const DEV_KEY = "domotica.devUser";
const SHARED = (uid: string) => `domotica.shared.${uid}`;
const me = (uid: string) => ({ user: { uid, email: `${uid}@esempio.it`, display_name: "" }, role: "operator", tenant: { tenant_id: "t1", name: "Demo" }, env: {} });

/** The development BFF: /app/me answers for the person of the X-Dev-User header; the sign-in page lists nobody. */
function bff() {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).includes("/app/dev/users")) return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
    const email = (init?.headers as Record<string, string> | undefined)?.["X-Dev-User"] ?? "";
    return new Response(JSON.stringify(me(email.split("@")[0])), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
}

function Probe() {
  const { status, devLogin, logout, refreshMe, autoLoggedOut } = useAuth();
  return (
    <>
      <div data-testid="status">{status}</div>
      <div data-testid="auto">{String(autoLoggedOut)}</div>
      <button data-testid="login-anna-shared" onClick={() => void devLogin("anna@esempio.it", true)} />
      <button data-testid="login-anna" onClick={() => void devLogin("anna@esempio.it")} />
      <button data-testid="login-bruno" onClick={() => void devLogin("bruno@esempio.it", false)} />
      <button data-testid="logout" onClick={() => void logout()} />
      <button data-testid="refresh" onClick={() => void refreshMe()} />
    </>
  );
}
const status = () => screen.getByTestId("status").textContent;
const auto = () => screen.getByTestId("auto").textContent;
const settle = (ms = 0) => act(async () => {
  await vi.advanceTimersByTimeAsync(ms);
});
const press = (id: string) => act(async () => {
  screen.getByTestId(id).click();
  await vi.advanceTimersByTimeAsync(0);
});
function start() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
}
function visibility(value: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { value, configurable: true });
}

/** For each push cleaning: the development sign-in still present at that moment, or null. */
let signedInAtPushCleaning: (string | null)[] = [];

beforeEach(() => {
  vi.clearAllMocks();
  signedInAtPushCleaning = [];
  vi.mocked(disablePush).mockImplementation(async () => {
    signedInAtPushCleaning.push(localStorage.getItem(DEV_KEY));
  });
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"] });
  vi.setSystemTime(new Date("2026-11-22T10:00:00Z"));
  localStorage.clear();
  bff();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete (document as { visibilityState?: unknown }).visibilityState;
});

describe("dispositivo condiviso (F-15)", () => {
  it("30 minuti senza usare l'app: si esce da soli, come «Esci», con la pulizia delle notifiche, l'avviso e senza chiave", async () => {
    start();
    await settle();
    await press("login-anna-shared");
    expect(status()).toBe("authenticated");
    await settle(SHARED_IDLE_MS - 60_000);
    expect(status()).toBe("authenticated");
    await settle(2 * 60_000);
    expect(status()).toBe("anonymous");
    expect(localStorage.getItem(DEV_KEY)).toBeNull();
    expect(disablePush).toHaveBeenCalledWith({ resume: true }); // P-44, as «Esci»
    expect(signedInAtPushCleaning[0]).toBe("anna@esempio.it"); // while still signed in
    expect(auto()).toBe("true");
    expect(localStorage.getItem(SHARED("anna"))).toBeNull(); // S-6
  });

  it("usare l'app fa ripartire i 30 minuti: tocco, e anche la rotella (S-7)", async () => {
    start();
    await settle();
    await press("login-anna-shared");
    await settle(20 * 60_000);
    await act(async () => window.dispatchEvent(new Event("pointerdown")));
    await settle(20 * 60_000);
    await act(async () => window.dispatchEvent(new Event("wheel")));
    await settle(20 * 60_000);
    expect(status()).toBe("authenticated");
    await settle(12 * 60_000);
    expect(status()).toBe("anonymous");
  });

  it("la rilettura automatica del profilo non è un uso (S-2): ogni 2 minuti per 31 minuti, senza tocchi, si esce", async () => {
    start();
    await settle();
    await press("login-anna-shared");
    for (let i = 0; i < 16 && status() === "authenticated"; i++) {
      await settle(2 * 60_000);
      if (status() === "authenticated") await press("refresh"); // as the administrators' notice does every 120 s
    }
    expect(status()).toBe("anonymous");
    expect(auto()).toBe("true");
  });

  it("app in sfondo per un'ora: al ritorno esce subito, prima di contare il ritorno come uso", async () => {
    start();
    await settle();
    await press("login-anna-shared");
    visibility("hidden");
    vi.setSystemTime(Date.now() + 60 * 60_000); // in the background the timers may not run
    visibility("visible");
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    await settle();
    expect(status()).toBe("anonymous");
    expect(auto()).toBe("true");
  });

  it("ricaricamento: dentro se l'ultimo uso è recente; dopo 30 minuti si chiede di nuovo l'accesso", async () => {
    const first = start();
    await settle();
    await press("login-anna-shared");
    first.unmount();
    vi.setSystemTime(Date.now() + 10 * 60_000);
    const second = start(); // the reload: DEV_KEY and the choice are still in localStorage
    await settle();
    expect(status()).toBe("authenticated");
    second.unmount();
    vi.setSystemTime(Date.now() + 21 * 60_000); // 31 minutes since the last use: the reload is not a use
    start();
    await settle();
    expect(status()).toBe("anonymous");
    expect(auto()).toBe("true");
  });

  it("accesso senza casella: la scelta si toglie e non si esce più da soli", async () => {
    start();
    await settle();
    await press("login-anna-shared");
    expect(isShared("anna")).toBe(true);
    await press("logout");
    await press("login-anna");
    expect(isShared("anna")).toBe(false);
    await settle(2 * SHARED_IDLE_MS);
    expect(status()).toBe("authenticated");
    expect(auto()).toBe("false");
  });

  it("due persone sullo stesso dispositivo: chi non ha spuntato resta dentro", async () => {
    start();
    await settle();
    await press("login-anna-shared");
    await press("logout");
    await press("login-bruno");
    await settle(2 * SHARED_IDLE_MS);
    expect(status()).toBe("authenticated");
    expect(isShared("bruno")).toBe(false);
    expect(localStorage.getItem(SHARED("anna"))).toBeNull(); // her «Esci» took her key (S-6)
  });

  it("«Esci» volontario: nessun avviso di uscita automatica", async () => {
    start();
    await settle();
    await press("login-anna-shared");
    await press("logout");
    expect(status()).toBe("anonymous");
    expect(auto()).toBe("false");
  });
});

// Review S-1: the real sign-in page with the real AuthProvider, opened on /login while the session is being loaded.
describe("pagina «Accedi» aperta con una sessione in caricamento (S-1)", () => {
  // In StrictMode, as main.tsx: the start reads the profile twice, the case of two reads of the profile close together
  function openLogin(path = "/login") {
    return render(
      <StrictMode>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <AuthProvider>
            <MemoryRouter initialEntries={[path]}>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/" element={<Home />} />
              </Routes>
            </MemoryRouter>
          </AuthProvider>
        </QueryClientProvider>
      </StrictMode>,
    );
  }
  /** «/» as Protected does it: in only when signed in. */
  function Home() {
    const { status } = useAuth();
    if (status === "anonymous") return <Navigate to="/login" replace />;
    return <div data-testid="home">{status}</div>;
  }

  it("sessione di Anna, scelta attiva e scaduta: niente casella durante il caricamento, la scelta non si cancella, si esce con l'avviso", async () => {
    localStorage.setItem(DEV_KEY, "anna@esempio.it");
    localStorage.setItem(SHARED("anna"), String(Date.now() - 60 * 60_000));
    openLogin();
    expect(screen.getByTestId("login-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("login-shared-device")).toBeNull();
    expect(localStorage.getItem("domotica.sharedPending")).toBeNull();
    await settle();
    expect(screen.queryByTestId("home")).toBeNull();
    expect(screen.getByTestId("login-auto-logout")).toHaveTextContent("Uscita automatica");
    expect(localStorage.getItem(DEV_KEY)).toBeNull();
    expect(localStorage.getItem(SHARED("anna"))).toBeNull();
  });

  it("riapertura su «/» dopo 30 minuti, con una seconda lettura del profilo che risponde dopo l'uscita: fuori, mai dentro", async () => {
    localStorage.setItem(DEV_KEY, "anna@esempio.it");
    localStorage.setItem(SHARED("anna"), String(Date.now() - 60 * 60_000));
    // the first /app/me answers at once, the next ones a second later (found in the browser: the late read put the
    // person back in, without a session)
    let reads = 0;
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (String(url).includes("/app/dev/users")) return new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } });
      if (reads++ > 0) await new Promise((r) => setTimeout(r, 1000));
      return new Response(JSON.stringify(me("anna")), { status: 200, headers: { "Content-Type": "application/json" } });
    }));
    openLogin("/");
    await settle();
    await settle(1500);
    expect(reads).toBeGreaterThan(1);
    expect(screen.queryByTestId("home")).toBeNull();
    expect(screen.getByTestId("login-auto-logout")).toHaveTextContent("Uscita automatica");
    expect(localStorage.getItem(DEV_KEY)).toBeNull();
  });

  it("sessione di Anna, scelta attiva e recente: si entra e la scelta resta", async () => {
    localStorage.setItem(DEV_KEY, "anna@esempio.it");
    localStorage.setItem(SHARED("anna"), String(Date.now() - 5 * 60_000));
    openLogin();
    await settle();
    expect(screen.getByTestId("home")).toBeInTheDocument();
    expect(isShared("anna")).toBe(true);
  });
});
