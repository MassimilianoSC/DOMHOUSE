import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CalendarRange, ChevronRight } from "lucide-react";
import { summariesApi, type NightsComparison, type SummaryStatus, type WeeklySummary } from "@/api/summaries";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { DEFAULT_TZ, fmtDateTime, fmtDayMonth, fmtNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApartmentStore } from "@/store/apartmentStore";

const part = (d: Date, tz: string, opts: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("it-IT", { ...opts, timeZone: tz }).format(d);

/** «dal 12 al 18 ottobre», «dal 28 settembre al 4 ottobre»: Monday to Sunday in the apartment's time zone; `to` is
 *  the exclusive end (the Monday after, at midnight), so the last day is the instant before it. */
export function weekRange(from: string, to: string, tz: string, now = new Date()): string {
  const first = new Date(from);
  const last = new Date(new Date(to).getTime() - 1);
  const sameMonth = part(first, tz, { month: "numeric", year: "numeric" }) === part(last, tz, { month: "numeric", year: "numeric" });
  const start = sameMonth ? part(first, tz, { day: "numeric" }) : fmtDayMonth(first.toISOString(), tz, now);
  return t("summaries.range", { from: start, to: fmtDayMonth(last.toISOString(), tz, now) });
}

const GREY = "border-stone-300 bg-stone-100 text-stone-600 dark:border-stone-700 dark:bg-stone-800/60 dark:text-stone-300";
const STATUS_STYLE: Record<SummaryStatus, string> = {
  normal: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  anomalous: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300",
  not_comparable: GREY,
  no_nights: GREY,
};

const kwh = (n: number | null) => `${fmtNumber(n, 1)} kWh`;

/** One comparison: «3 notti · 16 kWh per notte · mediana prima 10 kWh» and its state. */
function Comparison({ label, c, testId }: { label: string; c: NightsComparison; testId: string }) {
  const detail =
    c.status === "no_nights"
      ? [t("summaries.noNightsDetail")]
      : [
          c.nights === 1 ? t("summaries.nightsOne") : t("summaries.nights", { count: c.nights }),
          t("summaries.perNight", { kwh: kwh(c.kwh_per_night) }),
          ...(c.status === "not_comparable" || c.median_before === null ? [] : [t("summaries.before", { kwh: kwh(c.median_before) })]),
        ];
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b py-2 last:border-0" data-testid={testId} data-status={c.status}>
      <div className="min-w-0">
        <div className="text-sm font-semibold">{label}</div>
        <div className="text-xs text-muted-foreground tabular">{detail.join(" · ")}</div>
      </div>
      <Badge className={STATUS_STYLE[c.status] ?? GREY}>{t(`summaries.status.${c.status}`)}</Badge>
    </div>
  );
}

