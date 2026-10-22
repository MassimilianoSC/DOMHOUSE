import { render, screen } from "@testing-library/react";
import { toast } from "sonner";
import { t } from "@/i18n";
import { loginError, showLoginError } from "./loginErrors";

// D-156: a failed sign-in says what to do where someone can act, and always shows the Firebase code under it.
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const fail = (code: string) => Object.assign(new Error("Firebase: Error"), { code });
const DOMAIN = "Questo indirizzo del sito non è autorizzato per l'accesso: avvisa l'assistenza HQE";

beforeEach(() => vi.clearAllMocks());

describe("accesso non riuscito: la frase (D-156)", () => {
  it.each([
    ["auth/unauthorized-domain", DOMAIN],
    ["auth/requests-from-referer-https://domhouse-staging.web.app-are-blocked.", DOMAIN],
    ["auth/popup-blocked", "Il browser ha bloccato la finestra di Google: consenti le finestre pop-up per questo sito e riprova"],
    ["auth/operation-not-allowed", "Accesso con Google non attivo: avvisa l'assistenza HQE"],
    ["auth/internal-error", "Accesso con Google non riuscito"],
  ])("Google, %s: «%s», con il codice", (code, message) => {
    expect(loginError(fail(code), "google")).toEqual({ message, code });
  });

  it.each(["auth/popup-closed-by-user", "auth/cancelled-popup-request", "auth/user-cancelled"])("Google, %s: la persona ha chiuso la finestra, nessun messaggio", (code) => {
    expect(loginError(fail(code), "google")).toBeNull();
  });

  it.each([
    ["auth/invalid-credential", t("login.failed")],
    ["auth/wrong-password", t("login.failed")],
    ["auth/unauthorized-domain", DOMAIN],
    ["auth/too-many-requests", t("account.errors.tooManyRequests")],
    ["auth/network-request-failed", t("account.errors.network")],
  ])("email e password, %s: «%s», con il codice", (code, message) => {
    expect(loginError(fail(code), "email")).toEqual({ message, code });
  });

  it("errore senza codice: la frase generica, senza riga del codice", () => {
    expect(loginError(new Error("boom"), "email")).toEqual({ message: t("login.failed"), code: null });
    expect(loginError(undefined, "google")).toEqual({ message: "Accesso con Google non riuscito", code: null });
  });
});

describe("accesso non riuscito: l'avviso", () => {
  it("la frase e, sotto, «Codice: auth/…» intero e copiabile", () => {
    showLoginError(fail("auth/unauthorized-domain"), "google");
    expect(toast.error).toHaveBeenCalledTimes(1);
    const [message, opts] = vi.mocked(toast.error).mock.calls[0] as [string, { description: React.ReactNode }];
    expect(message).toBe(DOMAIN);
    render(<>{opts.description}</>);
    expect(screen.getByTestId("login-error-code")).toHaveTextContent("Codice: auth/unauthorized-domain");
    const id = screen.getByTestId("login-error-code-id");
    expect(id).toHaveAttribute("data-correlation-id", "auth/unauthorized-domain");
    expect(id).toHaveAttribute("aria-label", `${t("common.copy")} Codice auth/unauthorized-domain`);
  });

  it("finestra chiusa dalla persona: nessun avviso", () => {
    showLoginError(fail("auth/popup-closed-by-user"), "google");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("senza codice: la frase, senza seconda riga", () => {
    showLoginError(new Error("boom"), "email");
    expect(toast.error).toHaveBeenCalledWith(t("login.failed"), expect.objectContaining({ description: undefined }));
  });
});
