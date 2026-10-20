import { pushApi } from "@/api/admin";
import { firebaseApp, firebaseConfigured } from "@/auth/firebase";
import { isIos, isStandalone } from "@/hooks/useInstallPrompt";
import { env } from "@/lib/utils";

// Web push on this device (P-11). The service worker (src/sw.ts) shows the notifications; this module only manages
// the permission and the FCM token, kept in step with the BFF.

const TOKEN_KEY = "domotica.pushToken";
/** uid of the user the token was registered for (P-36, D-59): a token is never re-registered for another account. */
const OWNER_KEY = "domotica.pushTokenOwner";
/** Owner of a token whose deletion has not succeeded yet: nobody's (off for everyone), retried at every start (N2). */
const DELETING = "domotica:deleting";
/**
 * uids of the people who left this device with push on (P-44): on their own next sign-in here push comes back by
 * itself; never for anyone else. A list, so two people sharing an office phone each get theirs back.
 */
const RESUME_KEY = "domotica.pushResume";
const RESUME_MAX = 20;
const SW_READY_MS = 10_000;

export const pushSupported = () =>
  typeof window !== "undefined" && "Notification" in window && "serviceWorker" in navigator && "PushManager" in window;

/**
 * - unsupported: this browser cannot receive push; ios-install: iPhone/iPad outside the installed app (iOS delivers
 *   push only to a Home Screen app);
 * - denied: permission blocked; revoked: push was on here but the permission was taken back in the settings;
 * - off / on: ready to be turned on / on.
 */
export type PushState = "unsupported" | "ios-install" | "denied" | "revoked" | "off" | "on";

/** The device token, only if it belongs to `uid`; a token of another account (or of an older version, without owner) is ignored. */
function ownToken(uid: string): string | null {
  const token = localStorage.getItem(TOKEN_KEY);
  return token && localStorage.getItem(OWNER_KEY) === uid ? token : null;
}

function forgetToken() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(OWNER_KEY);
}

function resumeList(): string[] {
  try {
    const list: unknown = JSON.parse(localStorage.getItem(RESUME_KEY) ?? "[]");
    return Array.isArray(list) ? list.filter((u): u is string => typeof u === "string") : [];
  } catch {
    return [];
  }
}

function saveResumeList(list: string[]) {
  if (list.length) localStorage.setItem(RESUME_KEY, JSON.stringify(list.slice(-RESUME_MAX)));
  else localStorage.removeItem(RESUME_KEY);
}

/** True when push comes back by itself at `uid`'s next sign-in on this device (P-44). */
export const pushResumePending = (uid: string) => resumeList().includes(uid);

/** Nothing to resume for `uid` any more: account deleted, push turned on or off by hand, or resumed. */
export function forgetPushResume(uid: string) {
  const list = resumeList();
  if (list.includes(uid)) saveResumeList(list.filter((u) => u !== uid));
}

export function pushState(uid: string): PushState {
  if (!pushSupported() || !firebaseConfigured) return isIos() && !isStandalone() ? "ios-install" : "unsupported";
  const token = ownToken(uid);
  if (Notification.permission === "denied") return "denied";
  if (Notification.permission !== "granted") return token ? "revoked" : "off";
  return token ? "on" : "off";
}

export class PushError extends Error {
  constructor(public reason: "unsupported" | "denied" | "no_token") {
    super(reason);
  }
}

/** The site's service worker registration (the same one Workbox uses), with a timeout instead of waiting forever. */
async function swRegistration(): Promise<ServiceWorkerRegistration> {
  return Promise.race([
    navigator.serviceWorker.ready,
    new Promise<never>((_, reject) => setTimeout(() => reject(new Error("service worker non pronto")), SW_READY_MS)),
  ]);
}

async function messaging() {
  const [mod, app] = await Promise.all([import("firebase/messaging"), firebaseApp()]);
  return { mod, messaging: mod.getMessaging(app) };
}

async function currentToken(): Promise<string> {
  const [{ mod, messaging: m }, registration] = await Promise.all([messaging(), swRegistration()]);
  return mod.getToken(m, { vapidKey: import.meta.env.VITE_FIREBASE_VAPID_KEY, serviceWorkerRegistration: registration });
}

