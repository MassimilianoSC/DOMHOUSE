import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { disablePush } from "@/lib/push";
import { isShared, rememberSharedChoice, SHARED_IDLE_MS, wasAutoLogout } from "@/lib/sharedDevice";
import { AuthProvider, useAuth } from "./AuthProvider";

// F-15 (answer 1244 = a) in the app: on a shared device, 30 minutes without using the app is «Esci» by itself, also
// after a reload and on coming back from the background; signing in without the box removes the choice; two people on
// the same device each keep their own. Development sign-in (the same exit as Firebase's, without Firebase).

vi.mock("@/lib/utils", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/utils")>();
  return { ...mod, env: { ...mod.env, authMode: "dev", bffUrl: "" } };
});
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() } }));
vi.mock("@/lib/push", () => ({ disablePush: vi.fn(async () => {}), forgetPushResume: vi.fn() }));

const DEV_KEY = "domotica.devUser";
const me = (uid: string) => ({ user: { uid, email: `${uid}@esempio.it`, display_name: "" }, role: "operator", tenant: { tenant_id: "t1", name: "Demo" }, env: {} });
let who = "anna";

function Probe() {
  const { status, devLogin, logout } = useAuth();
  return (
    <>
      <div data-testid="status">{status}</div>
      <button data-testid="login" onClick={() => void devLogin(`${who}@esempio.it`)} />
      <button data-testid="logout" onClick={() => void logout()} />
    </>
  );
}
const status = () => screen.getByTestId("status").textContent;
const settle = (ms = 0) => act(async () => {
  await vi.advanceTimersByTimeAsync(ms);
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
async function signIn(uid: string, shared: boolean) {
  who = uid;
  rememberSharedChoice(shared); // what the sign-in page writes for its box
  await act(async () => screen.getByTestId("login").click());
  await settle();
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
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(me(who)), { status: 200, headers: { "Content-Type": "application/json" } })));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete (document as { visibilityState?: unknown }).visibilityState;
});

describe("dispositivo condiviso (F-15)", () => {
  it("30 minuti senza usare l'app: si esce da soli, come «Esci», con la pulizia delle notifiche e l'avviso", async () => {
    start();
    await settle();
    await signIn("anna", true);
    expect(status()).toBe("authenticated");
    await settle(SHARED_IDLE_MS - 60_000);
    expect(status()).toBe("authenticated");
    await settle(2 * 60_000);
    expect(status()).toBe("anonymous");
    expect(localStorage.getItem(DEV_KEY)).toBeNull();
    expect(disablePush).toHaveBeenCalledWith({ resume: true }); // P-44, as «Esci»
    // the first cleaning while still signed in, as «Esci»: the server needs the person's session to drop the push
    expect(signedInAtPushCleaning[0]).toBe("anna@esempio.it");
    expect(wasAutoLogout()).toBe(true);
  });

  it("usare l'app fa ripartire i 30 minuti", async () => {
    start();
    await settle();
    await signIn("anna", true);
    await settle(20 * 60_000);
    await act(async () => window.dispatchEvent(new Event("pointerdown")));
    await settle(20 * 60_000);
    expect(status()).toBe("authenticated");
    await settle(12 * 60_000);
    expect(status()).toBe("anonymous");
  });

  it("app in sfondo per un'ora: al ritorno esce subito, prima di contare il ritorno come uso", async () => {
    start();
    await settle();
    await signIn("anna", true);
    visibility("hidden");
    // in the background the timers may not run: the clock moves, the minute check does not fire
    vi.setSystemTime(Date.now() + 60 * 60_000);
    visibility("visible");
    await act(async () => document.dispatchEvent(new Event("visibilitychange")));
    await settle();
    expect(status()).toBe("anonymous");
    expect(wasAutoLogout()).toBe(true);
  });

  it("ricaricamento: dentro se l'ultimo uso è recente; dopo 30 minuti si chiede di nuovo l'accesso", async () => {
    const first = start();
    await settle();
    await signIn("anna", true);
    first.unmount();
    vi.setSystemTime(Date.now() + 10 * 60_000);
    const second = start(); // the reload: DEV_KEY and the choice are still in localStorage
    await settle();
    expect(status()).toBe("authenticated");
    second.unmount();
    vi.setSystemTime(Date.now() + 31 * 60_000);
    start();
    await settle();
    expect(status()).toBe("anonymous");
    expect(wasAutoLogout()).toBe(true);
  });

  it("accesso senza casella: la scelta si toglie e non si esce più da soli", async () => {
    start();
    await settle();
    await signIn("anna", true);
    await act(async () => window.dispatchEvent(new Event("pointerdown")));
    expect(isShared("anna")).toBe(true);
    await act(async () => screen.getByTestId("logout").click());
    await settle();
    await signIn("anna", false);
    expect(isShared("anna")).toBe(false);
    await settle(2 * SHARED_IDLE_MS);
    expect(status()).toBe("authenticated");
  });

  it("due persone sullo stesso dispositivo: chi non ha spuntato resta dentro, la scelta dell'altra resta sua", async () => {
    start();
    await settle();
    await signIn("anna", true);
    await act(async () => screen.getByTestId("logout").click());
    await settle();
    await signIn("bruno", false);
    await settle(2 * SHARED_IDLE_MS);
    expect(status()).toBe("authenticated");
    expect(isShared("bruno")).toBe(false);
    expect(isShared("anna")).toBe(true);
  });

  it("senza casella spuntata tutto come oggi: nessuna uscita automatica", async () => {
    start();
    await settle();
    await signIn("anna", false);
    await settle(3 * SHARED_IDLE_MS);
    expect(status()).toBe("authenticated");
    expect(wasAutoLogout()).toBe(false);
  });
});
