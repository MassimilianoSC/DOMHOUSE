import { credentialsApi } from "./deviceCredentials";

// A3: the routes of docs/proposta-a3-server.md §2, under the two prefixes (the organization's admin; the platform
// manager in staging for lab-/test-). The site never sends a password: it only receives it from Registra/Rigenera.

type Call = { url: string; method: string; body: unknown; correlation: string | null };
let calls: Call[] = [];

beforeEach(() => {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    const headers = init.headers as Record<string, string>;
    calls.push({ url: new URL(url).pathname, method: init.method ?? "GET", body: init.body ? JSON.parse(init.body as string) : undefined, correlation: headers["X-Correlation-Id"] ?? null });
    return new Response(JSON.stringify({ items: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});

describe("credentialsApi", () => {
  it.each([
    ["apartment", "/app/apartments/lab-prova/device-credentials"],
    ["platform", "/app/platform/apartments/lab-prova/device-credentials"],
  ] as const)("prefisso %s: %s", async (scope, base) => {
    const api = credentialsApi("lab-prova", scope);
    await api.list();
    await api.register("shellyplugmg3-aa01", "c-1");
    await api.regenerate("shellyplugmg3-aa01", 3, "c-2");
    await api.revoke("shellyplugmg3-aa01", 4, "c-3");
    await api.retry("shellyplugmg3-aa01", 5, "c-4");
    expect(calls).toEqual([
      { url: base, method: "GET", body: undefined, correlation: null },
      { url: base, method: "POST", body: { device_id: "shellyplugmg3-aa01" }, correlation: "c-1" },
      { url: `${base}/shellyplugmg3-aa01/rigenera`, method: "POST", body: { version: 3 }, correlation: "c-2" },
      { url: `${base}/shellyplugmg3-aa01/revoca`, method: "POST", body: { version: 4 }, correlation: "c-3" },
      { url: `${base}/shellyplugmg3-aa01/riprova`, method: "POST", body: { version: 5 }, correlation: "c-4" },
    ]);
  });

  it("l'id dell'appartamento e del dispositivo vanno codificati nell'indirizzo", async () => {
    await credentialsApi("a b", "apartment").regenerate("x/y", 1, "c");
    expect(calls[0].url).toBe("/app/apartments/a%20b/device-credentials/x%2Fy/rigenera");
  });
});
