import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Hourglass, X } from "lucide-react";
import type { Approval } from "@/api/types";
import { instanceApi } from "@/api/instance";
import { useRole } from "@/auth/AuthProvider";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { PageHeader, SegmentedControl } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Badge, Card, Input, Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";
import { describeAction, personLabel } from "@/lib/describe";
import { DEFAULT_TZ, fmtCountdown, fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApartmentStore } from "@/store/apartmentStore";

const STATUS_STYLE: Record<Approval["status"], string> = {
  pending: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  approved: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  rejected: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300",
  expired: "border-stone-300 bg-stone-100 text-stone-600 dark:border-stone-700 dark:bg-stone-800/60 dark:text-stone-300",
};

function Countdown({ until, id }: { until: string; id: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const i = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(i);
  }, []);
  const ms = new Date(until).getTime() - now;
  const urgent = ms < 5 * 60_000;
  return (
    <span className={cn("inline-flex items-center gap-1 font-mono text-sm font-bold tabular", urgent ? "text-destructive" : "text-foreground")} data-testid={`approval-countdown-${id}`} aria-live="polite">
      <Hourglass className="h-3.5 w-3.5" aria-hidden /> {ms > 0 ? t("approvals.remaining", { time: fmtCountdown(ms) }) : t("approvals.expired")}
    </span>
  );
}

function ApprovalCard({ aptId, a, canWrite, onDecided }: { aptId: string; a: Approval; canWrite: boolean; onDecided: (a: Approval) => void }) {
  const devices = useApartmentStore((s) => s.devices);
  const tz = useApartmentStore((s) => s.apartment?.timezone) ?? DEFAULT_TZ;
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const pending = a.status === "pending";

  const decide = async (decision: "approve" | "reject") => {
    setBusy(decision);
    const res = await runAction((c) => instanceApi(aptId).decideApproval(a.approval_id, { decision, note: note.trim() || undefined }, c), {
      success: decision === "approve" ? t("approvals.approved") : t("approvals.rejected"),
    });
    setBusy(null);
    if (res) onDecided(res);
  };

  return (
    <Card className={cn("space-y-4 p-5 animate-fade-up", pending && "border-primary/40 shadow-md")} data-testid={`approval-card-${a.approval_id}`} data-status={a.status}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge className={STATUS_STYLE[a.status]} data-testid={`approval-status-${a.approval_id}`}>{t(`approvals.status.${a.status}`)}</Badge>
          <span className="text-xs text-muted-foreground">{t(`approvals.source.${a.source}`)} · {fmtDateTime(a.created_at, tz)}</span>
        </div>
        {pending && a.expires_at && <Countdown until={a.expires_at} id={a.approval_id} />}
      </div>
      <h3 className="text-lg font-bold leading-snug" data-testid={`approval-description-${a.approval_id}`}>{a.description}</h3>
      <div className="rounded-xl bg-secondary/60 p-3">
        <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("approvals.why")}</div>
        <p className="mt-1 text-sm" data-testid={`approval-reason-${a.approval_id}`}>{a.reason}</p>
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        <span><span className="text-muted-foreground">{t("approvals.proposed")}:</span> <strong data-testid={`approval-action-${a.approval_id}`}>{describeAction(a.proposed_action, devices)}</strong></span>
        {pending && <span className="text-xs text-muted-foreground">{t(`approvals.onExpiry.${a.expires_action}`)}</span>}
        <CopyableId id={a.correlation_id} testId={`approval-correlation-${a.approval_id}`} className="text-muted-foreground" />
      </div>
      {pending && canWrite ? (
        <div className="space-y-3 border-t pt-4">
          <Input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} placeholder={t("approvals.notePlaceholder")} aria-label={t("approvals.note")} data-testid={`approval-note-${a.approval_id}`} />
          <div className="flex gap-2">
            <Button className="flex-1" onClick={() => decide("approve")} disabled={busy !== null} data-testid={`approve-action-btn-${a.approval_id}`}>
              <Check /> {t("approvals.approve")}
            </Button>
            <Button className="flex-1 border-destructive/40 text-destructive hover:bg-destructive/10" variant="outline" onClick={() => decide("reject")} disabled={busy !== null} data-testid={`reject-action-btn-${a.approval_id}`}>
              <X /> {t("approvals.reject")}
            </Button>
          </div>
        </div>
      ) : a.decided_by ? (
        <p className="text-xs text-muted-foreground" data-testid={`approval-decided-${a.approval_id}`}>
          {t("approvals.decidedBy", { decision: t(`approvals.status.${a.status}`), who: personLabel(a.decided_by), when: fmtDateTime(a.decided_at, tz) })}
          {a.note ? ` · «${a.note}»` : ""}
        </p>
      ) : null}
    </Card>
  );
}

export default function ApprovalsPage() {
  const { aptId = "" } = useParams();
  const { canWrite } = useRole();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<"pending" | "all">("pending");
  const q = useQuery({ queryKey: ["approvals", aptId, filter], queryFn: () => instanceApi(aptId).listApprovals(filter), refetchInterval: 30_000 });
  const items = q.data?.items ?? [];

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <PageHeader
        title={t("approvals.title")}
        subtitle={t("approvals.subtitle")}
        testId="approvals-header"
        actions={<SegmentedControl value={filter} onChange={setFilter} testId="approvals-filter" options={[{ value: "pending", label: t("approvals.pending") }, { value: "all", label: t("approvals.all") }]} />}
      />
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="approvals-error" />}
      {q.isLoading ? (
        <div className="space-y-4">{[0, 1].map((i) => <Skeleton key={i} className="h-48 rounded-2xl" />)}</div>
      ) : items.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted-foreground" data-testid="approvals-empty">{filter === "pending" ? t("approvals.empty") : t("approvals.emptyAll")}</Card>
      ) : (
        <div className="space-y-4" data-testid="approvals-list">
          {items.map((a) => (
            <ApprovalCard key={a.approval_id} aptId={aptId} a={a} canWrite={canWrite} onDecided={() => void qc.invalidateQueries({ queryKey: ["approvals", aptId] })} />
          ))}
        </div>
      )}
    </div>
  );
}
