import { useEffect, useMemo, useRef, useState } from "react";
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
import { DEFAULT_TZ, fmtDateTime, fmtNumber } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApartmentStore } from "@/store/apartmentStore";

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

/** 1098 = b: «Limiti del setpoint» in two groups, winter (heating) and summer (cooling), in the order of their checks;
 *  any other parameter (and every other rule) in one group without a title, as before. */
type Group = { id: string; title?: () => string; keys: string[] };
const GROUPS: Record<string, Group[]> = {
  setpoint_limits: [
    { id: "winter", title: () => t("rules.groups.winter"), keys: ["min", "max", "eco_celsius", "comfort_celsius"] },
    { id: "summer", title: () => t("rules.groups.summer"), keys: ["summer_min", "summer_max", "comfort_cool_celsius"] },
  ],
};

function groupsOf(rule: Rule): Group[] {
  const known = (GROUPS[rule.rule_id] ?? []).map((g) => ({ ...g, keys: g.keys.filter((k) => k in rule.limits) })).filter((g) => g.keys.length);
  const grouped = new Set(known.flatMap((g) => g.keys));
  const rest = Object.keys(rule.limits).filter((k) => !grouped.has(k));
  return rest.length ? [...known, { id: "", keys: rest }] : known;
}

function RuleCard({ rule, draft, onChange, canWrite }: { rule: Rule; draft?: Draft[string]; onChange: (d: Draft[string]) => void; canWrite: boolean }) {
  const editable = canWrite && rule.editable;
  const eff = effective(rule, draft);
  const errs = paramErrors(rule, draft);
  const dirty = draft && (draft.enabled !== undefined || Object.keys(draft.params).length > 0);
  return (
    <Card className={cn("space-y-4 p-5", dirty && "border-primary/50 ring-1 ring-primary/20")} data-testid={`rule-card-${rule.rule_id}`} data-enabled={eff.enabled}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 basis-48">
          <h3 className="text-base font-semibold">{rule.label}</h3>
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
      {groupsOf(rule).map((group) => (
        <div key={group.id} className="space-y-2" data-testid={group.id ? `rule-group-${rule.rule_id}-${group.id}` : undefined}>
          {group.title && <h4 className="text-sm font-semibold">{group.title()}</h4>}
          <div className="grid gap-3 sm:grid-cols-2">
          {group.keys.map((key) => [key, rule.limits[key]] as const).map(([key, lim]) => (
            <div key={key} className="field-cell">
              <label htmlFor={`rule-${rule.rule_id}-${key}`} className="text-[13px] font-medium text-muted-foreground">
                {tOr(`rules.params.${key}`, key)} <span className="font-normal normal-case">({t("rules.range", { min: fmtNumber(lim.min), max: fmtNumber(lim.max) })})</span>
              </label>
              <div className="space-y-1">
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
            </div>
          ))}
          </div>
        </div>
      ))}
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
  const barRef = useRef<HTMLDivElement>(null);
  const [saveError, setSaveError] = useState<unknown>(null);
  const rules = useMemo(() => q.data?.rules ?? [], [q.data]);
  const tz = useApartmentStore((s) => s.apartment?.timezone) ?? DEFAULT_TZ; // P-83, D71: the apartment's clock

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
  // The same checks as the engine, before saving, with its sentences, in its order a–g (lotto 30; 1096/1097 = a;
  // 1098 = b, two ranges): winter min ≤ eco ≤ comfort ≤ winter max; summer min ≤ cooling ≤ summer max; comfort <
  // cooling. a, c, g always; b, d, e, f only when the change touches «Limiti del setpoint», as the engine does: rules
  // saved before that break them are said as a warning, and another rule still saves.
  const v = (k: string) => (slEff !== null && typeof slEff[k] === "number" ? slEff[k] : null);
  const lt = (x: number | null, y: number | null) => x !== null && y !== null && x < y;
  const slTouched = Boolean(sl && patches.some((p) => p.rule_id === sl.rule_id));
  const [min, max, eco, comfort, cool, sMin, sMax] = ["min", "max", "eco_celsius", "comfort_celsius", "comfort_cool_celsius", "summer_min", "summer_max"].map(v);
  const checks: [boolean, string, boolean][] = [   // [fails, message, always]
    [lt(max, min), t("rules.invalidRange"), true],
    [lt(eco, min), t("rules.ecoBelowMin"), false],
    [lt(comfort, eco), t("rules.ecoAboveComfort"), true],
    [lt(max, comfort), t("rules.comfortAboveMax"), false],
    [lt(sMax, sMin), t("rules.summerInvalidRange"), false],
    [lt(cool, sMin) || lt(sMax, cool), t("rules.coolOutsideSummer"), false],
    [cool !== null && comfort !== null && cool <= comfort, t("rules.coolNotAboveComfort"), true],
  ];
  const join = (messages: string[]) => (messages.length ? messages.join(" · ") : null);
  const failing = checks.filter(([fails]) => fails);
  const rangeError = join(failing.filter(([, , always]) => always || slTouched).map(([, k]) => k));
  const rangeWarning = slTouched ? null : join(failing.filter(([, , always]) => !always).map(([, k]) => k));

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

  // Part f: with the keyboard open the save bar (two lines on a phone) covered the field being typed in. While the
  // bar shows, the page scrolls with a bottom margin as tall as the bar, and the focused field is moved above it.
  const barShown = patches.length > 0;
  useEffect(() => {
    const root = document.documentElement;
    const bar = barRef.current;
    if (!barShown || !bar) return;
    const fit = () => {
      root.style.scrollPaddingBottom = `${bar.offsetHeight + 16}px`;
      const el = document.activeElement as HTMLElement | null;
      if (el && el !== document.body && el.getBoundingClientRect().bottom > bar.getBoundingClientRect().top) el.scrollIntoView?.({ block: "nearest" });
    };
    fit();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(fit) : null;
    ro?.observe(bar);
    window.visualViewport?.addEventListener("resize", fit);
    return () => {
      ro?.disconnect();
      window.visualViewport?.removeEventListener("resize", fit);
      root.style.scrollPaddingBottom = "";
    };
  }, [barShown]);
  return (
    <div className="mx-auto max-w-6xl space-y-8 pb-24">
      <PageHeader title={t("rules.title")} subtitle={t("rules.subtitle")} testId="rules-header" />
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="rules-error" />}
      {q.data && <p className="text-xs text-muted-foreground" data-testid="rules-updated-at">{t("rules.updatedAt", { when: fmtDateTime(q.data.updated_at, tz) })}</p>}
      {q.isLoading ? (
        <div className="space-y-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-40 rounded-2xl" />)}</div>
      ) : (
        // one column up to 1024 px; above, two columns that fill top to bottom, so cards of different heights leave no
        // ragged rows (design lot 2)
        <div className="flex flex-col gap-4 lg:block lg:columns-2 lg:gap-4 [&>*]:break-inside-avoid lg:[&>*]:mb-4">
          {rules.map((r) => (
            <RuleCard key={r.rule_id} rule={r} draft={draft[r.rule_id]} canWrite={canWrite} onChange={(d) => setDraft((s) => ({ ...s, [r.rule_id]: d }))} />
          ))}
        </div>
      )}
      {rangeError && <p className="text-sm font-medium text-destructive" data-testid="rules-range-error">{rangeError}</p>}
      {rangeWarning && <p className="rounded-xl border border-warning-border bg-warning-bg px-3 py-2 text-sm font-semibold text-warning-fg" data-testid="rules-range-warning">{t("rules.rangeWarning", { problem: rangeWarning })}</p>}
      {saveError ? <ErrorNotice error={saveError} testId="rules-save-error" /> : null}
      {/* D-151: the assistant proposes (after the rules, design lot 2), the manager applies; whoever only reads does not see it */}
      {canWrite && q.data && (
        <RuleProposalCard
          aptId={aptId}
          hasManualChanges={patches.length > 0}
          onApplied={(res) => qc.setQueryData(["rules", aptId], res)}
          onRulesChanged={() => void q.refetch()}
        />
      )}
      {/* D-151 point 6: the same rules on other apartments of the organization, admins only */}
      {isAdmin && canWrite && q.data && <CopyRulesCard aptId={aptId} hasManualChanges={patches.length > 0} />}
      {patches.length > 0 && (
        // a full bar along the bottom edge, solid with a 1 px top border and a light shadow (design lot 2)
        <div ref={barRef} className="fixed inset-x-0 bottom-0 z-30 border-t bg-card px-4 pb-[calc(0.75rem+env(safe-area-inset-bottom))] pt-3 sm:px-6 lg:px-10 shadow-[0_-4px_12px_hsl(var(--foreground)/0.06)] md:left-64" data-testid="rules-save-bar">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
            <span className="text-sm font-semibold">{patches.length === 1 ? t("rules.dirtyOne") : t("rules.dirty", { count: patches.length })}</span>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => { setDraft({}); setSaveError(null); }} disabled={saving} data-testid="rules-discard-btn">{t("rules.discard")}</Button>
              <Button onClick={save} disabled={saving || hasErrors || Boolean(rangeError)} data-testid="rules-save-btn">{t("rules.save")}</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
