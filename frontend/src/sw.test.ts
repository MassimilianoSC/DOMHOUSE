// P-92 / E-29, review P9: the service worker run for real, with a fake worker scope and a fake Cache Storage. It only
// does web push: no fetch handler (Chrome no longer starts it for navigations, so a stuck worker cannot hold the site),
// and on activate it deletes the copy of the site left by the workers before P-92, nothing else, then claims the pages.

type Listener = (event: unknown) => void;

async function loadWorker() {
  const listeners = new Map<string, Listener[]>();
  const scope = {
    skipWaiting: vi.fn(async () => undefined),
    clients: { claim: vi.fn(async () => undefined), matchAll: vi.fn(async () => []), openWindow: vi.fn() },
    registration: { showNotification: vi.fn() },
    navigator: { userAgent: "test" },
    addEventListener: (type: string, fn: Listener) => listeners.set(type, [...(listeners.get(type) ?? []), fn]),
  };
  const store = ["workbox-precache-v2-https://domhouse.example/", "workbox-runtime-x", "altro-del-sito"];
  const cacheStorage = {
    keys: vi.fn(async () => [...store]),
    delete: vi.fn(async (key: string) => {
      store.splice(store.indexOf(key), 1);
      return true;
    }),
  };
  vi.stubGlobal("self", scope);
  vi.stubGlobal("caches", cacheStorage);
  vi.resetModules();
  await import("./sw");
  return { listeners, scope, cacheStorage, store };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("service worker (P-92)", () => {
  it("ascolta solo activate, push e il clic sulla notifica: nessun gestore fetch", async () => {
    const { listeners, scope } = await loadWorker();
    expect([...listeners.keys()].sort()).toEqual(["activate", "notificationclick", "push"]);
    expect(scope.skipWaiting).toHaveBeenCalledTimes(1); // replaces the precaching worker at once
  });

  it("activate cancella le copie workbox-* e niente altro, poi prende le pagine aperte", async () => {
    const { listeners, scope, cacheStorage, store } = await loadWorker();
    let work: Promise<unknown> = Promise.resolve();
    listeners.get("activate")![0]({ waitUntil: (p: Promise<unknown>) => (work = p) });
    await work;
    expect(cacheStorage.delete.mock.calls.map((c) => c[0]).sort()).toEqual(["workbox-precache-v2-https://domhouse.example/", "workbox-runtime-x"]);
    expect(store).toEqual(["altro-del-sito"]);
    expect(scope.clients.claim).toHaveBeenCalledTimes(1);
    // claim only once the copies are gone
    expect(scope.clients.claim.mock.invocationCallOrder[0]).toBeGreaterThan(Math.max(...cacheStorage.delete.mock.invocationCallOrder));
  });

  it("una notifica arriva come prima: push la mostra", async () => {
    const { listeners, scope } = await loadWorker();
    let work: Promise<unknown> = Promise.resolve();
    listeners.get("push")![0]({ data: { json: () => ({ title: "Prova", body: "Messaggio" }) }, waitUntil: (p: Promise<unknown>) => (work = p) });
    await work;
    expect(scope.registration.showNotification).toHaveBeenCalledTimes(1);
  });
});
