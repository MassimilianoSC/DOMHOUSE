// Pure logic of the push messages, shared by the service worker (src/sw.ts) and the page; no browser globals here.
//
// Message format agreed with the BFF (S2, D-31): an FCM web message with ONLY "data" (no "notification" block, so
// nothing is displayed twice), every value a string:
//   title, body       text of the notification
//   link              path inside the app opened on tap, e.g. "/a/apt-001/approvazioni" (relative, starts with "/")
//   tag               grouping key: a notification with the same tag replaces the previous one
//                     ("approval:<approval_id>", "offline:<apartment_id>:<device_id>", "instance:<apartment_id>",
//                     "booking:<decision_id>", "summary:<apartment_id>:<week>")
//   kind              "approval" | "device_offline" | "instance_down" | "booking" (D-123) | "summary" (D-150) |
//                     "frost_inactive" (lotto 30, tag "frost:<apartment_id>:<device_id>") |
//                     "schedule_failed" (D-219, also an action done in part; tag "schedule:<apartment_id>:<decision_id>",
//                     "maintenance:<apartment_id>" for the summary after a planned shutdown);
//                     the page uses it to skip the toast only for what the apartment's live stream announces (P-83, D24)
//   apartment_id      always; approval_id / device_id / ts when relevant
// Extra keys are ignored. A push is never silent: a missing title/body/link gives a generic notification opening "/".

export interface PushNotice {
  title: string;
  body: string;
  link: string;
  tag?: string;
  apartmentId?: string;
  kind?: string;
}

/**
 * Only a same-app path: "/..." but not "//host" (protocol-relative) nor anything with a scheme. Control characters
 * are refused too (P-83, D78): the URL parser drops tab and newlines, so "/\t/evil.example" would become "//evil.example".
 */
export function safeLink(link: unknown): string {
  return typeof link === "string" && link.startsWith("/") && !link.startsWith("//") && !link.includes("\\") &&
    !/[\u0000-\u001f\u007f]/.test(link) ? link : "/";
}

const str = (v: unknown) => (typeof v === "string" && v.trim() ? v : undefined);

/** FCM delivers web push as JSON { data: {...}, from, fcmMessageId, ... }; anything unreadable still gives a notice. */
export function toNotice(payload: unknown, fallbackTitle: string): PushNotice {
  const data = (payload && typeof payload === "object" ? (payload as { data?: unknown }).data : undefined) ?? {};
  const d = (typeof data === "object" && data ? data : {}) as Record<string, unknown>;
  const title = str(d.title);
  const body = str(d.body);
  if (!title || !body || !str(d.link)) return { title: fallbackTitle, body: body ?? "", link: "/" };
  return { title, body, link: safeLink(d.link), tag: str(d.tag), apartmentId: str(d.apartment_id), kind: str(d.kind) };
}

/**
 * Options of the system notification. A notice with a tag replaces the previous one with the same tag (a device that
 * goes offline again, the next outage): renotify makes the replacement sound and vibrate again (P-83, D49), otherwise
 * it would change silently. Browsers refuse renotify without a tag.
 */
export function notificationOptions(notice: PushNotice): NotificationOptions & { renotify?: boolean } {
  const base = { body: notice.body, icon: "/icons/icon-192.png", tag: notice.tag, data: { link: notice.link } };
  return notice.tag ? { ...base, renotify: true } : base;
}

/** Message the service worker posts to an open, focused page instead of a system notification. */
export interface PushMessage {
  type: "domotica-push";
  notice: PushNotice;
}

/** Message the service worker posts after a tap on a notification, when the app is already open. */
export interface OpenMessage {
  type: "domotica-open";
  link: string;
}

export const isPushMessage = (m: unknown): m is PushMessage =>
  Boolean(m && typeof m === "object" && (m as PushMessage).type === "domotica-push" && (m as PushMessage).notice);

export const isOpenMessage = (m: unknown): m is OpenMessage =>
  Boolean(m && typeof m === "object" && (m as OpenMessage).type === "domotica-open" && typeof (m as OpenMessage).link === "string");

/** Safari's engine (iPhone, iPad, Mac): Chrome, Edge and Firefox on iOS also say "Safari" but carry their own token. */
export const isWebKitSafari = (ua: string) => /safari/i.test(ua) && !/chrome|chromium|crios|edg|fxios|firefox|android/i.test(ua);

/**
 * With the app open and focused the notice goes to the page (an in-app toast) instead of the system tray.
 * Safari always gets the system notification: WebKit may revoke the permission of a site whose pushes show nothing.
 */
export function deliverInApp(focusedVisible: boolean, safari: boolean): boolean {
  return focusedVisible && !safari;
}

/**
 * Kinds whose event the apartment's live stream announces with its own toast (useApartmentStream): approval.created and
 * device.online. instance_down is not here: the stream says it only when the engine reports its connector down, never
 * when the server cannot reach the engine (D-217), and a second toast is better than none.
 */
const STREAM_ANNOUNCED = new Set(["approval", "device_offline"]);

/**
 * The page skips the toast only when it is already showing that apartment AND its live stream announces the same event
 * (P-83, D24): antigelo, actions not done, bookings, summaries have no toast of their own there and were lost.
 */
export function toastWanted(notice: PushNotice, pathname: string): boolean {
  const here = notice.apartmentId && (pathname === `/a/${notice.apartmentId}` || pathname.startsWith(`/a/${notice.apartmentId}/`));
  return !(here && notice.kind && STREAM_ANNOUNCED.has(notice.kind));
}
