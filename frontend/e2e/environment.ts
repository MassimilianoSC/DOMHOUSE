import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import { join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

// What the browser checks need on this machine (P-73), shared by playwright.config.ts and the specs: a Chromium and
// the BFF's Python. A machine without a browser skips the checks with this reason instead of failing.

export const REPO_ROOT = resolve(fileURLToPath(new URL(".", import.meta.url)), "..", "..");

const BROWSERS_DIR =
  process.env.PLAYWRIGHT_BROWSERS_PATH ||
  (process.platform === "win32" ? join(process.env.LOCALAPPDATA ?? homedir(), "ms-playwright")
    : process.platform === "darwin" ? join(homedir(), "Library", "Caches", "ms-playwright")
    : join(homedir(), ".cache", "ms-playwright"));

const CHROME_IN = ["chrome-win64/chrome.exe", "chrome-win/chrome.exe", "chrome-linux64/chrome", "chrome-linux/chrome", "chrome-mac/Chromium.app/Contents/MacOS/Chromium"];

/** The Chromium of this Playwright version; otherwise (CHROMIUM_PATH, or the newest one already downloaded by another
 *  version) one that is on the machine, so nothing has to be downloaded; null when there is none. */
function findChromium(): string | null {
  if (process.env.CHROMIUM_PATH) return existsSync(process.env.CHROMIUM_PATH) ? process.env.CHROMIUM_PATH : "";
  try {
    if (existsSync(chromium.executablePath())) return null; // Playwright's own: no override needed
  } catch {
    /* unknown platform: look in the folder */
  }
  if (!existsSync(BROWSERS_DIR)) return "";
  const found = readdirSync(BROWSERS_DIR)
    .filter((d) => /^chromium-\d+$/.test(d))
    .sort((a, b) => Number(b.split("-")[1]) - Number(a.split("-")[1]))
    .flatMap((d) => CHROME_IN.map((p) => join(BROWSERS_DIR, d, p)))
    .find((p) => existsSync(p));
  return found ?? "";
}

const chromiumPath = findChromium();
/** "" = no browser at all; null = Playwright's own; a path = the one to use. */
export const CHROMIUM_EXECUTABLE: string | null = chromiumPath === "" ? null : chromiumPath;
export const NO_BROWSER_REASON =
  chromiumPath === ""
    ? `Nessun browser per le prove a larghezza di telefono su questa macchina (P-73): installarlo con «npx playwright install chromium» nella cartella frontend, oppure indicarne uno con CHROMIUM_PATH. Cercato in ${BROWSERS_DIR}.`
    : null;

/** The BFF's Python: PYTHON, else the repository's .venv, else «python». */
export const PYTHON =
  process.env.PYTHON ||
  [join(REPO_ROOT, ".venv", "Scripts", "python.exe"), join(REPO_ROOT, ".venv", "bin", "python")].find((p) => existsSync(p)) ||
  "python";
