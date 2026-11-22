import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Ban, ChevronRight, KeyRound, Link2, Loader2, Plus, RotateCcw, TriangleAlert } from "lucide-react";
import { credentialsApi, type CredentialScope, type DeviceCredential } from "@/api/deviceCredentials";
import { ApiError } from "@/api/bff";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Badge, Skeleton } from "@/components/ui/primitives";
import { RowMenu, RowMenuItem } from "@/components/ui/RowMenu";
import { t } from "@/i18n";
import { allowedActions, credentialsSignature, MAX_POLL_MS, POLL_MS, refusalNote, splitCredentials, type CredentialAction } from "@/lib/deviceCredentials";
import { pollWindow } from "@/lib/pollWindow";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** What a row asks the panel to do: an action of the menu, or the connection data. */
export type RowRequest = { kind: CredentialAction | "connection"; credential: DeviceCredential };

const TONE: Record<DeviceCredential["stato"], string> = {
  // «Abilitato» (usability reading 2.2): it may connect, not «it is connected»; green stays for «In linea» only
  pronto: "border-neutral-border bg-neutral-bg text-neutral-fg",
  in_attesa: "border-neutral-border bg-neutral-bg text-neutral-fg",
  cambio_in_corso: "border-warning-border bg-warning-bg text-warning-fg",
  revoca_in_corso: "border-warning-border bg-warning-bg text-warning-fg",
  revocato: "border-neutral-border bg-neutral-bg text-neutral-fg",
  non_applicato: "border-negative-border bg-negative-bg text-negative-fg",
};

function StateIcon({ stato }: { stato: DeviceCredential["stato"] }) {
  const cls = "size-3";
  if (stato === "pronto") return <KeyRound className={cls} aria-hidden />;
  if (stato === "non_applicato") return <TriangleAlert className={cls} aria-hidden />;
  if (stato === "revocato") return <Ban className={cls} aria-hidden />;
  return <Loader2 className={cn(cls, "motion-safe:animate-spin")} aria-hidden />;
}

/** The explanation under the state label (docs/proposta-a3-sito.md §3, §3.2). */
function StateLine({ c }: { c: DeviceCredential }) {
  if (c.stato === "non_applicato") {
    const what = c.azione ? t(`credentials.notApplied.${c.azione}`) : t("credentials.notApplied.other");
    return (
      <div className="space-y-1 text-sm">
        <p>
          <strong className="font-semibold text-negative-fg">{what}</strong> {t("credentials.notApplied.useRetry")}
        </p>
        {c.op && (
          <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            {c.op.messaggio && <span>{c.op.messaggio} ·</span>}
            <span>{t("credentials.requestId")}</span>
            <CopyableId id={c.op.op_id} testId={`credential-op-${c.device_id}`} label={t("credentials.requestId")} />
          </p>
        )}
      </div>
    );
  }
  if (c.stato === "revocato") return <p className="text-sm">{t("credentials.lines.revocato", { date: fmtDate(c.updated_at) })}</p>;
  if (c.stato === "pronto")
    return (
      <p className="text-sm">
        {t("credentials.lines.pronto")} <span className="text-xs text-muted-foreground">{t("credentials.readyNote")}</span>
      </p>
    );
  return <p className="text-sm">{t(`credentials.lines.${c.stato}`)}</p>;
}

/** A5 (docs/proposta-a5.md): the refused connections of the last 24 hours; nothing when there are none or the server
 *  does not know. Yellow with «Cosa fare» only when they came after the last change. */
function Refusals({ c }: { c: DeviceCredential }) {
  const note = refusalNote(c, Date.now());
  if (!note) return null;
  const warning = note.kind === "warning";
  return (
    <div
      className={cn("space-y-1 text-sm", warning ? "rounded-lg border border-warning-border bg-warning-bg px-2.5 py-2 text-warning-fg" : "text-muted-foreground")}
      data-testid={`credential-refusals-${c.device_id}`}
      data-kind={note.kind}
    >
      <p className={cn(warning && "flex items-start gap-1.5 font-medium")}>
        {warning && <TriangleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />}
        <span>
          {note.text}
          {note.kind === "past" && <> {t("credentials.refusals.past")}</>}
          {note.kind === "revoked" && <> {t("credentials.refusals.revoked")}</>}
        </span>
      </p>
      {warning && (
        <>
          <p>{t("credentials.refusals.todo")}</p>
          <p className="text-xs">{t("credentials.refusals.delay")}</p>
        </>
      )}
    </div>
  );
}

