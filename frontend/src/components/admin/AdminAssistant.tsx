import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { adminApi, type AssistantWeek } from "@/api/admin";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { Card, Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { DEFAULT_TZ, fmtNumber, weekRange } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Share of the questions that ended in a quick answer because the model did not answer in time (decision 120). */
const percent = (w: AssistantWeek) => (w.asks > 0 ? (w.timeouts / w.asks) * 100 : 0);
/** The week as «dal 13 al 19 ottobre». The BFF sends calendar dates, Monday and Sunday included (o1 32d50fe): read
 *  as days, with no time zone in between; instants with an exclusive end are still understood. */
const isDate = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s);
const weekLabel = (w: AssistantWeek) =>
  isDate(w.from) && isDate(w.to)
    ? weekRange(`${w.from}T00:00:00Z`, new Date(Date.parse(`${w.to}T00:00:00Z`) + 86_400_000).toISOString(), "UTC")
    : weekRange(w.from, w.to, DEFAULT_TZ);
const quickTotal = (w: AssistantWeek) => w.quick.timeout + w.quick.model_unavailable + w.quick.monthly_cap + w.quick.json_invalid;

/**
 * Amministrazione › Assistente (decision 120, D-183): the organization's questions to the assistant week by week,
 * the timeouts and the quick answers. Weeks above the threshold are highlighted; two complete weeks in a row above it
 * (the server's over_threshold) say that the choice of the model has to be reopened (D-182).
 */
export function AdminAssistant() {
  const q = useQuery({ queryKey: ["admin", "assistant-stats"], queryFn: () => adminApi.assistantStats(8) });
  const data = q.data;
  const weeks = data?.weeks ?? [];
  const threshold = data?.threshold_percent ?? 10;
  const anyAsk = weeks.some((w) => w.asks > 0);
  const causes = weeks.reduce(
    (s, w) => ({ timeout: s.timeout + w.quick.timeout, model_unavailable: s.model_unavailable + w.quick.model_unavailable, monthly_cap: s.monthly_cap + w.quick.monthly_cap, json_invalid: s.json_invalid + w.quick.json_invalid }),
    { timeout: 0, model_unavailable: 0, monthly_cap: 0, json_invalid: 0 },
  );
  return (
    <div className="space-y-4" data-testid="admin-assistant">
      <div>
        <h2 className="text-base font-semibold">{t("admin.assistant.title")}</h2>
        <p className="text-sm text-muted-foreground">{t("admin.assistant.hint")}</p>
      </div>
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="admin-assistant-error" />}
      {q.isLoading && <Skeleton className="h-48 rounded-2xl" />}
      {data?.over_threshold && (
        <p className="flex items-start gap-2 rounded-xl border border-warning-border bg-warning-bg px-3 py-2 text-sm font-semibold text-warning-fg" data-testid="admin-assistant-alert">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {t("admin.assistant.alert", { threshold })}
        </p>
      )}
      {data && !anyAsk && <Card className="p-5 text-sm text-muted-foreground" data-testid="admin-assistant-empty">{t("admin.assistant.empty")}</Card>}
      {data && anyAsk && (
        <Card className="space-y-3 p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" data-testid="admin-assistant-table">
              <thead>
                <tr className="border-b text-left text-xs font-medium text-muted-foreground">
                  <th className="px-4 py-2 font-semibold">{t("admin.assistant.week")}</th>
                  <th className="px-2 py-2 text-right font-semibold">{t("admin.assistant.asks")}</th>
                  <th className="px-2 py-2 text-right font-semibold">{t("admin.assistant.timeouts")}</th>
                  <th className="px-2 py-2 text-right font-semibold">{t("admin.assistant.quick")}</th>
                  <th className="px-4 py-2 text-right font-semibold">{t("admin.assistant.percent")}</th>
                </tr>
              </thead>
              <tbody>
                {weeks.map((w, i) => {
                  const p = percent(w);
                  const over = p > threshold;
                  return (
                    <tr key={w.week} className="border-b last:border-0" data-testid={`admin-assistant-week-${w.week}`} data-over={over}>
                      <td className="px-4 py-2">
                        {weekLabel(w)}
                        {i === 0 && <span className="ml-1 text-xs text-muted-foreground">({t("admin.assistant.current")})</span>}
                      </td>
                      <td className="px-2 py-2 text-right tabular">{w.asks}</td>
                      <td className="px-2 py-2 text-right tabular">{w.timeouts}</td>
                      <td className="px-2 py-2 text-right tabular">{quickTotal(w)}</td>
                      <td className={cn("px-4 py-2 text-right tabular", over && "font-semibold text-warning-fg")}>
                        {over && <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-warning-fg align-middle" aria-hidden />}
                        {w.asks > 0 ? `${fmtNumber(p, 1)} %` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="px-4 pb-3 text-xs text-muted-foreground" data-testid="admin-assistant-causes">{t("admin.assistant.causes", causes)}</p>
        </Card>
      )}
    </div>
  );
}
