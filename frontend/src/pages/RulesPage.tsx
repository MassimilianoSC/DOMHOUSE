import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import type { Rule, RulePatch } from "@/api/types";
import { instanceApi } from "@/api/instance";
import { useRole } from "@/auth/AuthProvider";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { PageHeader } from "@/components/layout/PageHeader";
import { CopyRulesCard } from "@/components/rules/CopyRulesCard";
import { RuleProposalCard } from "@/components/rules/RuleProposalCard";
import { Button } from "@/components/ui/button";
import { Badge, Card, Input, Skeleton, Switch, Tip } from "@/components/ui/primitives";
import { t, tOr } from "@/i18n";
import { runAction } from "@/lib/actions";
import { fmtDateTime, fmtNumber } from "@/lib/format";
import { cn } from "@/lib/utils";

type Draft = Record<string, { enabled?: boolean; params: Record<string, string> }>;

function paramErrors(rule: Rule, draft: Draft[string] | undefined): Record<string, string> {
  const errs: Record<string, string> = {};
  for (const [key, lim] of Object.entries(rule.limits)) {
    const raw = draft?.params[key];
    if (raw === undefined) continue;
    const n = Number(raw);
    if (raw.trim() === "" || Number.isNaN(n) || n < lim.min || n > lim.max) errs[key] = t("rules.outOfRange", { min: fmtNumber(lim.min), max: fmtNumber(lim.max) });
  }
  return errs;
}

function effective(rule: Rule, d?: Draft[string]) {
  const params = { ...rule.params };
  for (const [k, v] of Object.entries(d?.params ?? {})) if (v.trim() !== "" && !Number.isNaN(Number(v))) params[k] = Number(v);
  return { enabled: d?.enabled ?? rule.enabled, params };
}

