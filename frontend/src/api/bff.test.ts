import { t } from "@/i18n";
import { startSupportSession, endSupportSession } from "@/lib/support";
import { ApiError, bffDownload, bffFetch, fileNameFrom } from "./bff";

// What the user reads when the BFF refuses a request: its Italian message, or a plain fallback, never a bare code.
function answer(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(body === undefined ? "" : JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })));
}

async function failure(): Promise<ApiError> {
  try {
    await bffFetch("/app/admin/users/u1", { method: "PATCH", body: { apartment_ids: "tutti" }, correlationId: "corr-1" });
  } catch (e) {
    return e as ApiError;
  }
  throw new Error("nessun errore");
}

describe("messaggi d'errore del BFF", () => {
  it("errore del BFF con codice e messaggio: arriva così com'è, con l'ID richiesta", async () => {
    answer(422, { error: "unknown_apartment", message: "Appartamento sconosciuto: apt-x", details: { apartment_ids: ["apt-x"] } });
    const e = await failure();
    expect(e).toMatchObject({ status: 422, code: "unknown_apartment", message: "Appartamento sconosciuto: apt-x", correlationId: "corr-1" });
  });

  it("422 standard di FastAPI ({detail: [...]}): «Richiesta non accettata…», non «Errore 422»", async () => {
    answer(422, { detail: [{ type: "literal_error", loc: ["body", "apartment_ids"], msg: "Input should be 'all'" }] });
    const e = await failure();
    expect(e).toMatchObject({ status: 422, code: "validation_error", message: t("errors.invalidRequest") });
  });

  it("errore senza corpo leggibile: «Errore N»", async () => {
    answer(502, undefined);
    const e = await failure();
    expect(e).toMatchObject({ status: 502, code: "error", message: t("errors.status", { status: 502 }) });
  });

  it("server non raggiungibile: «Server non raggiungibile»", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const e = await failure();
    expect(e).toMatchObject({ status: 0, code: "network", message: t("errors.network") });
  });
});

describe("file dal BFF (P-52)", () => {
  it("nome del file: filename* in UTF-8 prima, poi filename, altrimenti nessuno", () => {
    expect(fileNameFrom(`attachment; filename="consumi-apt-001-2026-10.xlsx"; filename*=UTF-8''consumi-apt-001-2026-10.xlsx`)).toBe("consumi-apt-001-2026-10.xlsx");
    expect(fileNameFrom("attachment; filename*=UTF-8''consumi%20Milano%20%C3%A8.xlsx")).toBe("consumi Milano è.xlsx");
    expect(fileNameFrom('attachment; filename="consumi-apt-001-RES-1.xlsx"')).toBe("consumi-apt-001-RES-1.xlsx");
    expect(fileNameFrom("attachment; filename=semplice.xlsx")).toBe("semplice.xlsx");
    expect(fileNameFrom(null)).toBeNull();
    expect(fileNameFrom("attachment")).toBeNull();
  });

  it("scaricamento: con le intestazioni (anche quella dell'assistenza), il file e il nome dato dal server", async () => {
    const seen: Record<string, string>[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_url: string, init?: RequestInit) => {
      seen.push(init?.headers as Record<string, string>);
      return new Response("xlsx", { status: 200, headers: { "Content-Disposition": 'attachment; filename="consumi-apt-001-2026-10.xlsx"' } });
    }));
    startSupportSession({ tenant_id: "t-2", tenant_name: "Riviera", access_id: "sa-1", expires_at: "2099-01-01T00:00:00Z" });
    const res = await bffDownload("/app/apartments/apt-001/energy/export", { query: { month: "2026-10" }, correlationId: "c-1", fallbackName: "x.xlsx" });
    endSupportSession();
    expect(res.name).toBe("consumi-apt-001-2026-10.xlsx");
    expect(res.blob.size).toBe(4);
    expect(seen[0]).toMatchObject({ "X-Correlation-Id": "c-1", "X-Support-Tenant": "t-2" });
  });

  it("senza Content-Disposition: il nome di riserva", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(new Blob(["x"]), { status: 200 })));
    expect((await bffDownload("/app/apartments/apt-001/energy/export", { fallbackName: "riserva.xlsx" })).name).toBe("riserva.xlsx");
  });

  it("rifiuto del server: l'ApiError di sempre, con il suo messaggio", async () => {
    answer(501, { error: "not_implemented", message: "Consumi non disponibili per questo appartamento" });
    await expect(bffDownload("/app/apartments/apt-001/energy/export", { query: { month: "2026-10" }, fallbackName: "x" })).rejects.toMatchObject({ status: 501, code: "not_implemented", message: "Consumi non disponibili per questo appartamento" });
  });
});
