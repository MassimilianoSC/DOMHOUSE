import { useSyncExternalStore } from "react";
import { PALETTES, themeTokens, type ColorScheme, type PaletteId, type ThemePreference } from "./palettes";

export type AppearancePreferences = {
  palette: PaletteId;
  mode: ThemePreference;
};

export const DEFAULT_APPEARANCE: AppearancePreferences = {
  palette: "sorgente",
  mode: "system",
};

const STORAGE_KEY = "domhouse.appearance.v1";
const listeners = new Set<() => void>();
let preferences = DEFAULT_APPEARANCE;
let initialized = false;

function isPaletteId(value: unknown): value is PaletteId {
  return typeof value === "string" && Object.prototype.hasOwnProperty.call(PALETTES, value);
}

function isThemePreference(value: unknown): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

function parsePreferences(value: unknown): AppearancePreferences {
  if (!value || typeof value !== "object") return DEFAULT_APPEARANCE;
  const candidate = value as Record<string, unknown>;
  return {
    palette: isPaletteId(candidate.palette) ? candidate.palette : DEFAULT_APPEARANCE.palette,
    mode: isThemePreference(candidate.mode) ? candidate.mode : DEFAULT_APPEARANCE.mode,
  };
}

function readPreferences(): AppearancePreferences {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    return parseStoredPreferences(stored);
  } catch {
    return DEFAULT_APPEARANCE;
  }
}

function parseStoredPreferences(value: string | null): AppearancePreferences {
  if (value === null) return DEFAULT_APPEARANCE;
  try {
    return parsePreferences(JSON.parse(value) as unknown);
  } catch {
    return DEFAULT_APPEARANCE;
  }
}

function savePreferences(next: AppearancePreferences): boolean {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    return true;
  } catch {
    return false;
  }
}

function resolveScheme(mode: ThemePreference): ColorScheme {
  if (mode !== "system") return mode;
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

function applyAppearance(next: AppearancePreferences): void {
  const root = document.documentElement;
  const scheme = resolveScheme(next.mode);
  root.dataset.palette = next.palette;
  root.dataset.theme = scheme;
  root.dataset.themePreference = next.mode;
  root.classList.toggle("dark", scheme === "dark");

  for (const [token, value] of Object.entries(themeTokens(next.palette, scheme))) {
    root.style.setProperty(token, value);
  }

  const themeColor = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (themeColor) themeColor.content = PALETTES[next.palette].themeColor[scheme];
}

function notify(): void {
  listeners.forEach((listener) => listener());
}

function handleSystemColorSchemeChange(): void {
  if (preferences.mode === "system") applyAppearance(preferences);
}

function handleStorageChange(event: StorageEvent): void {
  if (event.key !== STORAGE_KEY && event.key !== null) return;
  preferences = event.key === null ? DEFAULT_APPEARANCE : parseStoredPreferences(event.newValue);
  applyAppearance(preferences);
  notify();
}

/** Apply saved preferences before React mounts, and keep system and other-tab changes in sync. */
export function initializeAppearance(): void {
  if (initialized || typeof window === "undefined" || typeof document === "undefined") return;
  initialized = true;
  preferences = readPreferences();
  applyAppearance(preferences);

  try {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    if (typeof media.addEventListener === "function") media.addEventListener("change", handleSystemColorSchemeChange);
    else media.addListener(handleSystemColorSchemeChange);
  } catch { /* Older or restricted browsers keep the selected appearance for this session. */ }
  window.addEventListener("storage", handleStorageChange);
}

export function setAppearance(patch: Partial<AppearancePreferences>): boolean {
  if (!initialized) initializeAppearance();
  preferences = parsePreferences({ ...preferences, ...patch });
  applyAppearance(preferences);
  const saved = savePreferences(preferences);
  notify();
  return saved;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot(): AppearancePreferences {
  return preferences;
}

export function useAppearance(): AppearancePreferences {
  return useSyncExternalStore(subscribe, getSnapshot, () => DEFAULT_APPEARANCE);
}
