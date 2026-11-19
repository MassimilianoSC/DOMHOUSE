import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { credentialsApi, type CredentialScope, type CredentialWithPassword, type DeviceCredential } from "@/api/deviceCredentials";
import { CopyableId } from "@/components/ui/CopyableId";
import { t } from "@/i18n";
import { showError } from "@/lib/actions";
import { newCorrelationId } from "@/lib/utils";
import { ConnectionDialog, PasswordDialog, RegenerateDialog, RegisterDialog, RevokeDialog } from "./CredentialDialogs";
import { credentialsKey, CredentialsPanel, type RowRequest } from "./CredentialsPanel";

type Confirm = { kind: "rigenera" | "revoca"; credential: DeviceCredential };

/** The operation of a refused order (502 agent_publish_failed): its op_id is the «ID richiesta» (server §5.3). */
const opIdOf = (err: ApiError): string | null => {
  const op = err.details?.op as { op_id?: unknown } | undefined;
  return typeof op?.op_id === "string" ? op.op_id : null;
};

/**
 * The list of the device credentials and the windows of its actions (A3, docs/proposta-a3-sito.md §2, §4). Each
 * refusal of the server ends with the list read again: a stale page is the usual cause, and the person sees the new
 * state before deciding again. The site never repeats an action by itself.
 */
export function CredentialsWorkspace({ apartmentId, scope }: { apartmentId: string; scope: CredentialScope }) {
  const qc = useQueryClient();
  const api = credentialsApi(apartmentId, scope);
  const [registering, setRegistering] = useState(false);
  const [registerProblem, setRegisterProblem] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [connection, setConnection] = useState<DeviceCredential | null>(null);
  // the password, only here and only while its window is open (§5)
  const [shown, setShown] = useState<CredentialWithPassword | null>(null);
  const [busy, setBusy] = useState(false);
  const refresh = () => void qc.invalidateQueries({ queryKey: credentialsKey(apartmentId, scope) });

  /** Runs an action; undefined on a refusal, after saying what happened (§4). `createsPassword`: Registra, Rigenera. */
  async function run<T>(fn: (correlationId: string) => Promise<T>, createsPassword: boolean): Promise<T | undefined> {
    const correlationId = newCorrelationId();
    setBusy(true);
    try {
      return await fn(correlationId);
    } catch (err) {
      if (err instanceof ApiError && err.code === "version_changed") toast.info(t("credentials.errors.versionChanged"));
      else if (err instanceof ApiError && err.code === "invalid_state") toast.info(t("credentials.errors.invalidState"));
      else if (err instanceof ApiError && err.code === "network" && createsPassword) toast.error(t("credentials.errors.networkPassword"), { duration: 10000 });
      else if (err instanceof ApiError && err.code === "agent_publish_failed" && opIdOf(err)) {
        const opId = opIdOf(err)!;
        toast.error(err.message, {
          description: (
            <span className="flex items-center gap-1.5" data-testid="toast-error-correlation">
              {t("credentials.requestId")} <CopyableId id={opId} testId="toast-correlation-id" label={t("credentials.requestId")} />
            </span>
          ),
          duration: 10000,
        });
      } else showError(err, correlationId);
      throw err;
    } finally {
      setBusy(false);
      refresh();
    }
  }

  const register = async (deviceId: string) => {
    setRegisterProblem(null);
    try {
      const res = await run((c) => api.register(deviceId, c), true);
      setRegistering(false);
      if (res) setShown(res);
    } catch (err) {
      // a code the server refuses stays in the window, under the field; any other refusal closes it
      if (err instanceof ApiError && err.code === "invalid_device_id") setRegisterProblem(err.message);
      else setRegistering(false);
    }
  };

  const onRequest = async ({ kind, credential: c }: RowRequest) => {
    if (kind === "connection") return setConnection(c);
    if (kind === "rigenera" || kind === "revoca") return setConfirm({ kind, credential: c });
    try {
      if (kind === "registra") {
        const res = await run((id) => api.register(c.device_id, id), true);
        if (res) setShown(res);
      } else if (kind === "riprova") {
        await run((id) => api.retry(c.device_id, c.version, id), false);
        toast.success(t("credentials.retrySent"));
      }
    } catch {
      /* already said by run */
    }
  };

  const confirmAction = async () => {
    if (!confirm) return;
    const c = confirm.credential;
    try {
      if (confirm.kind === "rigenera") {
        const res = await run((id) => api.regenerate(c.device_id, c.version, id), true);
        setConfirm(null);
        if (res) setShown(res);
      } else {
        await run((id) => api.revoke(c.device_id, c.version, id), false);
        setConfirm(null);
        toast.success(t("credentials.revokeDialog.sent"));
      }
    } catch {
      setConfirm(null);
    }
  };

  return (
    <>
      <CredentialsPanel
        apartmentId={apartmentId}
        scope={scope}
        onRequest={(r) => void onRequest(r)}
        onRegister={() => {
          setRegisterProblem(null);
          setRegistering(true);
        }}
      />
      {registering && <RegisterDialog busy={busy} serverProblem={registerProblem} onSave={(id) => void register(id)} onClose={() => setRegistering(false)} />}
      {confirm?.kind === "rigenera" && <RegenerateDialog c={confirm.credential} busy={busy} onConfirm={() => void confirmAction()} onClose={() => setConfirm(null)} />}
      {confirm?.kind === "revoca" && <RevokeDialog c={confirm.credential} busy={busy} onConfirm={() => void confirmAction()} onClose={() => setConfirm(null)} />}
      {connection && <ConnectionDialog c={connection} onClose={() => setConnection(null)} />}
      {shown && <PasswordDialog shown={shown} onClose={() => setShown(null)} />}
    </>
  );
}
