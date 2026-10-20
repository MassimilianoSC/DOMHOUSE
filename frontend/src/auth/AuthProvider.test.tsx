import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import { bffFetch } from "@/api/bff";
import { t } from "@/i18n";
import { AuthProvider, useAuth, useRole } from "./AuthProvider";

// Firebase and the BFF are simulated: a signed-in Firebase user, and /app/me answered by a stubbed fetch.
const fb = vi.hoisted(() => {
  const user = { email: "gestore@esempio.it", providerData: [{ providerId: "password" }], getIdToken: async () => "token-finto" };
  return { user, auth: { currentUser: user }, signOut: vi.fn(async () => {}), sendEmailVerification: vi.fn(async () => {}), deleteToken: vi.fn(async () => true), cb: null as null | ((u: unknown) => void) };
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
    cb(fb.user);
    return () => {};
  },
  signOut: fb.signOut,
  sendEmailVerification: fb.sendEmailVerification,
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));
vi.mock("firebase/messaging", () => ({ getMessaging: () => ({}), deleteToken: fb.deleteToken }));

function answerMe(status: number, body: unknown) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function Probe() {
  const { status, me } = useAuth();
  const { isAdmin, hasTenant } = useRole();
  return (
    <>
      <div data-testid="auth-status">{status}{me ? ` ${me.user.email}` : ""}</div>
      <div data-testid="auth-role">{`admin=${isAdmin} tenant=${hasTenant}`}</div>
    </>
  );
}

