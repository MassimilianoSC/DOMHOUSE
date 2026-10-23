import type { Device, ScheduledAction } from "@/api/types";
import { t, tOr } from "@/i18n";
import { fmtNumber } from "./format";

export function deviceLabel(deviceId: string | undefined, devices: Device[]): string {
  return devices.find((d) => d.device_id === deviceId)?.label ?? deviceId ?? "—";
}

/** Human sentence for a ScheduledAction (schedule items, approvals, assistant). */
export function describeAction(a: ScheduledAction, devices: Device[]): string {
  if (a.type === "apartment_mode") return t("action.mode", { mode: t(`mode.${a.mode}`) });
  const name = deviceLabel(a.device_id, devices);
  const sp = a.params?.setpoint;
  if (a.action === "turn_off") return t("action.turnOff", { name });
  if (a.action === "turn_on") return t("action.turnOn", { name });
  if (typeof sp === "number") return t("action.setpoint", { name, value: fmtNumber(sp) });
  return `${a.action ?? ""} ${name}`.trim();
}

/** Decision actor → Italian label: brain · rule:<id> · organ:<name> · user:<email> · assistant · system */
/** Domain of the pseudonyms the BFF sends to the engine instead of emails (D-87); the BFF always rewrites them. */
const PSEUDONYM_DOMAIN = "@pseudo.hqe.it";

export const isPseudonym = (who: string) => who.trim().toLowerCase().endsWith(PSEUDONYM_DOMAIN);

/**
 * A person as the site shows them (P-48, D-87): the email the BFF resolved, or «utente rimosso» for a deleted account
 * (the BFF's "removed"). A pseudonym that reached the site unresolved is never shown raw.
 */
export function personLabel(who: string): string {
  const w = who.trim();
  if (!w || w === "removed" || isPseudonym(w)) return t("common.removedUser");
  return w;
}

export function describeActor(actor: string, ruleLabels: Record<string, string> = {}): { kind: string; label: string } {
  if (isPseudonym(actor) && !actor.startsWith("user:")) return { kind: "user", label: personLabel(actor) };
  const [kind, rest] = actor.includes(":") ? [actor.slice(0, actor.indexOf(":")), actor.slice(actor.indexOf(":") + 1)] : [actor, ""];
  switch (kind) {
    case "rule":
      return { kind, label: t("actor.rule", { name: ruleLabels[rest] ?? rest }) };
    case "user":
      return { kind, label: personLabel(rest) };
    case "organ":
      return { kind, label: t("actor.organ", { name: rest }) };
    case "brain":
    case "assistant":
    case "system":
      return { kind, label: t(`actor.${kind}`) };
    default:
      return { kind: "other", label: actor };
  }
}

/**
 * Every action code the engine writes in a decision (engine/core.py, D-125): its own actions, the commands to devices,
 * the booking events and the answers to approvals. Shown in Italian; a code the site does not know yet shows as it is.
 */
export const DECISION_ACTIONS = [
  "set_mode", "turn_on", "turn_off", "set_climate", "set_heating",
  "hold", "hold_cancel", "hold_expired", "expire", "approve", "reject", "update_device", "update_rules",
  "schedule_create", "schedule_move", "schedule_cancel", "schedule_missed", "schedule_deferred",
  "booking_created", "booking_changed", "booking_cancelled", "checkin", "checkout", "booking_cancel_reset",
  "offline_alert", "mold_warning", "frost_heating_on", "frost_heating_off", "thermostat_sensor",
  "window_rule_suspended", "command_unverified", "connector_down", "connector_up", "auto_regulation_off", "frost_inactive",
  "setpoint_limits_ignored",
] as const;

/** The kind of action of a decision, in Italian («Forzatura scaduta»); its code for one not translated yet. */
/** A value before or after a decision: a mode in Italian («empty» → «casa vuota», D-158), anything else as the
 *  engine writes it. */
const MODE_VALUES = new Set(["comfort", "eco", "empty"]);
export const decisionValue = (v: string | null | undefined): string => (v === null || v === undefined || v === "" ? "—" : MODE_VALUES.has(v) ? t(`mode.${v}`) : v);

export const actionLabel = (code: string): string => (code ? tOr(`decisions.actions.${code}`, code) : code);
