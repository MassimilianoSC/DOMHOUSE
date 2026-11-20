// @vitest-environment node
import italian from "./it.json";
import pageTexts from "./it.pages.json";

/**
 * The texts are in two files (P-20, the main block under 400 kB): it.json for the first screens, in the main block;
 * it.pages.json for the pages loaded on demand, in their own block, added by src/i18n/pages.ts.
 * - No file reached from src/main.tsx by static imports (the main block) may use a section of it.pages.json: it would
 *   show the bare key until a page loaded on demand is opened.
 * - Every page loaded on demand (lazyPage in App.tsx) imports "@/i18n/pages" first, so its texts are there before any
 *   of its modules runs.
 */

const SOURCES = import.meta.glob<string>(["/src/**/*.{ts,tsx}", "!/src/**/*.test.{ts,tsx}", "!/src/api/schema.ts"], {
  query: "?raw",
  import: "default",
  eager: true,
});

const EXT = ["", ".ts", ".tsx", "/index.ts", "/index.tsx"];

function resolve(from: string, spec: string): string | null {
  let base: string;
  if (spec.startsWith("@/")) base = `/src/${spec.slice(2)}`;
  else if (spec.startsWith(".")) {
    const parts = from.split("/").slice(0, -1);
    for (const p of spec.split("/")) {
      if (p === "..") parts.pop();
      else if (p !== ".") parts.push(p);
    }
    base = parts.join("/");
  } else return null;
  return EXT.map((e) => base + e).find((f) => f in SOURCES) ?? null;
}

/** The static imports of a file (not `import type`, not `import()`). */
export function staticImports(src: string): string[] {
  const found: string[] = [];
  for (const m of src.matchAll(/^\s*(?:import|export)\s+(?!type\b)[^;]*?\sfrom\s+["']([^"']+)["']/gm)) found.push(m[1]);
  for (const m of src.matchAll(/^\s*import\s+["']([^"']+)["']/gm)) found.push(m[1]);
  return found;
}

/** Every file of the main block: src/main.tsx and what it reaches by static imports. */
function mainBlock(): Set<string> {
  const seen = new Set<string>();
  const todo = ["/src/main.tsx"];
  while (todo.length) {
    const f = todo.pop()!;
    if (seen.has(f)) continue;
    seen.add(f);
    for (const spec of staticImports(SOURCES[f])) {
      const r = resolve(f, spec);
      if (r) todo.push(r);
    }
  }
  return seen;
}

const withoutComments = (src: string) => src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

/** The sections of `sections` a file asks for ("rules.x", `audit.actions.${a}`, 'credentials.y'). */
export function sectionsUsed(src: string, sections: string[]): string[] {
  const code = withoutComments(src);
  return sections.filter((s) => new RegExp(`["'\`]${s}\\.`).test(code));
}

const PAGE_SECTIONS = Object.keys(pageTexts);

describe("testi divisi fra il blocco principale e le pagine a richiesta", () => {
  it("le due parti non hanno sezioni in comune", () => {
    expect(PAGE_SECTIONS.filter((s) => s in italian)).toEqual([]);
    expect(PAGE_SECTIONS.length).toBeGreaterThan(0);
  });

  it("il lettore trova gli import e le sezioni usate", () => {
    const fake = 'import "@/i18n/pages";\nimport type { A } from "./a";\nimport {\n  b,\n  c,\n} from "@/lib/b";\nexport { d } from "./d";\nconst e = () => import("@/pages/E");\n// t("rules.x") in a comment\nt(`audit.actions.${a}`);';
    expect(staticImports(fake)).toEqual(["@/lib/b", "./d", "@/i18n/pages"]);
    expect(sectionsUsed(fake, ["rules", "audit", "nav"])).toEqual(["audit"]);
  });

  it("nessun file del blocco principale usa i testi delle pagine a richiesta", () => {
    const main = mainBlock();
    // the first screens are there, the pages loaded on demand are not
    expect(main.has("/src/pages/ApartmentsPage.tsx")).toBe(true);
    expect(main.has("/src/pages/RulesPage.tsx")).toBe(false);
    const found = [...main].flatMap((f) => sectionsUsed(SOURCES[f], PAGE_SECTIONS).map((s) => `${f}: ${s}`));
    expect(found).toEqual([]);
  });

  it("ogni pagina a richiesta carica per prima cosa i suoi testi", () => {
    const pages = [...SOURCES["/src/App.tsx"].matchAll(/lazyPage\(\(\) => import\("([^"]+)"\)\)/g)].map((m) => resolve("/src/App.tsx", m[1])!);
    expect(pages.length).toBeGreaterThan(10);
    const firstImport = (f: string) => withoutComments(SOURCES[f]).match(/^\s*import\s[^;]*;/m)?.[0].trim();
    expect(pages.filter((f) => firstImport(f) !== 'import "@/i18n/pages";')).toEqual([]);
  });
});
