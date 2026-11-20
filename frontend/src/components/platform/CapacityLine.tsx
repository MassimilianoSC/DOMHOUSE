import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw, Server, TriangleAlert } from "lucide-react";
import { ApiError } from "@/api/bff";
import { platformApi, type CapienzaView } from "@/api/platform";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { MAX_POLL_MS, POLL_MS } from "@/lib/apartmentCreation";
import { capacityLine, refreshState } from "@/lib/capacity";
import { pollWindow } from "@/lib/pollWindow";
import { cn, newCorrelationId } from "@/lib/utils";

// A7 (docs/proposta-a7.md §2 n. 5, §3; answers 1201, 1203): the free places of the VM in «Nuovo appartamento», from the
// last reading the server keeps (opening the form sends no order). «Aggiorna» sends one, read again every 4 s while it
// is «inviato», at most 20 minutes. It informs only: «Crea» stays on, the server and the agent check again.

export const capacityKey = ["platform", "capienza"];

type Failure = { text: string; requestId: string | null };

/** Ticks at the given instant (when «Aggiorna» is free again) and every 30 s (the age of the reading). */
function useNow(until: string | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const every = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(every);
  }, []);
  useEffect(() => {
    if (!until) return;
    const ms = new Date(until).getTime() - Date.now();
    if (!(ms > 0)) return;
    const timer = setTimeout(() => setNow(Date.now()), ms + 50);
    return () => clearTimeout(timer);
  }, [until]);
  return now;
}

const failureOf = (err: unknown, correlationId: string | null): Failure => {
  if (!(err instanceof ApiError)) return { text: t("capacity.failed", { message: t("errors.generic") }), requestId: correlationId };
  const op = err.details?.op as { op_id?: unknown } | undefined;
  return { text: t("capacity.failed", { message: err.message }), requestId: typeof op?.op_id === "string" ? op.op_id : err.correlationId ?? correlationId };
};

export function CapacityLine() {
  const qc = useQueryClient();
  const [inWindow] = useState(() => pollWindow(MAX_POLL_MS));
  const q = useQuery({
    queryKey: capacityKey,
    queryFn: () => platformApi.capacity(),
    staleTime: 0,
    refetchOnMount: "always",
    refetchInterval: (query) => {
      const data = query.state.data;
      const running = data && refreshState(data, Date.now()).kind === "running" ? data.aggiornamento!.op_id : "";
      return inWindow(running, Date.now()) ? POLL_MS : false;
    },
  });
  const [sending, setSending] = useState(false);
  const [callFailure, setCallFailure] = useState<Failure | null>(null);
  const [hidden, setHidden] = useState(false);
  const now = useNow(q.data?.aggiornabile_dal ?? null);

  const refresh = async () => {
    const correlationId = newCorrelationId();
    setSending(true);
    setCallFailure(null);
    try {
      qc.setQueryData(capacityKey, await platformApi.refreshCapacity(correlationId));
    } catch (err) {
      if (err instanceof ApiError && err.code === "agent_not_configured") setHidden(true);
      else if (err instanceof ApiError && err.code === "rate_limited") {
        const when = err.details?.riprova_dal;
        if (typeof when === "string") qc.setQueryData<CapienzaView>(capacityKey, (old) => (old ? { ...old, aggiornabile_dal: when } : old));
        void q.refetch();
      } else setCallFailure(failureOf(err, correlationId));
    } finally {
      setSending(false);
    }
  };

  if (hidden || (q.error instanceof ApiError && q.error.code === "agent_not_configured")) return null;
  if (q.isPending) return <Skeleton className="h-11 rounded-xl" />;

  const line = q.data ? capacityLine(q.data.capienza, now) : null;
  const state = q.data ? refreshState(q.data, now) : null;
  const failure = callFailure ?? (state?.kind === "failed" ? { text: state.text, requestId: state.requestId } : q.isError ? failureOf(q.error, null) : null);
  const running = state?.kind === "running";
  const cooling = Boolean(q.data?.aggiornabile_dal && new Date(q.data.aggiornabile_dal).getTime() > now);
  const zero = line?.kind === "zero";

  return (
    <div
      role="status"
      data-testid="new-apt-capacity"
      data-kind={line?.kind ?? "error"}
      className={cn("space-y-2 rounded-xl border px-3 py-2.5 text-sm", zero ? "border-warning-border bg-warning-bg text-warning-fg" : "border-border/80 bg-secondary/60 text-foreground")}
    >
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <span className="flex min-w-0 flex-1 basis-56 items-start gap-2">
          {zero ? <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden /> : <Server className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />}
          {line && <span className="[overflow-wrap:anywhere]" data-testid="new-apt-capacity-text">{line.text}</span>}
        </span>
        <span className="ml-auto" title={cooling ? t("capacity.refreshSoon") : undefined} data-testid="new-apt-capacity-refresh-wrap">
          <Button size="sm" variant="outline" onClick={() => void refresh()} disabled={sending || running || cooling} data-testid="new-apt-capacity-refresh">
            <RefreshCw /> {t("capacity.refresh")}
          </Button>
        </span>
      </div>
      {running && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground" data-testid="new-apt-capacity-running">
          <Loader2 className="size-3.5 motion-safe:animate-spin" aria-hidden /> {t("capacity.running")}
        </p>
      )}
      {failure && (
        <div className="space-y-1 text-xs text-negative-fg" data-testid="new-apt-capacity-failed">
          <p className="font-medium">{failure.text}</p>
          {failure.requestId && (
            <p className="flex flex-wrap items-center gap-1.5">
              {t("credentials.requestId")} <CopyableId id={failure.requestId} testId="new-apt-capacity-failed-id" label={t("credentials.requestId")} />
            </p>
          )}
        </div>
      )}
    </div>
  );
}
