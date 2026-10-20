import type { components, operations } from "./schema";

export type Schemas = components["schemas"];
export type Apartment = Schemas["Apartment"];
export type ApartmentMode = Schemas["ApartmentMode"];
export type Occupancy = Schemas["Occupancy"];
export type Hold = Schemas["Hold"];
export type Room = Schemas["Room"];
export type Device = Schemas["Device"];
export type Capabilities = Schemas["Capabilities"];
export type Command = Schemas["Command"];
export type CommandStatus = Schemas["CommandStatus"];
export type CommandState = Schemas["CommandState"];
export type CommandReason = Schemas["CommandReason"];
/** The BFF passes on only what the site uses (P-51, D-90): no per-device list, uptime, database or check details. */
export type Health = Omit<Schemas["Health"], "apartment_id" | "uptime_s" | "database" | "devices" | "checked_at">;
export type Version = Schemas["Version"];
export type StreamEnvelope = Schemas["StreamEnvelope"];
export type StreamEventName = StreamEnvelope["event"];
export type EventDeviceState = Schemas["EventDeviceState"];
export type EventDeviceOnline = Schemas["EventDeviceOnline"];
export type EventCommandUpdated = Schemas["EventCommandUpdated"];
export type Approval = Schemas["Approval"];
export type ScheduledAction = Schemas["ScheduledAction"];
export type ScheduleItem = Schemas["ScheduleItem"];
export type Rule = Schemas["Rule"];
export type RuleSet = Schemas["RuleSet"];
export type RulePatch = Schemas["RulePatch"];
export type Decision = Schemas["Decision"];
export type EnergyReport = Schemas["EnergyReport"];
export type AskStatus = Schemas["AskStatus"];
export type ApiErrorBody = Schemas["Error"];

type JsonOf<R> = R extends { content: { "application/json": infer B } } ? B : never;
export type Ok<K extends keyof operations, S extends keyof operations[K]["responses"] = 200 extends keyof operations[K]["responses"] ? 200 : never> =
  JsonOf<operations[K]["responses"][S]>;
export type Body<K extends keyof operations> = operations[K] extends { requestBody: { content: { "application/json": infer B } } } ? B : never;

export type DevicesResponse = Ok<"listDevices">;
export type FeatureName = Version["features"][number];

export const STREAM_EVENTS: StreamEventName[] = [
  "device.state",
  "device.online",
  "command.updated",
  "decision.logged",
  "approval.pending",
  "apartment.changed",
  "instance.health",
];

export const APP_FEATURES = ["apartment", "devices", "commands", "energy", "schedule", "rules", "approvals", "decisions", "ask"] as const;
export type AppFeature = (typeof APP_FEATURES)[number];

export interface ApartmentSummary {
  apartment_id: string;
  name: string;
  address: string;
  timezone: string;
  enabled: boolean;
  online: boolean;
  /** Simulated instance, set by the platform (D-97): admins get the Simulatore, every list shows «Dimostrativo». */
  simulated?: boolean;
  apartment: Apartment | null;
  health: Health | null;
  contract_version: string | null;
  features: AppFeature[];
  pending_approvals: number | null;
  kwh_today: number | null;
}

export type Role = "admin" | "operator" | "viewer";

import type { ApartmentScope } from "./admin";

export interface Me {
  user: {
    uid: string;
    email: string;
    display_name: string;
    role: Role;
    notification_prefs: { approvals: boolean; offline: boolean; decisions: boolean } | null;
    /** Apartments this user sees (P-18, D-43); absent from a BFF older than P-18 = "all". */
    apartment_ids?: ApartmentScope;
    /** Platform role (P-36, D-61a): manages the organizations, separate from admin/operator/viewer. */
    platform_manager?: boolean;
  };
  /** null for a platform manager who belongs to no organization: only Organizzazioni and Impostazioni then. */
  /** suspended (P-50): only a platform manager still gets /app/me for a suspended organization; everyone else a 403. */
  tenant: { tenant_id: string; name: string; enabled_features?: string[] | null; suspended?: boolean } | null;
  /** Present while a platform manager works inside this organization through an assistance access (P-50, D-86). */
  support?: { access_id: string; tenant_id: string; expires_at: string; reason: string } | null;
  /** Assistance accesses open on the organization: filled for admins only, [] otherwise. */
  support_access?: SupportAccess[];
  role: Role | null;
  /** simulator: no longer sent (D-97): the Simulatore follows the apartment's `simulated`, not the environment. */
  env: { app_env: string; auth_mode: string; fcm_enabled: boolean; simulator?: boolean; instance_mode: string };
}

export interface DevUser {
  email: string;
  display_name: string;
  role: Role | null;
}

/** An assistance access (P-50, D-86): HQE inside an organization for 1-24 hours, with an operator's permissions. */
export interface SupportAccess {
  access_id: string;
  tenant_id?: string;
  /** null for both when the person who opened it has since deleted their account («utente rimosso»). */
  operator_email: string | null;
  operator_name: string | null;
  reason: string;
  opened_at?: string;
  expires_at: string;
  closed_at?: string | null;
  status?: "active" | "closed" | "expired";
}
