// @vitest-environment node
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { PALETTES, themeTokens, type ColorScheme, type PaletteId } from "./palettes";

// The three palettes of PR #19 (Sorgente, Aria, Bosco), light and dark. The colours of the site no longer sit in
// index.css: they are set from here before React starts. So every CSS variable the site uses must come out of every
// palette in both schemes, and the text must keep its contrast (WCAG 4.5:1), as the site's colours did before.

const PALETTE_IDS = Object.keys(PALETTES) as PaletteId[];
const SCHEMES: ColorScheme[] = ["light", "dark"];
const SRC = join(__dirname, "..");

/** Variables defined elsewhere on purpose: --radius in index.css, --cols set by a page, --hero-image-ratio inline. */
const NOT_A_COLOUR = new Set(["--radius", "--cols", "--hero-image-ratio"]);

function usedVariables(): string[] {
  const files: string[] = [join(SRC, "..", "tailwind.config.cjs")];
  const walk = (dir: string) => {
    for (const name of readdirSync(dir)) {
      const p = join(dir, name);
      if (statSync(p).isDirectory()) walk(p);
      else if (/\.(tsx?|css)$/.test(name) && !/\.test\.tsx?$/.test(name)) files.push(p);
    }
  };
  walk(SRC);
  const found = new Set<string>();
  for (const f of files) for (const m of readFileSync(f, "utf8").matchAll(/var\((--[a-z0-9-]+)/g)) found.add(m[1]);
  return [...found].filter((v) => !NOT_A_COLOUR.has(v) && !v.startsWith("--tw-") && !v.startsWith("--radix-")).sort();
}

/** "h s% l%" → relative luminance. */
function luminance(hsl: string): number {
  const [h, s, l] = hsl.replace(/%/g, "").split(" ").map(Number);
  const sat = s / 100, lig = l / 100;
  const k = (n: number) => (n + h / 30) % 12;
  const a = sat * Math.min(lig, 1 - lig);
  const f = (n: number) => lig - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
  const lin = (c: number) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(f(0)) + 0.7152 * lin(f(8)) + 0.0722 * lin(f(4));
}
const contrast = (a: string, b: string) => {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};

describe("palette", () => {
  const used = usedVariables();

  it("il sito usa le variabili dei colori (la lista non è vuota)", () => {
    expect(used).toContain("--background");
    expect(used).toContain("--negative-fg");
  });

  it.each(PALETTE_IDS.flatMap((p) => SCHEMES.map((s) => [p, s] as const)))("%s %s: definisce ogni variabile usata dal sito", (p, s) => {
    const defined = new Set(Object.keys(themeTokens(p, s)));
    expect(used.filter((v) => !defined.has(v))).toEqual([]);
  });

  it.each(PALETTE_IDS.flatMap((p) => SCHEMES.map((s) => [p, s] as const)))("%s %s: il testo si legge (almeno 4,5:1)", (p, s) => {
    const v = themeTokens(p, s);
    const pairs: [string, string, string][] = [
      ["testo su sfondo", "--foreground", "--background"],
      ["testo su scheda", "--foreground", "--card"],
      ["testo secondario su sfondo", "--muted-foreground", "--background"],
      ["testo secondario su scheda", "--muted-foreground", "--card"],
      ["pulsante principale", "--background", "--foreground"],
      ["neutro", "--neutral-fg", "--neutral-bg"],
      ["positivo", "--positive-fg", "--positive-bg"],
      ["avviso", "--warning-fg", "--warning-bg"],
      ["negativo", "--negative-fg", "--negative-bg"],
      ["modalità comfort", "--mode-comfort-fg", "--mode-comfort-bg"],
      ["modalità eco", "--mode-eco-fg", "--mode-eco-bg"],
      ["modalità casa vuota", "--mode-empty-fg", "--mode-empty-bg"],
    ];
    const low = pairs.filter(([, fg, bg]) => contrast(v[fg], v[bg]) < 4.5).map(([name, fg, bg]) => `${name} ${contrast(v[fg], v[bg]).toFixed(2)}`);
    expect(low).toEqual([]);
  });
});
