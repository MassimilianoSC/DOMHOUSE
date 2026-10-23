import { useQuery, useQueryClient } from "@tanstack/react-query";
import { adminApi, type AdminApartment } from "@/api/admin";
import type { AppFeature } from "@/api/types";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { Button } from "@/components/ui/button";
import { Card, Skeleton, Switch } from "@/components/ui/primitives";
import { t, tOr } from "@/i18n";
import { runAction } from "@/lib/actions";

function FeatureGrid({ all, value, inherited, onToggle, testId }: { all: AppFeature[]; value: string[] | null; inherited?: string[] | null; onToggle: (f: AppFeature, on: boolean) => void; testId: string }) {
  const effective = value ?? inherited ?? all;
  return (
    <div className="grid gap-2 sm:grid-cols-3" data-testid={testId}>
      {all.map((f) => (
        <label key={f} className="flex items-center justify-between gap-2 rounded-xl bg-secondary/60 px-3 py-2 text-sm font-semibold">
          <span>{tOr(`nav.${f === "ask" ? "assistant" : f === "apartment" ? "overview" : f}`, f)} <span className="tabular text-xs text-muted-foreground">{f}</span></span>
          <Switch checked={effective.includes(f)} onCheckedChange={(on) => onToggle(f, on)} aria-label={f} data-testid={`${testId}-${f}`} />
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
        <FeatureGrid all={all} value={tenant.data?.enabled_features ?? null} onToggle={toggleTenant} testId="tenant-feature" />
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
