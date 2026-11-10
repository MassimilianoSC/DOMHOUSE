import { t } from "@/i18n";
import { adminApi } from "./admin";
import { ApiError, bffDownload, bffFetch, CALL_TIMEOUT_MS, setAuthResolver, SLOW_CALL_TIMEOUT_MS } from "./bff";
import { instanceApi } from "./instance";
import { platformApi } from "./platform";
import { ruleCopyApi, type CopyPreview } from "./ruleCopy";
import { ruleProposalApi } from "./ruleProposals";

// D-198: a call to the server that never answers ends in the usual «Server non raggiungibile», it does not leave the
// page loading for ever. The calls the server itself may spend time on get a longer limit.
const never = () => new Promise<never>(() => {});
let signals: AbortSignal[];

function hangingFetch() {
  vi.stubGlobal("fetch", vi.fn((_url: string, init: RequestInit) => {
    signals.push(init.signal as AbortSignal);
    return never();
  }));
}

/** Watches a call without letting its failure go unhandled. */
function watch(call: Promise<unknown>) {
  const seen: { done: boolean; error?: unknown } = { done: false };
  call.then(() => (seen.done = true), (error) => Object.assign(seen, { done: true, error }));
  return seen;
}
const advance = (ms: number) => vi.advanceTimersByTimeAsync(ms);
const NETWORK = { status: 0, code: "network", message: t("errors.network") };

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  signals = [];
  setAuthResolver(async () => ({}));
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  setAuthResolver(async () => ({}));
});

