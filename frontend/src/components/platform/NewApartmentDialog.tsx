import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Clock, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { platformApi, type Creazione, type PlatformApartment } from "@/api/platform";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Dialog, DialogContent, DialogDescription, DialogTitle, Input, Label } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { freeFromText, newIdProblem, rateLimitOf } from "@/lib/apartmentCreation";
import { cn, newCorrelationId } from "@/lib/utils";
import { CapacityLine } from "./CapacityLine";

const NAME_MAX = 80;
const DEFAULT_LIMIT = 5;

export const tenantKey = (tenantId: string) => ["platform", "tenant", tenantId];

type Limit = { limite: number; usate: number | null; riprova_dal: string | null; reached: boolean };
type BoxError = { text: string; requestId: string | null };

/** The «ID richiesta» of a refusal: the order's op_id when the server sent one (502), else the call's correlation id. */
function requestIdOf(err: ApiError, correlationId: string): string {
  const op = err.details?.op as { op_id?: unknown } | undefined;
  return typeof op?.op_id === "string" ? op.op_id : err.correlationId ?? correlationId;
}

export function FormField({ id, label, hint, problem, problemTestId, children }: { id: string; label: string; hint?: string; problem?: string | null; problemTestId?: string; children: ReactNode }) {
  return (
    <div className="field-cell">
      <Label htmlFor={id}>{label}</Label>
      <div className="space-y-1">
        {children}
        {problem ? (
          <p className="text-xs font-medium text-negative-fg" role="alert" data-testid={problemTestId}>{problem}</p>
        ) : (
          hint && <p className="text-xs text-muted-foreground">{hint}</p>
        )}
      </div>
    </div>
  );
}

/** The box with the limit (§2.2): always in sight above the buttons; yellow, with the hour, once it is reached. */
function LimitBox({ limit }: { limit: Limit }) {
  let text: string;
  if (!limit.reached) text = limit.usate === null ? t("platform.creation.limitInfoPlain", { limit: limit.limite }) : t("platform.creation.limitInfo", { limit: limit.limite, used: limit.usate });
  else if (limit.riprova_dal) text = t("platform.creation.limitReached", { limit: limit.limite, when: freeFromText(limit.riprova_dal) });
  else text = t("platform.creation.limitReachedNoTime", { limit: limit.limite });
  return (
    <div
      role="status"
      data-testid="new-apt-limit"
      data-reached={limit.reached}
      className={cn("flex items-start gap-2 rounded-xl border px-3 py-2.5 text-sm", limit.reached ? "border-warning-border bg-warning-bg text-warning-fg" : "border-border/80 bg-secondary/60 text-foreground")}
    >
      {limit.reached ? <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden /> : <Clock className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />}
      <span>{text}</span>
    </div>
  );
}

/**
 * «Nuovo appartamento in ‹organizzazione›» (A2, docs/proposta-a2-sito.md §2, §6.1): the platform manager writes id,
 * name, time zone and the optional Italianway code; the server chooses address and port and starts the creation. Every
 * refusal stays inside the form with what was written: under its field, in the limit box, or in a red box.
 */
