import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { platformApi } from "@/api/platform";
import { AdminWebhookLogs } from "@/components/admin/AdminWebhookLogs";
import { PageHeader, SegmentedControl } from "@/components/layout/PageHeader";
import { PlatformAudit } from "@/components/platform/PlatformAudit";
import { PlatformManagers } from "@/components/platform/PlatformManagers";
import { PlatformTenants } from "@/components/platform/PlatformTenants";
import { t } from "@/i18n";
import { OPEN_APARTMENTS_PARAM } from "@/lib/routes";

type Tab = "tenants" | "managers" | "webhooks" | "audit";

/** Organizzazioni (P-36): platform managers only, guarded by PlatformOnly in App. */
export default function OrganizationsPage() {
  const [tab, setTab] = useState<Tab>("tenants");
  const own = useAuth().me?.tenant;
  // "+ Appartamento" on the Appartamenti page lands here with ?appartamenti=<organization>: its apartments open at once.
  const [params, setParams] = useSearchParams();
  const [openTenant] = useState(() => params.get(OPEN_APARTMENTS_PARAM));
  useEffect(() => {
    // Drop the parameter once used, so a reload or "back" does not reopen the list.
    if (params.has(OPEN_APARTMENTS_PARAM)) {
      params.delete(OPEN_APARTMENTS_PARAM);
      setParams(params, { replace: true });
    }
  }, [params, setParams]);
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title={t("platform.title")}
        subtitle={t("platform.subtitle")}
        testId="organizations-header"
        actions={
          <SegmentedControl
            value={tab}
            onChange={setTab}
            testId="platform-tab"
            options={[
              { value: "tenants", label: t("platform.tabTenants") },
              { value: "managers", label: t("platform.tabManagers") },
              { value: "webhooks", label: t("platform.tabUnattributed") },
              { value: "audit", label: t("audit.titlePlatform") },
            ]}
          />
        }
      />
      {own?.suspended && (
        <p role="status" className="rounded-xl border border-negative-border bg-negative-bg px-3 py-2 text-sm font-medium text-negative-fg" data-testid="own-tenant-suspended">
          {t("platform.ownSuspended", { name: own.name })}
        </p>
      )}
      {tab === "tenants" && <PlatformTenants openTenant={openTenant} />}
      {tab === "managers" && <PlatformManagers />}
      {tab === "audit" && <PlatformAudit />}
      {tab === "webhooks" && <AdminWebhookLogs load={platformApi.webhookLogs} queryKey={["platform", "webhook-logs"]} hint={t("platform.unattributedHint")} apartmentNames={false} />}
    </div>
  );
}
