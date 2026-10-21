import type { AuditPage } from "@/lib/auditLog";
import { AUDIT_PAGE, type EmailStatus, type VerifyResult, type WebhookLog } from "./admin";
import type { SupportAccess } from "./types";
import { bffFetch } from "./bff";

// Platform area (P-36, API shapes D-61a and D-66): organizations, platform managers and the technical record of the
// apartments (identifier, name, connection to the engine). Only for users with user.platform_manager; everyone else
// gets 403. A platform manager never sees how an organization uses the app (users, devices, decisions, consumption).

export interface PlatformTenant {
  tenant_id: string;
  name: string;
  created_at: string;
  /** null when no first administrator was invited; pending = invited, never signed in yet. */
  first_admin: { email: string; pending: boolean } | null;
  /** Suspended by the platform (P-50, D-85): the app stops for its users, bookings still reach the engine. */
  suspended?: boolean;
  suspended_at?: string | null;
  suspended_reason?: string | null;
  /** The active assistance access (P-50, D-86): the manager's own when there is one (mine), else someone else's. */
  support_access?: (SupportAccess & { mine: boolean }) | null;
}

/** Answer of the creation: the organization plus the outcome of the invitation email. */
export type CreatedTenant = PlatformTenant & { email_status?: EmailStatus };

export interface PlatformManager {
  email: string;
  display_name: string;
  /** Has already signed in at least once with that (verified) email. */
  active: boolean;
}

/**
 * An apartment as the platform sees it (D-66): only the technical record. Name and enabled are the organization
 * admin's (D-64); the platform sets them at creation and then changes only the connection to the engine.
 */
export interface PlatformApartment {
  apartment_id: string;
  name: string;
  instance_url: string;
  port: number | null;
  enabled: boolean;
  timezone: string;
  /** Italianway code: set only by the platform (D-72); it decides where real bookings go. */
  italianway_id: string | null;
  /** Simulated instance (D-97): always true with mock://; a real engine in simulated mode may be marked too. */
  simulated?: boolean;
  /** Outcome of the last "Verifica connessione", whoever ran it; null if never verified. */
  last_check: { ok: boolean; checked_at: string; error: string | null } | null;
}

export interface NewPlatformApartment {
  apartment_id: string;
  name: string;
  instance_url: string;
  port?: number | null;
  timezone?: string;
  enabled?: boolean;
  /** Absent or null = no code; 409 external_id_in_use if another apartment has it. */
  italianway_id?: string | null;
  /** Simulated instance (D-97); forced true by the BFF with mock://. */
  simulated?: boolean;
}

/** Value of the audit scope for the platform's own log (P-47). */
export const PLATFORM_SCOPE = "platform";

const enc = encodeURIComponent;
const apts = (tenantId: string) => `/app/platform/tenants/${enc(tenantId)}/apartments`;

export const platformApi = {
  /** «Registro attività» (P-47) of one organization, or "platform" for the actions without one (managers added and removed). */
  audit: (scope: string, before?: string) =>
    bffFetch<AuditPage>("/app/platform/audit", { query: { ...(scope === PLATFORM_SCOPE ? { scope: PLATFORM_SCOPE } : { tenant_id: scope }), limit: AUDIT_PAGE, before } }),
  tenants: () => bffFetch<PlatformTenant[]>("/app/platform/tenants"),
  /** One call: the BFF checks name and email first, then creates organization and invitation, then sends the email. */
  createTenant: (body: { name: string; admin_email: string; admin_display_name?: string }, correlationId: string) =>
    bffFetch<CreatedTenant>("/app/platform/tenants", { method: "POST", body, correlationId }),
  renameTenant: (tenantId: string, name: string, correlationId: string) =>
    bffFetch<PlatformTenant>(`/app/platform/tenants/${enc(tenantId)}`, { method: "PATCH", body: { name }, correlationId }),
  /** Resends the first administrator's invitation: answers the row + email_status; 409 already_active once signed in. */
  resendInvite: (tenantId: string, correlationId: string) =>
    bffFetch<CreatedTenant>(`/app/platform/tenants/${enc(tenantId)}/invite`, { method: "POST", correlationId }),
  /** reason 1–500 characters (422 invalid_reason); 409 already_suspended. Answers the row. */
  suspendTenant: (tenantId: string, reason: string, correlationId: string) =>
    bffFetch<PlatformTenant>(`/app/platform/tenants/${enc(tenantId)}/suspend`, { method: "POST", body: { reason }, correlationId }),
  /** 409 not_suspended. Answers the row. */
  reactivateTenant: (tenantId: string, correlationId: string) =>
    bffFetch<PlatformTenant>(`/app/platform/tenants/${enc(tenantId)}/reactivate`, { method: "POST", correlationId }),
  /** hours 1-24 (422 invalid_hours), reason 1-500 (422 invalid_reason); 409 tenant_suspended, 409 support_active. */
  openSupport: (tenantId: string, body: { hours: number; reason: string }, correlationId: string) =>
    bffFetch<SupportAccess>(`/app/platform/tenants/${enc(tenantId)}/support-access`, { method: "POST", body, correlationId }),
  closeSupport: (tenantId: string, accessId: string, correlationId: string) =>
    bffFetch<void>(`/app/platform/tenants/${enc(tenantId)}/support-access/${enc(accessId)}`, { method: "DELETE", correlationId }),
  managers: () => bffFetch<PlatformManager[]>("/app/platform/managers"),
  addManager: (email: string, correlationId: string) => bffFetch<PlatformManager>("/app/platform/managers", { method: "POST", body: { email }, correlationId }),
  /** 409 last_manager: the platform always keeps one manager. The email travels in the body, never in the path, so it
   *  stays out of the server's and the browser's logs (P-71 a). */
  removeManager: (email: string, correlationId: string) => bffFetch<void>("/app/platform/managers/remove", { method: "POST", body: { email }, correlationId }),
  /** Webhook calls not attributed to any organization (no longer visible to organization admins). */
  webhookLogs: () => bffFetch<WebhookLog[]>("/app/platform/webhook-logs"),
  apartments: (tenantId: string) => bffFetch<PlatformApartment[]>(apts(tenantId)),
  /** Id unique on the whole platform (409); 422 for an instance URL that cannot work (D-28). */
  createApartment: (tenantId: string, body: NewPlatformApartment, correlationId: string) =>
    bffFetch<PlatformApartment>(apts(tenantId), { method: "POST", body, correlationId }),
  /** Connection and Italianway code (D-66, D-72); name and enabled stay with the organization admin. Absent = no
   *  change; italianway_id null (or "") = remove the code. */
  patchConnection: (tenantId: string, aptId: string, body: { instance_url?: string; port?: number | null; italianway_id?: string | null; simulated?: boolean }, correlationId: string) =>
    bffFetch<PlatformApartment>(`${apts(tenantId)}/${enc(aptId)}`, { method: "PATCH", body, correlationId }),
  verifyApartment: (tenantId: string, aptId: string, correlationId: string) =>
    bffFetch<VerifyResult>(`${apts(tenantId)}/${enc(aptId)}/verify`, { method: "POST", correlationId }),
  /** Only the platform deletes apartments, in every mode (D-65, D-77). */
  deleteApartment: (tenantId: string, aptId: string, correlationId: string) =>
    bffFetch<void>(`${apts(tenantId)}/${enc(aptId)}`, { method: "DELETE", correlationId }),
};
