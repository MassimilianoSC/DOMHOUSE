import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Check, Hourglass, X } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Approval } from "@/api/types";
import { ApiError } from "@/api/bff";
import { instanceApi } from "@/api/instance";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { showError } from "@/lib/actions";
import { DEFAULT_TZ, fmtTime } from "@/lib/format";
import { newCorrelationId } from "@/lib/utils";
import { useApartmentStore } from "@/store/apartmentStore";

/** How the question's approvals ended, for the badge of the answer (P-75): it follows the decision instead of
 *  staying «richiede approvazione». */
export type ApprovalOutcome = "approved" | "rejected" | "expired";

/**
 * A closed approval as one line (P-75): decided by the person signed in («Approvata da te alle 12:40»), by someone
 * else («Già decisa: approvata»), or expired («Scaduta»). Who decided comes from decided_by, the email the BFF puts
 * back in place of the pseudonym, so the line is right also after the chat is read again.
 */
function closedText(a: Approval, me: string | undefined, tz: string): string {
  if (a.status === "expired") return t("assistant.confirm.expired");
  const mine = Boolean(me && a.decided_by && a.decided_by.toLowerCase() === me.toLowerCase());
  if (mine && a.decided_at) {
    const time = fmtTime(a.decided_at, tz);
    return a.status === "approved" ? t("assistant.confirm.approvedByYou", { time }) : t("assistant.confirm.rejectedByYou", { time });
  }
  return a.status === "approved" ? t("assistant.confirm.alreadyApproved") : t("assistant.confirm.alreadyRejected");
}

/**
 * «Sì» / «No» under an answer that needs an approval (D-154): the same call as the Approvazioni page, so the same
 * person, time, outcome, entry and expiry by construction. The approval is the pending one with the question's
 * correlation id; several actions of one question come one at a time, and the buttons move to the next. None of the
 * question's approvals yet: it waits behind one of another source. Operators and admins only, as the Approvazioni page.
 * When the last one is closed, onOutcome tells the chat how it ended (P-75).
 */
export function ChatApproval({ aptId, askId, correlationId, approvalId, onOutcome }: {
  aptId: string;
  askId: string;
  correlationId: string;
  approvalId: string | null;
  onOutcome?: (outcome: ApprovalOutcome) => void;
}) {
  const qc = useQueryClient();
  const me = useAuth().me?.user.email;
  const tz = useApartmentStore((s) => s.apartment?.timezone) ?? DEFAULT_TZ;
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [last, setLast] = useState<"approved" | "rejected" | null>(null);
  // the Approvazioni page's own query (filter «all»): a decision on either side shows on both
  const q = useQuery({ queryKey: ["approvals", aptId, "all"], queryFn: () => instanceApi(aptId).listApprovals("all"), refetchInterval: 10_000 });
  const ours = (q.data?.items ?? []).filter((a) => a.correlation_id === correlationId || (approvalId !== null && a.approval_id === approvalId));
  const open = ours.find((a) => a.status === "pending");
  // the most recent closed one: the question's last action when it had several
  const closed = [...ours].filter((a) => a.status !== "pending").sort((a, b) => (b.decided_at ?? b.created_at).localeCompare(a.decided_at ?? a.created_at))[0];
  const outcome: ApprovalOutcome | null = open ? null : last ?? (closed ? (closed.status as ApprovalOutcome) : null);

  useEffect(() => {
    if (outcome) onOutcome?.(outcome);
  }, [outcome, onOutcome]);

  const decide = async (decision: "approve" | "reject") => {
    if (!open) return;
    setBusy(decision);
    const cid = newCorrelationId();
    try {
      await instanceApi(aptId).decideApproval(open.approval_id, { decision }, cid);
      setLast(decision === "approve" ? "approved" : "rejected");
    } catch (err) {
      // closed meanwhile (decided elsewhere or expired): the list below says how; anything else is the usual error
      if (!(err instanceof ApiError && err.code === "already_closed")) showError(err, cid);
      setLast(null);
    } finally {
      setBusy(null);
      await qc.invalidateQueries({ queryKey: ["approvals", aptId] });
    }
  };

  if (!q.data) return null;
  const result = last && (
    <p className="text-sm font-semibold" data-testid={`ask-confirm-result-${askId}`}>
      {last === "approved" ? t("assistant.confirm.approved") : t("assistant.confirm.rejected")}
    </p>
  );

  if (open) {
    return (
      <div className="space-y-2 border-t pt-2" data-testid={`ask-confirm-${askId}`} data-approval={open.approval_id}>
        {result}
        {last && ours.length > 1 && <p className="text-xs text-muted-foreground">{t("assistant.confirm.next", { description: open.description })}</p>}
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" onClick={() => void decide("approve")} disabled={busy !== null} data-testid={`ask-confirm-yes-${askId}`}><Check /> {t("assistant.confirm.yes")}</Button>
          <Button size="sm" variant="outline" onClick={() => void decide("reject")} disabled={busy !== null} data-testid={`ask-confirm-no-${askId}`}><X /> {t("assistant.confirm.no")}</Button>
          {open.expires_at && <span className="text-xs text-muted-foreground" data-testid={`ask-confirm-expiry-${askId}`}>{t("assistant.confirm.expiresAt", { time: fmtTime(open.expires_at, tz) })}</span>}
        </div>
      </div>
    );
  }
  // just decided here: what the click did, never «Già decisa» (P-75)
  if (result) return <div className="border-t pt-2" data-testid={`ask-confirm-${askId}`}>{result}</div>;
  if (closed) return <p className="border-t pt-2 text-sm font-semibold" data-testid={`ask-confirm-closed-${askId}`}>{closedText(closed, me, tz)}</p>;
  // none of the question's approvals is listed yet: it waits behind an open one of another source
  return (
    <p className="flex flex-wrap items-center gap-1.5 border-t pt-2 text-sm text-muted-foreground" data-testid={`ask-confirm-queued-${askId}`}>
      <Hourglass className="h-4 w-4" aria-hidden /> {t("assistant.confirm.queued")}
      <Link to={`/a/${aptId}/approvazioni`} className="font-semibold text-primary underline-offset-2 hover:underline">{t("assistant.openApprovals")}</Link>
    </p>
  );
}
