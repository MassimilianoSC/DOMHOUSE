// P-92: a page still running the previous release after a publication. The service worker no longer answers for the
// site (no fetch handler, E-29), so every opening takes index.html from the network; this watch covers the page that
// stays open (a tab never reloaded, the installed app resumed from the background). It compares the /assets/ files of
// the running page with those of index.html on the network: Vite names them by content, so a difference is a new
// version. The service worker is not involved: the check works the same where there is none (or it is stuck, E-29).

/** In the first seconds after opening or coming back to the app, on a page never touched, a new version reloads by itself. */
export const AUTO_RELOAD_MS = 8_000;
/** At most one automatic reload per tab in this time, whatever the version (review P3: old and new pages alternating). */
export const AUTO_RELOAD_GAP_MS = 10 * 60_000;
/** While the page stays visible. */
export const CHECK_EVERY_MS = 10 * 60_000;
export const RELOAD_KEY = "domotica.versionReload";
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

/**
 * The page is in use: a dialog open, a field with the cursor, or work still on its way (a request that changes
 * something, the removal of the push token at sign-out). Never reload then.
 */
export function pageBusy(doc: Document, working: () => boolean): boolean {
  if (working()) return true;
  if (doc.querySelector('[role="dialog"], [role="alertdialog"]')) return true;
  const el = doc.activeElement as HTMLElement | null;
  return !!el && (el.matches("input, textarea, select") || el.isContentEditable === true);
}

/** sessionStorage as it is: its errors reach the watch, which then never reloads by itself (review P4). */
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
  /** pageBusy: a dialog, a field in use or work on its way. */
  busy: () => boolean;
  /** Work on its way only (requests that change something, push token removal): a change of page waits for it. */
  working: () => boolean;
  storage: Storage;
  /** Monotonic, for the seconds after an opening (performance.now). */
  clock: () => number;
  /** Wall clock, for the record that outlives the reload (Date.now). */
  wall: () => number;
}

export type CheckResult = "off" | "unknown" | "same" | "reloaded" | "banner";

export class VersionWatch {
  private openedAt: number;
  /** Ever touched since the page was loaded: coming back from the background does not clear it (review P1). */
  private touchedEver = false;
  /** Fingerprint of the newer version on the network, once found. */
  private ready: string | null = null;
  private bannerFor: string | null = null;

  constructor(private deps: VersionWatchDeps) {
    this.openedAt = deps.clock();
  }

  /** The page came back from the background (or from the back-forward cache). */
  opened() {
    this.openedAt = this.deps.clock();
  }

  /** A tap, click or key: from now on until the next load, the page may hold something not saved. */
  touched() {
    this.touchedEver = true;
  }

  async check(): Promise<CheckResult> {
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
    // Measured when the answer arrives (review P5): a slow answer does not stretch the seconds after the opening.
    const fresh = this.deps.clock() - this.openedAt <= AUTO_RELOAD_MS && !this.touchedEver;
    if (fresh && !this.deps.busy() && this.reloadTo(refs)) return "reloaded";
    if (this.bannerFor !== refs) {
      this.bannerFor = refs;
      this.deps.banner();
    }
    return "banner";
  }

  /**
   * At a change of page the screen is being replaced anyway: the newer version, if there is one, loads now. Not while
   * work is on its way (review P2, P7): the next change of page tries again.
   */
  navigated() {
    if (this.ready && !this.deps.working()) this.reloadTo(this.ready);
  }

  /**
   * Reloads by itself towards `target` only if this tab has not done it already towards that version, nor towards any
   * version in the last AUTO_RELOAD_GAP_MS, and the record of it can be written and read back. Otherwise only the
   * banner remains, never a loop of reloads.
   */
  private reloadTo(target: string): boolean {
    try {
      const { storage, wall } = this.deps;
      const last = JSON.parse(storage.getItem(RELOAD_KEY) ?? "null") as { to?: unknown; at?: unknown } | null;
      if (last?.to === target) return false;
      // A clock moved backwards counts as «recent»: the automatic reload waits, the banner does not.
      if (typeof last?.at === "number" && wall() - last.at < AUTO_RELOAD_GAP_MS) return false;
      const record = JSON.stringify({ to: target, at: wall() });
      storage.setItem(RELOAD_KEY, record);
      if (storage.getItem(RELOAD_KEY) !== record) return false;
    } catch {
      return false; // storage unavailable (review P4): no record, so no automatic reload; the banner stays
    }
    this.deps.reload();
    return true;
  }
}
