import { bffFetch } from "./bff";

// Weekly summary (P-60 step 11, D-150): made by the BFF every Monday from 08:00 (apartment time) on the week just
// ended; routes #36 and #37 of bff/API.md. The sentences are written by the server; the site shows them as they are.

/** normal | anomalous (+30 % and +5 kWh on the median) | not_comparable (no nights of that kind before: never an
 *  alarm) | no_nights (no night of that kind this week, kwh_per_night null). */
export type SummaryStatus = "normal" | "anomalous" | "not_comparable" | "no_nights";

export interface NightsComparison {
  nights: number;
  kwh_per_night: number | null;
  median_before: number | null;
  status: SummaryStatus;
}

export type SummaryEnergy =
  | {
      available: true;
      occupied: NightsComparison;
      vacant: NightsComparison;
      devices: { device_id: string; label: string; occupied: NightsComparison; vacant: NightsComparison }[];
    }
  | { available: false; since?: string | null; reason: string };

export interface SummaryListItem {
  week: string;
  from: string;
  /** Exclusive end: the Monday after, at midnight in the apartment's time zone. */
  to: string;
  notable: boolean;
  /** How many sentences the summary has. */
  items: number;
}

export interface WeeklySummary {
  apartment_id: string;
  week: string;
  from: string;
  to: string;
  generated_at: string;
  energy: SummaryEnergy;
  offline: { now: { device_id: string; label: string; last_seen: string | null }[]; episodes: { device_id: string; label: string; times: number }[] };
  approvals_expired: { approval_id: string; description: string; created_at: string }[];
  windows: { window: string; times: number }[];
  /** The sentences to show, in order; empty = a week with nothing to report. */
  items: string[];
  notable: boolean;
}

const base = (aptId: string) => `/app/apartments/${encodeURIComponent(aptId)}/summaries`;

export const summariesApi = (aptId: string) => ({
  /** Most recent first, at most 20; [] before the first one. */
  list: () => bffFetch<SummaryListItem[]>(base(aptId)),
  /** 404 not_found «Riepilogo inesistente». */
  get: (week: string) => bffFetch<WeeklySummary>(`${base(aptId)}/${encodeURIComponent(week)}`),
});
