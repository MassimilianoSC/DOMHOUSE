import "@/i18n/pages";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
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
import { Badge, Card, Input, NativeSelect, Skeleton, Switch, Tip } from "@/components/ui/primitives";
import { t, tOr } from "@/i18n";
import { runAction } from "@/lib/actions";
import { DEFAULT_TZ, fmtDateTime, fmtNumber } from "@/lib/format";
import { SEASON_KEYS, ZONES, dayExists, dayName, elides, monthName, seasonParams, zoneOf, type Season, type ZoneId } from "@/lib/heatingSeason";
import { cn } from "@/lib/utils";
import { useApartmentStore } from "@/store/apartmentStore";

type Draft = Record<string, { enabled?: boolean; params: Record<string, string> }>;

/** Item 15: the four numbers of the heating season, drawn as two dates inside the winter group (SeasonBlock). */
const SEASON_PARAMS: string[] = Object.values(SEASON_KEYS);

function paramErrors(rule: Rule, draft: Draft[string] | undefined): Record<string, string> {
  const errs: Record<string, string> = {};
  for (const [key, lim] of Object.entries(rule.limits)) {
    const raw = draft?.params[key];
    if (raw === undefined) continue;
    const n = Number(raw);
    if (raw.trim() === "" || Number.isNaN(n) || n < lim.min || n > lim.max || (SEASON_PARAMS.includes(key) && !Number.isInteger(n))) errs[key] = t("rules.outOfRange", { min: fmtNumber(lim.min), max: fmtNumber(lim.max) });
  }
  return errs;
}

function effective(rule: Rule, d?: Draft[string]) {
  const params = { ...rule.params };
  for (const [k, v] of Object.entries(d?.params ?? {})) if (v.trim() !== "" && !Number.isNaN(Number(v))) params[k] = Number(v);
  return { enabled: d?.enabled ?? rule.enabled, params };
}

/** 1098 = b: «Limiti del setpoint» in two groups, winter (heating) and summer (cooling), in the order of their checks;
 *  A8: a third one, the split measured by its meter (off_watts, valid also with the rule off: said in its note);
 *  any other parameter (and every other rule) in one group without a title, as before. */
type Group = { id: string; title?: () => string; note?: () => string; keys: string[] };
const GROUPS: Record<string, Group[]> = {
  setpoint_limits: [
    { id: "winter", title: () => t("rules.groups.winter"), keys: ["min", "max", "eco_celsius", "comfort_celsius"] },
    { id: "summer", title: () => t("rules.groups.summer"), keys: ["summer_min", "summer_max", "comfort_cool_celsius"] },
    { id: "split", title: () => t("rules.groups.split"), note: () => t("rules.notes.off_watts"), keys: ["off_watts"] },
  ],
};

/** A problem of the chain of «Limiti del setpoint»: where it shows (under the winter group, between the two groups,
 *  under the summer group), the boxes it concerns, and whether it blocks the save (otherwise a warning). */
type Place = "winter" | "between" | "summer";
type LimitProblem = { place: Place; message: string; keys: string[]; blocking: boolean };

