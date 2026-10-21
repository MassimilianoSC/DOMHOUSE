import { bffFetch } from "./bff";
import type { RuleChange } from "./ruleProposals";

// Copy of the rules to other apartments of the organization (P-60 step 12d, D-151 point 22): routes #40 and #41 of
// bff/API.md, admins only, always in two steps (preview, then confirmation with what the preview returned).

export interface CopyFrom {
  apartment_id: string;
  name: string;
  based_on: string;
}

/** A value of the target that differs from the contract's default and will be overwritten. */
export interface Customized {
  rule_id: string;
  label: string;
  field: string;
  value: number | boolean | null;
  default: number | boolean | null;
}

export interface CopyTarget {
  apartment_id: string;
  name: string;
  based_on: string | null;
  /** changes (with `changes`), same, disabled, unreachable, refused (with `message`). */
  status: "changes" | "same" | "disabled" | "unreachable" | "refused" | (string & {});
  changes?: RuleChange[];
  customized?: Customized[];
  message?: string | null;
}

export interface CopyPreview {
  from: CopyFrom;
  rules: unknown[];
  targets: CopyTarget[];
}

export interface CopyResult {
  apartment_id: string;
  name: string;
  /** applied, same, changed_meanwhile, disabled, unreachable, refused. */
  outcome: "applied" | "same" | "changed_meanwhile" | "disabled" | "unreachable" | "refused" | (string & {});
  message?: string | null;
  changes?: RuleChange[];
}

const base = (aptId: string) => `/app/apartments/${encodeURIComponent(aptId)}/rules/copy`;

export const ruleCopyApi = (aptId: string) => ({
  /** Changes nothing. 403 to non-admins; 422 bad_request, same_apartment, too_many; 404 for a target not visible. */
  preview: (to: string[], correlationId: string) => bffFetch<CopyPreview>(`${base(aptId)}/preview`, { method: "POST", body: { to }, correlationId }),
  /** Everything taken from the preview; 409 rules_changed when the source's rules changed after it. */
  copy: (p: CopyPreview, correlationId: string) =>
    bffFetch<{ from: CopyFrom; results: CopyResult[] }>(base(aptId), {
      method: "POST",
      body: {
        to: p.targets.map((x) => x.apartment_id),
        from_based_on: p.from.based_on,
        based_on: Object.fromEntries(p.targets.map((x) => [x.apartment_id, x.based_on])),
      },
      correlationId,
    }),
});
