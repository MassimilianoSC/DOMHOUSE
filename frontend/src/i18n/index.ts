import it from "./it.json";

// The texts of the first screens (it.json) ship in the main block; those of the pages loaded on demand
// (it.pages.json) come with them, through src/i18n/pages.ts (P-20: the main block stays under 400 kB).
// src/i18n/split.test.ts checks that no file of the main block asks for a text of it.pages.json.

type Dict = { [key: string]: string | Dict };
const dictionaries: Record<string, Dict> = { it: { ...it } };
let current: Dict = dictionaries.it;

/** Adds whole sections to the Italian texts: called once by src/i18n/pages.ts. */
export function addTexts(sections: Dict) {
  Object.assign(dictionaries.it, sections);
}

export function setLanguage(lang: string) {
  current = dictionaries[lang] ?? dictionaries.it;
}

export function t(key: string, vars?: Record<string, string | number>): string {
  const value = key.split(".").reduce<string | Dict | undefined>(
    (node, part) => (node && typeof node === "object" ? node[part] : undefined),
    current,
  );
  if (typeof value !== "string") return key;
  if (!vars) return value;
  return value.replace(/\{(\w+)\}/g, (_, name) => (name in vars ? String(vars[name]) : `{${name}}`));
}

export function tOr(key: string, fallback: string): string {
  const v = t(key);
  return v === key ? fallback : v;
}
