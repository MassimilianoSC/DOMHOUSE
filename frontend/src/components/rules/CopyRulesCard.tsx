import { useMemo, useState } from "react";
import { AlertTriangle, Copy } from "lucide-react";
import { ApiError } from "@/api/bff";
import { ruleCopyApi, type CopyPreview, type CopyResult, type CopyTarget, type Customized } from "@/api/ruleCopy";
import type { RuleChange } from "@/api/ruleProposals";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/primitives";
import { useApartments } from "@/hooks/useFeatures";
import { t } from "@/i18n";
import { runAction, showError } from "@/lib/actions";
import { changeValue, fieldLabel } from "@/lib/ruleChanges";
import { newCorrelationId } from "@/lib/utils";

const lower = (s: string) => (s ? s.charAt(0).toLowerCase() + s.slice(1) : s);

function Changes({ changes, testId }: { changes: RuleChange[]; testId: string }) {
  return (
    <ul className="space-y-1 text-sm" data-testid={testId}>
      {changes.map((c) => (
        <li key={`${c.rule_id}-${c.field}`}>
          <span className="font-semibold">{c.label}</span>
          <span className="text-muted-foreground"> · {fieldLabel(c.field)}: </span>
          <span className="tabular">{changeValue(c.field, c.old)} → <strong>{changeValue(c.field, c.new)}</strong></span>
        </li>
      ))}
    </ul>
  );
}

/** «Ha regole personalizzate che verranno sovrascritte: Avviso dispositivo offline, minuti 60 (predefinito 15)». */
export const customizedText = (list: Customized[]) =>
  t("rules.copy.customized", {
    list: list.map((c) => t("rules.copy.customizedItem", { label: c.label, field: lower(fieldLabel(c.field)), value: changeValue(c.field, c.value), default: changeValue(c.field, c.default) })).join("; "),
  });

function statusText(x: CopyTarget): string | null {
  switch (x.status) {
    case "changes":
      return null;
    case "same":
      return t("rules.copy.same");
    case "disabled":
      return t("rules.copy.disabled");
    case "unreachable":
      return t("rules.copy.unreachable");
    default:
      return x.message || t("rules.copy.refused");
  }
}

function outcomeText(r: CopyResult): string {
  switch (r.outcome) {
    case "applied":
      return t("rules.copy.applied");
    case "same":
      return t("rules.copy.same");
    case "changed_meanwhile":
      return t("rules.copy.changedMeanwhile");
    case "disabled":
      return t("rules.copy.disabledDone");
    case "unreachable":
      return t("rules.copy.unreachableDone");
    default:
      return t("rules.copy.refused");
  }
}

/**
 * «Applica le stesse regole ad altri appartamenti» (D-151 point 6): admins only; the apartments to touch, then a
 * preview with what changes in each and an explicit warning where customized rules will be overwritten, then the
 * outcome per apartment. The saved rules are copied: unsaved changes made by hand must be saved or discarded first.
 */
