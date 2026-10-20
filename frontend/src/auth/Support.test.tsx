import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import { bffFetch } from "@/api/bff";
import { t } from "@/i18n";
import { supportSession } from "@/lib/support";
import { AuthProvider, useAuth, useRole } from "./AuthProvider";

// Assistance access (P-50, D-86): entering and leaving another organization empties the tab like a change of user
// (P-36); the end of the access, by the server (403 support_expired) or by the clock, brings the manager back.
vi.mock("@/lib/utils", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/utils")>();
  return { ...mod, env: { ...mod.env, authMode: "dev", bffUrl: "", fcmEnabled: false } };
});
vi.mock("@/auth/firebase", () => ({ firebaseConfigured: false, firebaseApp: async () => ({}), firebaseAuth: async () => ({}), continueUrl: () => ({ url: "" }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn(), dismiss: vi.fn() } }));

const OWN = { tenant_id: "t-1", name: "Flatsharing", suspended: false };
const OTHER = { tenant_id: "t-2", name: "Riviera", suspended: false };
const EXPIRES = new Date(Date.now() + 2 * 3600 * 1000).toISOString();

let ctx: ReturnType<typeof useAuth>;
let client: QueryClient;
let calls: { path: string; method: string; support?: string }[];
let expired: boolean;
/** What the server answers to a call carrying the header once the access is over (or the organization suspended). */
let blockedCode: string;
/** /app/me with the header still accepted (sent before the end), while the other calls are already refused. */
let meStillValid: boolean;
/** Holds /app/me until released: a profile read in flight. */
let meGate: Promise<void> | null;
let history: string[];

function Probe() {
  ctx = useAuth();
  const { role, isAdmin } = useRole();
  if (history.at(-1) !== ctx.status) history.push(ctx.status);
  return <p data-testid="who">{`${ctx.status} ${ctx.me?.tenant?.name ?? "-"} ${role} admin=${isAdmin} support=${ctx.me?.support?.access_id ?? "-"}`}</p>;
}

function bff() {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    const support = (init?.headers as Record<string, string>)["X-Support-Tenant"];
    calls.push({ path, method: init?.method ?? "GET", support });
    if (path === "/app/me" && meGate) await meGate;
    if (support && expired && !(path === "/app/me" && meStillValid)) return new Response(JSON.stringify({ error: blockedCode, message: "bloccato" }), { status: 403 });
    if (path === "/app/me") {
      const user = { uid: "m1", email: "m@hqe.it", display_name: "Marco", platform_manager: true };
      const body = support
        ? { user, role: "operator", tenant: OTHER, support: { access_id: "sa-1", tenant_id: "t-2", expires_at: EXPIRES, reason: "verifica" }, support_access: [], env: {} }
        : { user, role: "admin", tenant: OWN, support_access: [], env: {} };
      return new Response(JSON.stringify(body), { status: 200 });
    }
    return new Response("[]", { status: 200 });
  }));
}

async function start() {
  calls = [];
  expired = false;
  blockedCode = "support_expired";
  meStillValid = false;
  meGate = null;
  history = [];
  sessionStorage.clear();
  localStorage.clear();
  client = new QueryClient();
  bff();
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
  await act(() => ctx.devLogin("m@hqe.it"));
  await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("authenticated Flatsharing admin admin=true support=-"));
}

async function enter() {
  client.setQueryData(["apartments"], [{ apartment_id: "apt-own" }]);
  await act(() => ctx.enterSupport({ tenant_id: "t-2", tenant_name: "Riviera", access_id: "sa-1", expires_at: EXPIRES }));
  await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("authenticated Riviera operator admin=false support=sa-1"));
  history.length = 0; // from here on: never signed out
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("assistenza: entrata e uscita (P-50, D-86)", () => {
  it("entrata: i dati della propria organizzazione spariscono; il profilo diventa quello dell'assistenza, da operatore", async () => {
    await start();
    await enter();
    expect(client.getQueryData(["apartments"])).toBeUndefined();
    expect(calls.filter((c) => c.path === "/app/me").at(-1)?.support).toBe("t-2");
    expect(supportSession()?.access_id).toBe("sa-1");
  });

  it("uscita volontaria: dati svuotati, intestazione tolta, di nuovo nella propria organizzazione", async () => {
    await start();
    await enter();
    client.setQueryData(["apartments"], [{ apartment_id: "apt-other" }]);
    await act(() => ctx.leaveSupport());
    await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("authenticated Flatsharing admin admin=true support=-"));
    expect(client.getQueryData(["apartments"])).toBeUndefined();
    expect(supportSession()).toBeNull();
    expect(calls.filter((c) => c.path === "/app/me").at(-1)?.support).toBeUndefined();
    expect(toast.info).not.toHaveBeenCalledWith(t("support.expired", { name: "Riviera" }), expect.anything());
  });

  it("scaduto o chiuso dall'admin: qualunque chiamata con 403 support_expired riporta indietro, con l'avviso", async () => {
    await start();
    await enter();
    expired = true;
    await act(async () => {
      await Promise.all(["/app/apartments", "/app/apartments/apt-001/devices"].map((p) => bffFetch(p).catch(() => undefined)));
    });
    await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("authenticated Flatsharing admin admin=true support=-"));
    expect(toast.info).toHaveBeenCalledWith(t("support.expired", { name: "Riviera" }), expect.anything());
    expect(supportSession()).toBeNull();
  });

  it("scaduto mentre la scheda era chiusa: alla riapertura /app/me risponde 403 support_expired e si torna indietro", async () => {
    await start();
    await enter();
    expired = true;
    await act(() => ctx.refreshMe());
    await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("authenticated Flatsharing admin admin=true support=-"));
    expect(screen.getByTestId("who")).not.toHaveTextContent("anonymous");
  });

  it("scadenza dell'orologio: si esce all'ora prevista anche senza nessuna chiamata", async () => {
    await start();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await enter();
    expired = true;
    await act(async () => {
      vi.advanceTimersByTime(2 * 3600 * 1000 + 10_000); // the expected end plus the margin before asking the server
    });
    await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("Flatsharing"));
    expect(supportSession()).toBeNull();
  });

  it("«Esci» durante l'assistenza: anche la modalità assistenza finisce", async () => {
    await start();
    await enter();
    await act(() => ctx.logout());
    expect(supportSession()).toBeNull();
  });
});

