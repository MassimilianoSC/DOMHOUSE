import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronDown, ChevronUp, Loader2, SendHorizontal, Trash2 } from "lucide-react";
import type { AskStatus } from "@/api/types";
import { ApiError } from "@/api/bff";
import { instanceApi } from "@/api/instance";
import { useRole } from "@/auth/AuthProvider";
import { ChatApproval, type ApprovalOutcome } from "@/components/assistant/ChatApproval";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Badge, Card, Input } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { showError } from "@/lib/actions";
import { newCorrelationId } from "@/lib/utils";
import { cn } from "@/lib/utils";

const SUGGESTIONS = ["off", "temp", "at", "boiler"] as const;

/** A question of the chat; approval_outcome is kept by the site only, so the badge follows the decision (P-75). */
type ChatMessage = AskStatus & { approval_outcome?: ApprovalOutcome };

const OUTCOME_STYLE: Record<ApprovalOutcome, string> = {
  approved: "border-positive-border bg-positive-bg text-positive-fg",
  rejected: "border-neutral-border bg-neutral-bg text-neutral-fg",
  expired: "border-neutral-border bg-neutral-bg text-neutral-fg",
};
const outcomeText = (o: ApprovalOutcome) => (o === "approved" ? t("assistant.outcome.approved") : o === "rejected" ? t("assistant.outcome.rejected") : t("assistant.outcome.expired"));
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function load(aptId: string): ChatMessage[] {
  try {
    return JSON.parse(sessionStorage.getItem(`assistant.${aptId}`) ?? "[]") as ChatMessage[];
  } catch {
    return [];
  }
}

/**
 * One question and its answer (design lot 2): the question on the right in the brand colour (the committente keeps it on
 * the chat bubbles), the answer on the left without a bubble, under the name «Assistente». A state only when it says
 * something (approval needed, its outcome, failure), never «Risposto»; what was done in words, the codes behind
 * «Dettagli».
 */
