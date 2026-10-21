import { t, tOr } from "@/i18n";
import { fmtNumber } from "@/lib/format";

// One changed value of a rule, as the Regole page and the «Registro attività» show it (D-151): the field with the same
// label as the page («Minuti», «Stato») and the values («5», «attiva»).

export interface ChangeLike {
  label?: unknown;
  field?: unknown;
  old?: unknown;
  new?: unknown;
}

/** «Stato» for enabled, else the parameter's label on the Regole page; an unknown parameter by its name. */
export const fieldLabel = (field: string): string => (field === "enabled" ? t("rules.proposal.state") : tOr(`rules.params.${field}`, field));

/** «attiva» / «spenta» for the state, a number in Italian, «—» for anything else. */
export function changeValue(field: string, v: unknown): string {
  if (field === "enabled" && typeof v === "boolean") return v ? t("rules.proposal.on") : t("rules.proposal.off");
  return typeof v === "number" ? fmtNumber(v, 2) : "—";
}

const lower = (s: string) => (s ? s.charAt(0).toLowerCase() + s.slice(1) : s);

/** The change as a clause of the log's sentence: «Finestra aperta spegne il clima, minuti da 5 a 10»,
 *  «Antimuffa disattivata». */
export function describeChange(c: ChangeLike): string {
  const label = typeof c.label === "string" && c.label.trim() ? c.label : "—";
  const field = typeof c.field === "string" ? c.field : "";
  if (field === "enabled" && typeof c.new === "boolean") return t(c.new ? "rules.proposal.logEnabled" : "rules.proposal.logDisabled", { label });
  return t("rules.proposal.logChange", { label, field: lower(fieldLabel(field)), from: changeValue(field, c.old), to: changeValue(field, c.new) });
}
