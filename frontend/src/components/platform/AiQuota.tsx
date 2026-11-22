import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { platformApi, type AiQuotaView } from "@/api/platform";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { showError } from "@/lib/actions";
import { fmtEuro, monthLabel, parseQuota } from "@/lib/aiQuota";
import { newCorrelationId } from "@/lib/utils";

/**
 * F-13: «Quota mensile dell'assistente (€)» in an organisation's card (platform managers only). Empty = the project's
 * cap; 0 = only quick answers; the limits and their sentence come from the server (422 invalid_quota). A server
 * without the route (or any error reading it): the block is not shown.
 */
export function AiQuota({ tenantId, tenantName }: { tenantId: string; tenantName: string }) {
  const qc = useQueryClient();
  const key = ["platform", "ai-quota", tenantId];
  const q = useQuery({ queryKey: key, queryFn: () => platformApi.aiQuota(tenantId), retry: false });
  const [typed, setTyped] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (!q.data) return null;
  const d = q.data;
  const value = typed ?? (d.quota_eur === null ? "" : fmtEuro(d.quota_eur));
  const next = parseQuota(value);
  const changed = next !== undefined && next !== d.quota_eur;
  const id = `ai-quota-${tenantId}`;

  const save = async () => {
    if (next === undefined) return;
    const correlationId = newCorrelationId();
    setSaving(true);
    try {
      const saved = await platformApi.setAiQuota(tenantId, next, correlationId);
      qc.setQueryData<AiQuotaView>(key, saved);
      setTyped(null);
      toast.success(saved.quota_eur === null ? t("platform.aiQuota.removed", { name: tenantName }) : t("platform.aiQuota.saved", { name: tenantName, quota: fmtEuro(saved.quota_eur) }));
    } catch (err) {
      // the server's limits, in its own sentence, under the field
      if (err instanceof ApiError && err.code === "invalid_quota") setProblem(err.message);
      else showError(err, correlationId);
    } finally {
      setSaving(false);
    }
  };

  const month = monthLabel(d.month);
  return (
    <div className="space-y-1.5 border-t pt-3 text-sm" data-testid={`tenant-ai-quota-${tenantId}`}>
      <Label htmlFor={id}>{t("platform.aiQuota.label")}</Label>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          id={id}
          inputMode="decimal"
          className="w-32"
          value={value}
          aria-invalid={Boolean(problem)}
          aria-describedby={`${id}-spent ${id}-rules${problem ? ` ${id}-problem` : ""}`}
          onChange={(e) => {
            setTyped(e.target.value);
            setProblem(null);
          }}
          data-testid={`tenant-ai-quota-input-${tenantId}`}
        />
        <Button variant="outline" size="sm" onClick={() => void save()} disabled={saving || !changed} data-testid={`tenant-ai-quota-save-${tenantId}`}>
          {t("common.save")}
        </Button>
      </div>
      {problem && <p id={`${id}-problem`} className="text-xs font-medium text-negative-fg" role="alert" data-testid={`tenant-ai-quota-problem-${tenantId}`}>{problem}</p>}
      <p id={`${id}-spent`} className="text-xs text-muted-foreground" data-testid={`tenant-ai-quota-spent-${tenantId}`}>
        {d.quota_eur === null
          ? t("platform.aiQuota.spentNoQuota", { month, spent: fmtEuro(d.spent_eur), cap: fmtEuro(d.project_cap_eur), projectSpent: fmtEuro(d.project_spent_eur) })
          : t("platform.aiQuota.spentWithQuota", { month, spent: fmtEuro(d.spent_eur), quota: fmtEuro(d.quota_eur) })}
      </p>
      <p id={`${id}-rules`} className="text-xs text-muted-foreground">{t("platform.aiQuota.rules")}</p>
    </div>
  );
}
