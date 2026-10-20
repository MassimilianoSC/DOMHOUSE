import { lazy, type ComponentType } from "react";

const KEY = "domotica.staleReloadAt";
const WINDOW_MS = 60_000;

/** Indirection so tests can observe the reload (jsdom's location.reload cannot be spied on). */
export const browser = { reload: () => window.location.reload() };

/**
 * A tab still running a previous release asks for page blocks that Firebase Hosting no longer has (it answers
 * index.html instead): reload once to pick up the new release. Returns false when a reload already happened in the
 * last minute, so a real failure surfaces instead of reloading in a loop.
 */
export function reloadOnce(now = Date.now()): boolean {
  let last = 0;
  try {
    last = Number(sessionStorage.getItem(KEY) ?? 0);
  } catch {
    /* storage unavailable: still reload once per page life */
  }
  if (now - last < WINDOW_MS) return false;
  try {
    sessionStorage.setItem(KEY, String(now));
  } catch {
    /* see above */
  }
  browser.reload();
  return true;
}

/** React.lazy for a page block: a failed load triggers reloadOnce and keeps the Suspense fallback until the reload. */
export function lazyPage(load: () => Promise<{ default: ComponentType }>) {
  return lazy(() =>
    load().catch((err: unknown) => {
      if (reloadOnce()) return new Promise<never>(() => {});
      throw err;
    }),
  );
}
