/// <reference lib="webworker" />
// The site's only service worker (P-11), for web push only. FCM data-only messages arrive as standard web push JSON,
// so no Firebase SDK is needed here: the page gets the token with firebase/messaging, passing this registration.
//
// P-92 / E-29: no fetch handler and no copy of the site. Until P-92 this worker kept the whole site in Cache Storage
// and answered every opening with it, so the first opening after a publication showed the previous release, and a
// worker stuck in «starting» held the navigation (E-29). Now every opening takes index.html from the network (no-cache
// in firebase.json); the files under /assets/ stay in the browser cache for a year (immutable, named by content).
// Without network the app does not open: accepted with P-92 (answer 1227 = a). The new version of an open page is
// src/lib/appVersion.ts.

import { t } from "@/i18n";
import { deliverInApp, isWebKitSafari, notificationOptions, safeLink, toNotice, type OpenMessage, type PushMessage } from "@/lib/pushPayload";

declare let self: ServiceWorkerGlobalScope;

// Replaces the previous worker at once, so the copy of the site it kept stops being served on the very next opening.
self.skipWaiting();

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // The precache of the workers before P-92 («workbox-precache-v2-…»): nothing reads it any more.
      const keys = await caches.keys();
      await Promise.all(keys.filter((k) => k.startsWith("workbox-")).map((k) => caches.delete(k)));
      await self.clients.claim();
    })(),
  );
});

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
      await self.registration.showNotification(notice.title, notificationOptions(notice));
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
