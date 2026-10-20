/// <reference lib="webworker" />
// The site's only service worker (P-11): Workbox cache and updates exactly as the generated worker did for P-20,
// plus web push. FCM data-only messages arrive as standard web push JSON, so no Firebase SDK is needed here: the page
// gets the token with firebase/messaging, passing this registration.
import { clientsClaim } from "workbox-core";
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from "workbox-precaching";
import { NavigationRoute, registerRoute } from "workbox-routing";
import { t } from "@/i18n";
import { deliverInApp, isWebKitSafari, safeLink, toNotice, type OpenMessage, type PushMessage } from "@/lib/pushPayload";

declare let self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Array<string | { url: string; revision: string | null }> };

self.skipWaiting();
clientsClaim();
cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);
registerRoute(new NavigationRoute(createHandlerBoundToURL("index.html"), { denylist: [/^\/app\//, /^\/api\//, /^\/webhooks\//, /^\/healthz/] }));

const appWindows = () => self.clients.matchAll({ type: "window", includeUncontrolled: true });

self.addEventListener("push", (event) => {
  let payload: unknown = null;
  try {
    payload = event.data?.json();
  } catch {
    /* not JSON: toNotice falls back to a generic notice */
  }
  const notice = toNotice(payload, t("app.name"));
  event.waitUntil(
    (async () => {
      const focused = (await appWindows()).find((w) => w.focused && w.visibilityState === "visible");
      if (focused && deliverInApp(true, isWebKitSafari(self.navigator.userAgent))) {
        focused.postMessage({ type: "domotica-push", notice } satisfies PushMessage);
        return;
      }
      await self.registration.showNotification(notice.title, { body: notice.body, icon: "/icons/icon-192.png", tag: notice.tag, data: { link: notice.link } });
    })(),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const link = safeLink((event.notification.data as { link?: unknown } | null)?.link);
  event.waitUntil(
    (async () => {
      const open = (await appWindows())[0];
      if (open) {
        // The page navigates with its router: no reload, works also for a window this worker does not control yet.
        await open.focus();
        open.postMessage({ type: "domotica-open", link } satisfies OpenMessage);
        return;
      }
      await self.clients.openWindow(link);
    })(),
  );
});
