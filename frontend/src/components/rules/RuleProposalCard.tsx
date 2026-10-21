import { useState } from "react";
import { Sparkles } from "lucide-react";
import { ApiError } from "@/api/bff";
import { PROPOSAL_MAX_CHARS, ruleProposalApi, type RuleProposal } from "@/api/ruleProposals";
import type { RuleSet } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction, showError } from "@/lib/actions";
import { changeValue, fieldLabel } from "@/lib/ruleChanges";
import { cn, newCorrelationId } from "@/lib/utils";
import { toast } from "sonner";

/**
 * «Chiedi all'assistente» on the Regole page (D-151, level 2): the manager writes what to change, the server answers
 * with a checked proposal, the manager sees before and after and applies it. Nothing changes until «Applica».
 * Operators and admins only: the page does not render it for whoever only reads.
 */
export function RuleProposalCard({ aptId, hasManualChanges, onApplied, onRulesChanged }: {
  aptId: string;
  /** Unsaved changes made by hand: «Applica» waits until they are saved or discarded, so two edits never mix. */
  hasManualChanges: boolean;
  onApplied: (rules: RuleSet) => void;
  /** 409 rules_changed: the rules changed meanwhile; the page reads them again. */
  onRulesChanged: () => void;
}) {
  const api = ruleProposalApi(aptId);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState<"ask" | "apply" | null>(null);
  const [proposal, setProposal] = useState<RuleProposal | null>(null);
  const tooLong = text.length > PROPOSAL_MAX_CHARS;

  const ask = async () => {
    setBusy("ask");
    setProposal(null);
    const res = await runAction((c) => api.propose(text.trim(), c));
    setBusy(null);
    if (res) setProposal(res);
  };

  const apply = async () => {
    if (!proposal) return;
    setBusy("apply");
    const correlationId = newCorrelationId();
    try {
      const rules = await api.apply(proposal, correlationId);
      toast.success(t("rules.proposal.applied"));
      setProposal(null);
      setText("");
      onApplied(rules);
    } catch (err) {
      showError(err, correlationId);
      if (err instanceof ApiError && err.code === "rules_changed") {
        setProposal(null);
        onRulesChanged();
      }
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card className="space-y-4 p-5" data-testid="rule-proposal">
      <div className="flex items-start gap-3">
        <span className="rounded-xl bg-accent/15 p-2 text-accent"><Sparkles className="h-5 w-5" /></span>
        <div>
          <h2 className="text-base font-bold md:text-lg">{t("rules.proposal.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("rules.proposal.hint")}</p>
        </div>
      </div>
      <div className="space-y-1">
        <textarea
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("rules.proposal.placeholder")}
          aria-label={t("rules.proposal.title")}
          aria-invalid={tooLong}
          disabled={busy !== null}
          className={cn("w-full resize-y rounded-xl border border-input bg-card px-3.5 py-2.5 text-sm focus-ring placeholder:text-muted-foreground", tooLong && "border-destructive")}
          data-testid="rule-proposal-text"
        />
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className={cn("text-xs tabular", tooLong ? "font-medium text-destructive" : "text-muted-foreground")} data-testid="rule-proposal-counter">
            {t("rules.proposal.counter", { count: text.length, max: PROPOSAL_MAX_CHARS })}
          </span>
          <Button onClick={() => void ask()} disabled={busy !== null || !text.trim() || tooLong} data-testid="rule-proposal-ask">
            <Sparkles /> {busy === "ask" ? t("rules.proposal.asking") : t("rules.proposal.ask")}
          </Button>
        </div>
      </div>
      {proposal && proposal.changes.length === 0 && (
        <p className="rounded-xl bg-secondary/60 px-3 py-2 text-sm" data-testid="rule-proposal-none">{proposal.explanation}</p>
      )}
      {proposal && proposal.changes.length > 0 && (
        <div className="space-y-3 rounded-xl border border-primary/40 bg-primary/5 p-4" data-testid="rule-proposal-result">
          <h3 className="text-sm font-bold">{t("rules.proposal.changesTitle")}</h3>
          <ul className="space-y-2">
            {proposal.changes.map((c) => (
              <li key={`${c.rule_id}-${c.field}`} className="text-sm" data-testid={`rule-proposal-change-${c.rule_id}-${c.field}`}>
                <span className="font-semibold">{c.label}</span>
                <span className="text-muted-foreground"> · {fieldLabel(c.field)}: </span>
                <span className="tabular">{changeValue(c.field, c.old)} → <strong>{changeValue(c.field, c.new)}</strong></span>
              </li>
            ))}
          </ul>
          {proposal.explanation && <p className="text-sm text-muted-foreground" data-testid="rule-proposal-explanation">{proposal.explanation}</p>}
          {hasManualChanges && <p className="text-xs font-medium text-amber-700 dark:text-amber-300" data-testid="rule-proposal-unsaved">{t("rules.proposal.unsaved")}</p>}
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="ghost" onClick={() => setProposal(null)} disabled={busy !== null} data-testid="rule-proposal-discard">{t("rules.proposal.discard")}</Button>
            <Button onClick={() => void apply()} disabled={busy !== null || hasManualChanges} data-testid="rule-proposal-apply">{t("rules.proposal.apply")}</Button>
          </div>
        </div>
      )}
    </Card>
  );
}