export function NewApartmentDialog({ tenantId, tenantName, onClose, onCreated }: {
  tenantId: string;
  tenantName: string;
  onClose: () => void;
  onCreated: (res: { apartment: PlatformApartment; creazione: Creazione }) => void;
}) {
  const prod = useAuth().me?.env.app_env === "prod";
  // the count of the last hour, read again at every opening
  const q = useQuery({ queryKey: tenantKey(tenantId), queryFn: () => platformApi.tenant(tenantId), staleTime: 0, refetchOnMount: "always" });
  const [f, setF] = useState({ apartment_id: "", name: "", timezone: "Europe/Rome", italianway_id: "" });
  const [idError, setIdError] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);
  const [tzError, setTzError] = useState<string | null>(null);
  const [iwError, setIwError] = useState<string | null>(null);
  const [boxError, setBoxError] = useState<BoxError | null>(null);
  const [refused, setRefused] = useState<{ limite: number; riprova_dal: string | null } | null>(null);
  const [saving, setSaving] = useState(false);

  const quota = q.data?.creazioni_ultima_ora;
  const limit: Limit = refused
    ? { limite: refused.limite, usate: refused.limite, riprova_dal: refused.riprova_dal, reached: true }
    : quota
      ? { limite: quota.limite, usate: quota.usate, riprova_dal: quota.libera_dal, reached: quota.usate >= quota.limite }
      : { limite: DEFAULT_LIMIT, usate: null, riprova_dal: null, reached: false };

  const typed = newIdProblem(f.apartment_id);
  const idProblem = idError ?? (typed === "invalid" ? t("platform.creation.idInvalid") : null);
  const ready = !typed && f.name.trim().length > 0 && !limit.reached;

  const save = async () => {
    const correlationId = newCorrelationId();
    const body = { apartment_id: f.apartment_id.trim(), name: f.name.trim(), timezone: f.timezone.trim() || "Europe/Rome", italianway_id: f.italianway_id.trim() || null };
    setSaving(true);
    setBoxError(null);
    try {
      const res = await platformApi.createNew(tenantId, body, correlationId);
      toast.success(t("platform.creation.started", { name: body.name }));
      onCreated(res);
      onClose();
    } catch (err) {
      const limited = rateLimitOf(err);
      if (limited) {
        setRefused(limited);
        void q.refetch();
      } else if (err instanceof ApiError) {
        if (err.code === "invalid_apartment_id") setIdError(t("platform.creation.idInvalid"));
        else if (err.code === "already_exists") setIdError(t("platform.creation.idTaken"));
        else if (err.code === "external_id_in_use") setIwError(err.message);
        else if (err.code === "invalid_name") setNameError(err.message);
        else if (err.code === "invalid_timezone") setTzError(err.message);
        else if (err.code === "no_free_port") setBoxError({ text: t("platform.creation.noFreePort"), requestId: null });
        else if (err.code === "secret_conflict") setBoxError({ text: t("platform.creation.secretConflict"), requestId: requestIdOf(err, correlationId) });
        else if (err.code === "agent_not_configured" && prod) setBoxError({ text: t("platform.creation.notInProd"), requestId: null });
        else setBoxError({ text: err.message, requestId: requestIdOf(err, correlationId) });
      } else {
        setBoxError({ text: t("errors.generic"), requestId: correlationId });
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl" data-testid="new-apt-dialog">
        <DialogTitle>{t("platform.creation.formTitle", { name: tenantName })}</DialogTitle>
        <DialogDescription>{t("platform.creation.formHint")}</DialogDescription>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <FormField id="apartment_id" label={t("admin.apartments.id")} hint={t("platform.creation.idHint")} problem={idProblem} problemTestId="new-apt-id-problem">
            <Input
              id="apartment_id"
              value={f.apartment_id}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={Boolean(idProblem)}
              placeholder={t("platform.creation.idPlaceholder")}
              onChange={(e) => {
                setIdError(null);
                setF({ ...f, apartment_id: e.target.value });
              }}
              data-testid="apt-form-apartment_id"
            />
          </FormField>
          <FormField id="name" label={t("admin.apartments.name")} problem={nameError} problemTestId="new-apt-name-problem">
            <Input id="name" value={f.name} maxLength={NAME_MAX} onChange={(e) => {
              setNameError(null);
              setF({ ...f, name: e.target.value });
            }} data-testid="apt-form-name" />
          </FormField>
          <FormField id="timezone" label={t("admin.apartments.timezone")} hint={t("admin.apartments.timezoneInitial")} problem={tzError} problemTestId="new-apt-timezone-problem">
            <Input id="timezone" value={f.timezone} onChange={(e) => {
              setTzError(null);
              setF({ ...f, timezone: e.target.value });
            }} data-testid="apt-form-timezone" />
          </FormField>
          <FormField id="italianway_id" label={t("admin.apartments.italianway")} hint={t("platform.creation.italianwayHint")} problem={iwError} problemTestId="new-apt-italianway-problem">
            <Input id="italianway_id" value={f.italianway_id} onChange={(e) => {
              setIwError(null);
              setF({ ...f, italianway_id: e.target.value });
            }} data-testid="apt-form-italianway_id" />
          </FormField>
        </div>
        <div className="mt-4 space-y-3">
          <LimitBox limit={limit} />
          {/* A7: the free places of the VM; it informs only, «Crea» does not depend on it (answer 1201) */}
          <CapacityLine />
          {boxError && (
            <div role="alert" className="space-y-1 rounded-xl border border-negative-border bg-negative-bg px-3 py-2.5 text-sm text-negative-fg" data-testid="new-apt-error">
              <p>{boxError.text}</p>
              {boxError.requestId && (
                <p className="flex flex-wrap items-center gap-1.5 text-xs">
                  {t("credentials.requestId")} <CopyableId id={boxError.requestId} testId="new-apt-error-id" label={t("credentials.requestId")} />
                </p>
              )}
            </div>
          )}
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={() => void save()} disabled={saving || !ready} data-testid="new-apt-save">{t("platform.creation.create")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
