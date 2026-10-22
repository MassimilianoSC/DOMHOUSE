import { useState } from "react";
import { Link } from "react-router-dom";
import { Check, Hourglass, X } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Approval } from "@/api/types";
import { ApiError } from "@/api/bff";
import { instanceApi } from "@/api/instance";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { showError } from "@/lib/actions";
import { DEFAULT_TZ, fmtTime } from "@/lib/format";
import { newCorrelationId } from "@/lib/utils";
import { useApartmentStore } from "@/store/apartmentStore";

/** The closed state of an approval as one line: «Già decisa: approvata», «Già decisa: respinta», «Scaduta». */
const closedText = (status: Approval["status"]) =>
  status === "approved" ? t("assistant.confirm.alreadyApproved") : status === "rejected" ? t("assistant.confirm.alreadyRejected") : t("assistant.confirm.expired");

/**
 * «Sì» / «No» under an answer that needs an approval (D-154): the same call as the Approvazioni page, so the same
 * person, time, outcome, entry and expiry by construction. The approval is the pending one with the question's
 * correlation id; several actions of one question come one at a time, and the buttons move to the next. None of the
 * question's approvals yet: it waits behind one of another source. Operators and admins only, as the Approvazioni page.
 */
export function ChatApproval({ aptId, askId, correlationId, approvalId }: { aptId: string; askId: string; correlationId: string; approvalId: string | null }) {
  const qc = useQueryClient();
  const tz = useApartmentStore((s) => s.apartment?.timezone) ?? DEFAULT_TZ;
  const [busy, setBusy] = useState<"approve" | "reject" | null>(null);
  const [last, setLast] = useState<"approved" | "rejected" | null>(null);
  // the Approvazioni page's own query (filter «all»): a decision on either side shows on both
  const q = useQuery({ queryKey: ["approvals", aptId, "all"], queryFn: () => instanceApi(aptId).listApprovals("all"), refetchInterval: 10_000 });
  const ours = (q.data?.items ?? []).filter((a) => a.correlation_id === correlationId || (approvalId !== null && a.approval_id === approvalId));
  const open = ours.find((a) => a.status === "pending");
  const closed = ours.find((a) => a.approval_id === approvalId && a.status !== "pending") ?? ours.find((a) => a.status !== "pending");

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
  if (result) return <div className="border-t pt-2" data-testid={`ask-confirm-${askId}`}>{result}</div>;
  if (closed) return <p className="border-t pt-2 text-sm font-semibold" data-testid={`ask-confirm-closed-${askId}`}>{closedText(closed.status)}</p>;
  // none of the question's approvals is listed yet: it waits behind an open one of another source
  return (
    <p className="flex flex-wrap items-center gap-1.5 border-t pt-2 text-sm text-muted-foreground" data-testid={`ask-confirm-queued-${askId}`}>
      <Hourglass className="h-4 w-4" aria-hidden /> {t("assistant.confirm.queued")}
      <Link to={`/a/${aptId}/approvazioni`} className="font-semibold text-primary underline-offset-2 hover:underline">{t("assistant.openApprovals")}</Link>
    </p>
  );
}
