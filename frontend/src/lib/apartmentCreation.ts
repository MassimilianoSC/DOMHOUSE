import { ApiError } from "@/api/bff";
import type { Creazione, CreazionePasso, PlatformApartment, PlatformTenant } from "@/api/platform";
import { t } from "@/i18n";
import { DEFAULT_TZ } from "./format";

// A2: the rules of «Nuovo appartamento» and of the creation that do not depend on React (docs/proposta-a2-sito.md §2,
// §3, §4, §6; the server's shapes in docs/proposta-a2.md §2.1, §2.2, §6), so each is proved on its own.

/** In staging only lab-… and test-…; lowercase letters, digits and dashes, no dash at the end (docs/proposta-a2.md §3.1). */
const NEW_ID_RE = /^(lab|test)-[a-z0-9]([a-z0-9-]*[a-z0-9])?$/;
const NEW_ID_MAX = 64;

/** Checked while the person types; the server checks the same rule again (422 invalid_apartment_id). */
export function newIdProblem(value: string): "empty" | "invalid" | null {
  const v = value.trim();
  if (!v) return "empty";
  // «-devices» at the end would clash with the name of the apartment's device key (§3.3)
  if (v.length > NEW_ID_MAX || !NEW_ID_RE.test(v) || v.endsWith("-devices")) return "invalid";
  return null;
}

export const CREATION_STEPS: readonly CreazionePasso[] = ["riserva", "segreti", "capienza", "motore", "collegamento"];

export type StepState = "fatto" | "in_corso" | "da_fare" | "fallito";

/** One step of the strip (§3.3): `passo` is the last one reached, in progress or, when non_creato, the one that stopped. */
export function stepState(c: Creazione, step: CreazionePasso): StepState {
  if (c.stato === "pronto") return "fatto";
  const at = CREATION_STEPS.indexOf(c.passo);
  const i = CREATION_STEPS.indexOf(step);
  if (i < at) return "fatto";
  if (i > at) return "da_fare";
  return c.stato === "non_creato" ? "fallito" : "in_corso";
}

/** «Si è fermata a: ‹passo› (passo N di 5)» (§3.2). */
export function stoppedAt(c: Creazione): { passo: CreazionePasso; n: number; of: number } {
  return { passo: c.passo, n: CREATION_STEPS.indexOf(c.passo) + 1, of: CREATION_STEPS.length };
}

/** An apartment the organization can use: connected by hand (no creation) or created and ready. */
export const isUsable = (a: PlatformApartment) => !a.creazione || a.creazione.stato === "pronto";

const rank = (a: PlatformApartment) => {
  const s = a.creazione?.stato;
  const e = a.eliminazione?.stato;
  if (s === "non_creato" || e === "non_riuscita") return 0;
  if (s === "in_preparazione" || s === "annullamento_in_corso" || e === "in_corso") return 1;
  return 2;
};

/** The platform's list (§3.1): stopped creations first, then the ones on their way, then the others as the server sends them. */
export function sortForPlatform(items: PlatformApartment[]): PlatformApartment[] {
  return items.map((a, i) => ({ a, i })).sort((x, y) => rank(x.a) - rank(y.a) || x.i - y.i).map(({ a }) => a);
}

export const POLL_MS = 4_000;
/** After 20 minutes without an outcome the server itself gives non_creato: the page stops reading too. */
export const MAX_POLL_MS = 20 * 60_000;

const moving = (a: PlatformApartment) => a.creazione?.stato === "in_preparazione" || a.creazione?.stato === "annullamento_in_corso";

/** What is on its way, for pollWindow: each creation or cancellation with its state and version; "" for nothing. A
 *  «Riprova» changes the version, so it opens another 20 minutes. */
export function creationSignature(items: PlatformApartment[] | undefined): string {
  return (items ?? []).filter(moving).map((a) => `${a.apartment_id}:${a.creazione!.stato}:${a.creazione!.version}`).join("|");
}

