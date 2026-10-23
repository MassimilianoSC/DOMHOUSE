import { t } from "@/i18n";

const LOCALE = "it-IT";
export const DEFAULT_TZ = "Europe/Rome";

export function fmtDateTime(iso: string | null | undefined, tz = DEFAULT_TZ): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(LOCALE, {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: tz,
  }).format(new Date(iso));
}

/** Day only ("1 dic 2026"); "" for a missing or unreadable date, so a caller can leave it out. */
export function fmtDate(iso: string | null | undefined, tz = DEFAULT_TZ): string {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return "";
  return new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short", year: "numeric", timeZone: tz }).format(d);
}

/** Day and month in the apartment's time zone ("1 gennaio"), with the year when it is not the current one there
 *  ("1 gennaio 2025"); "" for a missing or unreadable date. */
export function fmtDayMonth(iso: string | null | undefined, tz = DEFAULT_TZ, now = new Date()): string {
  const d = iso ? new Date(iso) : null;
  if (!d || Number.isNaN(d.getTime())) return "";
  const year = (x: Date) => new Intl.DateTimeFormat("en-US", { year: "numeric", timeZone: tz }).format(x);
  const withYear = year(d) !== year(now);
  return new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "long", ...(withYear ? { year: "numeric" } : {}), timeZone: tz }).format(d);
}

export function fmtShortDateTime(iso: string | null | undefined, tz = DEFAULT_TZ): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(LOCALE, {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: tz,
  }).format(new Date(iso));
}

export function fmtTime(iso: string | null | undefined, tz = DEFAULT_TZ): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(LOCALE, { hour: "2-digit", minute: "2-digit", timeZone: tz }).format(new Date(iso));
}

/** First letter upper case, the rest as it is («casa vuota» → «Casa vuota»): CSS capitalize would give «Casa Vuota». */
export const capitalizeFirst = (s: string): string => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);

export function fmtNumber(n: number | null | undefined, maxDigits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat(LOCALE, { maximumFractionDigits: maxDigits }).format(n);
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
  ["second", 1],
];

export function fmtRelative(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const diff = (new Date(iso).getTime() - now) / 1000;
  const rtf = new Intl.RelativeTimeFormat(LOCALE, { numeric: "auto" });
  for (const [unit, secs] of UNITS) {
    if (Math.abs(diff) >= secs || unit === "second") {
      return rtf.format(Math.round(diff / secs), unit);
    }
  }
  return "";
}

export function fmtRemaining(ms: number): string {
  if (ms <= 0) return "0 min";
  const totalMin = Math.ceil(ms / 60000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  return h > 0 ? `${h} h ${m.toString().padStart(2, "0")} min` : `${m} min`;
}

export function fmtCountdown(ms: number): string {
  if (ms <= 0) return "00:00";
  const s = Math.floor(ms / 1000);
  const mm = Math.floor(s / 60).toString().padStart(2, "0");
  const ss = (s % 60).toString().padStart(2, "0");
  return `${mm}:${ss}`;
}

const part = (d: Date, tz: string, opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("it-IT", { ...opts, timeZone: tz }).format(d);

/** «dal 12 al 18 ottobre», «dal 28 settembre al 4 ottobre»: Monday to Sunday in the apartment's time zone; `to` is
 *  the exclusive end (the Monday after, at midnight), so the last day is the instant before it. */
export function weekRange(from: string, to: string, tz: string, now = new Date()): string {
  const first = new Date(from);
  const last = new Date(new Date(to).getTime() - 1);
  const sameMonth = part(first, tz, { month: "numeric", year: "numeric" }) === part(last, tz, { month: "numeric", year: "numeric" });
  const start = sameMonth ? part(first, tz, { day: "numeric" }) : fmtDayMonth(first.toISOString(), tz, now);
  return t("summaries.range", { from: start, to: fmtDayMonth(last.toISOString(), tz, now) });
}
