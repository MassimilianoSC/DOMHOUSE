import type { AuditPage } from "@/lib/auditLog";
import { bffFetch } from "./bff";
import type { AppFeature } from "./types";

/** Entries per page of the «Registro attività» (P-47). */
export const AUDIT_PAGE = 50;

export type Role = "admin" | "operator" | "viewer";

/** Apartments an operator or viewer sees (P-18, D-43): "all" or a list of ids ([] = none). Always present in answers. */
export type ApartmentScope = "all" | string[];

export interface AdminUser {
  uid: string;
  email: string;
  display_name: string;
  role: Role;
  pending: boolean;
  push_tokens: number;
  apartment_ids: ApartmentScope;
}

/** Outcome of the invitation email sent by the BFF (absent on older BFF versions). */
export type EmailStatus = "sent" | "not_configured" | "failed";
export type InviteResult = AdminUser & { email_status?: EmailStatus };

export interface AdminApartment {
  apartment_id: string;
  name: string;
  address: string;
  timezone: string;
  instance_url: string;
  port: number | null;
  enabled: boolean;
  italianway_id: string | null;
  enabled_features: string[] | null;
  /** Simulated instance (D-97): set by the platform; with mock:// it is always true. */
  simulated?: boolean;
  /** €/kWh for this apartment only (P-52, D-92); null = the organization's. */
  energy_price_eur_kwh?: number | null;
  /** Outcome of the last "Verifica connessione" (D-66); absent from a BFF older than D-64. Never sent back. */
  last_check?: { ok: boolean; checked_at: string; error: string | null } | null;
}

export interface AdminTenant {
  tenant_id: string;
  name: string;
  enabled_features: string[] | null;
  all_features: AppFeature[];
  /** €/kWh of the organization, for the amount in the Excel reports (P-52, D-92); null = not set. */
  energy_price_eur_kwh?: number | null;
}

/**
 * "Verifica connessione". The organization admin gets the full answer; the platform only {apartment_id, ok, error,
 * contract_version} (L4 of the Fable review: never the engine's /health body), hence the optional fields.
 */
export interface VerifyResult {
  apartment_id: string;
  ok: boolean;
  error: string | null;
  contract_version: string | null;
  reachable?: boolean;
  features?: string[];
  health?: { status_code: number; body: Record<string, unknown> | null } | null;
  version?: { status_code: number; body: Record<string, unknown> | null } | null;
}

export type ApartmentInput = Omit<AdminApartment, "last_check">;

export interface WebhookLog {
  log_id: string;
  source: string;
  received_at: string;
  tenant_id: string | null;
  apartment_id: string | null;
  signature_ok: boolean;
  status_code: number;
  outcome: string;
  event_id: string | null;
  booking_id: string | null;
  correlation_id: string;
  forward_status: number | null;
  forward_attempts: number;
  /** With personal data obscured ("[oscurato]") by the BFF (P-51, D-90): shown as it is, in the technical details. */
  raw_body: string;
  /** Read by the BFF from the body (P-51, D-90); absent from an older BFF, null when the body could not be read. */
  event_type?: string | null;
  external_id?: string | null;
  checkin_at?: string | null;
  checkout_at?: string | null;
  guests?: number | null;
}