// From 1024 px one table, as the other lists of the site; the date and the buttons have fixed widths, so every column
// starts in the same place on every row whatever its buttons. Below, one card per device, as the apartments' cards.
const GRID = "lg:grid lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1.7fr)_9.5rem_19rem] lg:items-start lg:gap-4";
const CARD = "rounded-2xl border border-border/80 bg-card lg:rounded-none lg:border-0 lg:bg-transparent";
const LIST = "space-y-3 lg:space-y-0 lg:divide-y";
const TABLE = "lg:overflow-hidden lg:rounded-2xl lg:border lg:border-border/80 lg:bg-card";

function Row({ c, onRequest }: { c: DeviceCredential; onRequest: (r: RowRequest) => void }) {
  const actions = allowedActions(c);
  const menu = actions.filter((a) => a === "rigenera" || a === "revoca");
  return (
    <li
      // the red line of «Non applicato» drawn inside the row (a shadow), so it moves nothing
      className={cn("space-y-2.5 p-4 lg:space-y-0 lg:py-3.5", CARD, GRID, c.stato === "non_applicato" && "border-negative-border bg-negative-bg/45 shadow-[inset_4px_0_0_0_hsl(var(--negative))] lg:bg-negative-bg/45")}
      data-testid={`credential-row-${c.device_id}`}
      data-state={c.stato}
    >
      <div className="min-w-0">
        {c.name && <div className="text-sm font-semibold [overflow-wrap:anywhere]">{c.name}</div>}
        <div className="font-mono text-[13px] font-bold tracking-tight [overflow-wrap:anywhere]">{c.device_id}</div>
      </div>
      <div className="min-w-0 space-y-1">
        <Badge className={TONE[c.stato]} data-testid={`credential-state-${c.device_id}`}>
          <StateIcon stato={c.stato} /> {t(`credentials.states.${c.stato}`)}
        </Badge>
        <StateLine c={c} />
        <Refusals c={c} />
      </div>
      {/* on a card one quiet line, «Ultima modifica: 19 nov 2026, 16:12 · Giulia Rossi»; in the table its own column */}
      <div className="min-w-0 text-xs text-muted-foreground lg:text-sm lg:text-foreground">
        <span className="lg:hidden">{t("credentials.colUpdated")}: </span>
        <span className="tabular">{fmtDateTime(c.updated_at)}</span>
        {c.updated_by && (
          <>
            <span className="lg:hidden"> · </span>
            <span className="lg:block lg:text-xs lg:text-muted-foreground">{c.updated_by}</span>
          </>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2 lg:justify-end">
        {actions.includes("riprova") && (
          <Button size="sm" onClick={() => onRequest({ kind: "riprova", credential: c })} data-testid={`credential-retry-${c.device_id}`}>
            <RotateCcw /> {t("credentials.actions.riprova")}
          </Button>
        )}
        {actions.includes("registra") && (
          <Button size="sm" variant="outline" onClick={() => onRequest({ kind: "registra", credential: c })} data-testid={`credential-reregister-${c.device_id}`}>
            <Plus /> {t("credentials.actions.registra")}
          </Button>
        )}
        {c.stato !== "revocato" && (
          <Button size="sm" variant="outline" onClick={() => onRequest({ kind: "connection", credential: c })} data-testid={`credential-connection-${c.device_id}`}>
            <Link2 /> {t("credentials.actions.connection")}
          </Button>
        )}
        {menu.length > 0 && (
          <RowMenu label={t("credentials.actionsOf", { id: c.device_id })} testId={`credential-menu-${c.device_id}`}>
            {menu.includes("rigenera") && (
              <RowMenuItem onSelect={() => onRequest({ kind: "rigenera", credential: c })} testId={`credential-regenerate-${c.device_id}`}>
                <KeyRound /> {t("credentials.actions.rigenera")}
              </RowMenuItem>
            )}
            {menu.includes("revoca") && (
              <RowMenuItem danger onSelect={() => onRequest({ kind: "revoca", credential: c })} testId={`credential-revoke-${c.device_id}`}>
                <Ban /> {t("credentials.actions.revoca")}
              </RowMenuItem>
            )}
          </RowMenu>
        )}
      </div>
    </li>
  );
}

function Header() {
  return (
    <div className={cn("hidden bg-secondary/50 px-4 py-2.5 text-xs font-semibold text-muted-foreground", GRID)} aria-hidden>
      <div>{t("credentials.colDevice")}</div>
      <div>{t("credentials.colState")}</div>
      <div>{t("credentials.colUpdated")}</div>
      <div />
    </div>
  );
}

/**
 * The list of the device credentials of one apartment (A3), with the state of each and the actions it allows. Used by
 * the apartment's page (scope apartment) and, in staging, under a lab-/test- apartment in Organizzazioni (scope
 * platform). While an order is on its way the list is read again every 4 s, for at most 20 minutes.
 */
export function CredentialsPanel({ apartmentId, scope, onRequest, onRegister }: { apartmentId: string; scope: CredentialScope; onRequest: (r: RowRequest) => void; onRegister: () => void }) {
  const api = credentialsApi(apartmentId, scope);
  const pollOpen = useRef(pollWindow(MAX_POLL_MS));
  const q = useQuery({
    queryKey: credentialsKey(apartmentId, scope),
    queryFn: async () => (await api.list()).items,
    refetchInterval: (query) => (pollOpen.current(credentialsSignature(query.state.data), Date.now()) ? POLL_MS : false),
  });
  const [showRevoked, setShowRevoked] = useState(false);
  const { active, revoked } = splitCredentials(q.data ?? []);

  return (
    <div className="space-y-4" data-testid={`credentials-panel-${apartmentId}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground" data-testid="credentials-count">
          {q.data ? t("credentials.count", { active: active.length, revoked: revoked.length }) : null}
        </p>
        <Button onClick={onRegister} data-testid="credentials-register-btn">
          <Plus /> {t("credentials.register")}
        </Button>
      </div>
      {q.error && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-xl border border-negative-border bg-negative-bg px-3 py-2 text-sm text-negative-fg" data-testid="credentials-error">
          <span className="min-w-0 flex-1">{q.error instanceof ApiError ? q.error.message : t("credentials.loadError")}</span>
          <Button size="sm" variant="outline" onClick={() => void q.refetch()}>{t("common.retry")}</Button>
        </div>
      )}
      {q.isLoading ? (
        <Skeleton className="h-40 rounded-2xl" />
      ) : q.data && active.length === 0 && revoked.length === 0 ? (
        <div className="rounded-2xl border border-border/80 bg-card p-8 text-center" data-testid="credentials-empty">
          <p className="font-semibold">{t("credentials.empty")}</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{t("credentials.emptyHint")}</p>
        </div>
      ) : (
        q.data && (
          <>
            {active.length > 0 && (
              <div className={TABLE}>
                <Header />
                <ul className={LIST}>
                  {active.map((c) => <Row key={c.device_id} c={c} onRequest={onRequest} />)}
                </ul>
              </div>
            )}
            {revoked.length > 0 && (
              <div className={cn("space-y-3 lg:space-y-0", TABLE)}>
                <button
                  type="button"
                  className={cn("flex w-full flex-wrap items-center gap-x-2 gap-y-0.5 px-4 py-3.5 text-left text-sm font-semibold focus-ring", CARD)}
                  aria-expanded={showRevoked}
                  onClick={() => setShowRevoked((v) => !v)}
                  data-testid="credentials-revoked-toggle"
                >
                  <ChevronRight className={cn("size-4 transition-transform motion-reduce:transition-none", showRevoked && "rotate-90")} aria-hidden />
                  <span className="whitespace-nowrap" data-testid="credentials-revoked-title">{t("credentials.revoked", { count: revoked.length })}</span>
                  <span className="basis-full pl-6 text-xs font-normal text-muted-foreground sm:basis-auto sm:pl-0">{t("credentials.revokedHint")}</span>
                </button>
                {showRevoked && (
                  <ul className={cn(LIST, "lg:border-t")}>
                    {revoked.map((c) => <Row key={c.device_id} c={c} onRequest={onRequest} />)}
                  </ul>
                )}
              </div>
            )}
          </>
        )
      )}
    </div>
  );
}

export const credentialsKey = (apartmentId: string, scope: CredentialScope) => ["device-credentials", scope, apartmentId];