/** Asks the permission (must run inside the click), gets the token and registers it on the user. */
export async function enablePush(uid: string): Promise<void> {
  if (!pushSupported() || !firebaseConfigured) throw new PushError("unsupported");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") throw new PushError("denied");
  const token = await currentToken();
  if (!token) throw new PushError("no_token");
  await pushApi.subscribe(token);
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(OWNER_KEY, uid);
  forgetPushResume(uid);
}

/**
 * Turns push off on this device; also called on every sign-out (D-59). resume (sign-outs, P-44): if push was on for
 * a person, it comes back at that same person's next sign-in here. Without it («Disattiva» in Impostazioni) it stays off.
 */
export async function disablePush({ resume = false }: { resume?: boolean } = {}): Promise<void> {
  const token = localStorage.getItem(TOKEN_KEY);
  if (!token) return;
  const owner = localStorage.getItem(OWNER_KEY);
  if (owner && owner !== DELETING) {
    if (resume) saveResumeList([...resumeList().filter((u) => u !== owner), owner]);
    else forgetPushResume(owner);
  }
  // From now on the token belongs to nobody: "off" for every account, and syncPushToken retries the deletion (N2).
  localStorage.setItem(OWNER_KEY, DELETING);
  await pushApi.unsubscribe(token).catch(() => undefined);
  try {
    const { mod, messaging: m } = await messaging();
    await mod.deleteToken(m); // the token stops working at FCM too, not only on our side
    forgetToken(); // only once FCM confirmed: without network the local copy stays and the next start tries again
  } catch {
    /* offline: kept with no owner, retried at the next start */
  }
}

/** What a start did that the person should hear about (P-44): push back on, or left off for lack of permission. */
export type PushResume = "resumed" | "permission";

/**
 * Push back on for a person who left this device with push on (P-44). Never asks the permission: if the browser no
 * longer grants it, push stays off and the caller says so (once: the resume is dropped).
 */
async function resumePush(uid: string): Promise<PushResume | undefined> {
  if (!pushResumePending(uid)) return undefined;
  if (Notification.permission !== "granted") {
    forgetPushResume(uid);
    return "permission";
  }
  try {
    const token = await currentToken();
    if (!token) return undefined;
    await pushApi.subscribe(token);
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(OWNER_KEY, uid);
    forgetPushResume(uid);
    return "resumed";
  } catch {
    return undefined; // offline or BFF unreachable: the resume stays pending, tried again at the next start
  }
}

/**
 * At every start of a signed-in session: FCM renews tokens, and the BFF drops dead ones, so the token is fetched again
 * and registered (subscribe is idempotent); a renewed token replaces the old one. If the permission was taken back,
 * the BFF stops sending to this device; the stored token stays as the marker of the "revoked" state. With no token
 * of its own, push comes back for a person who left here with push on (P-44).
 */
export async function syncPushToken(uid: string): Promise<PushResume | undefined> {
  if (!env.fcmEnabled || !pushSupported() || !firebaseConfigured) return undefined;
  const stored = localStorage.getItem(TOKEN_KEY);
  if (!stored) return resumePush(uid);
  if (localStorage.getItem(OWNER_KEY) !== uid) {
    // Left by another account that did not sign out from here (expired or revoked session), or by a version without
    // owner: never adopt it, and make it stop delivering (F4, Fable review of P-36). The BFF drops the token from
    // every user who holds it (o1), and FCM invalidates it, so the previous user's notifications stop on this device.
    // Its owner gets push back at their own next sign-in here (P-44).
    await disablePush({ resume: true });
    // A token still being deleted at FCM (offline): no new one before the deletion succeeds, or the deletion retried
    // at the next start would remove the new token instead (deleteToken acts on the current one).
    if (localStorage.getItem(TOKEN_KEY)) return undefined;
    return resumePush(uid);
  }
  try {
    if (Notification.permission !== "granted") {
      await pushApi.unsubscribe(stored);
      return;
    }
    const token = await currentToken();
    if (!token) return;
    await pushApi.subscribe(token);
    if (token !== stored) {
      await pushApi.unsubscribe(stored).catch(() => undefined);
      localStorage.setItem(TOKEN_KEY, token);
    }
  } catch {
    /* offline or BFF unreachable: try again at the next start */
  }
  return undefined;
}