export function CopyRulesCard({ aptId, hasManualChanges }: { aptId: string; hasManualChanges: boolean }) {
  const api = ruleCopyApi(aptId);
  const all = useApartments();
  const others = useMemo(() => (all.data ?? []).filter((a) => a.apartment_id !== aptId), [all.data, aptId]);
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState<"preview" | "copy" | null>(null);
  const [preview, setPreview] = useState<CopyPreview | null>(null);
  const [results, setResults] = useState<CopyResult[] | null>(null);
  const toTouch = preview?.targets.filter((x) => x.status === "changes").length ?? 0;

  const toggle = (id: string, on: boolean) => setChosen((s) => (on ? [...s, id] : s.filter((x) => x !== id)));

  const askPreview = async () => {
    setBusy("preview");
    setResults(null);
    const res = await runAction((c) => api.preview(chosen, c));
    setBusy(null);
    if (res) setPreview(res);
  };

  const confirm = async () => {
    if (!preview) return;
    setBusy("copy");
    const correlationId = newCorrelationId();
    try {
      const res = await api.copy(preview, correlationId);
      setResults(res.results);
      setPreview(null);
      setChosen([]);
    } catch (err) {
      showError(err, correlationId);
      // The source's rules changed after the preview: nothing was touched; a new preview is needed.
      if (err instanceof ApiError && err.code === "rules_changed") setPreview(null);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className="space-y-4 p-5" data-testid="rules-copy">
      <div className="flex items-start gap-3">
        <span className="rounded-xl bg-accent/15 p-2 text-accent"><Copy className="h-5 w-5" /></span>
        <div>
          <h2 className="text-base font-semibold">{t("rules.copy.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("rules.copy.hint")}</p>
        </div>
      </div>

      {!preview && !results && (
        <>
          {all.data && others.length === 0 && <p className="text-sm text-muted-foreground" data-testid="rules-copy-none">{t("rules.copy.noOthers")}</p>}
          {others.length > 0 && (
            <div className="space-y-2">
              <label className="flex items-center gap-2 text-sm font-semibold">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-primary"
                  checked={chosen.length === others.length}
                  onChange={(e) => setChosen(e.target.checked ? others.map((a) => a.apartment_id) : [])}
                  data-testid="rules-copy-all"
                />
                {t("rules.copy.selectAll")}
              </label>
              <div className="grid gap-1 sm:grid-cols-2">
                {others.map((a) => (
                  <label key={a.apartment_id} className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-secondary/60">
                    <input
                      type="checkbox"
                      className="h-4 w-4 accent-primary"
                      checked={chosen.includes(a.apartment_id)}
                      onChange={(e) => toggle(a.apartment_id, e.target.checked)}
                      data-testid={`rules-copy-target-${a.apartment_id}`}
                    />
                    {a.name}
                  </label>
                ))}
              </div>
            </div>
          )}
          {hasManualChanges && others.length > 0 && <p className="text-xs font-medium text-warning-fg" data-testid="rules-copy-unsaved">{t("rules.proposal.unsaved")}</p>}
          {others.length > 0 && (
            <div className="flex justify-end">
              <Button variant="outline" onClick={() => void askPreview()} disabled={busy !== null || chosen.length === 0 || hasManualChanges} data-testid="rules-copy-preview">
                {busy === "preview" ? t("rules.copy.previewing") : t("rules.copy.preview")}
              </Button>
            </div>
          )}
        </>
      )}

      {preview && (
        <div className="space-y-3" data-testid="rules-copy-preview-result">
          <h3 className="text-sm font-semibold">{t("rules.copy.previewTitle", { from: preview.from.name })}</h3>
          {preview.targets.map((x) => (
            <div key={x.apartment_id} className="space-y-2 rounded-xl border p-3" data-testid={`rules-copy-row-${x.apartment_id}`} data-status={x.status}>
              <div className="text-sm font-bold">{x.name}</div>
              {x.status === "changes" && x.changes && <Changes changes={x.changes} testId={`rules-copy-changes-${x.apartment_id}`} />}
              {statusText(x) && <p className="text-sm text-muted-foreground">{statusText(x)}</p>}
              {x.customized && x.customized.length > 0 && (
                <p className="flex items-start gap-1.5 rounded-lg bg-warning-bg px-2.5 py-2 text-xs font-medium text-warning-fg" data-testid={`rules-copy-customized-${x.apartment_id}`}>
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden /> {customizedText(x.customized)}
                </p>
              )}
            </div>
          ))}
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={() => setPreview(null)} disabled={busy !== null} data-testid="rules-copy-cancel">{t("rules.copy.cancel")}</Button>
            <Button onClick={() => void confirm()} disabled={busy !== null || toTouch === 0} data-testid="rules-copy-confirm">
              {busy === "copy" ? t("rules.copy.copying") : toTouch === 1 ? t("rules.copy.confirmOne") : t("rules.copy.confirm", { count: toTouch })}
            </Button>
          </div>
        </div>
      )}

      {results && (
        <div className="space-y-3" data-testid="rules-copy-results">
          <h3 className="text-sm font-semibold">{t("rules.copy.resultsTitle")}</h3>
          {results.map((r) => (
            <div key={r.apartment_id} className="space-y-1 rounded-xl border p-3" data-testid={`rules-copy-result-${r.apartment_id}`} data-outcome={r.outcome}>
              <div className="text-sm"><span className="font-bold">{r.name}</span> · <span className={r.outcome === "applied" ? "font-semibold text-positive-fg" : "text-muted-foreground"}>{outcomeText(r)}</span></div>
              {r.message && <p className="text-xs text-muted-foreground">{r.message}</p>}
              {r.outcome === "applied" && r.changes && r.changes.length > 0 && <Changes changes={r.changes} testId={`rules-copy-result-changes-${r.apartment_id}`} />}
            </div>
          ))}
          <div className="flex justify-end">
            <Button variant="outline" onClick={() => setResults(null)} data-testid="rules-copy-close">{t("rules.copy.close")}</Button>
          </div>
        </div>
      )}
    </Card>
  );
}
