import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";
import { toast } from "sonner";
import { t } from "@/i18n";
import { CHECK_EVERY_MS, documentRefs, fetchIndexHtml, VersionWatch } from "@/lib/appVersion";
import { browser } from "@/lib/lazyPage";

// P-92. Read when this module is evaluated, at start-up, before any page block is loaded (see documentRefs).
const STARTUP_REFS = typeof document !== "undefined" ? documentRefs(document) : "";
/** The page has just come from the network: one check a little later covers a publication in those seconds. */
const FIRST_CHECK_MS = 2_000;

const session = {
  getItem: (k: string) => {
    try {
      return sessionStorage.getItem(k);
    } catch {
      return null;
    }
  },
  setItem: (k: string, v: string) => {
    try {
      sessionStorage.setItem(k, v);
    } catch {
      /* storage unavailable */
    }
  },
};

/** A dialog open or a field in use. */
function busy(): boolean {
  if (document.querySelector('[role="dialog"], [role="alertdialog"]')) return true;
  const el = document.activeElement as HTMLElement | null;
  return !!el && (el.matches("input, textarea, select") || el.isContentEditable);
}

const showBanner = () =>
  toast(t("app.newVersion.title"), {
    id: "new-version",
    duration: Infinity,
    action: { label: t("app.newVersion.reload"), onClick: () => browser.reload() },
  });

/** «È disponibile una versione nuova — Aggiorna» (P-92); inside the router, so a change of page loads it. */
export function VersionWatcher({ baseline = STARTUP_REFS }: { baseline?: string }) {
  const watch = useRef<VersionWatch | null>(null);
  if (!watch.current) {
    watch.current = new VersionWatch({ baseline, fetchHtml: fetchIndexHtml, reload: () => browser.reload(), banner: showBanner, busy, storage: session });
  }

  useEffect(() => {
    const w = watch.current!;
    w.opened(Date.now());
    if (!baseline) return;
    const check = () => void w.check(Date.now());
    const opened = () => {
      w.opened(Date.now());
      check();
    };
    const onVisibility = () => document.visibilityState === "visible" && opened();
    const onPageShow = (e: PageTransitionEvent) => e.persisted && opened();
    const touched = () => w.touched();
    const first = setTimeout(check, FIRST_CHECK_MS);
    const every = setInterval(() => document.visibilityState === "visible" && check(), CHECK_EVERY_MS);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("pageshow", onPageShow);
    window.addEventListener("online", check);
    window.addEventListener("pointerdown", touched, true);
    window.addEventListener("keydown", touched, true);
    return () => {
      clearTimeout(first);
      clearInterval(every);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener("online", check);
      window.removeEventListener("pointerdown", touched, true);
      window.removeEventListener("keydown", touched, true);
    };
  }, [baseline]);

  const { pathname } = useLocation();
  const shown = useRef(pathname);
  useEffect(() => {
    if (pathname === shown.current) return;
    shown.current = pathname;
    watch.current!.navigated();
  }, [pathname]);

  return null;
}
