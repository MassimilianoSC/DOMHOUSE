// D-212: the date and time of the apartment (its time zone, not the browser's) ↔ an instant. One place for the
// conversion, so the nights the clocks change are handled the same everywhere.

const MINUTE = 60_000;
const DAY = 86_400_000;

/** How a wall-clock time of the apartment became an instant. */
export type WallKind =
  /** the time exists once: the normal case */
  | "exact"
  /** the time does not exist (the clocks go forward): moved forward by the length of the jump */
  | "skipped"
  /** the time happens twice (the clocks go back): the first time */
  | "repeated";

export interface Resolved {
  at: Date;
  kind: WallKind;
}

const formatters = new Map<string, Intl.DateTimeFormat>();
function formatter(tz: string) {
  let f = formatters.get(tz);
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
    formatters.set(tz, f);
  }
  return f;
}

/** The wall clock in `tz` at instant `ms`, written as if it were UTC (minutes only). */
function wallAsUtc(ms: number, tz: string): number {
  const parts = formatter(tz).formatToParts(new Date(ms));
  const get = (k: string) => Number(parts.find((p) => p.type === k)?.value);
  return Date.UTC(get("year"), get("month") - 1, get("day"), get("hour") % 24, get("minute"));
}

/** How far the wall clock of `tz` is ahead of UTC at instant `ms`. */
const offsetAt = (ms: number, tz: string) => wallAsUtc(Math.floor(ms / MINUTE) * MINUTE, tz) - Math.floor(ms / MINUTE) * MINUTE;

/**
 * The instant at which the clock of `tz` shows that date and time. A time that does not exist is moved forward by the
 * length of the jump (02:30 → 03:30); a time that happens twice is taken the first time. It is the rule Python applies
 * by default (fold=0) and the browsers' «compatible» one, so the server reads the same instant.
 */
export function zonedToInstant(year: number, month: number, day: number, hour: number, minute: number, tz: string): Resolved {
  const wall = Date.UTC(year, month - 1, day, hour, minute);
  // The offsets in force around that day: before, at and after a change of the clocks (never two changes in two days).
  const offsets = [...new Set([offsetAt(wall - DAY, tz), offsetAt(wall, tz), offsetAt(wall + DAY, tz)])];
  const found = [...new Set(offsets.map((o) => wall - o).filter((ms) => wallAsUtc(ms, tz) === wall))].sort((a, b) => a - b);
  if (found.length === 1) return { at: new Date(found[0]), kind: "exact" };
  if (found.length > 1) return { at: new Date(found[0]), kind: "repeated" };
  // Not on the clock: read with the offset before the jump, which lands as far after the jump as the time was inside it.
  return { at: new Date(wall - offsetAt(wall - DAY, tz)), kind: "skipped" };
}

const WALL = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::\d{2}(?:\.\d+)?)?$/;

/** The value of a date-and-time field ("2027-03-28T02:30"), read in `tz`; null when empty or not a date and time. */
export function wallToInstant(value: string, tz: string): Resolved | null {
  const m = WALL.exec(value);
  if (!m) return null;
  const [y, mo, d, h, mi] = m.slice(1).map(Number);
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59) return null;
  const check = new Date(Date.UTC(y, mo - 1, d));
  if (check.getUTCMonth() !== mo - 1) return null; // 31 April and the like
  return zonedToInstant(y, mo, d, h, mi, tz);
}

const pad = (n: number) => String(n).padStart(2, "0");

/** The date and time the clock of `tz` shows at `at`, as a date-and-time field wants it ("2027-03-28T03:30"). */
export function instantToWall(at: Date, tz: string): string {
  const w = new Date(wallAsUtc(at.getTime(), tz));
  return `${w.getUTCFullYear()}-${pad(w.getUTCMonth() + 1)}-${pad(w.getUTCDate())}T${pad(w.getUTCHours())}:${pad(w.getUTCMinutes())}`;
}

/** The apartment's date `daysAhead` days from today (negative: back) at `hour`:`minute`, as a date-and-time field wants it. */
export function wallDaysFromToday(tz: string, daysAhead: number, hour: number, minute = 0, now = new Date()): string {
  const today = new Date(wallAsUtc(now.getTime(), tz));
  const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() + daysAhead));
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}T${pad(hour)}:${pad(minute)}`;
}
