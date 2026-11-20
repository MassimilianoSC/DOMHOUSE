import { useState } from "react";
import { Check, Circle, Loader2, RotateCcw, TriangleAlert } from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { platformApi, type Eliminazione, type PlatformApartment } from "@/api/platform";
import { showCreationError } from "@/components/platform/CreationRow";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Badge, Dialog, DialogContent, DialogDescription, DialogTitle, Input, Label } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { freeFromText, type StepState } from "@/lib/apartmentCreation";
import { DELETION_STEPS, deletionStepState, deletionStoppedAt, deletionWhat, nameMatches, type DeletionOffer } from "@/lib/apartmentDeletion";
import { fmtDateTime } from "@/lib/format";
import { cn, newCorrelationId } from "@/lib/utils";

// A6 (docs/proposta-a6.md; bff/API.md «Eliminazione di un appartamento»): «Disattiva» with what it really does,
// the 7 days, «Elimina» confirmed by writing the name, and the row of a deletion in progress or stopped with «Riprova».
// The same shapes as the creation of A2 (CreationRow), so the two read alike.

/** The row's own frame: the red line of «Eliminazione non riuscita» drawn inside it, as «Non creato». */
export const deletionRowClass = (e: Eliminazione) => (e.stato === "non_riuscita" ? "bg-negative-bg/45 shadow-[inset_4px_0_0_0_hsl(var(--negative))]" : "");

function StepIcon({ state }: { state: StepState }) {
  const cls = "size-4 shrink-0";
  if (state === "fatto") return <Check className={cn(cls, "text-positive-fg")} aria-hidden />;
  if (state === "in_corso") return <Loader2 className={cn(cls, "text-foreground motion-safe:animate-spin")} aria-hidden />;
  if (state === "fallito") return <TriangleAlert className={cn(cls, "text-negative-fg")} aria-hidden />;
  return <Circle className={cn(cls, "text-muted-foreground/70")} aria-hidden />;
}

/** The body of a row whose deletion is not over: the three steps while in progress; «Cosa è successo» and «Riprova»
 *  when it stopped. Nothing else: the apartment is on its way out. */
export function DeletionRow({ a, busy, onRetry }: { a: PlatformApartment; busy: boolean; onRetry: () => void }) {
  const e = a.eliminazione!;
  const stopped = e.stato === "non_riuscita";
  const id = a.apartment_id;
  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold [overflow-wrap:anywhere]">{a.name}</span>
        <Badge className={cn("gap-1", stopped ? "border-negative-border bg-negative-bg text-negative-fg" : "border-neutral-border bg-neutral-bg text-neutral-fg")} data-testid={`deletion-state-${id}`}>
          {stopped ? <TriangleAlert className="size-3" aria-hidden /> : <Loader2 className="size-3 motion-safe:animate-spin" aria-hidden />}
          {t(`platform.deletion.states.${stopped ? "non_riuscita" : "in_corso"}`)}
        </Badge>
        <CopyableId id={id} full label={t("admin.apartments.id")} testId={`platform-apt-id-${id}`} />
      </div>
      <ol className="flex flex-wrap gap-x-5 gap-y-1.5 text-sm" data-testid={`deletion-steps-${id}`}>
        {DELETION_STEPS.map((p, i) => {
          const state = deletionStepState(e, p);
          return (
            <li
              key={p}
              className={cn("flex items-center gap-1.5", state === "in_corso" && "font-semibold", state === "da_fare" && "text-muted-foreground")}
              data-testid={`deletion-step-${id}-${p}`}
              data-state={state}
              aria-current={state === "in_corso" ? "step" : undefined}
            >
              <StepIcon state={state} />
              <span>{i + 1} · {t(`platform.deletion.steps.${p}`)}</span>
              <span className="sr-only">({t(`platform.creation.stepState.${state}`)})</span>
            </li>
          );
        })}
      </ol>
      {stopped ? (
        <>
          <WhatHappened id={id} e={e} />
          <Button size="sm" onClick={onRetry} disabled={busy} data-testid={`deletion-retry-${id}`}><RotateCcw /> {t("platform.creation.retry")}</Button>
        </>
      ) : (
        <>
          <p className="text-sm">{t("platform.deletion.running")}</p>
          <p className="text-xs text-muted-foreground">
            {e.updated_by ? t("platform.deletion.startedBy", { when: fmtDateTime(e.iniziata_at), name: e.updated_by }) : t("platform.deletion.startedAt", { when: fmtDateTime(e.iniziata_at) })}
          </p>
        </>
      )}
    </div>
  );
}

