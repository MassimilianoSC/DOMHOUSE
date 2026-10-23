import { act, fireEvent, render, screen } from "@testing-library/react";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { t } from "@/i18n";
import { AccountSettings } from "./AccountSettings";

// Settings > Account with a simulated signed-in user: Firebase calls are mocks on the auth context.
const state = vi.hoisted(() => ({
  env: {} as Record<string, unknown>,
  auth: {
    me: { user: { uid: "u1", email: "gestore@esempio.it", display_name: "Gestore" } },
    providers: ["password"] as string[],
    changePassword: vi.fn(async (_current: string, _next: string) => {}),
    changeEmail: vi.fn(async (_current: string, _email: string) => {}),
    logoutEverywhere: vi.fn(async () => {}),
    deleteAccount: vi.fn(async () => {}),
    refreshMe: vi.fn(async () => {}),
  },
}));

vi.mock("@/lib/utils", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/utils")>();
  return { ...mod, env: Object.assign(state.env, mod.env) };
});
vi.mock("@/auth/AuthProvider", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/AuthProvider")>()),
  useAuth: () => state.auth,
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const type = (testId: string, value: string) => fireEvent.change(screen.getByTestId(testId), { target: { value } });

beforeEach(() => {
  vi.clearAllMocks();
  state.env.authMode = "firebase";
  state.auth.providers = ["password"];
});

describe("Impostazioni > Account: password", () => {
  it("chi accede con password vede il cambio password e il cambio email", () => {
    render(<AccountSettings />);
    expect(screen.getByTestId("account-password-form")).toBeInTheDocument();
    expect(screen.getByTestId("account-email-form")).toBeInTheDocument();
    expect(screen.queryByTestId("account-managed-elsewhere")).not.toBeInTheDocument();
  });

  it("nuova password di 7 caratteri: «almeno 8 caratteri» e pulsante disattivato", () => {
    render(<AccountSettings />);
    type("account-pw-current", "vecchia-password");
    type("account-pw-new", "1234567");
    type("account-pw-confirm", "1234567");
    expect(screen.getByTestId("account-password-form")).toHaveTextContent(t("account.passwordTooShort", { min: 8 }));
    expect(screen.getByTestId("account-pw-submit")).toBeDisabled();
  });

  it("conferma diversa: «Le due password non coincidono» e pulsante disattivato", () => {
    render(<AccountSettings />);
    type("account-pw-current", "vecchia-password");
    type("account-pw-new", "nuova-password");
    type("account-pw-confirm", "nuova-passwort");
    expect(screen.getByTestId("account-password-form")).toHaveTextContent(t("account.passwordMismatch"));
    expect(screen.getByTestId("account-pw-submit")).toBeDisabled();
  });

  it("senza password attuale il pulsante resta disattivato", () => {
    render(<AccountSettings />);
    type("account-pw-new", "nuova-password");
    type("account-pw-confirm", "nuova-password");
    expect(screen.getByTestId("account-pw-submit")).toBeDisabled();
  });

  it("dati validi: cambia la password, avvisa «Password cambiata» e svuota i campi", async () => {
    render(<AccountSettings />);
    type("account-pw-current", "vecchia-password");
    type("account-pw-new", "12345678");
    type("account-pw-confirm", "12345678");
    const form = screen.getByTestId("account-password-form");
    expect(form).not.toHaveTextContent(t("account.passwordTooShort", { min: 8 }));
    expect(form).not.toHaveTextContent(t("account.passwordMismatch"));
    expect(screen.getByTestId("account-pw-submit")).toBeEnabled();
    await act(async () => {
      fireEvent.click(screen.getByTestId("account-pw-submit"));
    });
    expect(state.auth.changePassword).toHaveBeenCalledWith("vecchia-password", "12345678");
    expect(toast.success).toHaveBeenCalledWith(t("account.passwordChanged"));
    expect(screen.getByTestId("account-pw-new")).toHaveValue("");
  });

  it("password attuale sbagliata: avvisa «Password attuale non corretta»", async () => {
    state.auth.changePassword.mockRejectedValueOnce({ code: "auth/wrong-password" });
    render(<AccountSettings />);
    type("account-pw-current", "sbagliata");
    type("account-pw-new", "12345678");
    type("account-pw-confirm", "12345678");
    await act(async () => {
      fireEvent.click(screen.getByTestId("account-pw-submit"));
    });
    expect(toast.error).toHaveBeenCalledWith(t("account.errors.wrongPassword"), expect.anything());
    expect(toast.success).not.toHaveBeenCalled();
  });
});

describe("Impostazioni > Account: chi non usa la password", () => {
  it("accesso con Google: niente moduli password ed email, al loro posto il rimando all'account Google", () => {
    state.auth.providers = ["google.com"];
    render(<AccountSettings />);
    expect(screen.queryByTestId("account-password-form")).not.toBeInTheDocument();
    expect(screen.queryByTestId("account-email-form")).not.toBeInTheDocument();
    expect(screen.getByTestId("account-managed-elsewhere")).toHaveTextContent(t("account.googleManaged"));
    expect(screen.getByTestId("account-security-card")).toBeInTheDocument();
  });

  it("modalità sviluppo: niente moduli password ed email, con il testo della modalità sviluppo", () => {
    state.env.authMode = "dev";
    state.auth.providers = [];
    render(<AccountSettings />);
    expect(screen.queryByTestId("account-password-form")).not.toBeInTheDocument();
    expect(screen.getByTestId("account-managed-elsewhere")).toHaveTextContent(t("account.devMode"));
  });
});

describe("Impostazioni > Sicurezza: Elimina il mio account rifiutato (D-73)", () => {
  it("ultimo gestore della piattaforma: avviso con il messaggio del server, non quello generico", async () => {
    const msg = "Sei l'ultimo gestore della piattaforma: nomina un altro gestore prima di eliminare il tuo account";
    state.auth.deleteAccount.mockRejectedValueOnce(new ApiError(409, "last_manager", msg, "c-1"));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AccountSettings />);
    await act(async () => {
      fireEvent.click(screen.getByTestId("account-delete"));
    });
    expect(toast.error).toHaveBeenCalledWith(msg, expect.anything());
    expect(toast.success).not.toHaveBeenCalled();
    confirm.mockRestore();
  });
});

