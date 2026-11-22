// F-15 (answer 1244 = a): «Questo è un dispositivo condiviso» on the sign-in page. Ticked, after 30 minutes without
// using the app the person is signed out by itself (the same exit as «Esci»), and on reopening after 30 minutes the
// sign-in is asked again. The choice belongs to this device and this person (one key per uid, in localStorage, so it
// outlives a reload and the app being in the background); signing in without the box removes it for that person.
// Review S-1: the box is written only at the moment of a real sign-in, never while a session is being loaded.

export const SHARED_IDLE_MS = 30 * 60_000;
/** Review S-4: a clock more than this behind the last use counts as expired (small corrections of the clock pass). */
export const CLOCK_BACK_MS = 2 * 60_000;
/** The box at the sign-in in progress, until the profile says who signed in: "1" ticked, "0" not. */
const PENDING_KEY = "domotica.sharedPending";
/** Per person: the last use of the app on this device (ms). Present = shared device for that person. */
const sharedKey = (uid: string) => `domotica.shared.${uid}`;
/** Writes of the last use at most this often: a tap every second does not rewrite localStorage every second. */
const TOUCH_EVERY_MS = 15_000;

const read = (k: string) => {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
};
const write = (k: string, v: string | null) => {
  try {
    if (v === null) localStorage.removeItem(k);
    else localStorage.setItem(k, v);
  } catch {
    /* storage unavailable: the device is treated as not shared */
  }
};

/** Right before a sign-in (the button pressed): the state of the box, for the profile that will answer. */
export function rememberSharedChoice(shared: boolean) {
  write(PENDING_KEY, shared ? "1" : "0");
}

/** A sign-in that did not happen (wrong password, window closed): its box is not left for anyone. */
export function forgetSharedChoice() {
  write(PENDING_KEY, null);
}

/**
 * The profile says who signed in: a box seen at this sign-in becomes that person's choice (ticked: shared from now;
 * not ticked: not shared any more). Without a sign-in (a reload, a session restored) the choice stays as it was.
 */
export function adoptSharedChoice(uid: string, now: number) {
  const pending = read(PENDING_KEY);
  if (pending === null) return;
  write(PENDING_KEY, null);
  write(sharedKey(uid), pending === "1" ? String(now) : null);
}

export function isShared(uid: string): boolean {
  return read(sharedKey(uid)) !== null;
}

/** Shared device and more than 30 minutes since the last use, or a clock that went back (review S-4). */
export function sharedExpired(uid: string, now: number): boolean {
  if (!isShared(uid)) return false;
  const last = Number(read(sharedKey(uid)));
  if (!Number.isFinite(last) || last <= 0) return true;
  return now - last > SHARED_IDLE_MS || now < last - CLOCK_BACK_MS;
}

/** A use of the app (a tap, a key, scrolling): the 30 minutes start again. Never moves the last use backwards. */
export function touchShared(uid: string, now: number) {
  if (!isShared(uid)) return;
  const last = Number(read(sharedKey(uid)));
  if (Number.isFinite(last) && now - last < TOUCH_EVERY_MS) return; // also when now < last: never backwards
  write(sharedKey(uid), String(now));
}

/** After «Esci» or the automatic exit (review S-6): no list of who used the device, nor when, stays on it. */
export function forgetShared(uid: string) {
  write(sharedKey(uid), null);
}