function EnergyCard({ energy }: { energy: WeeklySummary["energy"] }) {
  return (
    <Card className="space-y-3 p-5" data-testid="summary-energy">
      <div>
        <h2 className="text-base font-bold md:text-lg">{t("summaries.energyTitle")}</h2>
        <p className="text-xs text-muted-foreground">{t("summaries.energyHint")}</p>
      </div>
      {!energy.available ? (
        <p className="text-sm text-muted-foreground" data-testid="summary-energy-unavailable">{energy.reason}</p>
      ) : (
        <>
          <div>
            <Comparison label={t("summaries.occupied")} c={energy.occupied} testId="summary-energy-occupied" />
            <Comparison label={t("summaries.vacant")} c={energy.vacant} testId="summary-energy-vacant" />
          </div>
          {energy.devices.length > 0 && (
            <div className="space-y-3 pt-2">
              <h3 className="text-sm font-bold">{t("summaries.byDevice")}</h3>
              {energy.devices.map((d) => (
                <div key={d.device_id} className="rounded-xl bg-secondary/50 px-3 py-1" data-testid={`summary-device-${d.device_id}`}>
                  <div className="pt-1 text-xs font-bold uppercase tracking-wide text-muted-foreground">{d.label}</div>
                  <Comparison label={t("summaries.occupied")} c={d.occupied} testId={`summary-device-${d.device_id}-occupied`} />
                  <Comparison label={t("summaries.vacant")} c={d.vacant} testId={`summary-device-${d.device_id}-vacant`} />
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </Card>
  );
}

/** One week (the link of the «Riepilogo» push): the server's sentences, then the energy comparison behind them. */
function SummaryDetail({ aptId, week, tz }: { aptId: string; week: string; tz: string }) {
  const q = useQuery({ queryKey: ["summary", aptId, week], queryFn: () => summariesApi(aptId).get(week), retry: false });
  const s = q.data;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link to={`/a/${aptId}/riepiloghi`} className="inline-flex items-center gap-1 rounded-lg text-sm font-semibold text-primary hover:underline focus-ring" data-testid="summary-back">
        <ArrowLeft className="h-4 w-4" /> {t("summaries.back")}
      </Link>
      <PageHeader
        title={t("summaries.weekTitle")}
        subtitle={s ? `${t("summaries.week", { range: weekRange(s.from, s.to, tz) })} · ${t("summaries.generated", { when: fmtDateTime(s.generated_at, tz) })}` : undefined}
        testId="summary-header"
      />
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="summary-error" />}
      {q.isLoading && <Skeleton className="h-48 rounded-2xl" />}
      {s && (
        <>
          <Card className="p-5" data-testid="summary-items">
            {s.items.length === 0 ? (
              <p className="text-sm text-muted-foreground" data-testid="summary-no-news">{t("summaries.noNews")}</p>
            ) : (
              <ul className="list-disc space-y-2 pl-5 text-sm">
                {s.items.map((item, i) => <li key={i} data-testid="summary-item">{item}</li>)}
              </ul>
            )}
          </Card>
          <EnergyCard energy={s.energy} />
        </>
      )}
    </div>
  );
}

function SummaryList({ aptId, tz }: { aptId: string; tz: string }) {
  const q = useQuery({ queryKey: ["summaries", aptId], queryFn: () => summariesApi(aptId).list() });
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader title={t("summaries.title")} subtitle={t("summaries.subtitle")} testId="summaries-header" />
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="summaries-error" />}
      {q.isLoading && <Skeleton className="h-40 rounded-2xl" />}
      {q.data?.length === 0 && <Card className="p-5 text-sm text-muted-foreground" data-testid="summaries-empty">{t("summaries.empty")}</Card>}
      {q.data && q.data.length > 0 && (
        <Card className="divide-y overflow-hidden p-0" data-testid="summaries-list">
          {q.data.map((w) => (
            <Link key={w.week} to={`/a/${aptId}/riepiloghi/${encodeURIComponent(w.week)}`} className="flex items-center gap-3 px-5 py-4 hover:bg-secondary/60 focus-ring" data-testid={`summary-week-${w.week}`}>
              <CalendarRange className="h-5 w-5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold">{t("summaries.week", { range: weekRange(w.from, w.to, tz) })}</div>
                <div className={cn("text-xs", w.notable ? "font-semibold text-amber-700 dark:text-amber-300" : "text-muted-foreground")} data-testid={`summary-week-${w.week}-count`}>
                  {!w.notable ? t("summaries.nothing") : w.items === 1 ? t("summaries.itemsOne") : t("summaries.items", { count: w.items })}
                </div>
              </div>
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            </Link>
          ))}
        </Card>
      )}
    </div>
  );
}

/** «Riepiloghi» (D-150): the list of the weeks, or one week at /a/:aptId/riepiloghi/:week. Every role. */
export default function SummariesPage() {
  const { aptId = "", week } = useParams();
  const tz = useApartmentStore((s) => s.apartment?.timezone) ?? DEFAULT_TZ;
  return week ? <SummaryDetail aptId={aptId} week={week} tz={tz} /> : <SummaryList aptId={aptId} tz={tz} />;
}
