import { useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi, type AdminApartment } from "@/api/admin";
import type { AppFeature } from "@/api/types";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { Button } from "@/components/ui/button";
import { Card, Skeleton, Switch } from "@/components/ui/primitives";
import { t, tOr } from "@/i18n";
import { runAction } from "@/lib/actions";

/** A feature by the name of its menu entry («Consumi», «Assistente»), never by its code. */
export const featureName = (f: string) => tOr(`nav.${f === "ask" ? "assistant" : f === "apartment" ? "overview" : f}`, f);

/** One line on what each function shows, for the organization's list (design lot 2). */
const EXPLAIN: Record<string, () => string> = {
  apartment: () => t("admin.features.explain.apartment"),
  devices: () => t("admin.features.explain.devices"),
  commands: () => t("admin.features.explain.commands"),
  energy: () => t("admin.features.explain.energy"),
  schedule: () => t("admin.features.explain.schedule"),
  rules: () => t("admin.features.explain.rules"),
  approvals: () => t("admin.features.explain.approvals"),
  decisions: () => t("admin.features.explain.decisions"),
  ask: () => t("admin.features.explain.ask"),
};

/**
 * The switches of the functions (design lot 2). `explained`: one column, each with its line of explanation (the
 * organization's list); otherwise a compact grid of names and switches (each apartment's exceptions).
 */
function FeatureGrid({ all, value, inherited, onToggle, testId, explained }: { all: AppFeature[]; value: string[] | null; inherited?: string[] | null; onToggle: (f: AppFeature, on: boolean) => void; testId: string; explained?: boolean }) {
  const effective = value ?? inherited ?? all;
  return (
    <div className={explained ? "divide-y" : "grid gap-x-6 sm:grid-cols-2 lg:grid-cols-3"} data-testid={testId}>
      {all.map((f) => (
        <label key={f} className={explained ? "flex items-center justify-between gap-4 py-3" : "flex items-center justify-between gap-2 border-b py-2 text-sm"}>
          <span className="min-w-0">
            <span className="block text-sm font-semibold">{featureName(f)}</span>
            {explained && EXPLAIN[f] && <span className="block text-[13px] text-muted-foreground">{EXPLAIN[f]()}</span>}
          </span>
          <Switch checked={effective.includes(f)} onCheckedChange={(on) => onToggle(f, on)} aria-label={featureName(f)} data-testid={`${testId}-${f}`} />
        </label>
      ))}
    </div>
  );
}

export function AdminFeatures() {
  const qc = useQueryClient();
  const tenant = useQuery({ queryKey: ["admin", "tenant"], queryFn: adminApi.tenant });
  const apts = useQuery({ queryKey: ["admin", "apartments"], queryFn: adminApi.apartments });
  const all = tenant.data?.all_features ?? [];
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["admin"] });
    void qc.invalidateQueries({ queryKey: ["apartments"] });
    void qc.invalidateQueries({ queryKey: ["apartment-summary"] });
  };

  const toggleTenant = async (f: AppFeature, on: boolean) => {
    const current = tenant.data?.enabled_features ?? all;
    const next = on ? [...new Set([...current, f])] : current.filter((x) => x !== f);
    const res = await runAction((c) => adminApi.patchTenant({ enabled_features: next }, c), { success: t("admin.features.saved") });
    if (res) refresh();
  };

  const toggleApt = async (a: AdminApartment, f: AppFeature, on: boolean) => {
    const current = a.enabled_features ?? tenant.data?.enabled_features ?? all;
    const next = on ? [...new Set([...current, f])] : current.filter((x) => x !== f);
    const res = await runAction((c) => adminApi.patchApartment(a.apartment_id, { enabled_features: next }, c), { success: t("admin.features.saved") });
    if (res) refresh();
  };

  const resetApt = async (a: AdminApartment) => {
    const res = await runAction((c) => adminApi.patchApartment(a.apartment_id, { clear_features: true }, c), { success: t("admin.features.saved") });
    if (res) refresh();
  };

  if (tenant.error) return <ErrorNotice error={tenant.error} onRetry={() => void tenant.refetch()} testId="admin-features-error" />;
  if (tenant.isLoading || apts.isLoading) return <Skeleton className="h-48 rounded-2xl" />;

  return (
    <div className="space-y-6">
      <Card className="space-y-3 p-5" data-testid="admin-tenant-features">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-semibold">{t("admin.features.tenant", { name: tenant.data?.name ?? "" })}</h2>
          {tenant.data?.enabled_features !== null && (
            <Button size="sm" variant="ghost" onClick={async () => { const r = await runAction((c) => adminApi.patchTenant({ clear_features: true }, c), { success: t("admin.features.saved") }); if (r) refresh(); }} data-testid="admin-tenant-features-reset">{t("admin.features.enableAll")}</Button>
          )}
        </div>
        <p className="text-sm text-muted-foreground">{t("admin.features.tenantHint")}</p>
        <FeatureGrid all={all} value={tenant.data?.enabled_features ?? null} onToggle={toggleTenant} testId="tenant-feature" explained />
      </Card>
      {apts.data?.map((a) => (
        <Card key={a.apartment_id} className="space-y-3 p-5" data-testid={`admin-apartment-features-${a.apartment_id}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-base font-semibold">{a.name}</h3>
            <span className="text-xs text-muted-foreground">
              {a.enabled_features === null ? t("admin.features.inherit") : t("admin.features.override")}
              {a.enabled_features !== null && <Button size="sm" variant="ghost" className="ml-2" onClick={() => resetApt(a)} data-testid={`admin-apartment-features-reset-${a.apartment_id}`}>{t("admin.features.resetToTenant")}</Button>}
            </span>
          </div>
          <FeatureGrid all={all} value={a.enabled_features} inherited={tenant.data?.enabled_features} onToggle={(f, on) => toggleApt(a, f, on)} testId={`apt-feature-${a.apartment_id}`} />
        </Card>
      ))}
    </div>
  );
}
