import type { AuditPage } from "@/lib/auditLog";
import { AUDIT_PAGE, type EmailStatus, type VerifyResult, type WebhookLog } from "./admin";
import type { SupportAccess } from "./types";
import { bffFetch, SLOW_CALL_TIMEOUT_MS } from "./bff";

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
  /** A2 (docs/proposta-a2.md §2.2, n. 22): creations stopped half-way and creations on their way; absent = 0. */
  appartamenti_non_creati?: number;
  appartamenti_in_preparazione?: number;
}

/** One organization read alone (GET /app/platform/tenants/{id}): the list's row plus the count of the last hour. */
export type PlatformTenantDetail = PlatformTenant & {
  /** A2 (n. 20): creations started in the last 60 minutes; libera_dal (UTC) only when usate has reached limite. */
  creazioni_ultima_ora?: { usate: number; limite: number; libera_dal: string | null };
};

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
  /** A2 (n. 23): the creation from the app; null (or absent) for an apartment connected by hand (dev, lab-01, demos). */
  creazione?: Creazione | null;
  /** A6 (bff/API.md «Eliminazione di un appartamento»): when and by whom it was disabled, whoever did it (one state for
   *  «Disattiva» and the admin's «Attivo»); null if active, or disabled before A6. */
  disattivato_at?: string | null;
  disattivato_da?: { ruolo: "gestore" | "amministratore"; nome: string | null } | null;
  /** From when «Elimina» is allowed (disattivato_at + 7 days, computed by the server); null: not possible now. */
  eliminabile_dal?: string | null;
  /** How «Elimina» works: app = engine, keys and data; a_mano / dimostrativo = only the record; dev = never. */
  origine?: Origine;
  /** null until someone presses «Elimina»; while it is there the row is the deletion's. */
  eliminazione?: Eliminazione | null;
}

export type Origine = "app" | "a_mano" | "dimostrativo" | "dev";
export type EliminazionePasso = "motore" | "segreti" | "database";

/** A6: the deletion of an apartment (docs/proposta-a6.md §2). eliminato comes only in the answer that closes it. */
export interface Eliminazione {
  stato: "in_corso" | "non_riuscita" | "eliminato";
  passo: EliminazionePasso;
  /** Why it stopped, only with non_riuscita; messaggio is the server's sentence. */
  codice: string | null;
  messaggio: string | null;
  /** The last order to the agent; op_id is the «ID richiesta». */
  op: { op_id: string; operazione?: string; stato: string; codice: string | null; messaggio: string | null } | null;
  version: number;
  iniziata_at: string;
  updated_at: string;
  /** Visible name, never the email. */
  updated_by: string | null;
}

export type CreazioneStato = "in_preparazione" | "pronto" | "non_creato" | "annullamento_in_corso" | "annullato";
export type CreazionePasso = "riserva" | "segreti" | "capienza" | "motore" | "collegamento";

/** The creation of an apartment from the app (docs/proposta-a2.md §2.1). */
export interface Creazione {
  stato: CreazioneStato;
  /** The last step reached: in progress while in_preparazione, the one that failed when non_creato. */
  passo: CreazionePasso;
  version: number;
  porta: number | null;
  /** The last order to the agent; op_id is the «ID richiesta». */
  op: { op_id: string; operazione?: string; stato: string; codice: string | null; messaggio: string } | null;
  /** Why it stopped, only with non_creato (o1 cb3ee25): the codes of §6.3 and the server's own, which may have no order
   *  behind them (segreti_non_creati, secret_conflict, collegamento_fallito, chiavi_non_distrutte, non_inviato,
   *  tempo_scaduto). messaggio is the server's sentence, the fallback for a code the site does not know. */
  codice?: string | null;
  messaggio?: string | null;
  /** What exists already (id, porta, segreti, motore, broker). */
  fatti: string[];
  updated_at: string;
  /** Visible name, never the email. */
  updated_by: string | null;
}

