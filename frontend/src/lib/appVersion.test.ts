import { assetRefs, documentRefs, VersionWatch, AUTO_RELOAD_MS } from "./appVersion";

// P-92: a page that stays on the previous release after a publication. The watch compares the /assets/ files of the
// page it is running with those of index.html on the network: a difference is a new version. In the first seconds
// after opening (or coming back from the background), with nothing touched yet, it reloads by itself; otherwise the
// banner «È disponibile una versione nuova — Aggiorna» and a reload at the first change of page.

const page = (entry: string, css = "index-AAA.css") => `<!doctype html><html><head>
    <script type="module" crossorigin src="/assets/${entry}"></script>
    <link rel="modulepreload" crossorigin href="/assets/vendor-VVV.js">
    <link rel="stylesheet" crossorigin href="/assets/${css}">
  <link rel="manifest" href="/manifest.webmanifest"><script id="vite-plugin-pwa:register-sw" src="/registerSW.js"></script></head>
  <body><div id="root"></div></body></html>`;

const OLD = page("index-OLD.js");
const NEW = page("index-NEW.js");

describe("le asset di una pagina", () => {
  it("dal testo di index.html: solo /assets/, in ordine, senza doppioni", () => {
    expect(assetRefs(OLD)).toBe(["/assets/index-AAA.css", "/assets/index-OLD.js", "/assets/vendor-VVV.js"].join("\n"));
    expect(assetRefs(OLD + '<script src="/assets/index-OLD.js"></script>')).toBe(assetRefs(OLD));
    expect(assetRefs("<html>Errore 502</html>")).toBe("");
  });

  it("dalla pagina aperta: gli stessi file del testo da cui è nata", () => {
    const doc = new DOMParser().parseFromString(OLD, "text/html");
    expect(documentRefs(doc)).toBe(assetRefs(OLD));
  });

  it("solo una modifica del foglio di stile conta come versione nuova", () => {
    expect(assetRefs(page("index-OLD.js", "index-BBB.css"))).not.toBe(assetRefs(OLD));
  });
});

function setup(opts: { baseline?: string; html?: string | Error; busy?: boolean; reloadedFor?: string } = {}) {
  const store = new Map<string, string>();
  if (opts.reloadedFor) store.set("domotica.versionReload", JSON.stringify({ to: opts.reloadedFor, at: 0 }));
  const deps = {
    baseline: opts.baseline ?? assetRefs(OLD),
    fetchHtml: vi.fn(async () => {
      if (opts.html instanceof Error) throw opts.html;
      return opts.html ?? NEW;
    }),
    reload: vi.fn(),
    banner: vi.fn(),
    busy: () => opts.busy ?? false,
    storage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
  };
  return { deps, watch: new VersionWatch(deps), store };
}

describe("versione nuova appena aperta l'app", () => {
  it("nei primi secondi, senza aver toccato niente: ricarica da sola, senza avviso", async () => {
    const { deps, watch } = setup();
    watch.opened(1_000);
    expect(await watch.check(1_000 + AUTO_RELOAD_MS)).toBe("reloaded");
    expect(deps.reload).toHaveBeenCalledTimes(1);
    expect(deps.banner).not.toHaveBeenCalled();
  });

  it("stessa versione: niente", async () => {
    const { deps, watch } = setup({ html: OLD });
    watch.opened(0);
    expect(await watch.check(10)).toBe("same");
    expect(deps.reload).not.toHaveBeenCalled();
    expect(deps.banner).not.toHaveBeenCalled();
  });

  it("dopo i primi secondi: avviso, e ricarica al primo cambio di pagina", async () => {
    const { deps, watch } = setup();
    watch.opened(0);
    expect(await watch.check(AUTO_RELOAD_MS + 1)).toBe("banner");
    expect(deps.banner).toHaveBeenCalledTimes(1);
    expect(deps.reload).not.toHaveBeenCalled();
    watch.navigated();
    expect(deps.reload).toHaveBeenCalledTimes(1);
  });

  it("se ha già toccato lo schermo: avviso, mai una ricarica sotto le dita", async () => {
    const { deps, watch } = setup();
    watch.opened(0);
    watch.touched();
    expect(await watch.check(100)).toBe("banner");
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("con una finestra aperta o un campo in uso: avviso", async () => {
    const { deps, watch } = setup({ busy: true });
    watch.opened(0);
    expect(await watch.check(100)).toBe("banner");
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("ritorno dallo sfondo: è una nuova apertura, i secondi ripartono", async () => {
    const { deps, watch } = setup();
    watch.opened(0);
    watch.touched();
    watch.opened(3_600_000);
    expect(await watch.check(3_600_000 + 500)).toBe("reloaded");
    expect(deps.reload).toHaveBeenCalledTimes(1);
  });

  it("un avviso solo per la stessa versione, anche con più controlli", async () => {
    const { deps, watch } = setup();
    watch.opened(0);
    await watch.check(AUTO_RELOAD_MS + 1);
    await watch.check(AUTO_RELOAD_MS + 2);
    expect(deps.banner).toHaveBeenCalledTimes(1);
  });
});

describe("cosa non deve succedere", () => {
  it("senza rete o con un errore del sito: niente, si riprova al prossimo controllo", async () => {
    const { deps, watch } = setup({ html: new Error("offline") });
    watch.opened(0);
    expect(await watch.check(10)).toBe("unknown");
    watch.navigated();
    expect(deps.reload).not.toHaveBeenCalled();
    expect(deps.banner).not.toHaveBeenCalled();
  });

  it("una risposta senza asset (pagina di errore) non è una versione nuova", async () => {
    const { deps, watch } = setup({ html: "<html>Service Unavailable</html>" });
    watch.opened(0);
    expect(await watch.check(10)).toBe("unknown");
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("nel sito di sviluppo (nessuna asset nella pagina): nessun controllo", async () => {
    const { deps, watch } = setup({ baseline: "" });
    watch.opened(0);
    expect(await watch.check(10)).toBe("off");
    expect(deps.fetchHtml).not.toHaveBeenCalled();
  });

  it("già ricaricata verso la stessa versione e ancora vecchia: solo l'avviso, mai un giro di ricariche", async () => {
    const { deps, watch } = setup({ reloadedFor: assetRefs(NEW) });
    watch.opened(0);
    expect(await watch.check(10)).toBe("banner");
    watch.navigated();
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("la ricarica automatica si segna, così la seconda verso la stessa versione non parte", async () => {
    const { deps, watch, store } = setup();
    watch.opened(0);
    await watch.check(10);
    expect(JSON.parse(store.get("domotica.versionReload")!).to).toBe(assetRefs(NEW));
    const again = new VersionWatch({ ...deps, reload: vi.fn() });
    again.opened(20);
    expect(await again.check(30)).toBe("banner");
  });

  it("un cambio di pagina senza versione nuova non ricarica", () => {
    const { deps, watch } = setup();
    watch.navigated();
    expect(deps.reload).not.toHaveBeenCalled();
  });
});
