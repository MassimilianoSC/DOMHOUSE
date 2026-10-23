import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Download } from "lucide-react";
import { instanceApi } from "@/api/instance";
import { useApartmentSummary } from "@/hooks/useFeatures";
import { useCurrentStay, usePreviousStayEnergy, type BookingRecord } from "@/hooks/useStays";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { PageHeader, SegmentedControl } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, NativeSelect, Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";
import { downloadEnergyReport, monthLabel, recentMonths, type EnergyReport } from "@/lib/energyExport";
import { DEFAULT_TZ, fmtDateTime, fmtDayMonth, fmtNumber, fmtShortDateTime } from "@/lib/format";
import { useApartmentStore } from "@/store/apartmentStore";

type Period = "today" | "week" | "month" | "stay";

function localMidnight(tz: string, daysBack = 0): Date {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now);
  const get = (k: string) => Number(parts.find((p) => p.type === k)?.value);
  const guess = Date.UTC(get("year"), get("month") - 1, get("day") - daysBack);
  const check = new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", hour: "2-digit", minute: "2-digit" }).formatToParts(new Date(guess));
  const h = Number(check.find((p) => p.type === "hour")?.value), m = Number(check.find((p) => p.type === "minute")?.value);
  return new Date(guess - (h * 60 + m) * 60_000 + (h > 12 ? 86_400_000 : 0));
}

function range(period: Period, tz: string, stayFrom?: string | null) {
  const now = new Date();
  if (period === "stay" && stayFrom) {
    const from = new Date(stayFrom);
    const hours = (now.getTime() - from.getTime()) / 3600_000;
    return { from: from.toISOString(), to: new Date(now.getTime() + 3600_000).toISOString(), bucket: hours < 48 ? ("hour" as const) : ("day" as const) };
  }
  if (period === "today") return { from: localMidnight(tz).toISOString(), to: new Date(now.getTime() + 3600_000).toISOString(), bucket: "hour" as const };
  return { from: localMidnight(tz, period === "week" ? 6 : 29).toISOString(), to: now.toISOString(), bucket: "day" as const };
}

