import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PLATFORM_SCOPE, platformApi } from "@/api/platform";
import { AuditLog } from "@/components/audit/AuditLog";
import { PlatformError } from "@/components/platform/PlatformError";
import { Label, NativeSelect } from "@/components/ui/primitives";
import { t } from "@/i18n";

/**
 * Organizzazioni > Registro attività (P-47): the log of one organization at a time (the BFF wants tenant_id), or the
 * platform's own actions. Starts on the first organization; without any, on the platform's log.
 */
export function PlatformAudit() {
  const tenants = useQuery({ queryKey: ["platform", "tenants"], queryFn: platformApi.tenants });
  const [chosen, setChosen] = useState<string | null>(null);
  const scope = chosen ?? tenants.data?.[0]?.tenant_id ?? (tenants.isLoading ? null : PLATFORM_SCOPE);
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor="audit-scope">{t("audit.scope")}</Label>
        <NativeSelect id="audit-scope" className="w-auto max-w-full" value={scope ?? ""} disabled={!scope} onChange={(e) => setChosen(e.target.value)} data-testid="audit-scope-select">
          {tenants.data?.map((tn) => <option key={tn.tenant_id} value={tn.tenant_id}>{tn.name}</option>)}
          <option value={PLATFORM_SCOPE}>{t("audit.platformScope")}</option>
        </NativeSelect>
      </div>
      {tenants.error && <PlatformError error={tenants.error} onRetry={() => void tenants.refetch()} testId="audit-tenants-error" />}
      {scope && <AuditLog key={scope} load={(before) => platformApi.audit(scope, before)} queryKey={["platform", "audit", scope]} hint={t("audit.platformHint")} />}
    </div>
  );
}