// The same checks as the engine, before saving, with its sentences, in its order a–g (lotto 30; 1096/1097 = a;
// 1098 = b, two ranges): winter min ≤ eco ≤ comfort ≤ winter max; summer min ≤ cooling ≤ summer max; comfort <
// cooling. a, c, g always; b, d, e, f only when the change touches «Limiti del setpoint», as the engine does: rules
// saved before that break them are said as a warning, and another rule still saves.
function limitProblems(sl: Rule | undefined, d: Draft[string] | undefined, touched: boolean): LimitProblem[] {
  if (!sl) return [];
  const p = effective(sl, d).params;
  const v = (k: string) => (typeof p[k] === "number" ? p[k] : null);
  const lt = (x: number | null, y: number | null) => x !== null && y !== null && x < y;
  const [min, max, eco, comfort, cool, sMin, sMax] = ["min", "max", "eco_celsius", "comfort_celsius", "comfort_cool_celsius", "summer_min", "summer_max"].map(v);
  const checks: [boolean, string, boolean, Place, string[]][] = [   // [fails, message, always, place, boxes]
    [lt(max, min), t("rules.invalidRange"), true, "winter", ["min", "max"]],
    [lt(eco, min), t("rules.ecoBelowMin"), false, "winter", ["min", "eco_celsius"]],
    [lt(comfort, eco), t("rules.ecoAboveComfort"), true, "winter", ["eco_celsius", "comfort_celsius"]],
    [lt(max, comfort), t("rules.comfortAboveMax"), false, "winter", ["max", "comfort_celsius"]],
    [lt(sMax, sMin), t("rules.summerInvalidRange"), false, "summer", ["summer_min", "summer_max"]],
    [lt(cool, sMin), t("rules.coolOutsideSummer"), false, "summer", ["summer_min", "comfort_cool_celsius"]],
    [lt(sMax, cool), t("rules.coolOutsideSummer"), false, "summer", ["summer_max", "comfort_cool_celsius"]],
    [cool !== null && comfort !== null && cool <= comfort, t("rules.coolNotAboveComfort"), true, "between", ["comfort_celsius", "comfort_cool_celsius"]],
  ];
  return checks.filter(([fails]) => fails).map(([, message, always, place, keys]) => ({ place, message, keys, blocking: always || touched }));
}

/** The messages of one place: the blocking ones in red, the others as the yellow warning (texts as before). */
function LimitMessages({ ruleId, place, problems }: { ruleId: string; place: Place; problems: LimitProblem[] }) {
  const here = problems.filter((p) => p.place === place);
  const join = (ps: LimitProblem[]) => [...new Set(ps.map((p) => p.message))].join(" · ");
  const errors = here.filter((p) => p.blocking);
  const warnings = here.filter((p) => !p.blocking);
  return (
    <>
      {errors.length > 0 && <p id={`rule-${ruleId}-problem-${place}`} className="text-sm font-medium text-destructive" data-testid={`rules-range-error-${place}`}>{join(errors)}</p>}
      {warnings.length > 0 && <p className="rounded-xl border border-warning-border bg-warning-bg px-3 py-2 text-sm font-semibold text-warning-fg" data-testid={`rules-range-warning-${place}`}>{t("rules.rangeWarning", { problem: join(warnings) })}</p>}
    </>
  );
}

const hasSeason = (rule: Rule) => rule.rule_id === "setpoint_limits" && SEASON_PARAMS.every((k) => k in rule.limits);

type SeasonSide = "start" | "end";
const SEASON_SIDES = [
  ["start", SEASON_KEYS.startMonth, SEASON_KEYS.startDay],
  ["end", SEASON_KEYS.endMonth, SEASON_KEYS.endDay],
] as const;

/** Item 15: a day that does not exist in its month (31 April), said under its date before saving (the engine refuses it
 *  with invalid_date); a month or day outside the limits is the usual check of every box. 29 February is accepted. */
function seasonProblems(rule: Rule, d: Draft[string] | undefined): Partial<Record<SeasonSide, string>> {
  if (!hasSeason(rule)) return {};
  const out: Partial<Record<SeasonSide, string>> = {};
  const value = (key: string) => Number(d?.params[key] ?? rule.params[key]);
  const inLimits = (key: string, v: number) => Number.isInteger(v) && v >= rule.limits[key].min && v <= rule.limits[key].max;
  for (const [side, monthKey, dayKey] of SEASON_SIDES) {
    const month = value(monthKey);
    const day = value(dayKey);
    if (inLimits(monthKey, month) && inLimits(dayKey, day) && !dayExists(month, day)) out[side] = t("rules.season.missingDay", { date: dayName({ month, day }) });
  }
  return out;
}

const MONTHS = Array.from({ length: 12 }, (_, i) => i + 1);

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** «dal 15 ottobre», «dall'8 novembre»; «al 15 aprile», «all'11 marzo» (review point 6). */
function fromTo(season: Season) {
  const date = (d: Season["start"]) => ({ date: dayName(d) });
  return {
    from: elides(season.start.day) ? t("rules.season.fromElided", date(season.start)) : t("rules.season.from", date(season.start)),
    to: elides(season.end.day) ? t("rules.season.toElided", date(season.end)) : t("rules.season.to", date(season.end)),
  };
}

