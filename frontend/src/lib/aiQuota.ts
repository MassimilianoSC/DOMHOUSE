// F-13 (o1 59f3ba7): the monthly quota of the assistant of an organisation, set by the platform manager. null = only
// the project's cap counts; 0 = only quick answers. The limits are the server's: its 422 invalid_quota says them.

const EURO = new Intl.NumberFormat("it-IT", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** 3.4 → «3,40». */
export const fmtEuro = (n: number) => EURO.format(n);

/** «2026-11» → «novembre 2026»; anything else as it came. */
export function monthLabel(month: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(month);
  if (!m) return month;
  const date = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, 15));
  return new Intl.DateTimeFormat("it-IT", { month: "long", year: "numeric", timeZone: "UTC" }).format(date);
}

/** What the field says: "" = no quota (null), «3,40» or «3.40» = 3.4, anything else undefined (Salva stays off). */
export function parseQuota(input: string): number | null | undefined {
  const s = input.trim();
  if (s === "") return null;
  if (!/^\d+(?:[.,]\d+)?$/.test(s)) return undefined;
  return Number(s.replace(",", "."));
}
