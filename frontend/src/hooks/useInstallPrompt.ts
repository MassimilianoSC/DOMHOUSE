import { useEffect, useState } from "react";

// Chrome/Edge (Android and desktop) fire `beforeinstallprompt` once, right after load and before the Settings page
// is mounted: the listener is registered at import time (main.tsx imports this module) and the event is kept here.
// Safari (iOS/macOS) and Firefox never fire it: the UI falls back to written instructions.

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

type State = { deferred: BeforeInstallPromptEvent | null; installed: boolean };

export const isStandalone = () =>
  typeof window !== "undefined" &&
  (window.matchMedia?.("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone === true);

let state: State = { deferred: null, installed: isStandalone() };
const listeners = new Set<(s: State) => void>();
const emit = (next: Partial<State>) => {
  state = { ...state, ...next };
  listeners.forEach((l) => l(state));
};

if (typeof window !== "undefined") {
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault(); // keep the browser's mini-infobar away: the app offers its own button
    emit({ deferred: e as BeforeInstallPromptEvent });
  });
  window.addEventListener("appinstalled", () => emit({ deferred: null, installed: true }));
}

export const isIos = () =>
  /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);

export function useInstallPrompt() {
  const [s, setS] = useState(state);
  useEffect(() => {
    listeners.add(setS);
    setS(state);
    return () => void listeners.delete(setS);
  }, []);

  const install = async () => {
    const ev = state.deferred;
    if (!ev) return;
    await ev.prompt();
    const { outcome } = await ev.userChoice;
    emit({ deferred: null, installed: outcome === "accepted" }); // the event can be used only once
  };

  return { canInstall: !!s.deferred, installed: s.installed, install };
}