function Message({ aptId, m, canWrite, onOutcome }: { aptId: string; m: ChatMessage; canWrite: boolean; onOutcome: (askId: string, o: ApprovalOutcome) => void }) {
  const pending = m.status === "pending";
  const [open, setOpen] = useState(false);
  const settled = useCallback((o: ApprovalOutcome) => onOutcome(m.ask_id, o), [onOutcome, m.ask_id]);
  // P-75: once decided, the badge says how, never «richiede approvazione» next to the decision
  const outcome = m.status === "needs_approval" ? m.approval_outcome : undefined;
  const showStatus = m.status === "needs_approval" || m.status === "failed";
  const codes = m.actions.some((a) => a.command_id || a.schedule_id);
  return (
    <div className="space-y-3" data-testid={`ask-message-${m.ask_id}`} data-status={m.status}>
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground [overflow-wrap:anywhere]" data-testid={`ask-text-${m.ask_id}`}>{m.text}</div>
      </div>
      <div className="max-w-[85%] space-y-2 text-sm">
        <div className="text-[13px] font-medium text-muted-foreground">{t("assistant.title")}</div>
        {pending ? (
          <span className="inline-flex items-center gap-2 text-muted-foreground" data-testid={`ask-pending-${m.ask_id}`}><Loader2 className="h-4 w-4 animate-spin" aria-hidden /> {t("assistant.thinking")}</span>
        ) : (
          <p className={cn("[overflow-wrap:anywhere]", m.status === "failed" && "text-negative-fg")} data-testid={`ask-answer-${m.ask_id}`}>{m.answer}</p>
        )}
        {/* D-154: «Sì» / «No» right here, as on the Approvazioni page; whoever only reads sees the question only */}
        {m.status === "needs_approval" && canWrite && <ChatApproval aptId={aptId} askId={m.ask_id} correlationId={m.correlation_id} approvalId={m.approval_id ?? null} onOutcome={settled} />}
        {!pending && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-muted-foreground">
            {showStatus && (
              <Badge className={cn(m.status === "needs_approval" && !outcome && "border-warning-border bg-warning-bg text-warning-fg", outcome && OUTCOME_STYLE[outcome], m.status === "failed" && "border-negative-border bg-negative-bg text-negative-fg")} data-testid={`ask-status-${m.ask_id}`}>
                {outcome ? outcomeText(outcome) : t(`assistant.status.${m.status}`)}
              </Badge>
            )}
            {m.actions.map((a, i) => (
              <span key={i} className="font-medium text-foreground" data-testid={`ask-action-${m.ask_id}-${i}`}>
                {a.type === "command" ? t("assistant.commandSent") : a.type === "schedule" ? t("assistant.scheduleCreated") : t("assistant.rulesChanged")}
              </span>
            ))}
            {m.approval_id && (
              <Link to={`/a/${aptId}/approvazioni`} className="font-semibold text-foreground underline underline-offset-2" data-testid={`ask-approval-link-${m.ask_id}`}>{t("assistant.openApprovals")}</Link>
            )}
            {(m.status === "failed" || m.actions.length > 0 || m.approval_id) && (
              <button type="button" className="flex items-center gap-1 font-medium hover:text-foreground focus-ring [&_svg]:size-3.5" aria-expanded={open} onClick={() => setOpen((o) => !o)} data-testid={`ask-details-toggle-${m.ask_id}`}>
                {open ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />} {t("decisions.details")}
              </button>
            )}
          </div>
        )}
        {open && (
          <div className="space-y-1 text-xs text-muted-foreground" data-testid={`ask-details-${m.ask_id}`}>
            {codes && m.actions.map((a, i) => (a.command_id || a.schedule_id) && (
              <div key={i} className="tabular break-all">{a.type === "command" ? t("assistant.command") : t("assistant.schedule")} {a.command_id ?? a.schedule_id}</div>
            ))}
            {m.status === "failed" && m.reason && <div className="tabular break-all">{m.reason}</div>}
            <CopyableId id={m.correlation_id} testId={`ask-correlation-${m.ask_id}`} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function AssistantPage() {
  const { aptId = "" } = useParams();
  const { canWrite } = useRole();
  const [messages, setMessages] = useState<ChatMessage[]>(() => load(aptId));
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    sessionStorage.setItem(`assistant.${aptId}`, JSON.stringify(messages.slice(-50)));
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, aptId]);

  const update = (m: AskStatus) => setMessages((list) => list.map((x) => (x.ask_id === m.ask_id ? m : x)));
  // P-75: the outcome of the question's approvals, kept with the message (and in the tab's storage) for the badge
  const onOutcome = useCallback((askId: string, o: ApprovalOutcome) =>
    setMessages((list) => (list.some((x) => x.ask_id === askId && x.approval_outcome !== o) ? list.map((x) => (x.ask_id === askId ? { ...x, approval_outcome: o } : x)) : list)), []);

  const send = async (value: string) => {
    const q = value.trim();
    // A reader never asks (P-51): the server refuses ask and getAsk with 403, whatever reaches this function.
    if (!q || sending || !canWrite) return;
    setSending(true);
    setText("");
    const correlationId = newCorrelationId();
    const api = instanceApi(aptId);
    try {
      const ask = await api.ask(q, correlationId);
      setMessages((list) => [...list, ask]);
      setSending(false);
      let current = ask;
      for (let i = 0; i < 30 && current.status === "pending"; i++) {
        await sleep(1000);
        current = await api.getAsk(ask.ask_id);
      }
      if (current.status === "pending") current = { ...current, status: "failed", answer: t("assistant.timeout"), reason: "timeout" };
      update(current);
    } catch (err) {
      setSending(false);
      showError(err, err instanceof ApiError ? err.correlationId : correlationId);
    }
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <PageHeader
        title={t("assistant.title")}
        subtitle={t("assistant.subtitle")}
        testId="assistant-header"
        actions={messages.length > 0 && (
          <Button variant="ghost" size="sm" onClick={() => setMessages([])} data-testid="assistant-clear-btn"><Trash2 /> {t("assistant.clear")}</Button>
        )}
      />
      {/* one container (design lot 2): the conversation above, the form at its bottom, held to the screen's edge */}
      <Card className="flex min-h-[60vh] flex-col p-0" data-testid="assistant-thread">
        <div className="flex flex-1 flex-col gap-6 p-5">
          {messages.length === 0 ? (
            <div className="m-auto max-w-md space-y-4 text-center">
              <p className="text-sm text-muted-foreground" data-testid="assistant-empty">{t("assistant.empty")}</p>
              <div className="flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <Button key={s} variant="outline" size="sm" disabled={!canWrite} onClick={() => void send(t(`assistant.suggestions.${s}`))} data-testid={`assistant-suggestion-${s}`}>
                    {t(`assistant.suggestions.${s}`)}
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((m) => <Message key={m.ask_id} aptId={aptId} m={m} canWrite={canWrite} onOutcome={onOutcome} />)
          )}
          <div ref={endRef} />
        </div>
        <form
          className="sticky bottom-0 flex gap-2 rounded-b-lg border-t bg-card p-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))]"
          onSubmit={(e) => {
            e.preventDefault();
            void send(text);
          }}
          data-testid="assistant-form"
        >
          <Input
            value={text}
            onChange={(e) => setText(e.target.value)}
            maxLength={500}
            placeholder={canWrite ? t("assistant.placeholder") : t("device.readOnlyHint")}
            disabled={!canWrite || sending}
            aria-disabled={!canWrite || sending}
            className="border-0 bg-transparent focus-visible:ring-0"
            aria-label={t("assistant.placeholder")}
            data-testid="assistant-input"
          />
          <Button type="submit" size="icon" disabled={!canWrite || sending || !text.trim()} aria-label={t("assistant.send")} data-testid="assistant-send-btn">
            {sending ? <Loader2 className="animate-spin" /> : <SendHorizontal />}
          </Button>
        </form>
      </Card>
    </div>
  );
}
