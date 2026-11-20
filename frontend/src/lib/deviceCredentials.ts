import type { CredentialState, DeviceCredential } from "@/api/deviceCredentials";
import { t } from "@/i18n";
import { DEFAULT_TZ } from "@/lib/format";

// A3: the rules of the page «Credenziali dei dispositivi» that do not depend on React (docs/proposta-a3-sito.md §3,
// docs/proposta-a3-server.md §4.3), so each is proved on its own.

export type CredentialAction = "riprova" | "rigenera" | "revoca" | "registra";

const IN_PROGRESS: ReadonlySet<CredentialState> = new Set(["in_attesa", "cambio_in_corso", "revoca_in_corso"]);

/** An order is on its way: the page reads the list again until the outcome. */
export const inProgress = (s: CredentialState) => IN_PROGRESS.has(s);

/**
 * What the site offers for a device, the same table as the server's (§4.3), so a button never leads to a 409 that the
 * page could have avoided. A revoke not applied is closed only with «Riprova»: «Rigenera» would bring the device back.
 */
export function allowedActions(c: DeviceCredential): CredentialAction[] {
  switch (c.stato) {
    case "in_attesa":
    case "pronto":
      return ["rigenera", "revoca"];
    case "cambio_in_corso":
      return ["revoca"]; // a stolen device must not wait for the password change
    case "revoca_in_corso":
      return [];
    case "revocato":
      return ["registra"];
    case "non_applicato":
      return c.azione === "revoca" ? ["riprova"] : ["riprova", "rigenera", "revoca"];
  }
}

const rank = (s: CredentialState) => (s === "non_applicato" ? 0 : inProgress(s) ? 1 : 2);

/** The active devices (not applied first, then in progress, then ready, each by code) and the revoked ones apart. */
export function splitCredentials(items: DeviceCredential[]): { active: DeviceCredential[]; revoked: DeviceCredential[] } {
  const byCode = (a: DeviceCredential, b: DeviceCredential) => a.device_id.localeCompare(b.device_id);
  return {
    active: items.filter((c) => c.stato !== "revocato").sort((a, b) => rank(a.stato) - rank(b.stato) || byCode(a, b)),
    revoked: items.filter((c) => c.stato === "revocato").sort(byCode),
  };
}

/** The project's rule for a device code (§2.1): lowercase letters, digits and dashes, up to 64; capitals are refused. */
export const DEVICE_ID_RE = /^[a-z0-9][a-z0-9-]{0,63}$/;
/** The connector's own account on the broker (server §5.1, broker_accounts.RESERVED_DEVICE). */
const RESERVED_IDS = new Set(["connector"]);

export function deviceIdProblem(value: string): "empty" | "invalid" | "reserved" | null {
  const v = value.trim();
  if (!v) return "empty";
  if (!DEVICE_ID_RE.test(v)) return "invalid";
  return RESERVED_IDS.has(v) ? "reserved" : null;
}

export const POLL_MS = 4_000;
/** After 20 minutes the server itself gives «non applicato» (server §4.1): the page stops reading too. */
export const MAX_POLL_MS = 20 * 60_000;

/** What is on its way, for pollWindow: each device in progress with its state and version; "" for nothing. A new order
 *  changes the version, so it opens another 20 minutes. */
export function credentialsSignature(items: DeviceCredential[] | undefined): string {
  return (items ?? []).filter((c) => inProgress(c.stato)).map((c) => `${c.device_id}:${c.stato}:${c.version}`).join("|");
}

/**
 * A5 (docs/proposta-a5.md): the refused connections of a device in the last 24 hours. warning: after the last change,
 * with «Cosa fare»; past: all before the last change (a «Rigenera», a new registration), nothing to do if the Shelly
 * has the new data; revoked: the Shelly still tries; plain: a revoke on its way, only the number. null = no line: the
 * server does not know (null) or there are none.
 */
export type RefusalNote = { kind: "warning" | "past" | "revoked" | "plain"; text: string };

const rome = (iso: string | number, opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("it-IT", { ...opts, timeZone: DEFAULT_TZ }).format(new Date(iso));

export function refusalNote(c: DeviceCredential, now: number): RefusalNote | null {
  const r = c.rifiuti;
  if (!r || !(r.conteggio_24h > 0) || !r.ultimo) return null;
  const day = { day: "2-digit", month: "2-digit" } as const;
  const time = rome(r.ultimo, { hour: "2-digit", minute: "2-digit" });
  const when = rome(r.ultimo, day) === rome(now, day) ? t("credentials.refusals.whenToday", { time }) : t("credentials.refusals.whenDay", { date: rome(r.ultimo, day), time });
  const text = r.conteggio_24h === 1 ? t("credentials.refusals.one", { when }) : t("credentials.refusals.many", { count: r.conteggio_24h, when });
  if (c.stato === "revocato") return { kind: "revoked", text };
  if (c.stato === "revoca_in_corso") return { kind: "plain", text };
  if (new Date(r.ultimo).getTime() <= new Date(c.updated_at).getTime()) return { kind: "past", text };
  return { kind: "warning", text };
}
