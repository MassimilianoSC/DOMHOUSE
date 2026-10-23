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
import { Card, StatusBadge, type Tone } from "@/components/ui/primitives";
import { RowsSkeleton } from "@/components/ui/Skeletons";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";
import { describeAction } from "@/lib/describe";
import { DEFAULT_TZ, fmtShortDateTime } from "@/lib/format";
import { useApartmentStore } from "@/store/apartmentStore";

const STATUS_TONE: Record<ScheduleItem["status"], Tone> = {
  planned: "warning",
  done: "positive",
  cancelled: "neutral",
  failed: "negative",
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
    // one row of a single list (design lot 2): the time in a fixed column, the action in ink, kind and source in grey,
    // the state on the right; the booking code only in the tooltip
    <li className="grid gap-x-4 gap-y-2 py-3 sm:grid-cols-[9.5rem_minmax(0,1fr)_auto] sm:items-center" data-testid={`schedule-item-${item.schedule_id}`} data-status={item.status}>
      <span className="text-sm font-semibold tabular" data-testid={`schedule-run-at-${item.schedule_id}`}>{fmtShortDateTime(item.run_at, tz)}</span>
      <div className="min-w-0">
        <div className="text-sm font-semibold [overflow-wrap:anywhere]" data-testid={`schedule-action-${item.schedule_id}`}>{describeAction(item.action, devices)}</div>
        <div className="text-[13px] text-muted-foreground">
          <span title={item.booking_id ?? undefined}>{t(`schedule.kind.${item.kind}`)} · {t(`schedule.source.${item.source}`)}</span>
          {item.source === "booking" && item.status === "planned" && <span> · {t("schedule.bookingNote")}</span>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:justify-end">
        <StatusBadge tone={STATUS_TONE[item.status]} data-testid={`schedule-status-${item.schedule_id}`}>{t(`schedule.status.${item.status}`)}</StatusBadge>
        {canWrite && item.status === "planned" && (
          <>
            <Button size="sm" variant="outline" onClick={() => setMoveOpen(true)} disabled={busy} data-testid={`schedule-move-btn-${item.schedule_id}`}>
              <CalendarClock /> {t("schedule.move")}
            </Button>
            <Button size="sm" variant="destructive" onClick={cancel} disabled={busy} data-testid={`schedule-cancel-btn-${item.schedule_id}`}>
              <Trash2 /> {t("schedule.cancel")}
            </Button>
            <ScheduleDialog aptId={aptId} tz={tz} open={moveOpen} onOpenChange={setMoveOpen} move={item} onDone={refresh} />
          </>
        )}
      </div>
    </li>
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
    <div className="mx-auto max-w-6xl space-y-8">
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
        <RowsSkeleton rows={3} />
      ) : (
        <>
          <section className="space-y-3" aria-label={t("schedule.planned")}>
            <h2 className="text-base font-semibold">{t("schedule.planned")} <span className="font-normal text-muted-foreground tabular">{planned.length}</span></h2>
            {planned.length === 0 ? (
              <Card className="p-10 text-center text-sm text-muted-foreground" data-testid="schedule-empty">{t("schedule.empty")}</Card>
            ) : (
              <Card className="px-4 sm:px-5">
                <ul className="divide-y" data-testid="schedule-planned-list">
                  {planned.map((i) => <Row key={i.schedule_id} aptId={aptId} item={i} tz={tz} canWrite={canWrite} />)}
                </ul>
              </Card>
            )}
          </section>
          {history.length > 0 && (
            <section className="space-y-3" aria-label={t("schedule.history")}>
              <div>
                <h2 className="text-base font-semibold">{t("schedule.history")}</h2>
                <p className="text-sm text-muted-foreground">{t("schedule.historyHint")}</p>
              </div>
              <Card className="px-4 sm:px-5">
                <ul className="divide-y" data-testid="schedule-history-list">
                  {history.map((i) => <Row key={i.schedule_id} aptId={aptId} item={i} tz={tz} canWrite={false} />)}
                </ul>
              </Card>
            </section>
          )}
        </>
      )}
      <ScheduleDialog aptId={aptId} tz={tz} open={addOpen} onOpenChange={setAddOpen} onDone={() => qc.invalidateQueries({ queryKey: ["schedule", aptId] })} />
    </div>
  );
}