describe("Impostazioni > Sicurezza: cosa cancella «Elimina il mio account» (P-48, D-87)", () => {
  it("la conferma dice cosa viene cancellato e cosa resta, con «utente rimosso»", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<AccountSettings />);
    await act(async () => {
      fireEvent.click(screen.getByTestId("account-delete"));
    });
    const text = confirm.mock.calls[0][0] as string;
    expect(text).toBe(t("account.deleteConfirm"));
    expect(text).toMatch(/email/);
    expect(text).toMatch(/utente rimosso/);
    expect(text).toMatch(/nuovo invito/);
    expect(state.auth.deleteAccount).not.toHaveBeenCalled();
    confirm.mockRestore();
  });
});

describe("gestore della piattaforma senza organizzazione (D-178)", () => {
  const meBefore = state.auth.me;
  afterEach(() => {
    state.auth.me = meBefore;
    vi.unstubAllGlobals();
  });

  it("salva il nome visualizzato ed esce da tutti i dispositivi, come chiunque", async () => {
    state.auth.me = { user: { uid: "p1", email: "piattaforma@hqe.it", display_name: "", platform_manager: true }, role: null, tenant: null } as unknown as typeof state.auth.me;
    const calls: { path: string; method: string; body: unknown }[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ path: new URL(url).pathname, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
      return new Response(null, { status: 204 });
    }));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AccountSettings />);
    type("account-name-input", "Sol Bianchi");
    await act(async () => {
      fireEvent.submit(screen.getByTestId("account-name-form"));
    });
    expect(calls).toContainEqual({ path: "/app/me", method: "PATCH", body: { display_name: "Sol Bianchi" } });
    expect(state.auth.refreshMe).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith(t("account.nameSaved"));
    await act(async () => {
      fireEvent.click(screen.getByTestId("account-logout-all"));
    });
    expect(state.auth.logoutEverywhere).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith(t("account.logoutAllDone"));
    expect(toast.error).not.toHaveBeenCalled();
  });
});
