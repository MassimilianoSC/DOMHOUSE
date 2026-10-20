import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "@/auth/AuthProvider";
import { t } from "@/i18n";
import { syncPushToken } from "@/lib/push";
import { isOpenMessage, isPushMessage, safeLink, toastWanted } from "@/lib/pushPayload";

/**
 * Page side of the push (P-11), mounted once in the signed-in shell:
 * - keeps this device's FCM token in step with the BFF at every start, and brings push back for the same person (P-44);
 * - shows as a toast the push the service worker hands over while the app is focused (unless the page already shows
 *   that apartment, whose live stream announces the same event);
 * - opens the link of a tapped notification inside the running app, without a reload.
 */
export function usePushBridge() {
  const navigate = useNavigate();
  const uid = useAuth().me?.user.uid;
  const { pathname } = useLocation();
  const path = useRef(pathname);
  path.current = pathname;

  useEffect(() => {
    if (!uid) return;
    // The same person back on this device: push resumed by itself, or left off because the permission is gone (P-44).
    void syncPushToken(uid).then((r) => {
      if (r === "resumed") toast.success(t("notify.resumed"));
      else if (r === "permission") toast.warning(t("notify.resumeNoPermission"), { duration: 15000 });
    });
  }, [uid]);

  useEffect(() => {
    const sw = typeof navigator !== "undefined" ? navigator.serviceWorker : undefined;
    if (!sw) return;
    const onMessage = (e: MessageEvent) => {
      if (isOpenMessage(e.data)) {
        navigate(safeLink(e.data.link));
      } else if (isPushMessage(e.data) && toastWanted(e.data.notice, path.current)) {
        const { title, body, link } = e.data.notice;
        toast.info(title, { description: body, duration: 10000, action: { label: t("notify.open"), onClick: () => navigate(safeLink(link)) } });
      }
    };
    sw.addEventListener("message", onMessage);
    return () => sw.removeEventListener("message", onMessage);
  }, [navigate]);
}