function RuleCard({ rule, draft, onChange, canWrite }: { rule: Rule; draft?: Draft[string]; onChange: (d: Draft[string]) => void; canWrite: boolean }) {
  const editable = canWrite && rule.editable;
  const eff = effective(rule, draft);
  const errs = paramErrors(rule, draft);
  const dirty = draft && (draft.enabled !== undefined || Object.keys(draft.params).length > 0);
  return (
    <Card className={cn("space-y-4 p-5 animate-fade-up", dirty && "border-primary/50 ring-1 ring-primary/20")} data-testid={`rule-card-${rule.rule_id}`} data-enabled={eff.enabled}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-base font-bold">{rule.label}</h3>
          <p className="text-sm text-muted-foreground">{tOr(`rules.desc.${rule.rule_id}`, "")}</p>
        </div>
        <div className="flex items-center gap-2">
          {!rule.editable && (
            <Tip content={t("rules.lockedHint")}>
              <Badge tabIndex={0} className="border-neutral-border bg-neutral-bg text-neutral-fg" data-testid={`rule-locked-${rule.rule_id}`}>
                <Lock className="h-3 w-3" aria-hidden /> {t("rules.locked")}
              </Badge>
            </Tip>
          )}
          <Switch
            checked={eff.enabled}
            disabled={!editable}
            aria-disabled={!editable}
            aria-label={rule.label}
            onCheckedChange={(v) => onChange({ enabled: v === rule.enabled ? undefined : v, params: draft?.params ?? {} })}
            data-testid={`rule-toggle-${rule.rule_id}`}
          />
        </div>
      </div>
      {Object.keys(rule.limits).length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {Object.entries(rule.limits).map(([key, lim]) => (
            <div key={key} className="space-y-1">
              <label htmlFor={`rule-${rule.rule_id}-${key}`} className="text-[13px] font-medium text-muted-foreground">
                {tOr(`rules.params.${key}`, key)} <span className="font-normal normal-case">({t("rules.range", { min: fmtNumber(lim.min), max: fmtNumber(lim.max) })})</span>
              </label>
              <Input
                id={`rule-${rule.rule_id}-${key}`}
                type="number"
                inputMode="decimal"
                min={lim.min}
                max={lim.max}
                step={Number.isInteger(lim.min) && Number.isInteger(lim.max) ? 1 : 0.5}
                value={draft?.params[key] ?? String(rule.params[key] ?? "")}
                disabled={!editable}
                aria-disabled={!editable}
                aria-invalid={Boolean(errs[key])}
                onChange={(e) => {
                  const params = { ...(draft?.params ?? {}) };
                  if (e.target.value === String(rule.params[key])) delete params[key];
                  else params[key] = e.target.value;
                  onChange({ enabled: draft?.enabled, params });
                }}
                className={cn("tabular", errs[key] && "border-destructive focus-visible:ring-destructive")}
                data-testid={`rule-param-${rule.rule_id}-${key}`}
              />
              {errs[key] && <p className="text-xs font-medium text-destructive" data-testid={`rule-param-error-${rule.rule_id}-${key}`}>{errs[key]}</p>}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default function RulesPage() {
  const { aptId = "" } = useParams();
  const { canWrite, isAdmin } = useRole();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["rules", aptId], queryFn: () => instanceApi(aptId).getRules() });
  const [draft, setDraft] = useState<Draft>({});
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const rules = useMemo(() => q.data?.rules ?? [], [q.data]);

  const patches: RulePatch[] = rules.flatMap((r) => {
    const d = draft[r.rule_id];
    if (!d) return [];
    const p: RulePatch = { rule_id: r.rule_id };
    if (d.enabled !== undefined) p.enabled = d.enabled;
    const params: Record<string, number> = {};
    for (const [k, v] of Object.entries(d.params)) params[k] = Number(v);
    if (Object.keys(params).length) p.params = params;
    return p.enabled === undefined && !p.params ? [] : [p];
  });
  const hasErrors = rules.some((r) => Object.keys(paramErrors(r, draft[r.rule_id])).length > 0);
  const sl = rules.find((r) => r.rule_id === "setpoint_limits");
  const slEff = sl ? effective(sl, draft[sl.rule_id]).params : null;
  // The same checks as the engine, before saving, with its sentences (lotto 30): min ≤ max, and for an engine that has
  // the temperatures of the modes, eco ≤ comfort < cooling.
  const has = (k: string) => slEff !== null && typeof slEff[k] === "number";
  const rangeErrors = slEff
    ? [
        slEff.min > slEff.max ? t("rules.invalidRange") : null,
        has("eco_celsius") && has("comfort_celsius") && slEff.eco_celsius > slEff.comfort_celsius ? t("rules.ecoAboveComfort") : null,
        has("comfort_cool_celsius") && has("comfort_celsius") && slEff.comfort_cool_celsius <= slEff.comfort_celsius ? t("rules.coolNotAboveComfort") : null,
      ].filter((e): e is string => e !== null)
    : [];
  const rangeError = rangeErrors.length ? rangeErrors.join(" · ") : null;

  const save = async () => {
    setSaving(true);
    setSaveError(null);
    const res = await runAction(
      (c) => instanceApi(aptId).updateRules({ rules: patches }, c).catch((e) => { setSaveError(e); throw e; }),
      { success: t("rules.saved") },
    );
    setSaving(false);
    if (res) {
      setDraft({});
      qc.setQueryData(["rules", aptId], res);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-8 pb-24">
      <PageHeader title={t("rules.title")} subtitle={t("rules.subtitle")} testId="rules-header" />
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="rules-error" />}
      {/* D-151: the assistant proposes, the manager applies; whoever only reads does not see it */}
      {canWrite && q.data && (
        <RuleProposalCard
          aptId={aptId}
          hasManualChanges={patches.length > 0}
          onApplied={(res) => qc.setQueryData(["rules", aptId], res)}
          onRulesChanged={() => void q.refetch()}
        />
      )}
      {q.data && <p className="text-xs text-muted-foreground" data-testid="rules-updated-at">{t("rules.updatedAt", { when: fmtDateTime(q.data.updated_at) })}</p>}
      {q.isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-40 rounded-2xl" />)}</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {rules.map((r) => (
            <RuleCard key={r.rule_id} rule={r} draft={draft[r.rule_id]} canWrite={canWrite} onChange={(d) => setDraft((s) => ({ ...s, [r.rule_id]: d }))} />
          ))}
        </div>
      )}
      {rangeError && <p className="text-sm font-medium text-destructive" data-testid="rules-range-error">{rangeError}</p>}
      {saveError ? <ErrorNotice error={saveError} testId="rules-save-error" /> : null}
      {/* D-151 point 6: the same rules on other apartments of the organization, admins only */}
      {isAdmin && canWrite && q.data && <CopyRulesCard aptId={aptId} hasManualChanges={patches.length > 0} />}
      {patches.length > 0 && (
        <div className="fixed inset-x-0 bottom-20 z-30 mx-auto flex w-[calc(100%-2rem)] max-w-3xl flex-wrap items-center justify-between gap-3 rounded-2xl border bg-card/95 p-3 shadow-lg backdrop-blur md:bottom-6 animate-fade-up" data-testid="rules-save-bar">
          <span className="text-sm font-semibold">{t("rules.dirty", { count: patches.length })}</span>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={() => { setDraft({}); setSaveError(null); }} disabled={saving} data-testid="rules-discard-btn">{t("rules.discard")}</Button>
            <Button onClick={save} disabled={saving || hasErrors || Boolean(rangeError)} data-testid="rules-save-btn">{t("rules.save")}</Button>
          </div>
        </div>
      )}
    </div>
  );
}
