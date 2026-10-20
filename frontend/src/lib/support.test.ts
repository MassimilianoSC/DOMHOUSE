import { bffFetch } from "@/api/bff";
import { endSupportSession, startSupportSession, supportHeader, supportSession } from "./support";

// Assistance access (P-50, D-86): the X-Support-Tenant header goes on organization calls only, in this tab only.
const SESSION = { tenant_id: "t-2", tenant_name: "Riviera", access_id: "sa-1", expires_at: "2026-10-16T18:30:00Z" };

let sent: { path: string; method: string; headers: Record<string, string> }[];

beforeEach(() => {
  sessionStorage.clear();
  sent = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    sent.push({ path: new URL(url).pathname, method: init?.method ?? "GET", headers: (init?.headers ?? {}) as Record<string, string> });
    return new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } });
  }));
});

describe("assistenza: intestazione X-Support-Tenant", () => {
  it("senza accesso aperto in questa scheda: nessuna intestazione", async () => {
    await bffFetch("/app/apartments");
    expect(sent[0].headers["X-Support-Tenant"]).toBeUndefined();
    expect(supportSession()).toBeNull();
  });

  it("con l'accesso aperto: sulle rotte dell'organizzazione e su /app/me sì; su piattaforma e push mai", async () => {
    startSupportSession(SESSION);
    for (const p of ["/app/me", "/app/apartments", "/app/apartments/apt-001/devices", "/app/platform/tenants", "/app/push/subscribe"]) await bffFetch(p);
    const header = (p: string) => sent.find((x) => x.path === p)?.headers["X-Support-Tenant"];
    expect(header("/app/me")).toBe("t-2");
    expect(header("/app/apartments")).toBe("t-2");
    expect(header("/app/apartments/apt-001/devices")).toBe("t-2");
    expect(header("/app/platform/tenants")).toBeUndefined();
    expect(header("/app/push/subscribe")).toBeUndefined();
  });

  it("uscita: l'intestazione sparisce", async () => {
    startSupportSession(SESSION);
    endSupportSession();
    await bffFetch("/app/apartments");
    expect(sent[0].headers["X-Support-Tenant"]).toBeUndefined();
    expect(supportHeader("/app/apartments")).toEqual({});
  });

  it("dato rovinato in sessionStorage: come nessun accesso", () => {
    sessionStorage.setItem("domotica.support", "{rotto");
    expect(supportSession()).toBeNull();
    sessionStorage.setItem("domotica.support", JSON.stringify({ tenant_id: "t-2" }));
    expect(supportSession()).toBeNull();
  });
});

describe("assistenza: lista bianca (D-89)", () => {
  const header = (path: string, method = "GET") => sent.find((x) => x.path === path && x.method === method)?.headers["X-Support-Tenant"];

  it("mai sulle rotte del proprio account né su quelle di sviluppo; sì su GET /app/me, appartamenti e amministrazione", async () => {
    startSupportSession(SESSION);
    await bffFetch("/app/me");
    await bffFetch("/app/me", { method: "PATCH", body: { display_name: "x" } });
    await bffFetch("/app/me", { method: "DELETE" });
    await bffFetch("/app/me/notification-prefs", { method: "PUT", body: {} });
    await bffFetch("/app/me/revoke-sessions", { method: "POST" });
    await bffFetch("/app/dev/reset", { method: "POST" });
    await bffFetch("/app/apartments/apt-001/devices");
    await bffFetch("/app/admin/users");
    expect(header("/app/me")).toBe("t-2");
    expect(header("/app/me", "PATCH")).toBeUndefined();
    expect(header("/app/me", "DELETE")).toBeUndefined();
    expect(header("/app/me/notification-prefs", "PUT")).toBeUndefined();
    expect(header("/app/me/revoke-sessions", "POST")).toBeUndefined();
    expect(header("/app/dev/reset", "POST")).toBeUndefined();
    expect(header("/app/apartments/apt-001/devices")).toBe("t-2");
    // a stray admin call inside the assisted organization is refused by the server instead of reading the manager's own
    expect(header("/app/admin/users")).toBe("t-2");
  });
});
