import { assetRefs, AUTO_RELOAD_GAP_MS, AUTO_RELOAD_MS, documentRefs, pageBusy, RELOAD_KEY, VersionWatch, type VersionWatchDeps } from "./appVersion";

// P-92: a page that stays on the previous release after a publication. The watch compares the /assets/ files of the
// page it is running with those of index.html on the network: a difference is a new version. In the first seconds
// after opening (or coming back from the background), on a page never touched since it was loaded, it reloads by
// itself; otherwise the banner «È disponibile una versione nuova — Aggiorna» and a reload at the first change of page.

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

/** A fake world: a monotonic clock, a wall clock, a sessionStorage, a network answer that may take time. */
function setup(opts: { baseline?: string; html?: string | Error; busy?: boolean; working?: boolean; record?: { to: string; at: number }; fetchMs?: number } = {}) {
  const store = new Map<string, string>();
  if (opts.record) store.set(RELOAD_KEY, JSON.stringify(opts.record));
  const time = { mono: 0, wall: 1_000_000_000 };
  const state = { busy: opts.busy ?? false, working: opts.working ?? false };
  const deps: VersionWatchDeps & { reload: ReturnType<typeof vi.fn>; banner: ReturnType<typeof vi.fn>; fetchHtml: ReturnType<typeof vi.fn> } = {
    baseline: opts.baseline ?? assetRefs(OLD),
    fetchHtml: vi.fn(async () => {
      time.mono += opts.fetchMs ?? 50;
      if (opts.html instanceof Error) throw opts.html;
      return opts.html ?? NEW;
    }),
    reload: vi.fn(),
    banner: vi.fn(),
    busy: () => state.busy,
    working: () => state.working,
    storage: { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) },
    clock: () => time.mono,
    wall: () => time.wall,
  };
  return { deps, watch: new VersionWatch(deps), store, time, state };
}