/** Review point 7: the season the boxes hold now; null when one is empty, not a whole number or the date does not
 *  exist, so the summary never shows the saved dates under different boxes. */
function seasonInBoxes(rule: Rule, d: Draft[string] | undefined): Season | null {
  // an empty box reads 0, a day that does not exist
  const read = (key: string) => Number(d?.params[key] ?? rule.params[key] ?? NaN);
  const [sm, sd, em, ed] = [SEASON_KEYS.startMonth, SEASON_KEYS.startDay, SEASON_KEYS.endMonth, SEASON_KEYS.endDay].map(read);
  return dayExists(sm, sd) && dayExists(em, ed) ? { start: { month: sm, day: sd }, end: { month: em, day: ed } } : null;
}

/** The rule's description; review point 1: the sentences of item 15 only with an engine that has its parameters. */
function ruleDescription(rule: Rule): string {
  const noRise = rule.rule_id === "frost_protection" && "no_rise_minutes" in rule.limits;
  return [
    noRise ? t("rules.descSeason.frost_protection") : tOr(`rules.desc.${rule.rule_id}`, ""),
    hasSeason(rule) ? t("rules.descExtra.season") : "",
    noRise ? t("rules.descExtra.noRise") : "",
  ].filter(Boolean).join(" ");
}

/** Item 15 (texts A1–A7 agreed with the memoria storica): start and end of the heating season, the summary with the
 *  climatic zone when the dates are exactly a zone's, the shortcuts A–F, the note. Valid also with the rule off, so the
 *  boxes follow only the right to write. */
function SeasonBlock({ rule, draft, editable, onParams }: { rule: Rule; draft?: Draft[string]; editable: boolean; onParams: (changes: Record<string, string>) => void }) {
  const errs = paramErrors(rule, draft);
  const problems = seasonProblems(rule, draft);
  const season = seasonInBoxes(rule, draft);
  const zone = zoneOf(season);
  const range = !season ? null : zone === "F" ? t("rules.season.allYear") : capitalize(t("rules.season.range", fromTo(season)));
  const boxValue = (key: string) => draft?.params[key] ?? String(rule.params[key] ?? "");
  const zoneLabel = (z: ZoneId) => (z === "F" ? t("rules.season.zoneAllYear", { zone: z }) : t("rules.season.zoneRange", { zone: z, ...fromTo(ZONES[z]) }));
  return (
    <div className="space-y-3 border-t pt-3" data-testid={`rule-season-${rule.rule_id}`}>
      <h5 className="text-sm font-semibold">{t("rules.groups.season")}</h5>
      <div className="grid gap-3 sm:grid-cols-2">
        {SEASON_SIDES.map(([side, monthKey, dayKey]) => {
          const problem = problems[side];
          const errorId = `rule-season-error-${side}`;
          return (
            <div key={side} className="field-cell" data-testid={`rule-season-${side}`}>
              <span className="text-[13px] font-medium text-muted-foreground">{side === "start" ? t("rules.season.start") : t("rules.season.end")}</span>
              <div className="space-y-1">
                <div className="flex gap-2">
                  <Input
                    id={`rule-${rule.rule_id}-${dayKey}`}
                    type="number"
                    inputMode="numeric"
                    min={rule.limits[dayKey].min}
                    max={rule.limits[dayKey].max}
                    step={1}
                    value={boxValue(dayKey)}
                    disabled={!editable}
                    aria-disabled={!editable}
                    aria-label={tOr(`rules.params.${dayKey}`, dayKey)}
                    aria-invalid={Boolean(errs[dayKey] || problem)}
                    aria-describedby={problem ? errorId : undefined}
                    onChange={(e) => onParams({ [dayKey]: e.target.value })}
                    className={cn("w-20 shrink-0 tabular", (errs[dayKey] || problem) && "border-destructive focus-visible:ring-destructive")}
                    data-testid={`rule-param-${rule.rule_id}-${dayKey}`}
                  />
                  <NativeSelect
                    id={`rule-${rule.rule_id}-${monthKey}`}
                    value={boxValue(monthKey)}
                    disabled={!editable}
                    aria-disabled={!editable}
                    aria-label={tOr(`rules.params.${monthKey}`, monthKey)}
                    aria-invalid={Boolean(problem)}
                    aria-describedby={problem ? errorId : undefined}
                    onChange={(e) => onParams({ [monthKey]: e.target.value })}
                    className={cn("min-w-0 flex-1", problem && "border-destructive focus-visible:ring-destructive")}
                    data-testid={`rule-param-${rule.rule_id}-${monthKey}`}
                  >
                    {MONTHS.map((m) => <option key={m} value={String(m)}>{monthName(m)}</option>)}
                  </NativeSelect>
                </div>
                {errs[dayKey] && <p className="text-xs font-medium text-destructive" data-testid={`rule-param-error-${rule.rule_id}-${dayKey}`}>{errs[dayKey]}</p>}
                {problem && <p id={errorId} className="text-xs font-medium text-destructive" data-testid={errorId}>{problem}</p>}
              </div>
            </div>
          );
        })}
      </div>
      {range && <p className="text-sm font-medium" data-testid="rule-season-summary">{zone ? t("rules.season.withZone", { season: range, zone }) : range}</p>}
      <div className="flex flex-wrap items-center gap-2" data-testid="rule-season-zones">
        <span className="text-[13px] text-muted-foreground">{t("rules.season.zones")}</span>
        {(Object.keys(ZONES) as ZoneId[]).map((z) => (
          <Tip key={z} content={zoneLabel(z)}>
            <Button
              type="button"
              variant="outline"
              size="iconSm"
              aria-label={zoneLabel(z)}
              disabled={!editable}
              onClick={() => onParams(Object.fromEntries(Object.entries(seasonParams(ZONES[z])).map(([k, v]) => [k, String(v)])))}
              data-testid={`rule-season-zone-${z}`}
            >
              {z}
            </Button>
          </Tip>
        ))}
      </div>
      <p className="text-xs text-muted-foreground" data-testid="rule-season-note">{t("rules.notes.season")}</p>
    </div>
  );
}

