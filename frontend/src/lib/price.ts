import { fmtNumber } from "@/lib/format";

// Price of energy per kWh (P-52, D-92): set by the admin for the organization, with an exception per apartment.
// The BFF accepts 0-10 €/kWh with at most 4 decimals (422 invalid_price): the site checks the same before sending.

export const PRICE_MAX = 10;

/**
 * What the admin typed, with a comma or a dot: null for an empty field (no price, or "use the organization's"),
 * undefined when it is not a valid price.
 */
export function parsePrice(input: string): number | null | undefined {
  const s = input.trim().replace(",", ".");
  if (!s) return null;
  if (!/^\d+(\.\d{1,4})?$/.test(s)) return undefined;
  const n = Number(s);
  return n <= PRICE_MAX ? n : undefined;
}

/** "0,25" for 0.25 (up to 4 decimals, as entered). */
export const fmtPrice = (n: number) => fmtNumber(n, 4);

/** The field's starting text: the price as the admin writes it, or empty. */
export const priceInput = (n: number | null | undefined) => (n === null || n === undefined ? "" : fmtPrice(n));
