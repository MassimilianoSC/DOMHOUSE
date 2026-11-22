// P-92: a page still running the previous release after a publication. The service worker no longer answers for the
// site (no fetch handler, E-29), so every opening takes index.html from the network; this watch covers the page that
// stays open (a tab never reloaded, the installed app resumed from the background). It compares the /assets/ files of
// the running page with those of index.html on the network: Vite names them by content, so a difference is a new
// version. The service worker is not involved: the check works the same where there is none (or it is stuck, E-29).

/** In the first seconds after opening or coming back to the app, with nothing touched yet, a new version reloads by itself. */
export const AUTO_RELOAD_MS = 8_000;
/** While the page stays visible. */
export const CHECK_EVERY_MS = 10 * 60_000;
const RELOAD_KEY = "domotica.versionReload";
const FETCH_TIMEOUT_MS = 10_000;

const ASSET = /(?:src|href)=["'](\/assets\/[^"']+\.(?:js|css))["']/g;

const fingerprint = (refs: Iterable<string>) => [...new Set(refs)].sort().join("\n");

/** The /assets/ scripts and style sheets referenced by an index.html, sorted; "" when there are none (an error page). */
export function assetRefs(html: string): string {
  return fingerprint([...html.matchAll(ASSET)].map((m) => m[1]));
}

/**
 * The same for the page that is running. Read at start-up, before any page block is loaded: Vite adds modulepreload
 * links for the blocks it loads later, and those are not in index.html.
 */
export function documentRefs(doc: Document): string {
  const refs: string[] = [];
  doc.querySelectorAll("script[src], link[href]").forEach((el) => {
    const ref = el.getAttribute(el.tagName === "SCRIPT" ? "src" : "href") ?? "";
    if (/^\/assets\/[^?#]+\.(?:js|css)$/.test(ref)) refs.push(ref);
  });
  return fingerprint(refs);
}

/** index.html as published now: never from the browser cache. */
export async function fetchIndexHtml(): Promise<string> {
  const signal = typeof AbortSignal !== "undefined" && "timeout" in AbortSignal ? AbortSignal.timeout(FETCH_TIMEOUT_MS) : undefined;
  const res = await fetch("/", { cache: "no-store", credentials: "same-origin", headers: { Accept: "text/html" }, signal });
  if (!res.ok) throw new Error(`index.html ${res.status}`);
  return res.text();
}

interface Storage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

export interface VersionWatchDeps {
  /** documentRefs of the running page; "" (Vite dev server, tests) switches the watch off. */
  baseline: string;
  fetchHtml: () => Promise<string>;
  reload: () => void;
  /** Shows «È disponibile una versione nuova — Aggiorna». */
  banner: () => void;
  /** A dialog open or a field in use: never reload under the person's hands. */
  busy: () => boolean;
  storage: Storage;
}

export type CheckResult = "off" | "unknown" | "same" | "reloaded" | "banner";

export class VersionWatch {
  private openedAt = 0;
  private touchedSinceOpen = false;
  /** Fingerprint of the newer version on the network, once found. */
  private ready: string | null = null;
  private bannerFor: string | null = null;

  constructor(private deps: VersionWatchDeps) {}

  /** The page was loaded, or came back from the background. */
  opened(now: number) {
    this.openedAt = now;
    this.touchedSinceOpen = false;
  }

  /** A tap, click or key: from now on the page is in use. */
  touched() {
    this.touchedSinceOpen = true;
  }

  async check(now: number): Promise<CheckResult> {
    if (!this.deps.baseline) return "off";
    let refs: string;
    try {
      refs = assetRefs(await this.deps.fetchHtml());
    } catch {
      return "unknown"; // offline or the site not answering: the next check tries again
    }
    if (!refs) return "unknown";
    if (refs === this.deps.baseline) return "same";
    this.ready = refs;
    const fresh = now - this.openedAt <= AUTO_RELOAD_MS && !this.touchedSinceOpen;
    if (fresh && !this.deps.busy() && this.reloadTo(refs)) return "reloaded";
    if (this.bannerFor !== refs) {
      this.bannerFor = refs;
      this.deps.banner();
    }
    return "banner";
  }

  /** At a change of page the screen is being replaced anyway: the newer version, if there is one, loads now. */
  navigated() {
    if (this.ready) this.reloadTo(this.ready);
  }

  /**
   * Reloads towards `target`, at most once per tab: if the page is still the old one after it (a server still
   * handing out the previous index.html), only the banner remains, never a loop of reloads.
   */
  private reloadTo(target: string): boolean {
    try {
      const last = JSON.parse(this.deps.storage.getItem(RELOAD_KEY) ?? "null") as { to?: unknown } | null;
      if (last?.to === target) return false;
      this.deps.storage.setItem(RELOAD_KEY, JSON.stringify({ to: target, at: Date.now() }));
    } catch {
      /* storage unavailable: reload anyway, the banner stays the fallback */
    }
    this.deps.reload();
    return true;
  }
}