/** «Nuovo appartamento» (A2): the server chooses address and port. */
export interface NewCreatedApartment {
  apartment_id: string;
  name: string;
  timezone: string;
  italianway_id?: string | null;
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
  /** One organization, with the creations of the last hour (A2, before opening «Nuovo appartamento»). */
  tenant: (tenantId: string) => bffFetch<PlatformTenantDetail>(`/app/platform/tenants/${enc(tenantId)}`),
  /** One call: the BFF checks name and email first, then creates organization and invitation, then sends the email. */
  createTenant: (body: { name: string; admin_email: string; admin_display_name?: string }, correlationId: string) =>
    bffFetch<CreatedTenant>("/app/platform/tenants", { method: "POST", body, correlationId, timeoutMs: SLOW_CALL_TIMEOUT_MS }),
  renameTenant: (tenantId: string, name: string, correlationId: string) =>
    bffFetch<PlatformTenant>(`/app/platform/tenants/${enc(tenantId)}`, { method: "PATCH", body: { name }, correlationId }),
  /** Resends the first administrator's invitation: answers the row + email_status; 409 already_active once signed in. */
  resendInvite: (tenantId: string, correlationId: string) =>
    bffFetch<CreatedTenant>(`/app/platform/tenants/${enc(tenantId)}/invite`, { method: "POST", correlationId, timeoutMs: SLOW_CALL_TIMEOUT_MS }),
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
  /** A2: creates the apartment and its home automation system on the VM (staging only until the second VM). 202; 429
   *  rate_limited with details {limite, riprova_dal}; 503 agent_not_configured; 502 agent_publish_failed. */
  createNew: (tenantId: string, body: NewCreatedApartment, correlationId: string) =>
    bffFetch<{ apartment: PlatformApartment; creazione: Creazione }>(`${apts(tenantId)}/nuovo`, { method: "POST", body, correlationId }),
  /** 404 once the creation has been cancelled: the apartment no longer exists. */
  creation: (tenantId: string, aptId: string) => bffFetch<{ creazione: Creazione }>(`${apts(tenantId)}/${enc(aptId)}/creazione`),
  /** Only from non_creato; 409 version_changed or invalid_state otherwise. Not counted in the hourly limit. */
  retryCreation: (tenantId: string, aptId: string, version: number, correlationId: string) =>
    bffFetch<{ creazione: Creazione }>(`${apts(tenantId)}/${enc(aptId)}/creazione/riprova`, { method: "POST", body: { version }, correlationId }),
  /** Removes what was prepared; the apartment stays as annullamento_in_corso until the agent's outcome, then disappears.
   *  {creazione: {stato: "annullato"}} at once when nothing had been sent to the VM. */
  cancelCreation: (tenantId: string, aptId: string, version: number, correlationId: string) =>
    bffFetch<{ creazione: Pick<Creazione, "stato"> & Partial<Creazione> }>(`${apts(tenantId)}/${enc(aptId)}/creazione/annulla`, { method: "POST", body: { version }, correlationId }),
  /** Connection and Italianway code (D-66, D-72); name and enabled stay with the organization admin. Absent = no
   *  change; italianway_id null (or "") = remove the code. */
  patchConnection: (tenantId: string, aptId: string, body: { instance_url?: string; port?: number | null; italianway_id?: string | null; simulated?: boolean }, correlationId: string) =>
    bffFetch<PlatformApartment>(`${apts(tenantId)}/${enc(aptId)}`, { method: "PATCH", body, correlationId }),
  verifyApartment: (tenantId: string, aptId: string, correlationId: string) =>
    bffFetch<VerifyResult>(`${apts(tenantId)}/${enc(aptId)}/verify`, { method: "POST", correlationId, timeoutMs: SLOW_CALL_TIMEOUT_MS }),
  /** A6: «Disattiva» (the same state as the admin's «Attivo»; the 7 days start here) and «Riattiva». The row back. */
  disable: (tenantId: string, aptId: string, correlationId: string) =>
    bffFetch<PlatformApartment>(`${apts(tenantId)}/${enc(aptId)}/disattiva`, { method: "POST", correlationId }),
  reenable: (tenantId: string, aptId: string, correlationId: string) =>
    bffFetch<PlatformApartment>(`${apts(tenantId)}/${enc(aptId)}/riattiva`, { method: "POST", correlationId }),
  /** A6 «Elimina», only the platform for now (answer 1210, point 1), with the name as written: the server compares it
   *  again. 202 in_corso for an apartment created by the app; 200 eliminato for one connected by hand or a demo. The
   *  route of before answers 409 use_elimina. */
  deleteApartment: (tenantId: string, aptId: string, nome: string, correlationId: string) =>
    bffFetch<{ eliminazione: Eliminazione }>(`${apts(tenantId)}/${enc(aptId)}/elimina`, { method: "POST", body: { nome }, correlationId }),
  /** Takes a stopped deletion up again from its step; only with non_riuscita. */
  retryDeletion: (tenantId: string, aptId: string, version: number, correlationId: string) =>
    bffFetch<{ eliminazione: Eliminazione }>(`${apts(tenantId)}/${enc(aptId)}/eliminazione/riprova`, { method: "POST", body: { version }, correlationId }),
  /** «Prova l'agente» (strumento A, A1; o1 448a71a, bff/API.md): an order «stato» to the agent on the VM, for a staging
   *  apartment (lab-…, test-…) or dev. 202 with the operation; 422 invalid_apartment; 503 agent_not_configured;
   *  502 agent_publish_failed. */
  agentTest: (apartmentId: string, correlationId: string) =>
    bffFetch<AgentOp>("/app/platform/agent/prova", { method: "POST", body: { apartment_id: apartmentId }, correlationId }),
  /** The operation, to read again while it is «inviato»; after 20 minutes the server gives it «fallito/tempo_scaduto». */
  agentOp: (opId: string) => bffFetch<AgentOp>(`/app/platform/agent/ops/${enc(opId)}`),
  /** A7: the last reading of the VM's capacity the server keeps; no order to the agent. 503 agent_not_configured where
   *  the creation is not available. */
  capacity: () => bffFetch<CapienzaView>("/app/platform/capienza"),
  /** A7 «Aggiorna»: a new capienza order; 202 with aggiornamento «inviato», 429 rate_limited (details.riprova_dal) within
   *  30 s of the last one, 502 agent_publish_failed (details.op). */
  refreshCapacity: (correlationId: string) => bffFetch<CapienzaView>("/app/platform/capienza/aggiorna", { method: "POST", correlationId }),
};

