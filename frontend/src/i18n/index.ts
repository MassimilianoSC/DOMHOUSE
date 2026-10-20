import it from "./it.json";

type Dict = { [key: string]: string | Dict };
const dictionaries: Record<string, Dict> = { it };
let current: Dict = dictionaries.it;

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
