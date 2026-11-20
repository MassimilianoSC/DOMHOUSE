import type { ApartmentSummary } from "@/api/types";

/**
 * «Consumo registrato oggi» on the apartments page: the sum of each apartment's kwh_today (from the engine, local
 * midnight to now). A demonstration apartment has simulated numbers: next to real apartments it stays out of the total
 * and is counted apart (demosExcluded); when there are only demonstration apartments the total is theirs, said to be
 * simulated (demoOnly). `withData` of `counted` apartments have a value; no value at all gives null, never 0.
 */
export function energySummary(items: ApartmentSummary[]): { total: number | null; withData: number; counted: number; demosExcluded: number; demoOnly: boolean } {
  const real = items.filter((a) => !a.simulated);
  const demoOnly = real.length === 0 && items.length > 0;
  const pool = demoOnly ? items : real;
  const values = pool.map((a) => a.kwh_today).filter((k): k is number => typeof k === "number" && Number.isFinite(k) && k >= 0);
  return {
    total: values.length ? values.reduce((sum, k) => sum + k, 0) : null,
    withData: values.length,
    counted: pool.length,
    demosExcluded: demoOnly ? 0 : items.length - real.length,
    demoOnly,
  };
}
