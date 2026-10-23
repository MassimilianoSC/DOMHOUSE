import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, UserPlus } from "lucide-react";
import { platformApi, type PlatformManager } from "@/api/platform";
import { useAuth } from "@/auth/AuthProvider";
import { PlatformError } from "@/components/platform/PlatformError";
import { Button } from "@/components/ui/button";
import { Badge, Card, Input, Label, Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";

const KEY = ["platform", "managers"];
const same = (a: string | undefined, b: string) => (a ?? "").trim().toLowerCase() === b.trim().toLowerCase();

/**
 * Gestori della piattaforma (P-36, D-61a): kept here and not in Amministrazione > Utenti, which belongs to a single
 * organization. Added by email, also for someone without an account yet: the role applies when they sign in with that
 * verified email. The platform always keeps one manager (409 last_manager).
 */
export function PlatformManagers() {
  const { me, refreshMe } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: KEY, queryFn: platformApi.managers });
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const refresh = () => void qc.invalidateQueries({ queryKey: KEY });

  const add = async () => {
    const value = email.trim();
    setBusy(true);
    const res = await runAction((c) => platformApi.addManager(value, c), { success: t("platform.managerAdded", { email: value }) });
    setBusy(false);
    if (res) {
      setEmail("");
      refresh();
    }
  };

  const remove = async (m: PlatformManager) => {
    const self = same(me?.user.email, m.email);
    if (!window.confirm(self ? t("platform.removeSelfConfirm") : t("platform.removeConfirm", { email: m.email }))) return;
    const ok = await runAction(async (c) => {
      await platformApi.removeManager(m.email, c);
      return true;
    }, { success: t("platform.removed", { email: m.email }) });
    if (ok) {
      refresh();
      if (self) void refreshMe(); // own role gone: the menu entry disappears and PlatformOnly closes the page
    }
  };

  return (
    <div className="space-y-4">
      <Card className="space-y-3 p-5" data-testid="platform-manager-add-card">
        <p className="text-sm text-muted-foreground">{t("platform.managersHint")}</p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-1 space-y-1">
            <Label htmlFor="pm-email">{t("common.email")}</Label>
            <Input id="pm-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("admin.users.emailPlaceholder")} data-testid="platform-manager-email" />
          </div>
          <Button onClick={() => void add()} disabled={busy || !/^\S+@\S+\.\S+$/.test(email.trim())} data-testid="platform-manager-add-btn"><UserPlus /> {t("platform.addManager")}</Button>
        </div>
      </Card>
      {q.error && <PlatformError error={q.error} onRetry={() => void q.refetch()} testId="managers-error" />}
      {q.isLoading ? (
        <Skeleton className="h-32 rounded-2xl" />
      ) : (
        <Card className="divide-y px-5" data-testid="platform-managers-list">
          {q.data?.map((m) => (
            <div key={m.email} className="flex flex-wrap items-center gap-3 py-3" data-testid={`platform-manager-${m.email}`}>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-sm font-bold">
                  <span>{m.email}</span>
                  {same(me?.user.email, m.email) && <Badge>{t("admin.users.you")}</Badge>}
                  <Badge className={m.active ? "border-positive-border bg-positive-bg text-positive-fg" : "border-warning-border bg-warning-bg text-warning-fg"} data-testid={`platform-manager-state-${m.email}`}>
                    {m.active ? t("platform.managerActive") : t("platform.managerPending")}
                  </Badge>
                </div>
                <div className="text-xs text-muted-foreground">{m.display_name || "—"}</div>
              </div>
              <Button variant="destructive" size="sm" onClick={() => void remove(m)} data-testid={`platform-manager-remove-${m.email}`}>
                <Trash2 /> {t("platform.removeManager")}
              </Button>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}
