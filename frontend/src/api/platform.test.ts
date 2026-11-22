import { platformApi } from "./platform";

// P-71 (a): removing a platform manager never puts the email in the path (paths end up in the logs): POST with the
// email in the body.
const calls: { url: string; init: RequestInit }[] = [];

beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(null, { status: 204 });
  }));
});

describe("gestori della piattaforma: rimozione", () => {
  it("POST /app/platform/managers/remove con l'email nel corpo, mai nel percorso", async () => {
    await platformApi.removeManager("sol@hqe.it", "corr-1");
    expect(calls).toHaveLength(1);
    const { url, init } = calls[0];
    expect(new URL(url).pathname).toBe("/app/platform/managers/remove");
    expect(url).not.toMatch(/sol|hqe|%40/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ email: "sol@hqe.it" });
  });
});

// A7 (bff/API.md «Capienza della VM»): reading the capacity sends no order; «Aggiorna» is a POST without a body.
describe("capienza della VM", () => {
  it("GET /app/platform/capienza; «Aggiorna»: POST …/capienza/aggiorna senza corpo, con l'id della richiesta", async () => {
    await platformApi.capacity();
    expect(new URL(calls[0].url).pathname).toBe("/app/platform/capienza");
    expect(calls[0].init.method ?? "GET").toBe("GET");
    await platformApi.refreshCapacity("corr-7");
    const { url, init } = calls[1];
    expect(new URL(url).pathname).toBe("/app/platform/capienza/aggiorna");
    expect(init.method).toBe("POST");
    expect(init.body ?? null).toBeNull();
    expect((init.headers as Record<string, string>)["X-Correlation-Id"]).toBe("corr-7");
  });
});

// A2 (docs/proposta-a2.md §2): the routes of the creation from the app, with the correlation id of each action.
describe("creazione di un appartamento dall'app", () => {
  const last = () => ({ path: new URL(calls[calls.length - 1].url).pathname, init: calls[calls.length - 1].init });

  it("Crea: POST …/apartments/nuovo con id, nome, fuso e codice Italianway; nessun indirizzo né porta", async () => {
    await platformApi.createNew("t 1", { apartment_id: "lab-prova", name: "Prova", timezone: "Europe/Rome", italianway_id: null }, "corr-2");
    const { path, init } = last();
    expect(path).toBe("/app/platform/tenants/t%201/apartments/nuovo");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ apartment_id: "lab-prova", name: "Prova", timezone: "Europe/Rome", italianway_id: null });
    expect((init.headers as Record<string, string>)["X-Correlation-Id"]).toBe("corr-2");
  });

  it("Riprova e Annulla: POST …/creazione/riprova e …/annulla con la version", async () => {
    await platformApi.retryCreation("t-1", "lab-prova", 4, "corr-3");
    expect(last().path).toBe("/app/platform/tenants/t-1/apartments/lab-prova/creazione/riprova");
    expect(JSON.parse(String(last().init.body))).toEqual({ version: 4 });
    await platformApi.cancelCreation("t-1", "lab-prova", 5, "corr-4");
    expect(last().path).toBe("/app/platform/tenants/t-1/apartments/lab-prova/creazione/annulla");
    expect(JSON.parse(String(last().init.body))).toEqual({ version: 5 });
  });

  it("letture: l'organizzazione da sola (il conto dell'ultima ora) e la creazione di un appartamento", async () => {
    await platformApi.tenant("t-1");
    expect(last().path).toBe("/app/platform/tenants/t-1");
    expect(last().init.method).toBe("GET");
    await platformApi.creation("t-1", "lab-prova");
    expect(last().path).toBe("/app/platform/tenants/t-1/apartments/lab-prova/creazione");
  });
});

// A6 (bff/API.md «Eliminazione di un appartamento»): Disattiva, Riattiva, Elimina with the name, Riprova with the version.
describe("eliminazione di un appartamento", () => {
  const at = (i: number) => ({ path: new URL(calls[i].url).pathname, method: calls[i].init.method, body: calls[i].init.body ? JSON.parse(String(calls[i].init.body)) : null, cid: (calls[i].init.headers as Record<string, string>)["X-Correlation-Id"] });

  it("POST …/disattiva e …/riattiva senza corpo; …/elimina con il nome; …/eliminazione/riprova con la version", async () => {
    await platformApi.disable("t 1", "lab-ponte", "c-1");
    await platformApi.reenable("t 1", "lab-ponte", "c-2");
    await platformApi.deleteApartment("t 1", "lab-ponte", " Bilocale Ponte ", "c-3");
    await platformApi.retryDeletion("t 1", "lab-ponte", 4, "c-4");
    expect(at(0)).toEqual({ path: "/app/platform/tenants/t%201/apartments/lab-ponte/disattiva", method: "POST", body: null, cid: "c-1" });
    expect(at(1)).toEqual({ path: "/app/platform/tenants/t%201/apartments/lab-ponte/riattiva", method: "POST", body: null, cid: "c-2" });
    expect(at(2)).toEqual({ path: "/app/platform/tenants/t%201/apartments/lab-ponte/elimina", method: "POST", body: { nome: " Bilocale Ponte " }, cid: "c-3" });
    expect(at(3)).toEqual({ path: "/app/platform/tenants/t%201/apartments/lab-ponte/eliminazione/riprova", method: "POST", body: { version: 4 }, cid: "c-4" });
  });

  it("nessuna DELETE: la rotta di oggi risponde 409 use_elimina", () => {
    expect(Object.keys(platformApi)).not.toContain("removeApartment");
    expect(String(platformApi.deleteApartment)).not.toMatch(/DELETE/);
  });
});

// D-198 (o1 0b2548d): on an apartment created from the app the server takes a body with italianway_id alone; any other
// field answers 409 created_from_app. So the site sends exactly that, and null to remove the code.
describe("codice Italianway di un appartamento creato dall'app", () => {
  it("PATCH …/tenants/{t}/apartments/{id} con il solo italianway_id; null per toglierlo", async () => {
    await platformApi.setItalianwayCode("t 1", "lab-corte", "IW-4471", "corr-9");
    expect(new URL(calls[0].url).pathname).toBe("/app/platform/tenants/t%201/apartments/lab-corte");
    expect(calls[0].init.method).toBe("PATCH");
    expect(JSON.parse(String(calls[0].init.body))).toStrictEqual({ italianway_id: "IW-4471" });
    expect((calls[0].init.headers as Record<string, string>)["X-Correlation-Id"]).toBe("corr-9");
    await platformApi.setItalianwayCode("t 1", "lab-corte", null, "corr-10");
    expect(JSON.parse(String(calls[1].init.body))).toStrictEqual({ italianway_id: null });
  });
});