function WhatHappened({ id, e }: { id: string; e: Eliminazione }) {
  const at = deletionStoppedAt(e);
  const when = fmtDateTime(e.updated_at);
  return (
    <div className="space-y-1.5 rounded-xl border border-negative-border bg-card px-3.5 py-3 text-sm" data-testid={`deletion-what-${id}`}>
      <p className="font-semibold text-negative-fg">{t("platform.creation.whatTitle")}</p>
      <p className="font-medium text-negative-fg">{deletionWhat(e)}</p>
      <p>{t("platform.deletion.stoppedAt", { step: t(`platform.deletion.steps.${at.passo}`), n: at.n, of: at.of })}</p>
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>{e.updated_by ? t("platform.creation.lastAttempt", { when, name: e.updated_by }) : t("platform.creation.lastAttemptNoName", { when })}</span>
        {e.op && (
          <span className="inline-flex items-center gap-1.5">
            {t("credentials.requestId")}
            <CopyableId id={e.op.op_id} testId={`deletion-op-${id}`} label={t("credentials.requestId")} />
          </span>
        )}
      </p>
    </div>
  );
}

/** Under a disabled apartment: since when and by whom, and from when «Elimina» is possible. */
export function DisabledInfo({ a, offer }: { a: PlatformApartment; offer: DeletionOffer }) {
  const by = a.disattivato_da;
  const lines: string[] = [];
  if (a.disattivato_at) {
    const when = fmtDateTime(a.disattivato_at);
    lines.push(by?.nome ? t("platform.deletion.disabledBy", { when, name: by.nome, role: t(`platform.deletion.roles.${by.ruolo}`) }) : t("platform.deletion.disabledAt", { when }));
  }
  if (offer.del === "wait" && a.eliminabile_dal) lines.push(t("platform.deletion.deletableFrom", { when: fmtDateTime(a.eliminabile_dal) }));
  if (offer.del === "noDate") lines.push(t("platform.deletion.noDate"));
  if (lines.length === 0) return null;
  return (
    <p className="text-xs text-muted-foreground" data-testid={`platform-apt-disabled-${a.apartment_id}`}>
      {lines.join(" · ")}
    </p>
  );
}

