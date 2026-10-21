import { t } from "@/i18n";
import { isPseudonym } from "@/lib/describe";
import { fmtDateTime } from "@/lib/format";
import { fmtPrice } from "@/lib/price";
import { describeChange } from "@/lib/ruleChanges";

// «Registro attività» (P-47): who did what on what, as one Italian sentence. Names come resolved by the BFF at read
// time; a person who no longer exists arrives with removed: true and no email or name (P-48).

export const AUDIT_ACTIONS = [
  "invite_sent", "invite_resent", "invite_email_deferred", "role_changed", "scope_changed", "user_removed",
  "apartment_created", "apartment_updated", "apartment_relinked", "apartment_deleted", "italianway_changed", "features_changed",
  "tenant_created", "tenant_renamed", "tenant_suspended", "tenant_reactivated",
  "support_access_requested", "support_access_opened", "support_access_approved", "support_access_rejected", "support_access_closed", "support_access_expired",
  "manager_added", "manager_removed", "account_deleted",
  "energy_price_changed", "apartment_simulated_changed", "simulator_reset", "rules_changed",
] as const;
export type AuditAction = (typeof AUDIT_ACTIONS)[number];

export interface AuditActor {
  kind: "user" | "platform" | "support" | "system";
  /** No longer sent (D-90); kept optional for older answers. */
  uid?: string | null;
  email: string | null;
  display_name: string | null;
  removed: boolean;
  /** Role at the time of the action. In the platform's log a person of the organization comes with this only, no
   *  email or name (P-51, D-90); null for entries written before. */
  role?: string | null;
}

export interface AuditEntry {
  audit_id: string;
  at: string;
  /** No longer sent (D-90); kept optional for older answers. */
  tenant_id?: string | null;
  /** A closed enum agreed with o1; an action this version does not know still gets a sentence (fallback). */
  action: AuditAction | (string & {});
  actor: AuditActor;
  target: { type: "user" | "apartment" | "tenant" | "support_access" | "manager"; id: string; label: string | null; removed?: boolean; role?: string | null };
  details: Record<string, unknown>;
}

export interface AuditPage {
  items: AuditEntry[];
  next: string | null;
}

const text = (v: unknown): string | null => (typeof v === "string" && v.trim() ? v : typeof v === "number" ? String(v) : null);
const isAction = (a: string): a is AuditAction => (AUDIT_ACTIONS as readonly string[]).includes(a);
/** A person's email or name; a pseudonym that reached the site unresolved counts as missing (D-87). */
const nameText = (v: unknown): string | null => {
  const s = text(v);
  return s && !isPseudonym(s) ? s : null;
};

/**
 * Who acted: a person, the platform, the HQE support or the system itself. In an admin's log a platform manager comes
 * without email or name (only the support access shows the operator's real identity, P-50).
 */
export function actorLabel(a: AuditActor): string {
  if (a.removed) return t("audit.removedUser");
  if (a.kind === "system") return t("audit.system");
  const name = nameText(a.display_name) ?? nameText(a.email);
  if (a.kind === "support") return name ? t("audit.support", { name }) : t("audit.supportAnon");
  if (a.kind === "platform") return name ? t("audit.platform", { name }) : t("audit.platformAnon");
  if (name) return name;
  // Someone of the organization seen from the platform, or a pseudonym: by role only (P-51), never «utente rimosso»
  // unless the server says so.
  if (text(a.email) ?? text(a.display_name)) return t("audit.removedUser");
  if (a.role === "admin") return t("audit.anonAdmin");
  if (a.role === "operator") return t("audit.anonOperator");
  if (a.role === "viewer") return t("audit.anonViewer");
  return t("audit.anonUser");
}

/** What the action was on: a person by name, an apartment or an organization between «». */
function targetLabel(e: AuditEntry): string {
  const { type, id, label, removed } = e.target;
  if (type === "user" || type === "manager") {
    if (removed) return t("audit.removedUserInline");
    // A pseudonym that reached the site counts as removed; no label at all is the platform's view (P-51): «un utente».
    return nameText(label) ?? (text(label) ? t("audit.removedUserInline") : t("audit.someone"));
  }
  return `«${text(label) ?? id}»`;
}

/** A role as Settings shows it, between «» ("da «Sola lettura» a «Amministratore»"). */
const role = (v: unknown) => {
  const r = text(v);
  return `«${r && ["admin", "operator", "viewer"].includes(r) ? t(`roles.${r}`) : r ?? "—"}»`;
};