/** The site's sentence for each outcome code (§6.2); the codes that need a person all say the same thing. */
const WHAT: Record<string, string> = {
  capienza_insufficiente: "capienza_insufficiente",
  staging_pieno: "staging_pieno",
  porta_occupata: "porta_occupata",
  porta_fuori_fascia: "rifiutata",
  immagine_non_approvata: "rifiutata",
  gia_esiste_diverso: "rifiutata",
  dati_presenti: "rifiutata",
  non_creato_da_agente: "rifiutata",
  firma_non_valida: "rifiutata",
  segreto_illeggibile: "segreto_illeggibile",
  motore_non_sano: "motore_non_sano",
  broker_fallito: "broker_fallito",
  tempo_scaduto: "tempo_scaduto",
  // the server's own (o1 cb3ee25), some with no order to the agent behind them
  segreti_non_creati: "segreti_non_creati",
  secret_conflict: "secret_conflict",
  collegamento_fallito: "collegamento_fallito",
  chiavi_non_distrutte: "chiavi_non_distrutte",
  non_inviato: "non_inviato",
};

/** Every text of WHAT, for the check of it.json. */
export const WHAT_TEXTS = [...new Set(Object.values(WHAT))];

/** «Cosa è successo»: the site's text for the creation's code (or, from an older answer, the last order's), else the
 *  server's sentence, else a plain one. */
export function whatHappened(c: Creazione): string {
  const code = c.codice ?? c.op?.codice;
  if (code && WHAT[code]) return t(`platform.creation.what.${WHAT[code]}`);
  return c.messaggio?.trim() || c.op?.messaggio?.trim() || t("platform.creation.what.generic");
}

const romeDay = (d: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: DEFAULT_TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(d);
const romeTime = (d: Date) => new Intl.DateTimeFormat("it-IT", { timeZone: DEFAULT_TZ, hour: "2-digit", minute: "2-digit" }).format(d);
const romeDate = (d: Date) => new Intl.DateTimeFormat("it-IT", { timeZone: DEFAULT_TZ, day: "2-digit", month: "2-digit" }).format(d);

/** When a new creation is possible again, in Rome's time: «dalle 17:42», or «dal 21/11 alle 00:12» on another day. */
export function freeFromText(iso: string, now = new Date()): string {
  const d = new Date(iso);
  if (romeDay(d) === romeDay(now)) return t("platform.creation.freeFromSameDay", { time: romeTime(d) });
  return t("platform.creation.freeFromOtherDay", { date: romeDate(d), time: romeTime(d) });
}

const DEFAULT_LIMIT = 5;

/** The limit of a 429 rate_limited (o1: limite and riprova_dal inside details); riprova_dal null when missing or unreadable. */
export function rateLimitOf(err: unknown): { limite: number; riprova_dal: string | null } | null {
  if (!(err instanceof ApiError) || err.code !== "rate_limited") return null;
  const limite = typeof err.details?.limite === "number" ? err.details.limite : DEFAULT_LIMIT;
  const when = err.details?.riprova_dal;
  const readable = typeof when === "string" && !Number.isNaN(new Date(when).getTime());
  return { limite, riprova_dal: readable ? when : null };
}

/** The line under the organization's name (§4): red with stopped creations, neutral with creations on their way. */
export function tenantCreationLine(tn: Pick<PlatformTenant, "appartamenti_non_creati" | "appartamenti_in_preparazione">): { tone: "negative" | "neutral"; text: string } | null {
  const stopped = tn.appartamenti_non_creati ?? 0;
  const preparing = tn.appartamenti_in_preparazione ?? 0;
  if (stopped > 0) return { tone: "negative", text: t(stopped === 1 ? "platform.creation.tenantStoppedOne" : "platform.creation.tenantStoppedMany", { count: stopped }) };
  if (preparing > 0) return { tone: "neutral", text: t(preparing === 1 ? "platform.creation.tenantPreparingOne" : "platform.creation.tenantPreparingMany", { count: preparing }) };
  return null;
}
