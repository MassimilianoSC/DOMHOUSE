import { bffFetch } from "./bff";
import type { RuleSet } from "./types";

// Rules proposed by the assistant and confirmed by the manager (P-60 step 12, D-151): routes #38 and #39 of
// bff/API.md. The proposal is not saved anywhere: the site keeps it until «Applica» and sends it back as received.

/** One value that changes: `field` is "enabled" (old and new booleans) or the name of a parameter. */
export interface RuleChange {
  rule_id: string;
  label: string;
  field: string;
  old: number | boolean | null;
  new: number | boolean | null;
}

export interface RuleProposal {
  /** updated_at of the rules the proposal starts from: «Applica» answers 409 rules_changed if they changed since. */
  based_on: string;
  rules: { rule_id: string; enabled?: boolean; params?: Record<string, number> }[];
  /** Empty: no proposal, and `explanation` says why (out of range, already so, not about the rules). */
  changes: RuleChange[];
  explanation: string;
}

/** The longest request the server accepts (422 text_too_long beyond it). */
export const PROPOSAL_MAX_CHARS = 500;

const base = (aptId: string) => `/app/apartments/${encodeURIComponent(aptId)}/rules/proposal`;

export const ruleProposalApi = (aptId: string) => ({
  /** Operator or admin; 422 bad_request / text_too_long, 429 daily_limit / monthly_cap, 409 apartment_disabled, 502/504. */
  propose: (text: string, correlationId: string) => bffFetch<RuleProposal>(base(aptId), { method: "POST", body: { text }, correlationId }),
  /** The whole RuleSet after the change, as the PUT of the rules; 409 rules_changed when the rules changed meanwhile. */
  apply: (p: Pick<RuleProposal, "based_on" | "rules">, correlationId: string) =>
    bffFetch<RuleSet>(`${base(aptId)}/apply`, { method: "POST", body: { based_on: p.based_on, rules: p.rules }, correlationId }),
});
