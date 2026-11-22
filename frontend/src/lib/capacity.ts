import type { Capienza, CapienzaView } from "@/api/platform";
import { t } from "@/i18n";
import { DEFAULT_TZ } from "@/lib/format";
import { MAX_POLL_MS } from "@/lib/apartmentCreation";

// A7 (docs/proposta-a7.md §2 n. 5, §3; answers 1201, 1203): the line of the free places in «Nuovo appartamento», from
// the last reading the server keeps. Zero places turns «Crea» off (NewApartmentDialog); the server and the agent check
// again anyway.

/** After this a reading is old: how long ago, not the hour (the server's «vecchia» too, but the form may stay open). */
export const STALE_MS = 10 * 60_000;
const HOUR_MS = 60 * 60_000;
const DAY_MS = 24 * HOUR_MS;

const rome = (iso: string, opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("it-IT", { ...opts, timeZone: DEFAULT_TZ }).format(new Date(iso));

/** «letto alle 15:10»; old: «letto 25 minuti fa», «letto 2 ore fa», over a day «letto il 19/11 alle 15:10». */
export function readAge(lettaAt: string, oldForServer: boolean, now: number): string {
  const age = Math.max(0, now - new Date(lettaAt).getTime());
  const time = rome(lettaAt, { hour: "2-digit", minute: "2-digit" });
  if (age <= STALE_MS && !oldForServer) return t("capacity.readAt", { time });
  if (age < HOUR_MS) {
    const n = Math.max(1, Math.floor(age / 60_000));
    return n === 1 ? t("capacity.readMinuteAgo") : t("capacity.readMinutesAgo", { n });
  }
  if (age < DAY_MS) {
    const n = Math.floor(age / HOUR_MS);
    return n === 1 ? t("capacity.readHourAgo") : t("capacity.readHoursAgo", { n });
  }
  return t("capacity.readAtDay", { date: rome(lettaAt, { day: "2-digit", month: "2-digit" }), time });
}

export type CapacityLine = { kind: "places" | "zero" | "unread"; text: string };

export function capacityLine(c: Capienza | null, now: number): CapacityLine {
  if (!c) return { kind: "unread", text: t("capacity.unread") };
  const when = readAge(c.letta_at, c.vecchia, now);
  if (c.posti_liberi <= 0) return { kind: "zero", text: t("capacity.zero", { when }) };
  const env = c.ambiente === "prod" ? t("capacity.envProd") : t("capacity.envStaging");
  return { kind: "places", text: t("capacity.places", { env, count: c.posti_liberi, when }) };
}

export type RefreshState = { kind: "none" } | { kind: "running" } | { kind: "failed"; text: string; requestId: string };

/** The last «Aggiorna», only when it is newer than the last good reading: in progress (up to 20 minutes, as «Prova
 *  l'agente»), or not done with the server's sentence and its request id. */
export function refreshState(v: CapienzaView, now: number): RefreshState {
  const a = v.aggiornamento;
  if (!a || a.stato === "riuscito") return { kind: "none" };
  const sent = new Date(a.creato_at).getTime();
  if (v.capienza && new Date(v.capienza.letta_at).getTime() >= sent) return { kind: "none" };
  if (a.stato === "inviato") {
    if (now - sent < MAX_POLL_MS) return { kind: "running" };
    return { kind: "failed", text: t("capacity.timeout"), requestId: a.op_id };
  }
  const text = a.messaggio?.trim() ? t("capacity.failed", { message: a.messaggio.trim() }) : t("capacity.failedPlain");
  return { kind: "failed", text, requestId: a.op_id };
}
