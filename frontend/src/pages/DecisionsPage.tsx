import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, ChevronDown, ChevronUp, Loader2, SlidersHorizontal } from "lucide-react";
import type { Decision } from "@/api/types";
import { instanceApi } from "@/api/instance";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { PageHeader } from "@/components/layout/PageHeader";
import { useDecisionLog } from "@/hooks/useDecisionLog";
import { useDecisionSearch } from "@/hooks/useDecisionSearch";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Card, Input, NativeSelect, StatusBadge, type Tone } from "@/components/ui/primitives";
import { RowsSkeleton } from "@/components/ui/Skeletons";
import { t } from "@/i18n";
import { MAX_RESULTS, matchesDecision, periodFrom } from "@/lib/decisionSearch";
import { actionLabel, decisionValue, describeActor, deviceLabel } from "@/lib/describe";
import { DEFAULT_TZ, fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApartmentStore } from "@/store/apartmentStore";

const ACTOR_FILTERS = ["", "brain", "rule", "user", "assistant", "system"];
/** The outcome as a badge on the right, on a full colour (lot 34, D-194: full colour where a state is said). */
const OUTCOME_TONE: Record<Decision["outcome"], Tone> = {
  applied: "positive",
  rejected: "negative",
  pending_approval: "warning",
  failed: "negative",
  informational: "neutral",
};

/**
 * One decision on two lines (design lot 2): 1) what and the values, in ink, the outcome on the right; 2) when, who and
 * what it touched, in grey; then the reason. Only «ID richiesta» in sight; the command and approval codes behind
 * «Dettagli».
 */
function DecisionRow({ d, tz, ruleLabels }: { d: Decision; tz: string; ruleLabels: Record<string, string> }) {
  const devices = useApartmentStore((s) => s.devices);
  const [open, setOpen] = useState(false);
  const actor = describeActor(d.actor, ruleLabels);
  const target = d.target.type === "device" ? deviceLabel(d.target.device_id, devices) : t(`decisions.target.${d.target.type}`);
  const codes = Boolean(d.command_id || d.approval_id);
  return (
    <li className="space-y-1 py-4" data-testid={`decision-row-${d.decision_id}`} data-actor={actor.kind} data-outcome={d.outcome}>
      <div className="flex items-start gap-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm font-semibold">
          {/* The kind of action in Italian (D-125); the engine's code stays in the tooltip, and shows for a new one. */}
          <span title={d.action} data-testid={`decision-action-${d.decision_id}`}>{actionLabel(d.action)}</span>
          {(d.old_value || d.new_value) && (
            <span className="inline-flex flex-wrap items-center gap-1 font-normal">
              <span className="text-muted-foreground">{decisionValue(d.old_value)}</span>
              <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
              <span className="font-semibold">{decisionValue(d.new_value)}</span>
            </span>
          )}
        </div>
        <StatusBadge tone={OUTCOME_TONE[d.outcome]} className="shrink-0" data-testid={`decision-outcome-${d.decision_id}`}>{t(`decisions.outcome.${d.outcome}`)}</StatusBadge>
      </div>
      <div className="text-[13px] text-muted-foreground">
        <span className="tabular">{fmtDateTime(d.ts, tz)}</span> · <span className="font-medium text-foreground" data-testid={`decision-actor-${d.decision_id}`}>{actor.label}</span> · {target}
      </div>
      <p className="text-sm text-muted-foreground" data-testid={`decision-reasoning-${d.decision_id}`}>{d.reasoning}</p>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-1 text-xs text-muted-foreground">
        <CopyableId id={d.correlation_id} testId={`decision-correlation-${d.decision_id}`} />
        {codes && (
          <button type="button" className="flex items-center gap-1 font-medium hover:text-foreground focus-ring [&_svg]:size-3.5" aria-expanded={open} onClick={() => setOpen((o) => !o)} data-testid={`decision-details-toggle-${d.decision_id}`}>
            {open ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />} {t("decisions.details")}
          </button>
        )}
      </div>
      {open && codes && (
        <dl className="grid gap-x-4 gap-y-0.5 text-xs text-muted-foreground sm:grid-cols-[auto_1fr]" data-testid={`decision-details-${d.decision_id}`}>
          {d.command_id && (
            <>
              <dt className="font-medium">{t("decisions.commandId")}</dt>
              <dd className="tabular break-all">{d.command_id}</dd>
            </>
          )}
          {d.approval_id && (
            <>
              <dt className="font-medium">{t("decisions.approvalId")}</dt>
              <dd className="tabular break-all">{d.approval_id}</dd>
            </>
          )}
        </dl>
      )}
    </li>
  );
}

/** Period menu: days back from now (0 = the whole log, at least 90 days by contract). */
const PERIODS = [0, 7, 30, 90] as const;
const periodLabel = (days: number) =>
  days === 7 ? t("decisions.period7") : days === 30 ? t("decisions.period30") : days === 90 ? t("decisions.period90") : t("decisions.periodAll");