/** One indicator of the strip (design lot 2): label 13 px, value 24 px, unit in grey, an optional note under it. */
function Stat({ label, value, unit, sub, testId }: { label: string; value: string; unit?: string; sub?: React.ReactNode; testId: string }) {
  return (
    <div className="min-w-0 bg-card px-5 py-4" data-testid={testId}>
      <div className="text-[13px] font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular">
        {value} {unit && <span className="text-base font-medium text-muted-foreground">{unit}</span>}
      </div>
      {sub && <div className="mt-1 text-[13px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

/** Downloads an Excel report (P-52); the server's message on a refusal (feature off, apartment disabled, engine down). */
function useReportDownload(aptId: string) {
  const [busy, setBusy] = useState(false);
  const download = async (which: EnergyReport) => {
    setBusy(true);
    await runAction((c) => downloadEnergyReport(aptId, which, c));
    setBusy(false);
  };
  return { busy, download };
}

/** «Scarica Excel» of one stay (where the bookings show: the current stay and the previous one). */
function StayReportButton({ aptId, bookingId, testId, previous }: { aptId: string; bookingId: string; testId: string; previous?: boolean }) {
  const { busy, download } = useReportDownload(aptId);
  return (
    <Button size="sm" variant="outline" disabled={busy} onClick={() => void download({ booking_id: bookingId })} data-testid={testId}>
      <Download /> {previous ? t("energy.exportPreviousStay") : t("energy.exportStay")}
    </Button>
  );
}

/** Monthly report in Excel (P-52, D-92): the last 12 months in the apartment's time zone, the current one first. */
function MonthlyReport({ aptId, tz }: { aptId: string; tz: string }) {
  const months = useMemo(() => recentMonths(tz), [tz]);
  const [month, setMonth] = useState(months[0]);
  const { busy, download } = useReportDownload(aptId);
  return (
    <Card className="flex flex-wrap items-end gap-3 p-5" data-testid="energy-export">
      <div className="min-w-0 flex-1 space-y-1">
        <h2 className="text-base font-semibold">{t("energy.exportTitle")}</h2>
        <p className="text-xs text-muted-foreground">{t("energy.exportHint")}</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <NativeSelect className="w-auto" aria-label={t("energy.exportMonth")} value={month} onChange={(e) => setMonth(e.target.value)} data-testid="energy-export-month">
          {months.map((m) => <option key={m} value={m}>{monthLabel(m)}</option>)}
        </NativeSelect>
        <Button variant="outline" onClick={() => void download({ month })} disabled={busy} data-testid="energy-export-btn"><Download /> {t("energy.exportBtn")}</Button>
      </div>
    </Card>
  );
}

/** The comparison with the previous stay as one line of text (design lot 2); the sign in red only when it is worse. */
function StayComparison({ current, previous, prev, tz, aptId }: { current: number; previous: number; prev: BookingRecord; tz: string; aptId: string }) {
  const delta = previous > 0 ? Math.round(((current - previous) / previous) * 100) : null;
  const up = delta !== null && delta > 0;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm" data-testid="energy-stay-comparison" data-delta={delta ?? ""}>
      <p className="min-w-0 flex-1">
        <span className={up ? "font-semibold text-negative-fg tabular" : "font-semibold tabular"} data-testid="energy-stay-delta">
          {delta === null ? "—" : `${delta > 0 ? "+" : ""}${delta}%`}
        </span>{" "}
        <span className="text-muted-foreground">
          {t("energy.comparison", { from: fmtShortDateTime(prev.checkin_at, tz), to: fmtShortDateTime(prev.checkout_at, tz), kwh: fmtNumber(previous, 2) })}
          {prev.guests ? ` · ${t("energy.guests", { count: prev.guests })}` : ""}
        </span>
      </p>
      <StayReportButton aptId={aptId} bookingId={prev.booking_id} testId="energy-export-previous-stay" previous />
    </div>
  );
}

/** The bucket with the most consumption; null when everything is zero. */
function peakOf(series: { ts: string; kwh: number }[]) {
  return series.reduce<{ ts: string; kwh: number } | null>((m, x) => (x.kwh > (m?.kwh ?? 0) ? x : m), null);
}

export default function EnergyPage() {
  const { aptId = "" } = useParams();
  const tz = useApartmentStore((s) => s.apartment?.timezone) ?? DEFAULT_TZ;
  const { current: stay, previous } = useCurrentStay(aptId);
  const stayFrom = stay?.checkin_at ?? null;
  const stayAvailable = Boolean(stayFrom);
  const [period, setPeriod] = useState<Period>("today");
  const effectivePeriod = period === "stay" && !stayAvailable ? "today" : period;
  const params = useMemo(() => range(effectivePeriod, tz, stayFrom), [effectivePeriod, tz, stayFrom]);
  const q = useQuery({ queryKey: ["energy", aptId, effectivePeriod, effectivePeriod === "stay" ? stayFrom : null], queryFn: () => instanceApi(aptId).getEnergy(params), refetchInterval: 60_000 });
  const prevQ = usePreviousStayEnergy(aptId, effectivePeriod === "stay" ? previous : undefined);
  // D-130: since when the server has measured consumption (the same summary the apartment layout already reads).
  const since = fmtDayMonth(useApartmentSummary(aptId).data?.energy_since, tz);
  const r = q.data;
  const fmtTick = (ts: string) =>
    params.bucket === "hour"
      ? new Intl.DateTimeFormat("it-IT", { hour: "2-digit", timeZone: tz }).format(new Date(ts))
      : new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short", timeZone: tz }).format(new Date(ts));
  const maxDevice = Math.max(1, ...(r?.by_device.map((d) => d.kwh) ?? [1]));
  const peak = r ? peakOf(r.series) : null;

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <PageHeader
        title={t("energy.title")}
        subtitle={t("energy.subtitle")}
        testId="energy-header"
        actions={<SegmentedControl value={effectivePeriod} onChange={setPeriod} testId="energy-period" options={[{ value: "today", label: t("energy.today") }, { value: "week", label: t("energy.week") }, { value: "month", label: t("energy.month") }, ...(stayAvailable ? [{ value: "stay" as const, label: t("energy.stay") }] : [])]} />}
      />
      {effectivePeriod === "stay" && stayFrom && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-xs text-muted-foreground" data-testid="energy-stay-from">{t("energy.stayFrom", { when: fmtDateTime(stayFrom, tz) })}{stay?.guests ? ` · ${t("energy.guests", { count: stay.guests })}` : ""}</p>
          {stay && <StayReportButton aptId={aptId} bookingId={stay.booking_id} testId="energy-export-stay" />}
        </div>
      )}
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="energy-error" />}
      {q.isLoading || !r ? (
        <div className="space-y-4"><div className="grid gap-4 sm:grid-cols-2"><Skeleton className="h-24 rounded-2xl" /><Skeleton className="h-24 rounded-2xl" /></div><Skeleton className="h-72 rounded-2xl" /></div>
      ) : (
        <>
          <div className="space-y-3">
            {/* one strip divided by 1 px lines; «Ore di clima evitate» only once the engine computes them (design lot 2) */}
            <div className={`grid gap-px overflow-hidden rounded-lg border bg-border ${r.avoided_hvac_hours === null ? "sm:grid-cols-2" : "sm:grid-cols-3"}`} data-testid="energy-stats">
              <Stat label={t("energy.total")} value={fmtNumber(r.total_kwh, 2)} unit={t("energy.kwh")} testId="energy-total" />
              <Stat
                label={params.bucket === "hour" ? t("energy.peakHour") : t("energy.peakDay")}
                value={peak ? fmtNumber(peak.kwh, 2) : "—"}
                unit={peak ? t("energy.kwh") : undefined}
                sub={peak ? (params.bucket === "hour" ? t("energy.atHour", { hour: fmtTick(peak.ts) }) : fmtTick(peak.ts)) : undefined}
                testId="energy-peak"
              />
              {r.avoided_hvac_hours !== null && <Stat label={t("energy.avoided")} value={fmtNumber(r.avoided_hvac_hours)} unit="h" sub={t("energy.avoidedHint")} testId="energy-avoided" />}
            </div>
            {effectivePeriod === "stay" && previous && prevQ.data && <StayComparison current={r.total_kwh} previous={prevQ.data.total_kwh} prev={previous} tz={tz} aptId={aptId} />}
          </div>
          <Card className="p-5" data-testid="energy-chart">
            <h2 className="mb-4 text-base font-semibold">{t("energy.chart", { bucket: t(`energy.${params.bucket}`) })} <span className="font-normal text-muted-foreground">({t("energy.kwh")})</span></h2>
            {r.series.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted-foreground" data-testid="energy-empty">{t("energy.empty")}</p>
            ) : (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={r.series} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid stroke="hsl(var(--border))" vertical={false} />
                    <XAxis dataKey="ts" tickFormatter={fmtTick} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} interval="preserveStartEnd" />
                    <YAxis width={40} tickCount={4} tickFormatter={(v: number) => fmtNumber(v, 1)} tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} />
                    <Tooltip
                      cursor={{ fill: "hsl(var(--secondary))" }}
                      contentStyle={{ borderRadius: 6, border: "1px solid hsl(var(--border))", background: "hsl(var(--card))", fontSize: 13, boxShadow: "none" }}
                      separator=""
                      labelFormatter={(v) => (params.bucket === "hour" ? t("energy.atHour", { hour: fmtTick(String(v)) }) : fmtTick(String(v)))}
                      formatter={(v) => [`${fmtNumber(Number(v), 2)} ${t("energy.kwh")}`, ""]}
                    />
                    <Bar dataKey="kwh" fill="hsl(var(--chart-1))" radius={[2, 2, 0, 0]} maxBarSize={36} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
            {since && <p className="mt-3 text-xs text-muted-foreground" data-testid="energy-since">{t("energy.since", { date: since })}</p>}
          </Card>
          <Card className="space-y-3 p-5" data-testid="energy-by-device">
            <h2 className="text-base font-semibold">{t("energy.byDevice")}</h2>
            {r.by_device.map((d) => (
              <div key={d.device_id} className="space-y-1" data-testid={`energy-device-${d.device_id}`}>
                <div className="flex justify-between text-sm"><span className="font-semibold">{d.label}</span><span className="tabular text-muted-foreground">{fmtNumber(d.kwh, 2)} {t("energy.kwh")}</span></div>
                <div className="h-2 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-chart-1" style={{ width: `${Math.round((d.kwh / maxDevice) * 100)}%` }} /></div>
              </div>
            ))}
          </Card>
        </>
      )}
      <MonthlyReport aptId={aptId} tz={tz} />
    </div>
  );
}