/** A7, the last successful reading of the VM's capacity (bff/API.md «Capienza della VM»); letta_at in UTC. */
export interface Capienza {
  ambiente: string;
  letta_at: string;
  /** More than 10 minutes old when the server answered. */
  vecchia: boolean;
  posti_liberi: number;
  /** Why the places are 0: staging_pieno, capienza_insufficiente (null with places). */
  motivo: string | null;
  // for the support only, not shown (answer 1203)
  motori_ambiente: number | null;
  massimo_motori: number | null;
  mem_available_mb: number | null;
  tetto_nuovo_mb: number | null;
  somma_tetti_mb: number | null;
  budget_mb: number | null;
}

/** The last «Aggiorna» order. */
export interface CapienzaAggiornamento {
  op_id: string;
  stato: "inviato" | "riuscito" | "rifiutato" | "fallito";
  codice: string | null;
  messaggio: string | null;
  creato_at: string;
}

export interface CapienzaView {
  /** null without any reading: no number is invented. */
  capienza: Capienza | null;
  aggiornamento: CapienzaAggiornamento | null;
  /** Until when «Aggiorna» stays off (one every 30 s per environment), UTC; null when it is free. */
  aggiornabile_dal: string | null;
}

/** An order to the agent on the VM and its outcome (bff/agent.py describe). */
export interface AgentOp {
  op_id: string;
  operazione: string;
  apartment_id: string;
  seq: number;
  stato: "inviato" | "riuscito" | "rifiutato" | "scartato" | "fallito";
  codice: string | null;
  /** The Italian sentence of the code, ready to show. */
  messaggio: string;
  /** Only when riuscito, for «stato»: health 200 = engine sound, 0 = not answering. */
  dati: { health?: number; stato?: string; connector?: "up" | "down"; immagine?: string } | null;
  creato_at: string;
  finito_at: string | null;
}
