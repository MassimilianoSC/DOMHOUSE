import { useEffect, useRef, useState } from "react";
import { LifeBuoy, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { adminApi } from "@/api/admin";
import { platformApi } from "@/api/platform";
import { toast } from "sonner";
import { useAuth, useRole } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";
import { fmtDateTime, fmtTime } from "@/lib/format";
import { newCorrelationId } from "@/lib/utils";

const DISMISSED_KEY = "domotica.supportDismissed";
/** The admin's profile is re-read this often while the page is visible, so a new access shows up by itself. */
const NOTICE_REFRESH_MS = 120_000;

/**
 * Key of the organization shown (P-50): the routed pages remount when it changes, so nothing of the previous one
 * survives (live stream, page state); leaving an assistance access also goes back to the start page.
 */
export function useOrgContextKey(): string {
  const { me } = useAuth();
  const navigate = useNavigate();
  const access = me?.support?.access_id ?? "";
  const previous = useRef(access);
  useEffect(() => {
    if (previous.current && previous.current !== access) navigate("/", { replace: true });
    previous.current = access;
  }, [access, navigate]);
  return `${me?.tenant?.tenant_id ?? ""}:${access}`;
}

/** Notices hidden per person (D-89): on a shared device another admin still sees them. */
function dismissedIds(uid: string): string[] {
  try {
    const list: unknown = JSON.parse(localStorage.getItem(`${DISMISSED_KEY}.${uid}`) ?? "[]");
    return Array.isArray(list) ? list.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function saveDismissed(uid: string, ids: string[]) {
  try {
    localStorage.setItem(`${DISMISSED_KEY}.${uid}`, JSON.stringify(ids.slice(-50)));
  } catch {
    /* storage unavailable: the notice comes back at the next load */
  }
}

/**
 * Fixed bar while a platform manager works inside another organization (P-50, D-86). «Termina» closes the access on
 * the server and brings them back; if the server cannot be reached the mode ends anyway (the access then expires).
 */
export function SupportBar() {
  const { me, leaveSupport } = useAuth();
  const [busy, setBusy] = useState(false);
  const support = me?.support;
  if (!support) return null;
  const end = async () => {
    setBusy(true);
    // Out of the mode first: a call still in flight that meets the closed access then finds nothing to end.
    await leaveSupport();
    // Not closed on the server (network): it would stay open until it expires, visible to the admin. Say where to close it.
    await platformApi.closeSupport(support.tenant_id, support.access_id, newCorrelationId()).catch(() => toast.warning(t("support.closeFailed"), { duration: 15000 }));
    setBusy(false);
  };
  return (
    <div role="status" className="mb-4 flex flex-wrap items-center gap-3 rounded-2xl border border-warning-border bg-warning-bg px-4 py-3 text-sm font-medium text-warning-fg" data-testid="support-bar">
      <LifeBuoy className="h-4 w-4 shrink-0" aria-hidden />
      <span className="min-w-0 flex-1">{t("support.bar", { name: me?.tenant?.name ?? "", until: fmtTime(support.expires_at) })}</span>
      <Button size="sm" variant="outline" onClick={() => void end()} disabled={busy} data-testid="support-end-btn">{t("support.end")}</Button>
    </div>
  );
}

/** The admin sees every assistance access open on their organization: «Chiudi accesso» ends it, the X hides the notice. */
export function AdminSupportNotice() {
  const { me, refreshMe } = useAuth();
  const { isAdmin } = useRole();
  const uid = me?.user.uid ?? "";
  const [hidden, setHidden] = useState(() => ({ uid, ids: dismissedIds(uid) }));
  const dismissed = hidden.uid === uid ? hidden.ids : dismissedIds(uid);
  useEffect(() => {
    if (!isAdmin) return;
    const timer = setInterval(() => {
      if (document.visibilityState !== "hidden") void refreshMe();
    }, NOTICE_REFRESH_MS);
    return () => clearInterval(timer);
  }, [isAdmin, refreshMe]);
  if (!isAdmin) return null;
  const open = (me?.support_access ?? []).filter((a) => !dismissed.includes(a.access_id));
  if (!open.length) return null;

  const close = async (accessId: string, name: string) => {
    if (!window.confirm(t("support.closeConfirm", { name }))) return;
    const ok = await runAction(async (c) => {
      await adminApi.closeSupport(accessId, c);
      return true;
    }, { success: t("support.closed") });
    if (ok) await refreshMe();
  };
  const dismiss = (accessId: string) => {
    const next = [...dismissed, accessId];
    saveDismissed(uid, next);
    setHidden({ uid, ids: next });
  };

  return (
    <div className="mb-4 space-y-2">
      {open.map((a) => {
        // Both null when the operator has since deleted their account (D-87): «utente rimosso», never "null".
        const name = a.operator_name || a.operator_email || t("common.removedUser");
        const who = a.operator_name && a.operator_email ? `${a.operator_name} (${a.operator_email})` : name;
        return (
          <div key={a.access_id} role="status" className="flex items-start gap-3 rounded-2xl border border-warning-border bg-warning-bg px-4 py-3 text-sm text-warning-fg" data-testid={`support-notice-${a.access_id}`}>
            <LifeBuoy className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <div className="min-w-0 flex-1 space-y-1">
              <p className="font-medium">{t("support.notice", { name: who, until: fmtDateTime(a.expires_at) })}</p>
              {a.reason && <p>{t("support.reason", { reason: a.reason })}</p>}
              <Button size="sm" variant="outline" className="mt-1" onClick={() => void close(a.access_id, name)} data-testid={`support-close-${a.access_id}`}>{t("support.close")}</Button>
            </div>
            <Button size="icon" variant="ghost" className="h-7 w-7 shrink-0" aria-label={t("support.dismiss")} onClick={() => dismiss(a.access_id)} data-testid={`support-dismiss-${a.access_id}`}>
              <X />
            </Button>
          </div>
        );
      })}
    </div>
  );
}