function groupsOf(rule: Rule): Group[] {
  const known = (GROUPS[rule.rule_id] ?? []).map((g) => ({ ...g, keys: g.keys.filter((k) => k in rule.limits) })).filter((g) => g.keys.length);
  const grouped = new Set([...known.flatMap((g) => g.keys), ...(hasSeason(rule) ? SEASON_PARAMS : [])]);
  const rest = Object.keys(rule.limits).filter((k) => !grouped.has(k));
  return rest.length ? [...known, { id: "", keys: rest }] : known;
}

function RuleCard({ rule, draft, onChange, canWrite, problems = [] }: { rule: Rule; draft?: Draft[string]; onChange: (d: Draft[string]) => void; canWrite: boolean; problems?: LimitProblem[] }) {
  const editable = canWrite && rule.editable;
  const eff = effective(rule, draft);
  const errs = paramErrors(rule, draft);
  const dirty = draft && (draft.enabled !== undefined || Object.keys(draft.params).length > 0);
  /** Boxes changed together (a zone's four dates): a value back to the saved one leaves the draft. */
  const setParams = (changes: Record<string, string>) => {
    const params = { ...(draft?.params ?? {}) };
    for (const [key, value] of Object.entries(changes)) {
      if (value === String(rule.params[key])) delete params[key];
      else params[key] = value;
    }
    onChange({ enabled: draft?.enabled, params });
  };
  // D-198: the problems of the chain show under their group (winter, summer; «between» after winter), the boxes they
  // concern get the red border; a place without its group shows at the end of the card, never nowhere.
  const groups = groupsOf(rule);
  const shown = new Set<string>(groups.flatMap((g) => (g.id === "winter" ? ["winter", "between"] : [g.id])));
  const leftover = (["winter", "between", "summer"] as const).filter((p) => !shown.has(p));
  const describedBy = (key: string) => [...new Set(problems.filter((p) => p.blocking && p.keys.includes(key)).map((p) => `rule-${rule.rule_id}-problem-${p.place}`))].join(" ") || undefined;
  return (
    <Card className={cn("space-y-4 p-5", dirty && "border-primary/50 ring-1 ring-primary/20")} data-testid={`rule-card-${rule.rule_id}`} data-enabled={eff.enabled}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1 basis-48">
          <h3 className="text-base font-semibold">{rule.label}</h3>
          <p className="text-sm text-muted-foreground">{ruleDescription(rule)}</p>
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
      {groups.map((group) => (
        <Fragment key={group.id}>
        <div className="space-y-2" data-testid={group.id ? `rule-group-${rule.rule_id}-${group.id}` : undefined}>
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
                  aria-invalid={Boolean(errs[key] || describedBy(key))}
                  aria-describedby={describedBy(key)}
                  onChange={(e) => setParams({ [key]: e.target.value })}
                  className={cn("tabular", (errs[key] || describedBy(key)) && "border-destructive focus-visible:ring-destructive")}
                  data-testid={`rule-param-${rule.rule_id}-${key}`}
                />
                {errs[key] && <p className="text-xs font-medium text-destructive" data-testid={`rule-param-error-${rule.rule_id}-${key}`}>{errs[key]}</p>}
              </div>
            </div>
          ))}
          </div>
          {group.note && <p className="text-xs text-muted-foreground" data-testid={`rule-group-note-${rule.rule_id}-${group.id}`}>{group.note()}</p>}
          {(group.id === "winter" || group.id === "summer") && <LimitMessages ruleId={rule.rule_id} place={group.id} problems={problems} />}
          {group.id === "winter" && hasSeason(rule) && <SeasonBlock rule={rule} draft={draft} editable={canWrite && rule.editable} onParams={setParams} />}
        </div>
        {group.id === "winter" && <LimitMessages ruleId={rule.rule_id} place="between" problems={problems} />}
        </Fragment>
      ))}
      {leftover.map((place) => <LimitMessages key={place} ruleId={rule.rule_id} place={place} problems={problems} />)}
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
  const hasErrors = rules.some((r) => Object.keys(paramErrors(r, draft[r.rule_id])).length > 0 || Object.keys(seasonProblems(r, draft[r.rule_id])).length > 0);
  const sl = rules.find((r) => r.rule_id === "setpoint_limits");
  const slTouched = Boolean(sl && patches.some((p) => p.rule_id === sl.rule_id));
  const problems = limitProblems(sl, sl && draft[sl.rule_id], slTouched);
  // D-198: a grey save button always says why, in the bar; the reason itself is next to its boxes
  const blocked = hasErrors || problems.some((p) => p.blocking);
  const goToError = () => {
    const box = document.querySelector<HTMLInputElement>('[data-testid^="rule-param-"][aria-invalid="true"]');
    box?.scrollIntoView?.({ block: "center" });
    box?.focus({ preventScroll: true });
  };

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
            <RuleCard key={r.rule_id} rule={r} draft={draft[r.rule_id]} canWrite={canWrite} problems={r === sl ? problems : undefined} onChange={(d) => setDraft((s) => ({ ...s, [r.rule_id]: d }))} />
          ))}
        </div>
      )}
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
            <div className="flex flex-col items-start">
              <span className="text-sm font-semibold">{patches.length === 1 ? t("rules.dirtyOne") : t("rules.dirty", { count: patches.length })}</span>
              {blocked && (
                <button type="button" onClick={goToError} className="text-left text-sm font-medium text-destructive underline underline-offset-2 focus-ring rounded-sm" data-testid="rules-save-blocked">
                  {t("rules.saveBlocked")}
                </button>
              )}
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => { setDraft({}); setSaveError(null); }} disabled={saving} data-testid="rules-discard-btn">{t("rules.discard")}</Button>
              <Button onClick={save} disabled={saving || blocked} data-testid="rules-save-btn">{t("rules.save")}</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
