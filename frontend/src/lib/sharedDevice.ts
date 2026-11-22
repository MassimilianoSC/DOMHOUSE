// F-15 (answer 1244 = a): «Questo è un dispositivo condiviso» on the sign-in page. Ticked, after 30 minutes without
// using the app the person is signed out by itself (the same exit as «Esci»), and on reopening after 30 minutes the
// sign-in is asked again. The choice belongs to this device and this person (one key per uid, in localStorage, so it
// outlives a reload and the app being in the background); signing in without the box removes it for that person.

export const SHARED_IDLE_MS = 30 * 60_000;
/** The box at the last sign-in, until the profile says who signed in: "1" ticked, "0" not. */
const PENDING_KEY = "domotica.sharedPending";
/** Per person: the last use of the app on this device (ms). Present = shared device for that person. */
const sharedKey = (uid: string) => `domotica.shared.${uid}`;
/** Set by the automatic exit, read once by the sign-in page for its notice. */
const AUTO_LOGOUT_KEY = "domotica.autoLogout";
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

/** The sign-in page: the state of the box, for the sign-in about to happen. */
export function rememberSharedChoice(shared: boolean) {
  write(PENDING_KEY, shared ? "1" : "0");
}

/**
 * The profile says who signed in: a box seen at this sign-in becomes that person's choice (ticked: shared from now;
 * not ticked: not shared any more). Without a box (a reload, a session restored) the choice stays as it was.
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

/** Shared device and more than 30 minutes since the last use (a clock moved backwards does not keep it open longer). */
export function sharedExpired(uid: string, now: number): boolean {
  const last = Number(read(sharedKey(uid)));
  if (!isShared(uid)) return false;
  if (!Number.isFinite(last) || last <= 0) return true;
  return now - last > SHARED_IDLE_MS || now < last - SHARED_IDLE_MS;
}

/** A use of the app (a tap, a key, a reload): the 30 minutes start again. */
export function touchShared(uid: string, now: number) {
  if (!isShared(uid)) return;
  const last = Number(read(sharedKey(uid)));
  if (Number.isFinite(last) && now - last >= 0 && now - last < TOUCH_EVERY_MS) return;
  write(sharedKey(uid), String(now));
}

export function markAutoLogout() {
  write(AUTO_LOGOUT_KEY, "1");
}

/** After an automatic exit: the sign-in page says why the person is out. Read without consuming it (React may render
 *  a component twice in development); the page clears it once shown (clearAutoLogout). */
export function wasAutoLogout(): boolean {
  return read(AUTO_LOGOUT_KEY) === "1";
}

export function clearAutoLogout() {
  write(AUTO_LOGOUT_KEY, null);
}