export const adminApi = {
  /** The admin ends an assistance access on their organization (P-50, D-86). */
  closeSupport: (accessId: string, correlationId: string) =>
    bffFetch<void>(`/app/admin/support-access/${encodeURIComponent(accessId)}`, { method: "DELETE", correlationId }),
  /** «Registro attività» of the admin's organization (P-47), newest first; before = the `next` of the previous page. */
  audit: (before?: string) => bffFetch<AuditPage>("/app/admin/audit", { query: { limit: AUDIT_PAGE, before } }),
  webhookLogs: () => bffFetch<WebhookLog[]>("/app/admin/webhook-logs"),
  users: () => bffFetch<AdminUser[]>("/app/admin/users"),
  /** apartment_ids omitted = "all" (and always omitted for admins: a list on an admin is a 422). */
  invite: (body: { email: string; role: Role; display_name: string; apartment_ids?: ApartmentScope }, correlationId: string) =>
    bffFetch<InviteResult>("/app/admin/users", { method: "POST", body, correlationId }),
  resendInvite: (uid: string, correlationId: string) =>
    bffFetch<InviteResult>(`/app/admin/users/${encodeURIComponent(uid)}/invite`, { method: "POST", correlationId }),
  /** apartment_ids omitted = no change; "all" = back to every apartment; a list = only those ([] = none). */
  patchUser: (uid: string, body: Partial<Pick<AdminUser, "role" | "display_name" | "apartment_ids">>, correlationId: string) =>
    bffFetch<AdminUser>(`/app/admin/users/${encodeURIComponent(uid)}`, { method: "PATCH", body, correlationId }),
  deleteUser: (uid: string, correlationId: string) => bffFetch<void>(`/app/admin/users/${encodeURIComponent(uid)}`, { method: "DELETE", correlationId }),
  apartments: () => bffFetch<AdminApartment[]>("/app/admin/apartments"),
  /** The Italianway code is the platform's (D-72): never sent by the admin (a new code is a 403 platform_only). */
  patchApartment: (id: string, body: Partial<ApartmentInput> & { clear_features?: boolean }, correlationId: string) =>
    bffFetch<AdminApartment>(`/app/admin/apartments/${encodeURIComponent(id)}`, { method: "PATCH", body, correlationId }),
  verify: (id: string, correlationId: string) => bffFetch<VerifyResult>(`/app/admin/apartments/${encodeURIComponent(id)}/verify`, { method: "POST", correlationId }),
  tenant: () => bffFetch<AdminTenant>("/app/admin/tenant"),
  /** energy_price_eur_kwh: 0-10 with at most 4 decimals, null = none (422 invalid_price). */
  patchTenant: (body: { name?: string; enabled_features?: string[] | null; clear_features?: boolean; energy_price_eur_kwh?: number | null }, correlationId: string) =>
    bffFetch<AdminTenant>("/app/admin/tenant", { method: "PATCH", body, correlationId }),
};

export interface SimBookingInput {
  event_id: string;
  type: "booking_created" | "booking_changed" | "booking_cancelled" | "checkin" | "checkout";
  booking_id: string;
  checkin_at: string;
  checkout_at: string;
  guests: number | null;
  ts: string;
}

export const simulatorApi = (aptId: string) => ({
  state: (body: Record<string, unknown>, correlationId: string) =>
    bffFetch<void>(`/app/apartments/${encodeURIComponent(aptId)}/instance/_test/state`, { method: "POST", body, correlationId }),
  /** Back to the initial state (D-97): only with the built-in mock; 409 reset_not_available on a real engine. */
  reset: (correlationId: string) => bffFetch<void>(`/app/apartments/${encodeURIComponent(aptId)}/simulator/reset`, { method: "POST", correlationId }),
  booking: (body: SimBookingInput, correlationId: string) =>
    bffFetch<{ event_id: string; accepted: boolean; duplicate: boolean; schedule_ids: string[]; correlation_id: string }>(
      `/app/apartments/${encodeURIComponent(aptId)}/simulator/booking`,
      { method: "POST", body, correlationId },
    ),
});

export interface NotificationPrefs {
  approvals: boolean;
  offline: boolean;
  decisions: boolean;
  /** Bookings that change the apartment's programme (D-121, D-123); on by default. Always sent with the others. */
  bookings: boolean;
}

export const pushApi = {
  status: () => bffFetch<{ fcm_enabled: boolean; tokens: number; prefs: NotificationPrefs }>("/app/push/status"),
  subscribe: (token: string) => bffFetch<{ subscribed: boolean; tokens: number }>("/app/push/subscribe", { method: "POST", body: { token } }),
  unsubscribe: (token: string) => bffFetch<{ subscribed: boolean }>("/app/push/subscribe", { method: "DELETE", body: { token } }),
  setPrefs: (prefs: NotificationPrefs) => bffFetch<NotificationPrefs>("/app/me/notification-prefs", { method: "PUT", body: prefs }),
};
