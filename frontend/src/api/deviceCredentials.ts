import { bffFetch } from "./bff";

// A3, device credentials (docs/proposta-a3-server.md §2, §2.1; bff/API.md when o1's routes are there). The password of
// a Shelly on the broker exists only as a hash on the server: it reaches the site once, in the answer of «Registra» or
// «Rigenera», and the site keeps it only in the state of the window that shows it (docs/proposta-a3-sito.md §5). It is
// never in a query cache: these calls are not React Query mutations.

export type CredentialState = "in_attesa" | "pronto" | "cambio_in_corso" | "revoca_in_corso" | "revocato" | "non_applicato";
/** The action waiting for confirmation; «Riprova» does not change it, null when there is none (server §2.1). */
export type PendingAction = "registra" | "rigenera" | "revoca" | null;

export interface CredentialConnection {
  /** null when the environment has no address for the devices (DEVICE_BROKER_ADDRESS empty, today production). */
  server: string | null;
  ssl_ca: string;
  client_id: string;
  user: string;
  topic_prefix: string;
}

/** The last order to the broker; op_id is the «ID richiesta». */
export interface CredentialOp {
  op_id: string;
  stato: string;
  messaggio: string | null;
}

export interface DeviceCredential {
  device_id: string;
  /** The engine's name for the device: null until A4. */
  name: string | null;
  stato: CredentialState;
  version: number;
  updated_at: string;
  updated_by: string | null;
  azione: PendingAction;
  /** Only with A4: the engine's device_id bound to this Shelly id. */
  engine_device_id: string | null;
  op: CredentialOp | null;
  connection: CredentialConnection;
}

/** The answer of «Registra» and «Rigenera»: the only place a password appears. */
export interface CredentialWithPassword {
  credential: DeviceCredential;
  password: string;
}

/** apartment: the organization's admin; platform: the platform manager, staging only, lab-… and test-… (server §2). */
export type CredentialScope = "apartment" | "platform";

const enc = encodeURIComponent;

export function credentialsApi(apartmentId: string, scope: CredentialScope) {
  const base = `${scope === "platform" ? "/app/platform/apartments" : "/app/apartments"}/${enc(apartmentId)}/device-credentials`;
  const action = (deviceId: string, name: "rigenera" | "revoca" | "riprova") => `${base}/${enc(deviceId)}/${name}`;
  return {
    list: () => bffFetch<{ items: DeviceCredential[] }>(base),
    /** 201; also «Registra di nuovo» on a revoked device. */
    register: (deviceId: string, correlationId: string) =>
      bffFetch<CredentialWithPassword>(base, { method: "POST", body: { device_id: deviceId }, correlationId }),
    regenerate: (deviceId: string, version: number, correlationId: string) =>
      bffFetch<CredentialWithPassword>(action(deviceId, "rigenera"), { method: "POST", body: { version }, correlationId }),
    /** 202; 502 agent_publish_failed with details.op when the order could not be sent. */
    revoke: (deviceId: string, version: number, correlationId: string) =>
      bffFetch<{ credential: DeviceCredential }>(action(deviceId, "revoca"), { method: "POST", body: { version }, correlationId }),
    /** 202; sends the full list again, no new password. */
    retry: (deviceId: string, version: number, correlationId: string) =>
      bffFetch<{ credential: DeviceCredential }>(action(deviceId, "riprova"), { method: "POST", body: { version }, correlationId }),
  };
}

export type CredentialsApi = ReturnType<typeof credentialsApi>;