describe("versione nuova appena aperta l'app", () => {
  it("nei primi secondi, pagina mai toccata: ricarica da sola, senza avviso", async () => {
    const { deps, watch } = setup();
    expect(await watch.check()).toBe("reloaded");
    expect(deps.reload).toHaveBeenCalledTimes(1);
    expect(deps.banner).not.toHaveBeenCalled();
  });

  it("stessa versione: niente", async () => {
    const { deps, watch } = setup({ html: OLD });
    expect(await watch.check()).toBe("same");
    expect(deps.reload).not.toHaveBeenCalled();
    expect(deps.banner).not.toHaveBeenCalled();
  });

  it("dopo i primi secondi: avviso, e ricarica al primo cambio di pagina", async () => {
    const { deps, watch, time } = setup();
    time.mono = AUTO_RELOAD_MS + 1;
    expect(await watch.check()).toBe("banner");
    expect(deps.banner).toHaveBeenCalledTimes(1);
    expect(deps.reload).not.toHaveBeenCalled();
    watch.navigated();
    expect(deps.reload).toHaveBeenCalledTimes(1);
  });

  it("i secondi si misurano all'arrivo della risposta (P5): una risposta lenta non li allunga", async () => {
    const { deps, watch } = setup({ fetchMs: AUTO_RELOAD_MS + 1 });
    expect(await watch.check()).toBe("banner");
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("se ha già toccato lo schermo: avviso, mai una ricarica sotto le dita", async () => {
    const { deps, watch } = setup();
    watch.touched();
    expect(await watch.check()).toBe("banner");
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("con la pagina occupata (finestra, campo, richiesta in viaggio): avviso", async () => {
    const { deps, watch } = setup({ busy: true });
    expect(await watch.check()).toBe("banner");
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("ritorno dallo sfondo, pagina mai toccata: i secondi ripartono e ricarica da sola", async () => {
    const { deps, watch, time } = setup();
    time.mono = 3_600_000;
    watch.opened();
    expect(await watch.check()).toBe("reloaded");
    expect(deps.reload).toHaveBeenCalledTimes(1);
  });

  it("ritorno dallo sfondo dopo averla usata (P1): solo l'avviso, le modifiche non salvate restano", async () => {
    const { deps, watch, time } = setup();
    watch.touched(); // a switch changed in Regole, not saved; then WhatsApp
    time.mono = 3_600_000;
    watch.opened();
    expect(await watch.check()).toBe("banner");
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("un avviso solo per la stessa versione, anche con più controlli", async () => {
    const { deps, watch, time } = setup();
    time.mono = AUTO_RELOAD_MS + 1;
    await watch.check();
    await watch.check();
    expect(deps.banner).toHaveBeenCalledTimes(1);
  });
});

describe("cambio di pagina con lavoro in corso (P2, P7)", () => {
  it("una richiesta che cambia qualcosa ancora in viaggio: niente ricarica; al cambio di pagina successivo sì", async () => {
    const { deps, watch, time, state } = setup();
    time.mono = AUTO_RELOAD_MS + 1;
    await watch.check();
    state.working = true;
    watch.navigated();
    expect(deps.reload).not.toHaveBeenCalled();
    state.working = false;
    watch.navigated();
    expect(deps.reload).toHaveBeenCalledTimes(1);
  });
});

describe("cosa non deve succedere", () => {
  it("senza rete o con un errore del sito: niente, si riprova al prossimo controllo", async () => {
    const { deps, watch } = setup({ html: new Error("offline") });
    expect(await watch.check()).toBe("unknown");
    watch.navigated();
    expect(deps.reload).not.toHaveBeenCalled();
    expect(deps.banner).not.toHaveBeenCalled();
  });

  it("una risposta senza asset (pagina di errore) non è una versione nuova", async () => {
    const { deps, watch } = setup({ html: "<html>Service Unavailable</html>" });
    expect(await watch.check()).toBe("unknown");
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("nel sito di sviluppo (nessuna asset nella pagina): nessun controllo", async () => {
    const { deps, watch } = setup({ baseline: "" });
    expect(await watch.check()).toBe("off");
    expect(deps.fetchHtml).not.toHaveBeenCalled();
  });

  it("già ricaricata verso la stessa versione e ancora vecchia: solo l'avviso", async () => {
    // long ago, so only the «same version» rule can stop it
    const { deps, watch } = setup({ record: { to: assetRefs(NEW), at: 1_000_000_000 - AUTO_RELOAD_GAP_MS * 10 } });
    expect(await watch.check()).toBe("banner");
    watch.navigated();
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("pagine vecchia e nuova alternate (P3): al massimo una ricarica automatica ogni 10 minuti", async () => {
    // reloaded towards another version 2 minutes ago (the network handed out the old page again)
    const { deps, watch, time } = setup({ record: { to: "/assets/index-ALTRA.js", at: 1_000_000_000 - 2 * 60_000 } });
    expect(await watch.check()).toBe("banner");
    watch.navigated();
    expect(deps.reload).not.toHaveBeenCalled();
    // 10 minutes after that reload: allowed again
    time.wall = 1_000_000_000 - 2 * 60_000 + AUTO_RELOAD_GAP_MS;
    watch.navigated();
    expect(deps.reload).toHaveBeenCalledTimes(1);
  });

  it("orologio del telefono tornato indietro: conta come «da poco», niente ricarica automatica", async () => {
    const { deps, watch } = setup({ record: { to: "/assets/index-ALTRA.js", at: 1_000_000_000 + 3_600_000 } });
    expect(await watch.check()).toBe("banner");
    expect(deps.reload).not.toHaveBeenCalled();
  });

  it("la ricarica automatica si segna, così la seconda verso la stessa versione non parte", async () => {
    const { deps, watch, store } = setup();
    await watch.check();
    expect(JSON.parse(store.get(RELOAD_KEY)!).to).toBe(assetRefs(NEW));
    const again = new VersionWatch({ ...deps, reload: vi.fn() });
    expect(await again.check()).toBe("banner");
  });

  it("memoria della scheda che non funziona (P4): niente ricarica automatica, solo l'avviso", async () => {
    for (const storage of [
      { getItem: () => { throw new Error("SecurityError"); }, setItem: () => {} },
      { getItem: () => null, setItem: () => { throw new Error("QuotaExceededError"); } },
      { getItem: () => null, setItem: () => {} }, // writes nothing: the record cannot be read back
    ]) {
      const { deps } = setup();
      const watch = new VersionWatch({ ...deps, storage });
      expect(await watch.check()).toBe("banner");
      watch.navigated();
      expect(deps.reload).not.toHaveBeenCalled();
      expect(deps.banner).toHaveBeenCalledTimes(1);
    }
  });

  it("un cambio di pagina senza versione nuova non ricarica", () => {
    const { deps, watch } = setup();
    watch.navigated();
    expect(deps.reload).not.toHaveBeenCalled();
  });
});

describe("pagina occupata: pageBusy sul documento vero", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });
  const idle = () => false;

  it("niente aperto: libera", () => {
    document.body.innerHTML = "<main><button>Salva</button></main>";
    expect(pageBusy(document, idle)).toBe(false);
  });

  it("una finestra aperta (dialog o alertdialog)", () => {
    document.body.innerHTML = '<div role="dialog"><p>Disattivare?</p></div>';
    expect(pageBusy(document, idle)).toBe(true);
    document.body.innerHTML = '<div role="alertdialog"></div>';
    expect(pageBusy(document, idle)).toBe(true);
  });

  it("un campo con il cursore (input, textarea, select)", () => {
    for (const tag of ["input", "textarea", "select"]) {
      document.body.innerHTML = `<${tag} id="f"></${tag}>`;
      (document.getElementById("f") as HTMLElement).focus();
      expect(pageBusy(document, idle)).toBe(true);
    }
  });

  it("un pulsante con il fuoco non conta", () => {
    document.body.innerHTML = '<button id="b">Riprova</button>';
    (document.getElementById("b") as HTMLElement).focus();
    expect(pageBusy(document, idle)).toBe(false);
  });

  it("lavoro in viaggio", () => {
    expect(pageBusy(document, () => true)).toBe(true);
  });
});
