import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useQuery } from "@tanstack/react-query";
import { BellRing } from "lucide-react";
import { pushApi, type NotificationPrefs } from "@/api/admin";
import { useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Card, Switch } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction, showError } from "@/lib/actions";
import { disablePush, enablePush, PushError, pushState, type PushState } from "@/lib/push";
import { env } from "@/lib/utils";

// D-170: «Decisioni del motore» is gone (it saved a choice nothing used); whatever else the server sends in the
// preferences travels back unchanged when saving.
const KEYS: (keyof NotificationPrefs)[] = ["approvals", "offline", "bookings", "summary"];

/** Why this device does not receive push (null when it can): the card says it instead of a silent disabled button. */
function blockedText(state: PushState): string | null {
  switch (state) {
    case "unsupported":
      return t("settings.notifications.statusUnsupported");
    case "ios-install":
      return t("settings.notifications.statusIosInstall");
    case "denied":
      return t("settings.notifications.statusDenied");
    case "revoked":
      return t("settings.notifications.statusRevoked");
    default:
      return null;
  }
}

function pushErrorText(reason: PushError["reason"]): string {
  switch (reason) {
    case "denied":
      return t("settings.notifications.errorDenied");
    case "unsupported":
      return t("settings.notifications.statusUnsupported");
    default:
      return t("settings.notifications.errorNoToken");
  }
}

export function NotificationSettings() {
  const { me } = useAuth();
  // Without FCM the alerts are in-app toasts; only a dev environment may call itself "sviluppo" (staging is tested by
  // people who would read it as a fault).
  const dev = me?.env.app_env === "dev";
  const uid = me?.user.uid ?? "";
  const q = useQuery({ queryKey: ["push", "status"], queryFn: pushApi.status });
  const [prefs, setPrefs] = useState<NotificationPrefs | null>(null);
  const [state, setState] = useState<PushState>(() => pushState(uid));
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    // A BFF without «Prenotazioni» or «Riepilogo» yet: on, their default (D-123, D-150), so the saved preferences
    // always carry all five.
    if (q.data) setPrefs({ ...q.data.prefs, bookings: q.data.prefs.bookings ?? true, summary: q.data.prefs.summary ?? true });
  }, [q.data]);

  const toggle = async (k: keyof NotificationPrefs, v: boolean) => {
    if (!prefs) return;
    const next = { ...prefs, [k]: v };
    setPrefs(next);
    const res = await runAction(() => pushApi.setPrefs(next), { success: t("settings.notifications.saved") });
    if (!res) setPrefs(prefs);
  };

  // enablePush asks the permission first thing: nothing may be awaited before it, or the browser no longer sees a click.
  const togglePush = async () => {
    setBusy(true);
    try {
      if (state === "on") {
        await disablePush();
        toast.success(t("settings.notifications.disabledDone"));
      } else {
        await enablePush(uid);
        toast.success(t("settings.notifications.enabledDone"));
      }
    } catch (err) {
      if (err instanceof PushError) toast.error(pushErrorText(err.reason), { duration: 10000 });
      else showError(err, null);
    } finally {
      setState(pushState(uid));
      setBusy(false);
      void q.refetch();
    }
  };
  const blocked = blockedText(state);
  const canToggle = state === "on" || state === "off" || state === "revoked";

  return (
    <Card className="space-y-4 p-5" data-testid="settings-notifications">
      <h2 className="flex items-center gap-2 text-base font-semibold"><BellRing className="h-4 w-4" /> {t("settings.notifications.title")}</h2>
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-secondary/60 px-3 py-2">
        <div className="text-sm">
          <div className="font-semibold" data-testid="settings-push-mode">{env.fcmEnabled ? t("settings.notifications.pushMode") : t(dev ? "settings.notifications.devMode" : "settings.notifications.inAppMode")}</div>
          <div className="text-xs text-muted-foreground">{env.fcmEnabled ? t("settings.notifications.pushHint", { count: q.data?.tokens ?? 0 }) : t(dev ? "settings.notifications.devHint" : "settings.notifications.inAppHint")}</div>
          {env.fcmEnabled && state === "on" && <div className="text-xs text-muted-foreground" data-testid="settings-push-signout-hint">{t("settings.notifications.signOutHint")}</div>}
          {env.fcmEnabled && blocked && <p className="mt-1 text-xs font-medium text-foreground" data-testid="settings-push-status" data-state={state}>{blocked}</p>}
        </div>
        {env.fcmEnabled && canToggle && (
          <Button size="sm" variant={state === "on" ? "outline" : "default"} onClick={togglePush} disabled={busy} data-testid="settings-push-toggle-btn">
            {state === "on" ? t("settings.notifications.disable") : t("settings.notifications.enable")}
          </Button>
        )}
      </div>
      {KEYS.map((k) => (
        <div key={k} className="flex items-center justify-between gap-3 border-b py-2 last:border-0">
          <div>
            <div className="text-sm font-semibold">{t(`settings.notifications.${k}`)}</div>
            <div className="text-xs text-muted-foreground">{t(`settings.notifications.${k}Hint`)}</div>
          </div>
          <Switch checked={prefs?.[k] ?? false} disabled={!prefs} onCheckedChange={(v) => toggle(k, v)} aria-label={t(`settings.notifications.${k}`)} data-testid={`settings-pref-${k}`} />
        </div>
      ))}
    </Card>
  );
}