async function signIn() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByTestId("auth-status")).not.toHaveTextContent("loading"));
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("accesso: risposta di /app/me", () => {
  it("200: entra, con il token solo nell'intestazione Authorization", async () => {
    const fetchMock = answerMe(200, { user: { uid: "u1", email: "gestore@esempio.it", display_name: "" }, role: "operator", tenant: { tenant_id: "t1", name: "Demo" }, env: {} });
    await signIn();
    expect(screen.getByTestId("auth-status")).toHaveTextContent("authenticated gestore@esempio.it");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/app\/me$/);
    expect(url).not.toContain("token-finto");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer token-finto");
    expect(fb.signOut).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("403 forbidden: avvisa «Non hai i permessi…» ed esce da Firebase", async () => {
    answerMe(403, { error: "forbidden", message: "Utente senza tenant" });
    await signIn();
    expect(screen.getByTestId("auth-status")).toHaveTextContent("anonymous");
    await waitFor(() => expect(fb.signOut).toHaveBeenCalledTimes(1));
    expect(toast.error).toHaveBeenCalledWith(t("login.notEnabled"), expect.anything());
    expect(fb.sendEmailVerification).not.toHaveBeenCalled();
  });

  it("403 tenant_inactive: «La tua organizzazione non è attiva: contatta HQE.» ed esce da Firebase", async () => {
    answerMe(403, { error: "tenant_inactive", message: "Organizzazione non attiva" });
    await signIn();
    expect(screen.getByTestId("auth-status")).toHaveTextContent("anonymous");
    await waitFor(() => expect(fb.signOut).toHaveBeenCalledTimes(1));
    expect(toast.error).toHaveBeenCalledWith(t("login.tenantInactive"), expect.anything());
    expect(toast.error).not.toHaveBeenCalledWith(t("login.notEnabled"), expect.anything());
  });

  it("403 email_not_verified: manda il link di verifica, avvisa ed esce da Firebase", async () => {
    answerMe(403, { error: "email_not_verified", message: "Email non verificata" });
    await signIn();
    await waitFor(() => expect(fb.signOut).toHaveBeenCalledTimes(1));
    expect(fb.sendEmailVerification).toHaveBeenCalledWith(fb.user, { url: "http://localhost/login" });
    expect(toast.info).toHaveBeenCalledWith(t("login.verifySent", { email: "gestore@esempio.it" }), expect.anything());
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("403 email_not_verified con invio del link non riuscito: avvisa dell'errore ed esce lo stesso", async () => {
    fb.sendEmailVerification.mockRejectedValueOnce(new Error("auth/too-many-requests"));
    answerMe(403, { error: "email_not_verified", message: "Email non verificata" });
    await signIn();
    await waitFor(() => expect(fb.signOut).toHaveBeenCalledTimes(1));
    expect(toast.error).toHaveBeenCalledWith(t("login.verifyFailed"), expect.anything());
    expect(toast.info).not.toHaveBeenCalled();
  });

  it("401: resta sulla pagina di accesso senza avvisi e senza uscire da Firebase", async () => {
    answerMe(401, { error: "unauthorized", message: "Token scaduto" });
    await signIn();
    expect(screen.getByTestId("auth-status")).toHaveTextContent("anonymous");
    expect(toast.error).not.toHaveBeenCalled();
    expect(toast.info).not.toHaveBeenCalled();
    expect(fb.signOut).not.toHaveBeenCalled();
  });

  it("500: avvisa «Impossibile caricare il profilo» senza uscire da Firebase", async () => {
    answerMe(500, { error: "internal", message: "Errore interno" });
    await signIn();
    expect(screen.getByTestId("auth-status")).toHaveTextContent("anonymous");
    expect(toast.error).toHaveBeenCalledWith(t("login.bffError"), expect.objectContaining({ description: "Errore interno" }));
    expect(fb.signOut).not.toHaveBeenCalled();
  });
});

describe("sessione Firebase caduta da fuori (F4)", () => {
  it("onAuthStateChanged(null) dopo l'accesso: anonimo, token push tolto anche presso FCM", async () => {
    answerMe(200, { user: { uid: "u1", email: "gestore@esempio.it", display_name: "" }, role: "operator", tenant: { tenant_id: "t1", name: "Demo" }, env: {} });
    await signIn();
    expect(screen.getByTestId("auth-status")).toHaveTextContent("authenticated");
    localStorage.setItem("domotica.pushToken", "tok-u1");
    localStorage.setItem("domotica.pushTokenOwner", "u1");
    await act(async () => {
      fb.cb?.(null);
    });
    expect(screen.getByTestId("auth-status")).toHaveTextContent("anonymous");
    await waitFor(() => expect(fb.deleteToken).toHaveBeenCalledTimes(1));
    expect(localStorage.getItem("domotica.pushToken")).toBeNull();
  });
});

describe("/app/me senza risposta valida per un istante: le notifiche restano attive (N2)", () => {
  const ownToken = () => {
    localStorage.setItem("domotica.pushToken", "tok-u1");
    localStorage.setItem("domotica.pushTokenOwner", "u1");
  };

  it("5xx (per esempio cold start del BFF): nessuna cancellazione del token, né sul BFF né presso FCM", async () => {
    ownToken();
    const fetchMock = answerMe(503, { error: "unavailable", message: "Servizio non disponibile" });
    await signIn();
    await new Promise((r) => setTimeout(r, 50));
    expect(fb.deleteToken).not.toHaveBeenCalled();
    expect((fetchMock.mock.calls as unknown as [string, RequestInit?][]).some(([, init]) => init?.method === "DELETE")).toBe(false);
    expect(localStorage.getItem("domotica.pushToken")).toBe("tok-u1");
    expect(localStorage.getItem("domotica.pushTokenOwner")).toBe("u1");
  });

  it("rete assente all'avvio della PWA: nessuna cancellazione del token", async () => {
    ownToken();
    vi.stubGlobal("fetch", vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }));
    await signIn();
    await new Promise((r) => setTimeout(r, 50));
    expect(fb.deleteToken).not.toHaveBeenCalled();
    expect(localStorage.getItem("domotica.pushToken")).toBe("tok-u1");
  });

  it("401 di /app/me (sessione davvero finita): il token viene tolto", async () => {
    ownToken();
    answerMe(401, { error: "unauthorized", message: "Sessione scaduta" });
    await signIn();
    await waitFor(() => expect(fb.deleteToken).toHaveBeenCalledTimes(1));
    expect(localStorage.getItem("domotica.pushToken")).toBeNull();
  });
});

describe("organizzazione sospesa (P-50, D-85)", () => {
  const SUSPENDED = { error: "tenant_suspended", message: "Organizzazione sospesa: contatta l'assistenza HQE" };
  const ME = { user: { uid: "u1", email: "gestore@esempio.it", display_name: "" }, role: "admin", tenant: { tenant_id: "t1", name: "Demo", suspended: false }, env: {} };

  it("all'accesso (403 tenant_suspended): fuori, con il messaggio dedicato, ed esce da Firebase", async () => {
    const fetchMock = answerMe(403, SUSPENDED);
    await signIn();
    await new Promise((r) => setTimeout(r, 50));
    expect(fetchMock).toHaveBeenCalledTimes(1); // one profile read, not a loop of them
    expect(screen.getByTestId("auth-status")).toHaveTextContent("anonymous");
    await waitFor(() => expect(fb.signOut).toHaveBeenCalledTimes(1));
    expect(toast.error).toHaveBeenCalledWith(t("login.tenantSuspended"), expect.anything());
    expect(toast.error).not.toHaveBeenCalledWith(t("login.notEnabled"), expect.anything());
  });

  it("sospesa mentre si usa l'app: qualunque chiamata con 403 tenant_suspended rilegge il profilo, e si esce con il messaggio", async () => {
    answerMe(200, ME);
    await signIn();
    expect(screen.getByTestId("auth-status")).toHaveTextContent("authenticated");
    const fetchMock = answerMe(403, SUSPENDED);
    await act(async () => {
      // several queries failing at once (the page, the devices, the approvals)
      await Promise.all(["/app/apartments", "/app/apartments/apt-001/devices", "/app/apartments/apt-001/approvals"].map((p) => bffFetch(p).catch(() => undefined)));
    });
    await waitFor(() => expect(screen.getByTestId("auth-status")).toHaveTextContent("anonymous"));
    expect(toast.error).toHaveBeenCalledWith(t("login.tenantSuspended"), expect.anything());
    const meCalls = fetchMock.mock.calls.filter((c) => String((c as unknown[])[0]).endsWith("/app/me"));
    expect(meCalls).toHaveLength(1); // two failing calls, one profile re-read
  });

  it("gestore della piattaforma membro dell'organizzazione sospesa: resta dentro, senza le pagine dell'organizzazione", async () => {
    answerMe(200, { ...ME, user: { ...ME.user, platform_manager: true }, tenant: { ...ME.tenant, suspended: true } });
    await signIn();
    expect(screen.getByTestId("auth-status")).toHaveTextContent("authenticated");
    expect(screen.getByTestId("auth-role")).toHaveTextContent("admin=false tenant=false");
    expect(fb.signOut).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  });

  it("organizzazione attiva: tutto come prima", async () => {
    answerMe(200, ME);
    await signIn();
    expect(screen.getByTestId("auth-role")).toHaveTextContent("admin=true tenant=true");
  });
});
