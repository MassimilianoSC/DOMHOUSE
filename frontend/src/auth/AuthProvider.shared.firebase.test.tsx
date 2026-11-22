import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { isShared } from "@/lib/sharedDevice";
import { AuthProvider, useAuth } from "./AuthProvider";

// F-15, second review R-6: the shared-device choice with Firebase (the production sign-in), not only the development
// one: email and Google sign-ins write the box right before signing in, a failed sign-in leaves nothing, the profile
// read after Firebase's sign-in adopts it, and Firebase saying the session is over removes the key (R-1).

const fb = vi.hoisted(() => {
  const user = { uid: "anna", email: "anna@esempio.it", providerData: [{ providerId: "password" }], getIdToken: async () => "token-finto" };
  const auth = { currentUser: null as null | typeof user };
  return {
    user,
    auth,
    cb: null as null | ((u: unknown) => void),
    signIn: vi.fn(),
    popup: vi.fn(),
    pendingAtSignIn: [] as (string | null)[],
  };
});

vi.mock("@/lib/utils", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/utils")>();
  return { ...mod, env: { ...mod.env, authMode: "firebase", bffUrl: "" } };
});
vi.mock("./firebase", () => ({
  firebaseConfigured: true,
  firebaseApp: async () => ({}),
  firebaseAuth: async () => fb.auth,
  continueUrl: () => ({ url: "http://localhost/login" }),
}));
vi.mock("firebase/auth", () => ({
  onAuthStateChanged: (_auth: unknown, cb: (u: unknown) => void) => {
    fb.cb = cb;
    return () => {};
  },
  signInWithEmailAndPassword: (...args: unknown[]) => fb.signIn(...args),
  signInWithPopup: (...args: unknown[]) => fb.popup(...args),
  GoogleAuthProvider: class {},
  signOut: async () => {
    fb.auth.currentUser = null;
    fb.cb?.(null);
  },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() } }));
vi.mock("@/lib/push", () => ({ disablePush: vi.fn(async () => {}), forgetPushResume: vi.fn() }));

const ME = { user: { uid: "anna", email: "anna@esempio.it", display_name: "" }, role: "operator", tenant: { tenant_id: "t1", name: "Demo" }, env: {} };

/** Firebase signs in: the box must already be written, then the session starts (onAuthStateChanged). */
async function firebaseSignsIn() {
  fb.pendingAtSignIn.push(localStorage.getItem("domotica.sharedPending"));
  fb.auth.currentUser = fb.user;
  fb.cb?.(fb.user);
}

function Probe() {
  const { status, emailLogin, googleLogin } = useAuth();
  return (
    <>
      <div data-testid="status">{status}</div>
      <button data-testid="email-shared" onClick={() => void emailLogin("anna@esempio.it", "segreta-123", true).catch(() => undefined)} />
      <button data-testid="email" onClick={() => void emailLogin("anna@esempio.it", "segreta-123").catch(() => undefined)} />
      <button data-testid="google-shared" onClick={() => void googleLogin(true).catch(() => undefined)} />
    </>
  );
}
const status = () => screen.getByTestId("status").textContent;
const settle = () => act(async () => {
  await vi.dynamicImportSettled();
  await new Promise((r) => setTimeout(r, 0));
});
const press = async (id: string) => {
  await act(async () => screen.getByTestId(id).click());
  await settle();
};

async function start() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
  await settle();
  await act(async () => fb.cb?.(null)); // no session at first
  await settle();
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  fb.auth.currentUser = null;
  fb.cb = null;
  fb.pendingAtSignIn = [];
  fb.signIn.mockImplementation(firebaseSignsIn);
  fb.popup.mockImplementation(firebaseSignsIn);
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(ME), { status: 200, headers: { "Content-Type": "application/json" } })));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("dispositivo condiviso con Firebase (F-15, R-6)", () => {
  it("accesso con email e casella: la scelta è scritta prima dell'accesso e diventa della persona", async () => {
    await start();
    expect(status()).toBe("anonymous");
    await press("email-shared");
    expect(fb.pendingAtSignIn).toEqual(["1"]);
    expect(status()).toBe("authenticated");
    expect(isShared("anna")).toBe(true);
    expect(localStorage.getItem("domotica.sharedPending")).toBeNull();
  });

  it("accesso con Google e casella: lo stesso", async () => {
    await start();
    await press("google-shared");
    expect(fb.pendingAtSignIn).toEqual(["1"]);
    expect(isShared("anna")).toBe(true);
  });

  it("accesso con email senza casella: la scelta di prima si toglie", async () => {
    localStorage.setItem("domotica.shared.anna", String(Date.now()));
    await start();
    await press("email");
    expect(fb.pendingAtSignIn).toEqual(["0"]);
    expect(isShared("anna")).toBe(false);
  });

  it("accesso fallito (password sbagliata): non resta nessuna scelta in sospeso", async () => {
    fb.signIn.mockRejectedValueOnce(Object.assign(new Error("wrong"), { code: "auth/wrong-password" }));
    await start();
    await press("email-shared");
    expect(status()).toBe("anonymous");
    expect(localStorage.getItem("domotica.sharedPending")).toBeNull();
  });

  it("Firebase dice che la sessione è finita (un'altra scheda è uscita): la chiave si toglie (R-1)", async () => {
    await start();
    await press("email-shared");
    expect(isShared("anna")).toBe(true);
    await act(async () => {
      fb.auth.currentUser = null;
      fb.cb?.(null);
    });
    await settle();
    expect(status()).toBe("anonymous");
    expect(isShared("anna")).toBe(false);
  });
});
