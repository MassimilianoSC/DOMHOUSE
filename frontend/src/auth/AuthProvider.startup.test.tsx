import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { browser, reloadOnce } from "@/lib/lazyPage";
import { AuthProvider, STARTUP_TIMEOUT_MS, useAuth } from "./AuthProvider";

// E-29: the start of the app (Firebase, then /app/me) never stays in «loading» for ever, with no request and no message.
const fb = vi.hoisted(() => {
  const user = { email: "gestore@esempio.it", providerData: [{ providerId: "password" }], getIdToken: async () => "token-finto" };
  return { user, firebaseAuth: vi.fn(), cb: null as null | ((u: unknown) => void) };
});

vi.mock("@/lib/utils", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/utils")>();
  return { ...mod, env: { ...mod.env, authMode: "firebase", bffUrl: "" } };
});
vi.mock("./firebase", () => ({
  firebaseConfigured: true,
  firebaseApp: async () => ({}),
  firebaseAuth: fb.firebaseAuth,
  continueUrl: () => ({ url: "http://localhost/login" }),
}));
vi.mock("firebase/auth", () => ({
  onAuthStateChanged: (_auth: unknown, cb: (u: unknown) => void) => {
    fb.cb = cb;
    return () => {};
  },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() } }));
vi.mock("@/lib/push", () => ({ disablePush: vi.fn(async () => {}), forgetPushResume: vi.fn() }));

const ME = { user: { uid: "u1", email: "gestore@esempio.it", display_name: "" }, role: "operator", tenant: { tenant_id: "t1", name: "Demo" }, env: {} };
const answerMe = () => vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(ME), { status: 200, headers: { "Content-Type": "application/json" } })));
const never = () => new Promise<never>(() => {});

function Probe() {
  return <div data-testid="status">{useAuth().status}</div>;
}

const status = () => screen.getByTestId("status").textContent;
/** Lets promises and the dynamic imports finish, and moves the fake clock. */
const advance = (ms = 0) => act(async () => {
  await vi.dynamicImportSettled();
  await vi.advanceTimersByTimeAsync(ms);
});
function start() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
}

let reload: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  vi.clearAllMocks();
  fb.cb = null;
  fb.firebaseAuth.mockImplementation(async () => ({ currentUser: fb.user }));
  sessionStorage.clear();
  reload = vi.spyOn(browser, "reload").mockImplementation(() => {});
  answerMe();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("avvio dell'app: mai in caricamento per sempre (E-29)", () => {
  it("Firebase non si carica: una ricarica automatica, e intanto resta il caricamento", async () => {
    fb.firebaseAuth.mockRejectedValue(new TypeError("Failed to fetch dynamically imported module"));
    start();
    await advance();
    expect(reload).toHaveBeenCalledTimes(1);
    expect(status()).toBe("loading");
  });

  it("Firebase non si carica nemmeno dopo la ricarica: il messaggio, senza un secondo giro", async () => {
    reloadOnce(Date.now() - 5_000); // the automatic reload that just happened
    reload.mockClear();
    fb.firebaseAuth.mockRejectedValue(new TypeError("Failed to fetch dynamically imported module"));
    start();
    await advance();
    expect(status()).toBe("unavailable");
    expect(reload).not.toHaveBeenCalled();
  });

  it("Firebase non risponde: resta in caricamento fino al tempo massimo, poi il messaggio, senza ricaricare da solo", async () => {
    fb.firebaseAuth.mockImplementation(never);
    start();
    await advance(STARTUP_TIMEOUT_MS - 1);
    expect(status()).toBe("loading");
    await advance(1);
    expect(status()).toBe("unavailable");
    expect(reload).not.toHaveBeenCalled();
  });

  it("il profilo non risponde: anche /app/me rientra nel tempo massimo", async () => {
    vi.stubGlobal("fetch", vi.fn(never));
    start();
    await advance();
    act(() => fb.cb?.(fb.user));
    await advance(STARTUP_TIMEOUT_MS - 1);
    expect(status()).toBe("loading");
    await advance(1);
    expect(status()).toBe("unavailable");
  });

  it("risposta in ritardo (server che si sta avviando): l'app entra da sola, il messaggio sparisce", async () => {
    start();
    await advance();
    await advance(STARTUP_TIMEOUT_MS);
    expect(status()).toBe("unavailable");
    act(() => fb.cb?.(fb.user));
    await advance();
    expect(status()).toBe("authenticated");
  });

  it("risposta in ritardo senza sessione: pagina di accesso", async () => {
    start();
    await advance();
    await advance(STARTUP_TIMEOUT_MS);
    act(() => fb.cb?.(null));
    await advance();
    expect(status()).toBe("anonymous");
  });

  it.each([
    ["con sessione", () => fb.user, "authenticated"],
    ["senza sessione", () => null, "anonymous"],
  ])("avvio normale %s: nessun messaggio, nemmeno dopo il tempo massimo", async (_name, who, expected) => {
    start();
    await advance();
    act(() => fb.cb?.(who()));
    await advance();
    expect(status()).toBe(expected);
    await advance(STARTUP_TIMEOUT_MS * 2);
    expect(status()).toBe(expected);
    expect(reload).not.toHaveBeenCalled();
  });
});
