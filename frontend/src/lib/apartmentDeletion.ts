import type { Eliminazione, EliminazionePasso, PlatformApartment } from "@/api/platform";
import { t } from "@/i18n";
import type { StepState } from "@/lib/apartmentCreation";

// A6 (docs/proposta-a6.md; bff/API.md «Eliminazione di un appartamento»): the rules of the platform's row of a ready
// apartment that do not depend on React. Disattiva, then «Elimina» once the server's eliminabile_dal has passed; the
// deletion goes engine → keys → data, and is read again every 4 s while it is in progress (as the creation of A2).

export const DELETION_STEPS: readonly EliminazionePasso[] = ["motore", "segreti", "database"];

/** What the row offers. del: none (active, dev, or a deletion already started), noDate (off before A6: «Disattiva»
 *  starts the 7 days), wait (eliminabile_dal still ahead), ready. */
export type DeletionOffer = { disable: boolean; reenable: boolean; del: "none" | "noDate" | "wait" | "ready" };

export function deletionOffer(a: PlatformApartment, now: number): DeletionOffer {
  if (a.eliminazione) return { disable: false, reenable: false, del: "none" };
  if (a.enabled) return { disable: true, reenable: false, del: "none" };
  const noDate = !a.disattivato_at;
  if (a.origine === "dev") return { disable: noDate, reenable: true, del: "none" };
  if (noDate) return { disable: true, reenable: true, del: "noDate" };
  if (!a.eliminabile_dal) return { disable: false, reenable: true, del: "none" };
  return { disable: false, reenable: true, del: new Date(a.eliminabile_dal).getTime() <= now ? "ready" : "wait" };
}

const index = (p: EliminazionePasso) => DELETION_STEPS.indexOf(p);

export function deletionStepState(e: Eliminazione, step: EliminazionePasso): StepState {
  const i = index(step);
  const at = index(e.passo);
  if (i < at) return "fatto";
  if (i > at) return "da_fare";
  return e.stato === "non_riuscita" ? "fallito" : "in_corso";
}

export const deletionStoppedAt = (e: Eliminazione) => ({ passo: e.passo, n: index(e.passo) + 1, of: DELETION_STEPS.length });

/** Deletions on their way, for pollWindow; "" for nothing. A «Riprova» changes the version: another 20 minutes. */
export function deletionSignature(items: PlatformApartment[] | undefined): string {
  return (items ?? []).filter((a) => a.eliminazione?.stato === "in_corso").map((a) => `${a.apartment_id}:eliminazione:${a.eliminazione!.version}`).join("|");
}

const WHAT: Record<string, string> = {
  non_creato_da_agente: "manual",
  chiavi_non_distrutte: "chiavi_non_distrutte",
  non_inviato: "non_inviato",
  tempo_scaduto: "tempo_scaduto",
  errore_interno: "errore_interno",
};

/** Every text of WHAT, for the check of it.json. */
export const DELETION_WHAT_TEXTS = [...new Set([...Object.values(WHAT), "generic"])];

/** «Cosa è successo»: the site's text for the codes it knows, else the server's sentence, else a plain one. */
export function deletionWhat(e: Eliminazione): string {
  const code = e.codice ?? e.op?.codice;
  if (code && WHAT[code]) return t(`platform.deletion.what.${WHAT[code]}`);
  return e.messaggio?.trim() || e.op?.messaggio?.trim() || t("platform.deletion.what.generic");
}

/** The confirmation by writing the name: exact, capitals included, the spaces at the ends do not count (the server
 *  compares the same way). */
export const nameMatches = (typed: string, name: string) => typed.trim() !== "" && typed.trim() === name.trim();
