import type { CredentialState, DeviceCredential } from "@/api/deviceCredentials";

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

/** React Query's refetchInterval: every 4 s while something is in progress, for at most 20 minutes. */
export function refetchEvery(items: DeviceCredential[] | undefined, startedAt: number, now: number): number | false {
  if (!items?.some((c) => inProgress(c.stato))) return false;
  return now - startedAt < MAX_POLL_MS ? POLL_MS : false;
}
