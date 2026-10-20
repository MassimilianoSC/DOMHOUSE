import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Plus, Trash2 } from "lucide-react";
import type { ScheduleItem } from "@/api/types";
import { instanceApi } from "@/api/instance";
import { useRole } from "@/auth/AuthProvider";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { PageHeader } from "@/components/layout/PageHeader";
import { ScheduleDialog } from "@/components/schedule/ScheduleDialog";
import { Button } from "@/components/ui/button";
import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";
import { describeAction } from "@/lib/describe";
import { DEFAULT_TZ, fmtShortDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApartmentStore } from "@/store/apartmentStore";

const STATUS_STYLE: Record<ScheduleItem["status"], string> = {
  planned: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  done: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  cancelled: "border-stone-300 bg-stone-100 text-stone-600 dark:border-stone-700 dark:bg-stone-800/60 dark:text-stone-300",
  failed: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300",
};

function Row({ aptId, item, tz, canWrite }: { aptId: string; item: ScheduleItem; tz: string; canWrite: boolean }) {
  const devices = useApartmentStore((s) => s.devices);
  const qc = useQueryClient();
  const [moveOpen, setMoveOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const refresh = () => qc.invalidateQueries({ queryKey: ["schedule", aptId] });

  const cancel = async () => {
    if (!window.confirm(t("schedule.cancelConfirm"))) return;
    setBusy(true);
    const ok = await runAction(async (c) => {
      await instanceApi(aptId).cancelSchedule(item.schedule_id, c);
      return true;
    }, { success: t("schedule.cancelled") });
    setBusy(false);
    if (ok) void refresh();
  };

  return (
    <Card className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between animate-fade-up" data-testid={`schedule-item-${item.schedule_id}`} data-status={item.status}>
      <div className="min-w-0 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-bold tabular" data-testid={`schedule-run-at-${item.schedule_id}`}>{fmtShortDateTime(item.run_at, tz)}</span>
          <Badge className={STATUS_STYLE[item.status]} data-testid={`schedule-status-${item.schedule_id}`}>{t(`schedule.status.${item.status}`)}</Badge>
        </div>
        <div className="text-base font-semibold" data-testid={`schedule-action-${item.schedule_id}`}>{describeAction(item.action, devices)}</div>
        <div className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
          <span>{t(`schedule.kind.${item.kind}`)} · {t(`schedule.source.${item.source}`)}</span>
          {item.booking_id && <span className="font-mono">{item.booking_id}</span>}
          {item.source === "booking" && item.status === "planned" && <span>{t("schedule.bookingNote")}</span>}
        </div>
      </div>
      {canWrite && item.status === "planned" && (
        <div className="flex shrink-0 gap-2">
          <Button size="sm" variant="outline" onClick={() => setMoveOpen(true)} disabled={busy} data-testid={`schedule-move-btn-${item.schedule_id}`}>
            <CalendarClock /> {t("schedule.move")}
          </Button>
          <Button size="sm" variant="ghost" className="text-destructive" onClick={cancel} disabled={busy} data-testid={`schedule-cancel-btn-${item.schedule_id}`}>
            <Trash2 /> {t("schedule.cancel")}
          </Button>
          <ScheduleDialog aptId={aptId} tz={tz} open={moveOpen} onOpenChange={setMoveOpen} move={item} onDone={refresh} />
        </div>
      )}
    </Card>
  );
}

export default function SchedulePage() {
  const { aptId = "" } = useParams();
  const { canWrite } = useRole();
  const tz = useApartmentStore((s) => s.apartment?.timezone) ?? DEFAULT_TZ;
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const q = useQuery({ queryKey: ["schedule", aptId], queryFn: () => instanceApi(aptId).listSchedule(), refetchInterval: 30_000 });
  const items = q.data?.items ?? [];
  const planned = items.filter((i) => i.status === "planned");
  const history = items.filter((i) => i.status !== "planned").sort((a, b) => b.run_at.localeCompare(a.run_at));

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <PageHeader
        title={t("schedule.title")}
        subtitle={t("schedule.subtitle")}
        testId="schedule-header"
        actions={canWrite && (
          <Button onClick={() => setAddOpen(true)} data-testid="schedule-add-btn"><Plus /> {t("schedule.add")}</Button>
        )}
      />
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="schedule-error" />}
      {q.isLoading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-24 rounded-2xl" />)}</div>
      ) : (
        <>
          <section className="space-y-3" aria-label={t("schedule.planned")}>
            <h2 className="text-base font-bold md:text-lg">{t("schedule.planned")} <span className="rounded-full bg-secondary px-2 py-0.5 text-xs text-muted-foreground">{planned.length}</span></h2>
            {planned.length === 0 ? (
              <Card className="p-10 text-center text-sm text-muted-foreground" data-testid="schedule-empty">{t("schedule.empty")}</Card>
            ) : planned.map((i) => <Row key={i.schedule_id} aptId={aptId} item={i} tz={tz} canWrite={canWrite} />)}
          </section>
          {history.length > 0 && (
            <section className={cn("space-y-3")} aria-label={t("schedule.history")}>
              <h2 className="text-base font-bold text-muted-foreground md:text-lg">{t("schedule.history")}</h2>
              {history.map((i) => <Row key={i.schedule_id} aptId={aptId} item={i} tz={tz} canWrite={false} />)}
            </section>
          )}
        </>
      )}
      <ScheduleDialog aptId={aptId} tz={tz} open={addOpen} onOpenChange={setAddOpen} onDone={() => qc.invalidateQueries({ queryKey: ["schedule", aptId] })} />
    </div>
  );
}
