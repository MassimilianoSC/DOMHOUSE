import { StrictMode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import LoginPage from "./LoginPage";

// F-15 (answer 1244 = a) on the sign-in page: the box, off at first, inside the form above the sign-in buttons (review
// S-3), passed to the sign-in (S-1: the page itself writes nothing); the notice after an automatic exit; no form while
// a session loads. In StrictMode, as main.tsx.

const s = vi.hoisted(() => ({
  env: { authMode: "dev" } as Record<string, unknown>,
  auth: {
    status: "anonymous",
    problem: undefined,
    autoLoggedOut: false,
    devLogin: vi.fn(async () => {}),
    emailLogin: vi.fn(async () => {}),
    googleLogin: vi.fn(async () => {}),
  },
}));
vi.mock("@/lib/utils", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/utils")>();
  return { ...mod, env: Object.assign(s.env, { ...mod.env, authMode: s.env.authMode, bffUrl: "" }) };
});
vi.mock("@/auth/firebase", () => ({ firebaseConfigured: true, firebaseApp: async () => ({}), firebaseAuth: async () => ({}), continueUrl: () => ({ url: "" }) }));
vi.mock("@/auth/AuthProvider", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/AuthProvider")>()),
  useAuth: () => s.auth,
}));

const DEV_USERS = [{ email: "anna@esempio.it", display_name: "Anna", role: "operator" }];

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
const before = (a: HTMLElement, b: HTMLElement) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  s.env.authMode = "dev";
  s.auth.status = "anonymous";
  s.auth.autoLoggedOut = false;
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(DEV_USERS), { status: 200, headers: { "Content-Type": "application/json" } })));
});

describe("pagina «Accedi»: dispositivo condiviso (F-15)", () => {
  it("la casella, spenta all'inizio, con la sua riga; la pagina non scrive niente", () => {
    show();
    const box = screen.getByTestId("login-shared-device-box") as HTMLInputElement;
    expect(box.checked).toBe(false);
    expect(screen.getByTestId("login-shared-device")).toHaveTextContent("Questo è un dispositivo condiviso");
    expect(screen.getByTestId("login-shared-device")).toHaveTextContent("Dopo 30 minuti senza usare l'app l'uscita è automatica, e alla riapertura serve di nuovo l'accesso. Lasciala spenta sul tuo telefono o computer personale.");
    expect(box).toHaveAccessibleName(/Questo è un dispositivo condiviso/);
    fireEvent.click(box);
    expect(localStorage.length).toBe(0); // S-1: only the sign-in writes it
  });

  it("accesso di sviluppo: la casella sta sopra le persone (S-3) e va con l'accesso, spuntata o no", async () => {
    show();
    const person = await screen.findByTestId("dev-login-anna@esempio.it");
    expect(before(screen.getByTestId("login-shared-device"), person)).toBe(true);
    fireEvent.click(person);
    expect(s.auth.devLogin).toHaveBeenLastCalledWith("anna@esempio.it", false);
    fireEvent.click(screen.getByTestId("login-shared-device-box"));
    fireEvent.click(person);
    expect(s.auth.devLogin).toHaveBeenLastCalledWith("anna@esempio.it", true);
  });

  it("accesso con email o Google: la casella sta sopra «Accedi» e Google (S-3) e va con l'accesso", async () => {
    s.env.authMode = "firebase";
    show();
    const box = screen.getByTestId("login-shared-device-box");
    expect(before(screen.getByTestId("login-shared-device"), screen.getByTestId("login-submit-btn"))).toBe(true);
    expect(before(screen.getByTestId("login-shared-device"), screen.getByTestId("login-google-btn"))).toBe(true);
    fireEvent.click(box);
    fireEvent.change(screen.getByTestId("login-email-input"), { target: { value: "anna@esempio.it" } });
    fireEvent.change(screen.getByTestId("login-password-input"), { target: { value: "segreta-123" } });
    fireEvent.submit(screen.getByTestId("firebase-login-form"));
    await waitFor(() => expect(s.auth.emailLogin).toHaveBeenCalledWith("anna@esempio.it", "segreta-123", true));
    fireEvent.click(screen.getByTestId("login-google-btn"));
    expect(s.auth.googleLogin).toHaveBeenCalledWith(true);
  });

  it("dopo un'uscita automatica l'avviso; altrimenti niente", () => {
    s.auth.autoLoggedOut = true;
    const first = show();
    expect(screen.getByTestId("login-auto-logout")).toHaveTextContent("Uscita automatica: l'app non è stata usata per 30 minuti su un dispositivo condiviso. Accedi di nuovo per continuare.");
    first.unmount();
    s.auth.autoLoggedOut = false;
    show();
    expect(screen.queryByTestId("login-auto-logout")).toBeNull();
  });

  it("mentre una sessione si carica: nessun modulo, nessuna casella (S-1)", () => {
    s.auth.status = "loading";
    show();
    expect(screen.getByTestId("login-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("login-shared-device")).toBeNull();
    expect(screen.queryByTestId("dev-login")).toBeNull();
  });
});

describe("memoria del browser non scrivibile (seconda rilettura R-5)", () => {
  it("sotto la casella: l'uscita automatica non è disponibile, premi «Esci»", () => {
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    try {
      show();
      expect(screen.getByTestId("login-shared-device-unavailable")).toHaveTextContent("Su questo browser l'uscita automatica non è disponibile: premi «Esci» quando hai finito.");
    } finally {
      set.mockRestore();
    }
  });

  it("con la memoria che funziona: niente riga", () => {
    show();
    expect(screen.queryByTestId("login-shared-device-unavailable")).toBeNull();
  });
});
