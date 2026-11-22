import { useQuery } from "@tanstack/react-query";
import { Check, Circle, Loader2, RotateCcw, TriangleAlert, X } from "lucide-react";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { credentialsApi } from "@/api/deviceCredentials";
import type { Creazione, PlatformApartment } from "@/api/platform";
import { credentialsKey } from "@/components/credentials/CredentialsPanel";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Badge, Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { showError } from "@/lib/actions";
import { CREATION_STEPS, stepState, stoppedAt, whatHappened, type StepState } from "@/lib/apartmentCreation";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

// A2, the row of an apartment whose creation is not over (docs/proposta-a2-sito.md §3): «In preparazione» with the five
// steps, «Non creato» with «Cosa è successo», «Riprova» and «Annulla creazione», «Annullamento in corso». No connection,
// verification, deletion or agent test: there is no home automation system to talk to yet.

type Open = Exclude<Creazione["stato"], "pronto" | "annullato">;

const TONE: Record<Open, string> = {
  in_preparazione: "border-neutral-border bg-neutral-bg text-neutral-fg",
  annullamento_in_corso: "border-neutral-border bg-neutral-bg text-neutral-fg",
  non_creato: "border-negative-border bg-negative-bg text-negative-fg",
};

/** The row's own frame: the red line of «Non creato» drawn inside it (a shadow), as «Non applicato» in A3. */
export const creationRowClass = (c: Creazione | null | undefined) =>
  c?.stato === "non_creato" ? "bg-negative-bg/45 shadow-[inset_4px_0_0_0_hsl(var(--negative))]" : "";

function StepIcon({ state }: { state: StepState }) {
  const cls = "size-4 shrink-0";
  if (state === "fatto") return <Check className={cn(cls, "text-positive-fg")} aria-hidden />;
  if (state === "in_corso") return <Loader2 className={cn(cls, "text-foreground motion-safe:animate-spin")} aria-hidden />;
  if (state === "fallito") return <TriangleAlert className={cn(cls, "text-negative-fg")} aria-hidden />;
  return <Circle className={cn(cls, "text-muted-foreground/70")} aria-hidden />;
}

/** The five steps (§3.3), done, in progress, to do; wrapped on a phone. */
function StepStrip({ id, c }: { id: string; c: Creazione }) {
  return (
    <ol className="flex flex-wrap gap-x-5 gap-y-1.5 text-sm" data-testid={`creation-steps-${id}`}>
      {CREATION_STEPS.map((p, i) => {
        const state = stepState(c, p);
        return (
          <li
            key={p}
            className={cn("flex items-center gap-1.5", state === "in_corso" && "font-semibold", state === "da_fare" && "text-muted-foreground")}
            data-testid={`creation-step-${id}-${p}`}
            data-state={state}
            aria-current={state === "in_corso" ? "step" : undefined}
          >
            <StepIcon state={state} />
            <span>{i + 1} · {t(`platform.creation.steps.${p}`)}</span>
            <span className="sr-only">({t(`platform.creation.stepState.${state}`)})</span>
          </li>
        );
      })}
    </ol>
  );
}

function StateBadge({ id, stato }: { id: string; stato: Open }) {
  return (
    <Badge className={cn("gap-1", TONE[stato])} data-testid={`creation-state-${id}`}>
      {stato === "non_creato" ? <TriangleAlert className="size-3" aria-hidden /> : <Loader2 className="size-3 motion-safe:animate-spin" aria-hidden />}
      {t(`platform.creation.states.${stato}`)}
    </Badge>
  );
}

/** «Cosa è successo» (§3.2): in plain words, where it stopped, what stays reserved, the last attempt and the request id. */
function WhatHappened({ a, c }: { a: PlatformApartment; c: Creazione }) {
  const at = stoppedAt(c);
  const when = fmtDateTime(c.updated_at);
  return (
    <div className="space-y-1.5 rounded-xl border border-negative-border bg-card px-3.5 py-3 text-sm" data-testid={`creation-what-${a.apartment_id}`}>
      <p className="font-semibold text-negative-fg">{t("platform.creation.whatTitle")}</p>
      <p className="font-medium text-negative-fg">{whatHappened(c)}</p>
      <p>{t("platform.creation.stoppedAt", { step: t(`platform.creation.steps.${at.passo}`), n: at.n, of: at.of })}</p>
      <p className="[overflow-wrap:anywhere]">
        {c.porta ? t("platform.creation.reserved", { id: a.apartment_id, port: c.porta }) : t("platform.creation.reservedNoPort", { id: a.apartment_id })}
      </p>
      {/* «ID richiesta» and its code go to a new line together on a phone */}
      <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
        <span>{c.updated_by ? t("platform.creation.lastAttempt", { when, name: c.updated_by }) : t("platform.creation.lastAttemptNoName", { when })}</span>
        {c.op ? (
          <span className="inline-flex items-center gap-1.5">
            {t("credentials.requestId")}
            <CopyableId id={c.op.op_id} testId={`creation-op-${a.apartment_id}`} label={t("credentials.requestId")} />
          </span>
        ) : (
          // no order reached the VM: the messages say «con l'ID qui sotto», so the apartment's ID, with its own label;
          // the whole ID, on its own line under the label on a phone
          <span className="inline-flex max-w-full flex-wrap items-center gap-1.5">
            {t("platform.creation.aptId")}
            <CopyableId id={a.apartment_id} full testId={`creation-apt-id-${a.apartment_id}`} label={t("platform.creation.aptId")} />
          </span>
        )}
      </p>
    </div>
  );
}

