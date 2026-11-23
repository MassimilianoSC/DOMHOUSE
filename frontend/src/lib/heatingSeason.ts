/**
 * Item 15: the heating season, four numbers inside the engine's «Limiti del setpoint» rule (o1, option A: no contract
 * change), valid also with the rule off. Outside the season the boiler stays on frost protection only. «All year» is
 * 1 January → 31 December.
 */

export type DayOfYear = { month: number; day: number };
export type Season = { start: DayOfYear; end: DayOfYear };
export type ZoneId = "A" | "B" | "C" | "D" | "E" | "F";

export const SEASON_KEYS = {
  startMonth: "season_start_month",
  startDay: "season_start_day",
  endMonth: "season_end_month",
  endDay: "season_end_day",
} as const;

/**
 * The legal heating periods by climatic zone: DPR 16 aprile 2013, n. 74, art. 4, comma 2 (zone A 1 Dec–15 Mar, B 1
 * Dec–31 Mar, C 15 Nov–31 Mar, D 1 Nov–15 Apr, E 15 Oct–15 Apr, F «nessuna limitazione»: all year here). A town's zone is
 * in Annex A of DPR 412/1993; the mayor may extend the period (art. 5). The daily hour limits are not handled.
 */
export const ZONES: Record<ZoneId, Season> = {
  A: { start: { month: 12, day: 1 }, end: { month: 3, day: 15 } },
  B: { start: { month: 12, day: 1 }, end: { month: 3, day: 31 } },
  C: { start: { month: 11, day: 15 }, end: { month: 3, day: 31 } },
  D: { start: { month: 11, day: 1 }, end: { month: 4, day: 15 } },
  E: { start: { month: 10, day: 15 }, end: { month: 4, day: 15 } },
  F: { start: { month: 1, day: 1 }, end: { month: 12, day: 31 } },
};

/** Days in each month; February with 29, a day that exists in leap years. */
const DAYS_IN_MONTH = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

export function dayExists(month: number, day: number): boolean {
  return Number.isInteger(month) && Number.isInteger(day) && month >= 1 && month <= 12 && day >= 1 && day <= DAYS_IN_MONTH[month - 1];
}

const same = (a: DayOfYear, b: DayOfYear) => a.month === b.month && a.day === b.day;

export function zoneOf(season: Season | null): ZoneId | null {
  if (!season) return null;
  return (Object.keys(ZONES) as ZoneId[]).find((z) => same(ZONES[z].start, season.start) && same(ZONES[z].end, season.end)) ?? null;
}

/** The season in a rule's parameters; null when one of the four is missing (an engine from before item 15). */
export function seasonOf(params: Record<string, number | undefined>): Season | null {
  const [sm, sd, em, ed] = [SEASON_KEYS.startMonth, SEASON_KEYS.startDay, SEASON_KEYS.endMonth, SEASON_KEYS.endDay].map((k) => params[k]);
  if ([sm, sd, em, ed].some((v) => typeof v !== "number")) return null;
  return { start: { month: sm!, day: sd! }, end: { month: em!, day: ed! } };
}

/** «ottobre»: the month's Italian name (1–12). */
const MONTHS = new Intl.DateTimeFormat("it-IT", { month: "long", timeZone: "UTC" });
export const monthName = (month: number): string => MONTHS.format(Date.UTC(2024, month - 1, 1));

/** «15 ottobre». */
export const dayName = (d: DayOfYear): string => `${d.day} ${monthName(d.month)}`;

/** A month parameter of the season (season_start_month, season_end_month). */
export const isSeasonMonth = (key: string): boolean => key === SEASON_KEYS.startMonth || key === SEASON_KEYS.endMonth;

export function seasonParams(season: Season): Record<string, number> {
  return {
    [SEASON_KEYS.startMonth]: season.start.month,
    [SEASON_KEYS.startDay]: season.start.day,
    [SEASON_KEYS.endMonth]: season.end.month,
    [SEASON_KEYS.endDay]: season.end.day,
  };
}