describe("tempo massimo delle chiamate al server (D-198)", () => {
  it("i limiti: 30 secondi di norma, 90 per le chiamate lente note", () => {
    expect(CALL_TIMEOUT_MS).toBe(30_000);
    expect(SLOW_CALL_TIMEOUT_MS).toBe(90_000);
  });

  it("nessuna risposta: fino al limite aspetta, poi «Server non raggiungibile» e la richiesta è interrotta", async () => {
    hangingFetch();
    const seen = watch(bffFetch("/app/apartments", { correlationId: "corr-1" }));
    await advance(CALL_TIMEOUT_MS - 1);
    expect(seen.done).toBe(false);
    expect(signals[0].aborted).toBe(false);
    await advance(1);
    expect(seen.error).toBeInstanceOf(ApiError);
    expect(seen.error).toMatchObject({ ...NETWORK, correlationId: "corr-1" });
    expect(signals[0].aborted).toBe(true);
  });

  it("risposta iniziata ma mai finita: anche la lettura del corpo rientra nel limite", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ status: 200, ok: true, text: never }) as unknown as Response));
    const seen = watch(bffFetch("/app/apartments"));
    await advance(CALL_TIMEOUT_MS);
    expect(seen.error).toMatchObject(NETWORK);
  });

  it("corpo interrotto dalla rete: «Server non raggiungibile», non un errore grezzo", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ status: 200, ok: true, text: async () => { throw new TypeError("network error"); } }) as unknown as Response));
    const seen = watch(bffFetch("/app/apartments"));
    await advance(0);
    expect(seen.error).toMatchObject(NETWORK);
  });

  it("il token non arriva: anche l'attesa del token rientra nel limite", async () => {
    setAuthResolver(never);
    hangingFetch();
    const seen = watch(bffFetch("/app/apartments"));
    await advance(CALL_TIMEOUT_MS);
    expect(seen.error).toMatchObject(NETWORK);
    expect(signals).toHaveLength(0);
  });

  // Firebase renews an expired token over the network: in airplane mode that fails at once with this code.
  const noNetworkForToken = async () => Promise.reject(Object.assign(new Error("Firebase: Error (auth/network-request-failed)."), { code: "auth/network-request-failed" }));

  it("token scaduto e niente rete: «Server non raggiungibile» con il suo ID, non «Operazione non riuscita»", async () => {
    setAuthResolver(noNetworkForToken);
    hangingFetch();
    const seen = watch(bffFetch("/app/me/push/prefs", { method: "PUT", body: {}, correlationId: "corr-2" }));
    await advance(0);
    expect(seen.error).toBeInstanceOf(ApiError);
    expect(seen.error).toMatchObject({ ...NETWORK, correlationId: "corr-2" });
    expect(signals).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("token scaduto e niente rete, scaricando l'Excel: lo stesso messaggio", async () => {
    setAuthResolver(noNetworkForToken);
    hangingFetch();
    const seen = watch(bffDownload("/x", { fallbackName: "x.xlsx", correlationId: "corr-3" }));
    await advance(0);
    expect(seen.error).toMatchObject({ ...NETWORK, correlationId: "corr-3" });
  });

  it("un altro rifiuto del servizio di accesso resta quello che è", async () => {
    const revoked = Object.assign(new Error("revoked"), { code: "auth/user-token-expired" });
    setAuthResolver(() => Promise.reject(revoked));
    hangingFetch();
    const seen = watch(bffFetch("/app/apartments"));
    await advance(0);
    expect(seen.error).toBe(revoked);
  });

  it("risposta in tempo: il risultato, e nessun timer rimasto", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response('{"ok":true}', { status: 200 })));
    const seen = watch(bffFetch("/app/apartments"));
    await advance(0);
    expect(seen).toEqual({ done: true });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("un rifiuto del server resta il rifiuto del server", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "forbidden", message: "No" }), { status: 403 })));
    const seen = watch(bffFetch("/app/apartments"));
    await advance(0);
    expect(seen.error).toMatchObject({ status: 403, code: "forbidden", message: "No" });
    expect(vi.getTimerCount()).toBe(0);
  });

  it("scaricamento: con il limite lungo, e l'Excel che non arriva finisce nello stesso messaggio", async () => {
    hangingFetch();
    const seen = watch(bffDownload("/app/apartments/a/energy/export", { fallbackName: "x.xlsx" }));
    await advance(SLOW_CALL_TIMEOUT_MS - 1);
    expect(seen.done).toBe(false);
    await advance(1);
    expect(seen.error).toMatchObject(NETWORK);
    expect(signals[0].aborted).toBe(true);
  });

  it("scaricamento riuscito: il file e il suo nome, nessun timer rimasto", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("xlsx", { status: 200, headers: { "Content-Disposition": 'attachment; filename="c.xlsx"' } })));
    const seen = watch(bffDownload("/x", { fallbackName: "x.xlsx" }).then((r) => expect(r.name).toBe("c.xlsx")));
    await vi.waitFor(() => expect(seen).toEqual({ done: true }));
    expect(vi.getTimerCount()).toBe(0);
  });

  it("scaricamento rifiutato: il messaggio del server", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "no_data", message: "Nessun dato" }), { status: 404 })));
    const seen = watch(bffDownload("/x", { fallbackName: "x.xlsx" }));
    await vi.waitFor(() => expect(seen.done).toBe(true));
    expect(seen.error).toMatchObject({ status: 404, code: "no_data", message: "Nessun dato" });
  });

  const preview = { from: { based_on: "x" }, targets: [] } as unknown as CopyPreview;
  it.each<[string, () => Promise<unknown>]>([
    ["domanda all'assistente", () => instanceApi("a").ask("ciao", "c")],
    ["proposta di regole", () => ruleProposalApi("a").propose("testo", "c")],
    ["anteprima della copia", () => ruleCopyApi("a").preview(["b"], "c")],
    ["copia delle regole", () => ruleCopyApi("a").copy(preview, "c")],
    ["invito", () => adminApi.invite({ email: "a@b.it", role: "operator", display_name: "" }, "c")],
    ["nuovo invio dell'invito", () => adminApi.resendInvite("u", "c")],
    ["verifica della connessione", () => adminApi.verify("a", "c")],
    ["nuova organizzazione", () => platformApi.createTenant({ name: "n", admin_email: "a@b.it" }, "c")],
    ["invito della piattaforma", () => platformApi.resendInvite("t", "c")],
    ["verifica della piattaforma", () => platformApi.verifyApartment("t", "a", "c")],
  ])("chiamata lenta nota, %s: oltre il limite normale aspetta ancora", async (_name, call) => {
    hangingFetch();
    const seen = watch(call());
    await advance(CALL_TIMEOUT_MS);
    expect(seen.done).toBe(false);
    await advance(SLOW_CALL_TIMEOUT_MS - CALL_TIMEOUT_MS);
    expect(seen.error).toMatchObject(NETWORK);
  });

  it("chiamata normale del motore: il limite normale", async () => {
    hangingFetch();
    const seen = watch(instanceApi("a").getDevices());
    await advance(CALL_TIMEOUT_MS);
    expect(seen.error).toMatchObject(NETWORK);
  });
});