describe("assistenza: casi trovati dalla revisione", () => {
  const neverOut = () => expect(history.filter((s) => s === "anonymous")).toEqual([]);

  it("/app/me stesso risponde 403 support_expired: si torna indietro SENZA uscire dall'app e senza avvisi d'errore", async () => {
    await start();
    await enter();
    expired = true;
    await act(() => ctx.refreshMe());
    await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("authenticated Flatsharing admin admin=true support=-"));
    neverOut();
    expect(toast.error).not.toHaveBeenCalled();
    expect(toast.info).toHaveBeenCalledTimes(1);
  });

  it("organizzazione assistita sospesa nel frattempo (403 tenant_suspended): si torna nella propria, senza uscire", async () => {
    await start();
    await enter();
    expired = true;
    blockedCode = "tenant_suspended";
    await act(async () => {
      await bffFetch("/app/apartments").catch(() => undefined);
    });
    await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("authenticated Flatsharing admin admin=true support=-"));
    neverOut();
    expect(toast.error).not.toHaveBeenCalledWith(t("login.tenantSuspended"), expect.anything());
    expect(supportSession()).toBeNull();
  });

  it("orologio del dispositivo avanti: allo scadere locale si chiede al server, che dice ancora valido, e si resta", async () => {
    await start();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await enter();
    await act(async () => {
      vi.advanceTimersByTime(2 * 3600 * 1000 + 10_000);
    });
    await waitFor(() => expect(calls.filter((c) => c.path === "/app/me").at(-1)?.support).toBe("t-2"));
    expect(screen.getByTestId("who")).toHaveTextContent("support=sa-1");
    expect(toast.info).not.toHaveBeenCalled();
  });

  it("«Esci» durante l'assistenza: l'accesso viene chiuso anche sul server", async () => {
    await start();
    await enter();
    await act(() => ctx.logout());
    expect(calls).toContainEqual(expect.objectContaining({ path: "/app/platform/tenants/t-2/support-access/sa-1", method: "DELETE" }));
  });
});

describe("assistenza: rifiniture di Fable (D-89)", () => {
  it("«Elimina il mio account» in assistenza: prima chiude l'accesso sul server, poi elimina", async () => {
    await start();
    await enter();
    await act(() => ctx.deleteAccount());
    const close = calls.findIndex((c) => c.path === "/app/platform/tenants/t-2/support-access/sa-1" && c.method === "DELETE");
    const del = calls.findIndex((c) => c.path === "/app/me" && c.method === "DELETE");
    expect(close).toBeGreaterThanOrEqual(0);
    expect(del).toBeGreaterThan(close);
    expect(calls[del].support).toBeUndefined();
  });

  it("uscendo dall'assistenza gli avvisi dell'organizzazione assistita spariscono", async () => {
    await start();
    await enter();
    await act(() => ctx.leaveSupport());
    expect(toast.dismiss).toHaveBeenCalled();
  });

  it("un 403 support_expired arrivato mentre una lettura del profilo è in volo non va perso", async () => {
    await start();
    await enter();
    let release = () => {};
    meGate = new Promise<void>((r) => (release = r));
    meStillValid = true;
    expired = true;
    let reading: Promise<void> = Promise.resolve();
    await act(async () => {
      reading = ctx.refreshMe();
      await bffFetch("/app/apartments").catch(() => undefined);
    });
    meGate = null;
    release();
    await act(() => reading);
    await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent("authenticated Flatsharing admin admin=true support=-"));
    expect(toast.info).toHaveBeenCalledWith(t("support.expired", { name: "Riviera" }), expect.anything());
  });
});