/** The body of a row whose creation is not over; the buttons only for «Non creato». */
export function CreationRow({ a, busy, onRetry, onCancel }: { a: PlatformApartment; busy: boolean; onRetry: () => void; onCancel: () => void }) {
  const c = a.creazione!;
  const stato = c.stato as Open;
  const started = c.updated_by ? t("platform.creation.startedBy", { when: fmtDateTime(c.updated_at), name: c.updated_by }) : t("platform.creation.startedAt", { when: fmtDateTime(c.updated_at) });
  return (
    <div className="space-y-2.5">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-semibold [overflow-wrap:anywhere]">{a.name}</span>
        <StateBadge id={a.apartment_id} stato={stato} />
        <CopyableId id={a.apartment_id} full label={t("admin.apartments.id")} testId={`platform-apt-id-${a.apartment_id}`} />
      </div>
      {stato === "in_preparazione" && (
        <>
          <StepStrip id={a.apartment_id} c={c} />
          {/* 1209: how long it takes, only while «In preparazione» */}
          <p className="text-sm" data-testid={`creation-duration-${a.apartment_id}`}>{t("platform.creation.duration")}</p>
          <p className="text-xs text-muted-foreground">
            {started}
            {c.porta ? ` · ${t("platform.creation.port", { port: c.porta })}` : ""}
          </p>
        </>
      )}
      {stato === "annullamento_in_corso" && <p className="text-sm text-muted-foreground">{t("platform.creation.cancelling")}</p>}
      {stato === "non_creato" && (
        <>
          <WhatHappened a={a} c={c} />
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={onRetry} disabled={busy} data-testid={`creation-retry-${a.apartment_id}`}><RotateCcw /> {t("platform.creation.retry")}</Button>
            <Button size="sm" variant="outline" className="border-negative-border text-negative-fg hover:bg-negative-bg" onClick={onCancel} disabled={busy} data-testid={`creation-cancel-${a.apartment_id}`}>
              <X /> {t("platform.creation.cancel")}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

/** «Annulla creazione» asks first (§3.2): what goes away, and that the id cannot be used again. */
export function CancelCreationDialog({ a, onConfirm, onClose }: { a: PlatformApartment; onConfirm: () => void; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="creation-cancel-dialog">
        <DialogTitle>{t("platform.creation.cancelTitle", { name: a.name })}</DialogTitle>
        <DialogDescription className="[overflow-wrap:anywhere]">{t("platform.creation.cancelText", { name: a.name, id: a.apartment_id })}</DialogDescription>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <Button variant="ghost" onClick={onClose} data-testid="creation-cancel-back">{t("platform.creation.back")}</Button>
          <Button variant="destructive" onClick={onConfirm} data-testid="creation-cancel-confirm">{t("platform.creation.cancel")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** «Pronto» (§3.4): an invitation to the next steps while no Shelly has been registered on the apartment. */
export function ReadyInvite({ apartmentId }: { apartmentId: string }) {
  const q = useQuery({ queryKey: credentialsKey(apartmentId, "platform"), queryFn: async () => (await credentialsApi(apartmentId, "platform").list()).items });
  if (!q.data || q.data.length > 0) return null;
  return (
    <p className="flex items-start gap-2 rounded-xl border border-positive-border bg-positive-bg px-3 py-2.5 text-sm text-positive-fg" data-testid={`creation-ready-${apartmentId}`}>
      <Check className="mt-0.5 size-4 shrink-0" aria-hidden />
      <span><strong className="font-semibold">{t("platform.creation.readyLead")}</strong> {t("platform.creation.readyNext")}</span>
    </p>
  );
}

/** What a refused «Riprova» or «Annulla» says (§6.1): a stale page is the usual cause, so the list is read again. */
export function showCreationError(err: unknown, correlationId: string) {
  if (err instanceof ApiError && (err.code === "version_changed" || err.code === "invalid_state")) {
    toast.info(t("platform.creation.changed"));
    return;
  }
  const op = err instanceof ApiError ? (err.details?.op as { op_id?: unknown } | undefined) : undefined;
  if (err instanceof ApiError && err.code === "agent_publish_failed" && typeof op?.op_id === "string") {
    toast.error(err.message, {
      description: (
        <span className="flex items-center gap-1.5" data-testid="toast-error-correlation">
          {t("credentials.requestId")} <CopyableId id={op.op_id} testId="toast-correlation-id" label={t("credentials.requestId")} />
        </span>
      ),
      duration: 10000,
    });
    return;
  }
  showError(err, correlationId);
}