/** The sentence of an entry, plus an optional note (the reason given for a suspension or an assistance access). */
export function describeEntry(e: AuditEntry): { sentence: string; note: string | null } {
  const d = e.details ?? {};
  const v = { actor: actorLabel(e.actor), target: targetLabel(e) };
  const reason = text(d.reason);
  const note = reason ? t("audit.reason", { reason }) : null;
  if (!isAction(e.action)) return { sentence: t("audit.unknown", { ...v, action: e.action }), note };
  switch (e.action) {
    case "invite_sent": {
      const scope = d.apartment_ids;
      const sentence = t("audit.actions.invite_sent", { ...v, role: role(d.role) });
      if (!Array.isArray(scope)) return { sentence, note };
      return { sentence: sentence + (scope.length === 1 ? t("audit.oneApartment") : t("audit.someApartments", { count: scope.length })), note };
    }
    case "role_changed":
      return { sentence: t("audit.actions.role_changed", { ...v, from: role(d.from), to: role(d.to) }), note };
    case "scope_changed":
      return { sentence: t("audit.actions.scope_changed", { ...v, scope: !Array.isArray(d.to) ? t("audit.scopeAll") : d.to.length === 1 ? t("audit.scopeOne") : t("audit.scopeSome", { count: d.to.length }) }), note };
    case "italianway_changed":
      return { sentence: t("audit.actions.italianway_changed", { ...v, from: text(d.from) ?? t("audit.none"), to: text(d.to) ?? t("audit.none") }), note };
    case "features_changed":
      return { sentence: e.target.type === "tenant" ? t("audit.featuresTenant", v) : t("audit.actions.features_changed", v), note };
    case "tenant_renamed":
      return { sentence: t("audit.actions.tenant_renamed", { ...v, from: text(d.from) ?? "—", to: text(d.to) ?? "—" }), note };
    case "support_access_requested":
      return { sentence: t("audit.actions.support_access_requested", { ...v, hours: text(d.hours) ?? "—" }), note };
    case "support_access_closed":
      // Opened in the log but never saved on the server (P-52b): it was not open, so it was not closed either.
      return { sentence: d.not_opened === true ? t("audit.notOpened", v) : t("audit.actions.support_access_closed", v), note };
    case "apartment_simulated_changed":
      // Marked simulated or real by the platform (D-97); also when a relink to or from mock:// changes it.
      return { sentence: d.to === true ? t("audit.simulatedOn", v) : d.to === false ? t("audit.simulatedOff", v) : t("audit.actions.apartment_simulated_changed", v), note };
    case "energy_price_changed": {
      // Price of energy (P-52): set, changed, or removed (for an apartment: back to the organization's).
      const where = e.target.type === "tenant" ? t("audit.whereTenant", v) : t("audit.whereApartment", v);
      const from = typeof d.from === "number" ? fmtPrice(d.from) : null;
      const to = typeof d.to === "number" ? fmtPrice(d.to) : null;
      if (to === null) return { sentence: e.target.type === "apartment" ? t("audit.priceAptRemoved", v) : t("audit.priceRemoved", { ...v, where }), note };
      if (from === null) return { sentence: t("audit.priceSet", { ...v, where, to }), note };
      return { sentence: t("audit.priceChanged", { ...v, where, from, to }), note };
    }
    case "rules_changed": {
      // Rules changed on the assistant's proposal or copied from another apartment (D-151), with the values that
      // changed; the text the manager wrote is never saved. An unknown or missing source: the plain sentence.
      const from = d.from_apartment && typeof d.from_apartment === "object" ? (d.from_apartment as Record<string, unknown>) : null;
      const base =
        d.source === "assistant" ? t("audit.rulesByAssistant", v)
        : d.source === "copy" ? t("audit.rulesCopied", { ...v, from: text(from?.name) ?? text(from?.id) ?? "—" })
        : t("audit.actions.rules_changed", v);
      const changes = Array.isArray(d.changes) ? d.changes.filter((c) => c && typeof c === "object").map((c) => describeChange(c as Record<string, unknown>)) : [];
      return { sentence: changes.length ? t("audit.rulesChanges", { sentence: base, changes: changes.join("; ") }) : base, note };
    }
    case "support_access_opened":
      return { sentence: t("audit.actions.support_access_opened", { ...v, until: fmtDateTime(text(d.expires_at)) }), note };
    default:
      return { sentence: t(`audit.actions.${e.action}`, v), note };
  }
}