export default function DecisionsPage() {
  const { aptId = "" } = useParams();
  const devices = useApartmentStore((s) => s.devices);
  const tz = useApartmentStore((s) => s.apartment?.timezone) ?? DEFAULT_TZ;
  const [actor, setActor] = useState("");
  const [deviceId, setDeviceId] = useState("");
  // `from` is computed once, when the period is chosen: it is part of the query key and must not move per render.
  const [period, setPeriod] = useState<{ days: number; from?: string }>({ days: 0 });
  const [text, setText] = useState("");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const activeFilters = (actor ? 1 : 0) + (deviceId ? 1 : 0) + (period.days ? 1 : 0);
  const rules = useQuery({ queryKey: ["rules", aptId], queryFn: () => instanceApi(aptId).getRules(), staleTime: 300_000 });
  const ruleLabels = useMemo(() => Object.fromEntries((rules.data?.rules ?? []).map((r) => [r.rule_id, r.label])), [rules.data]);

  const filters = useMemo(() => ({ actor, device_id: deviceId, from: period.from }), [actor, deviceId, period.from]);
  const log = useDecisionLog(aptId, filters);
  const search = useDecisionSearch(aptId, filters, text, (d, needle) =>
    matchesDecision(d, needle, {
      actor: describeActor(d.actor, ruleLabels).label,
      target: d.target.type === "device" ? deviceLabel(d.target.device_id, devices) : t(`decisions.target.${d.target.type}`),
      action: actionLabel(d.action),
    }),
  );
  const searching = search.status !== "idle";
  const p = search.progress;
  const items = searching ? p.results : log.items;
  const when = p.oldestTs ? fmtDateTime(p.oldestTs, tz) : "—";

  let status: string | null = null;
  if (search.status === "searching") status = search.mode === "correlation" || p.scanned === 0 ? t("decisions.searchStarting") : t("decisions.searching", { count: p.scanned, when });
  else if (search.status === "ready" && search.mode === "correlation") status = t("decisions.searchCorrelation", { found: p.results.length });
  else if (search.status === "ready") status = p.done ? t("decisions.searchedAll", { found: p.results.length, count: p.scanned }) : t("decisions.searchedUntil", { found: p.results.length, when, count: p.scanned });

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader title={t("decisions.title")} subtitle={t("decisions.subtitle")} testId="decisions-header" />
      {/* the search on one full row; on a phone the three filters open under «Filtri» (design lot 2) */}
      <div className="space-y-3" data-testid="decisions-filters">
        <div className="flex gap-2">
          <Input type="search" className="flex-1" value={text} onChange={(e) => setText(e.target.value)} placeholder={t("decisions.searchPlaceholder")} aria-label={t("common.search")} data-testid="decisions-search-input" />
          <Button variant="outline" className="sm:hidden" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((o) => !o)} data-testid="decisions-filters-toggle">
            <SlidersHorizontal /> {activeFilters ? t("decisions.filtersCount", { count: activeFilters }) : t("decisions.filters")}
          </Button>
        </div>
        <div className={cn("grid gap-3 sm:grid-cols-3", !filtersOpen && "hidden sm:grid")}>
          <NativeSelect value={actor} onChange={(e) => setActor(e.target.value)} aria-label={t("decisions.actor")} data-testid="decisions-actor-select">
            {ACTOR_FILTERS.map((a) => <option key={a} value={a}>{a ? t(`actor.${a}`, { name: "" }).replace(" «»", "") : `${t("decisions.actor")}: ${t("common.all").toLowerCase()}`}</option>)}
          </NativeSelect>
          <NativeSelect value={deviceId} onChange={(e) => setDeviceId(e.target.value)} aria-label={t("decisions.device")} data-testid="decisions-device-select">
            <option value="">{t("decisions.allDevices")}</option>
            {devices.map((d) => <option key={d.device_id} value={d.device_id}>{d.label}</option>)}
          </NativeSelect>
          <NativeSelect value={period.days} onChange={(e) => { const days = Number(e.target.value); setPeriod({ days, from: periodFrom(days) }); }} aria-label={t("decisions.period")} data-testid="decisions-period-select">
            {PERIODS.map((d) => <option key={d} value={d}>{periodLabel(d)}</option>)}
          </NativeSelect>
        </div>
      </div>
      {status && (
        <p className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="decisions-search-status" data-status={search.status} aria-live="polite">
          {search.status === "searching" && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
          {status}
        </p>
      )}
      {p.limited && <p className="text-sm font-medium text-destructive" data-testid="decisions-search-limit">{t("decisions.searchLimit", { max: MAX_RESULTS })}</p>}
      {search.status === "error" && <ErrorNotice error={search.error} onRetry={search.more} testId="decisions-search-error" />}
      {!searching && log.head.error && <ErrorNotice error={log.head.error} onRetry={() => void log.head.refetch()} testId="decisions-error" />}
      {!searching && log.head.isLoading ? (
        <RowsSkeleton rows={4} lines={3} />
      ) : items.length === 0 ? (
        !searching && <Card className="p-10 text-center text-sm text-muted-foreground" data-testid="decisions-empty">{t("decisions.empty")}</Card>
      ) : (
        <Card className="px-5">
          <ul className="divide-y" data-testid="decisions-list">
            {items.map((d) => <DecisionRow key={d.decision_id} d={d} tz={tz} ruleLabels={ruleLabels} />)}
          </ul>
        </Card>
      )}
      {searching ? (
        search.status === "ready" && search.mode === "text" && !p.done && !p.limited && (
          <div className="text-center">
            <Button variant="outline" onClick={search.more} data-testid="decisions-search-more-btn">{t("decisions.searchMore")}</Button>
          </div>
        )
      ) : (
        <>
          {log.moreError ? <ErrorNotice error={log.moreError} onRetry={() => void log.loadMore()} testId="decisions-more-error" /> : null}
          {log.hasMore && (
            <div className="text-center">
              <Button variant="outline" onClick={() => void log.loadMore()} disabled={log.loadingMore} data-testid="decisions-load-more-btn">{t("common.loadMore")}</Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