/** «Disattiva» asks first, saying what disabling really does today (limiti-noti.md, «Appartamento disattivato»). */
export function DisableDialog({ a, onConfirm, onClose }: { a: PlatformApartment; onConfirm: () => void; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="apt-disable-dialog">
        <DialogTitle className="[overflow-wrap:anywhere]">{t("platform.deletion.disableTitle", { name: a.name })}</DialogTitle>
        <DialogDescription>{t("platform.deletion.disableText")}</DialogDescription>
        <div className="mt-3 space-y-1.5 text-sm">
          <p>{t("platform.deletion.disableWait")}</p>
          <p className="text-muted-foreground">{t("platform.deletion.email")}</p>
        </div>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button variant="ghost" onClick={onClose} data-testid="apt-disable-back">{t("common.cancel")}</Button>
          <Button onClick={onConfirm} data-testid="apt-disable-confirm">{t("platform.deletion.disable")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

type BoxError = { text: string; requestId: string | null };

/** The «ID richiesta» of a refusal: the order's op_id when the server sent one, else the call's correlation id. */
function requestIdOf(err: ApiError, correlationId: string): string {
  const op = err.details?.op as { op_id?: unknown } | undefined;
  return typeof op?.op_id === "string" ? op.op_id : err.correlationId ?? correlationId;
}

/**
 * «Elimina»: what is lost and what stays, the id that never comes back, the email; confirmed by writing the name.
 * The server checks everything again (the 7 days, the name, 2 a day per organization).
 */
export function DeleteDialog({ a, tenantId, tenantName, onClose, onDone }: { a: PlatformApartment; tenantId: string; tenantName: string; onClose: () => void; onDone: () => void }) {
  const [typed, setTyped] = useState("");
  const [saving, setSaving] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [boxError, setBoxError] = useState<BoxError | null>(null);
  const fromApp = a.origine === "app";
  const fieldId = `apt-delete-name-${a.apartment_id}`;

  const confirm = async () => {
    const correlationId = newCorrelationId();
    setSaving(true);
    setNameError(null);
    setBoxError(null);
    try {
      const res = await platformApi.deleteApartment(tenantId, a.apartment_id, typed, correlationId);
      toast.success(res?.eliminazione?.stato === "eliminato" ? t("platform.deletion.deleted", { name: a.name }) : t("platform.deletion.started", { name: a.name }));
      onDone();
      onClose();
    } catch (err) {
      if (!(err instanceof ApiError)) setBoxError({ text: t("errors.generic"), requestId: correlationId });
      else if (err.code === "name_mismatch") setNameError(err.message);
      else if (err.code === "rate_limited") {
        const when = err.details?.riprova_dal;
        const readable = typeof when === "string" && !Number.isNaN(new Date(when).getTime());
        setBoxError({ text: readable ? t("platform.deletion.limit", { when: freeFromText(when) }) : t("platform.deletion.limitNoTime"), requestId: null });
      } else if (err.code === "too_early") {
        const when = err.details?.eliminabile_dal;
        setBoxError({ text: typeof when === "string" ? t("platform.deletion.tooEarly", { when: fmtDateTime(when) }) : t("platform.deletion.tooEarlyNoDate"), requestId: null });
      } else if (err.code === "agent_publish_failed") {
        // the deletion started anyway and reads «non riuscita» with «Riprova»: close, and say it with the order's id
        showCreationError(err, correlationId);
        onDone();
        onClose();
      } else setBoxError({ text: err.message, requestId: requestIdOf(err, correlationId) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-xl" data-testid="apt-delete-dialog">
        <DialogTitle className="[overflow-wrap:anywhere]">{t("platform.deletion.deleteTitle", { name: a.name })}</DialogTitle>
        <DialogDescription className="[overflow-wrap:anywhere]">{t("platform.deletion.deleteWhich", { id: a.apartment_id, tenant: tenantName })}</DialogDescription>
        <div className="mt-3 space-y-2.5 text-sm">
          {a.origine === "a_mano" && (
            <p className="flex items-start gap-2 rounded-xl border border-warning-border bg-warning-bg px-3 py-2.5 text-warning-fg" data-testid="apt-delete-manual">
              <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>{t("platform.deletion.manual")}</span>
            </p>
          )}
          <p>{t(fromApp ? "platform.deletion.lostApp" : "platform.deletion.lostRecord")}</p>
          <p>{t(fromApp ? "platform.deletion.keptApp" : "platform.deletion.keptRecord")}</p>
          <p className="[overflow-wrap:anywhere]">{t("platform.deletion.idGone", { id: a.apartment_id })}</p>
          <p className="text-muted-foreground">{t("platform.deletion.email")}</p>
        </div>
        <div className="mt-4 space-y-1.5">
          <Label htmlFor={fieldId}>{t("platform.deletion.nameLabel")}</Label>
          <Input
            id={fieldId}
            value={typed}
            autoComplete="off"
            spellCheck={false}
            aria-invalid={nameError ? true : undefined}
            aria-describedby={`${fieldId}-hint`}
            onChange={(ev) => {
              setTyped(ev.target.value);
              setNameError(null);
            }}
            data-testid="apt-delete-name"
          />
          <p id={`${fieldId}-hint`} className="text-xs text-muted-foreground [overflow-wrap:anywhere]">{t("platform.deletion.nameHint", { name: a.name })}</p>
          {nameError && <p className="text-xs font-medium text-negative-fg" data-testid="apt-delete-name-error">{nameError}</p>}
        </div>
        {boxError && (
          <div role="alert" className="mt-3 space-y-1 rounded-xl border border-negative-border bg-negative-bg px-3 py-2.5 text-sm text-negative-fg" data-testid="apt-delete-error">
            <p>{boxError.text}</p>
            {boxError.requestId && (
              <p className="flex flex-wrap items-center gap-1.5 text-xs">
                {t("credentials.requestId")} <CopyableId id={boxError.requestId} testId="apt-delete-error-id" label={t("credentials.requestId")} />
              </p>
            )}
          </div>
        )}
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button variant="ghost" onClick={onClose} data-testid="apt-delete-back">{t("common.cancel")}</Button>
          <Button variant="destructive" onClick={() => void confirm()} disabled={saving || !nameMatches(typed, a.name)} data-testid="apt-delete-confirm">
            {t("platform.deletion.confirm")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
