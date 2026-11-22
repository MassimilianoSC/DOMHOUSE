import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, bffFetch, setAuthResolver, setBlockedHandler } from "@/api/bff";
import { platformApi } from "@/api/platform";
import type { Me } from "@/api/types";
import type { ProblemCause } from "@/components/layout/PageProblem";
import { t } from "@/i18n";
import { reloadOnce } from "@/lib/lazyPage";
import { disablePush, forgetPushResume } from "@/lib/push";
import { adoptSharedChoice, forgetShared, forgetSharedChoice, isShared, rememberSharedChoice, sharedExpired, touchShared } from "@/lib/sharedDevice";
import { clearUserData } from "@/lib/session";
import { endSupportSession, startSupportSession, supportSession, type SupportSession } from "@/lib/support";
import { env, newCorrelationId } from "@/lib/utils";
import { continueUrl, firebaseAuth, firebaseConfigured } from "./firebase";

const DEV_KEY = "domotica.devUser";
/** After the expected end of an assistance access, a little later the profile is re-read (P-50). */
const SUPPORT_END_MARGIN_MS = 5_000;
/** E-29: how long the start (Firebase, then /app/me) may take before the person is told. A late answer still gets in. */
export const STARTUP_TIMEOUT_MS = 15_000;

/** A deliberate sign-out also ends an assistance access on the server, so the admin stops seeing it (P-50). */
async function closeOwnSupport() {
  const s = supportSession();
  if (s) await platformApi.closeSupport(s.tenant_id, s.access_id, newCorrelationId()).catch(() => undefined);
}

type Status = "loading" | "unavailable" | "anonymous" | "authenticated";

interface AuthContextValue {
  status: Status;
  /** With status "unavailable": what went wrong, if the app knows it (D-211). */
  problem: ProblemCause | undefined;
  me: Me | null;
  /** Firebase sign-in providers of the current user ("password", "google.com"); empty in dev mode. */
  providers: string[];
  /** shared: the box «Questo è un dispositivo condiviso» at the moment of this sign-in (F-15, review S-1). */
  devLogin: (email: string, shared?: boolean) => Promise<void>;
  emailLogin: (email: string, password: string, shared?: boolean) => Promise<void>;
  googleLogin: (shared?: boolean) => Promise<void>;
  /** F-15: the person was signed out by the automatic exit of a shared device, in this page (review S-5). */
  autoLoggedOut: boolean;
  logout: () => Promise<void>;
  refreshMe: () => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
  changePassword: (current: string, next: string) => Promise<void>;
  changeEmail: (current: string, newEmail: string) => Promise<void>;
  logoutEverywhere: () => Promise<void>;
  deleteAccount: () => Promise<void>;
  /** Assistance access (P-50, D-86): into another organization and back, the tab emptied like a change of user. */
  enterSupport: (s: SupportSession) => Promise<void>;
  leaveSupport: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const firebaseMode = () => env.authMode !== "dev" && firebaseConfigured;

async function firebaseToken(): Promise<string | null> {
  if (!firebaseConfigured) return null;
  return (await (await firebaseAuth()).currentUser?.getIdToken()) ?? null;
}

async function firebaseSignOut() {
  if (!firebaseMode()) return;
  const { signOut } = await import("firebase/auth");
  await signOut(await firebaseAuth());
}

/** Password re-entry required by Firebase before sensitive changes (password, email). */
async function reauthenticate(current: string) {
  const { EmailAuthProvider, reauthenticateWithCredential } = await import("firebase/auth");
  const user = (await firebaseAuth()).currentUser;
  if (!user?.email) throw new Error("no-user");
  await reauthenticateWithCredential(user, EmailAuthProvider.credential(user.email, current));
  return user;
}

setAuthResolver(async (): Promise<Record<string, string>> => {
  if (env.authMode === "dev") {
    const email = localStorage.getItem(DEV_KEY);
    return email ? { "X-Dev-User": email } : {};
  }
  const token = await firebaseToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>("loading");
  const [me, setMe] = useState<Me | null>(null);
  /** Why the status is "unavailable", when the profile said it (D-211); unknown for a start that never answered. */
  const [problem, setProblem] = useState<ProblemCause | undefined>(undefined);
  const [providers, setProviders] = useState<string[]>([]);
  // F-15 (review S-5): a state of this page, never stored: an automatic exit happens in the open page, so its notice
  // cannot come back at a later visit
  const [autoLoggedOut, setAutoLoggedOut] = useState(false);
  const queryClient = useQueryClient();
  const lastUid = useRef<string | null>(null);
  /**
   * F-15: grows at every sign-out. A read of the profile that started before (or while) the person left is dropped
   * when it answers: found in the browser, a late read put the person back in after the automatic exit, without a
   * session. Also while a sign-out is under way (exiting), no read lets the person in.
   */
  const sessionGen = useRef(0);
  /** F-15 (second review R-2): the sign-out under way, one at a time; a second request waits for the same one. */
  const exiting = useRef<Promise<void> | null>(null);
  /** A profile read in flight: a blocking answer meanwhile (also /app/me's own) does not start another one (P-50). */
  const profileLoading = useRef(false);
  /** A blocking answer that came while a profile read was in flight: handled right after it (D-89). */
  const pendingBlock = useRef<string | null>(null);
  const onBlocked = useRef<(code: string) => void>(() => {});

  /**
   * Signed out, by the user or not (expired, revoked, refused): nothing of that user stays in the tab (P-36). When the
   * session is really over the device also stops receiving their push (F4): after a sign-out imposed from outside the
   * BFF refuses the unsubscribe (no session any more), but deleting the token at FCM still makes it useless. A network
   * failure or a 5xx of /app/me is not the end of a session: push stays on (N2). If push was on, it comes back by
   * itself when the same person signs in again on this device, never for anyone else (P-44).
   */
  const signedOut = useCallback((sessionOver: boolean = true) => {
    sessionGen.current += 1;
    setMe(null);
    setStatus("anonymous");
    // F-15 (second review R-1): the shared-device key is not removed here: a 401 ends the app's session but not
    // Firebase's, and a key kept makes the next read that succeeds find «expired». It goes with «Esci», the automatic
    // exit, Firebase saying the session is over, «Esci da tutti i dispositivi» and the deleted account.
    lastUid.current = null;
    endSupportSession();
    clearUserData(queryClient);
    if (sessionOver) void disablePush({ resume: true }).catch(() => undefined);
  }, [queryClient]);

  /** Leaving this device on purpose: it stops receiving that user's push (it would reach the next account too); back on
   *  at their own next sign-in here if it was on (P-44). */
  const leaveDevice = () => disablePush({ resume: true }).catch(() => undefined);

  /**
   * «Esci»: also the automatic exit of a shared device (F-15), with the same cleaning of the push (P-44). The person's
   * shared-device key goes too (review S-6): the next sign-in passes through the box anyway.
   */
  const leave = useCallback((uid: string | null = lastUid.current, hide = false): Promise<void> => {
    // F-15 (second review R-2): one sign-out at a time; touches during it do not start another one, which could
    // finish later and sign out the next person
    if (exiting.current) return exiting.current;
    // the automatic exit hides the person's page at once, before the network calls (and shows no form either)
    if (hide) setStatus("loading");
    const run = (async () => {
      try {
        await closeOwnSupport();
        await leaveDevice(); // while still signed in: the BFF needs the user's token to drop the push registration
        if (env.authMode === "dev") localStorage.removeItem(DEV_KEY);
        else await firebaseSignOut();
        if (uid) forgetShared(uid);
        signedOut();
      } catch (err) {
        // the key stays: the next opening finds «expired» again; the page does not stay hidden for ever
        if (hide) signedOut();
        throw err;
      }
    })();
    const shared = run.finally(() => {
      exiting.current = null;
    });
    exiting.current = shared;
    return shared;
  }, [signedOut]);

  /** F-15: 30 minutes without using the app on a shared device; the sign-in page says why the person is out. */
  const autoLeave = useRef<(uid: string) => Promise<void>>(async () => {});
  autoLeave.current = async (uid: string) => {
    if (exiting.current) return exiting.current;
    setAutoLoggedOut(true);
    await leave(uid, true).catch(() => undefined);
  };

  /** The assistance access ended (closed, expired): back to the manager's own area, the tab emptied (P-50). */
  const dropSupport = useCallback((expired: boolean) => {
    const s = supportSession();
    if (!s) return false;
    endSupportSession();
    clearUserData(queryClient);
    toast.dismiss(); // the assisted organization's notices go with it
    if (expired) toast.info(t("support.expired", { name: s.tenant_name }), { duration: 10000 });
    return true;
  }, [queryClient]);

  /** /app/me refused or unreachable: decide whether the session is over and what to tell the person. */
  const profileFailed = useCallback(async (err: unknown) => {
    // D-211: no network, no answer in time or a 5xx, at the start or while in the app, is a hiccup, not the end of the
    // session: nothing is emptied, push stays on (N2), and the page says so with «Ricarica» instead of showing the sign-in.
    if (err instanceof ApiError && (err.status === 0 || err.status >= 500)) {
      setProblem(err.status === 0 ? "network" : "server");
      setStatus("unavailable");
      return;
    }
    // Only the BFF can say the session is over (401, 403).
    signedOut(err instanceof ApiError && (err.status === 401 || err.status === 403));
    if (!(err instanceof ApiError) || err.status === 401) return; // no session yet / expired: the login page is enough
    if (err.status === 403 && err.code === "email_not_verified") {
      // Invited with an unverified address: send the verification email, then sign out until it is confirmed.
      try {
        const { sendEmailVerification } = await import("firebase/auth");
        const user = (await firebaseAuth()).currentUser;
        if (user) await sendEmailVerification(user, continueUrl());
        toast.info(t("login.verifySent", { email: user?.email ?? "" }), { duration: 15000 });
      } catch {
        toast.error(t("login.verifyFailed"), { duration: 10000 });
      }
      await firebaseSignOut();
      return;
    }
    if (err.status === 403 && err.code === "tenant_suspended") {
      // Organization suspended by the platform (P-50, D-85): its own text, and out of Firebase until reactivated.
      toast.error(t("login.tenantSuspended"), { duration: 15000 });
      await firebaseSignOut();
      return;
    }
    if (err.status === 403) {
      // Firebase accepted the account but the BFF has no tenant/role for it: say so and drop the Firebase session,
      // otherwise every reload silently repeats the 403. An organization without record gets its own text (D-63).
      toast.error(err.code === "tenant_inactive" ? t("login.tenantInactive") : t("login.notEnabled"), { duration: 10000 });
      await firebaseSignOut();
      return;
    }
    toast.error(t("login.bffError"), { description: err.message, duration: 10000 });
  }, [signedOut]);

  const loadMe = useCallback(async (): Promise<void> => {
    profileLoading.current = true;
    let retried = false;
    try {
      for (;;) {
        const gen = sessionGen.current;
        const stale = () => exiting.current !== null || gen !== sessionGen.current;
        try {
          const next = await bffFetch<Me>("/app/me");
          if (stale()) return; // the person left meanwhile (F-15): this answer belongs to a session that is over
          // F-15: the box of this sign-in becomes this person's choice; an opening after 30 minutes on a shared
          // device asks the sign-in again, before any page is shown. A read of the profile is never a use (review
          // S-2: the administrators' notice reads it every 2 minutes): it only checks.
          const now = Date.now();
          adoptSharedChoice(next.user.uid, now);
          if (sharedExpired(next.user.uid, now)) {
            await autoLeave.current(next.user.uid);
            return;
          }
          setAutoLoggedOut(false);
          if (lastUid.current && lastUid.current !== next.user.uid) clearUserData(queryClient);
          lastUid.current = next.user.uid;
          setMe(next);
          setStatus("authenticated");
          return;
        } catch (err) {
          // Refused while working inside another organization (access over, or that organization suspended): back to
          // the manager's own profile without the header, never out of the app (P-50). At most one retry.
          if (!retried && err instanceof ApiError && err.status === 403 && supportSession()) {
            retried = true;
            dropSupport(true);
            continue;
          }
          if (stale()) return;
          await profileFailed(err);
          return;
        }
      }
    } finally {
      profileLoading.current = false;
      const code = pendingBlock.current;
      pendingBlock.current = null;
      // Checked again only if the person is still in: a read that ended the session already answered it.
      if (code && lastUid.current) queueMicrotask(() => onBlocked.current(code));
    }
  }, [queryClient, dropSupport, profileFailed]);

  const leaveSupport = useCallback(async (expired = false) => {
    if (dropSupport(expired)) await loadMe();
  }, [dropSupport, loadMe]);

  // One place for "the organization was suspended" (P-50): any call answering 403 tenant_suspended re-reads the
  // profile, which decides. A member is signed out with the dedicated text; a platform manager stays, without the
  // organization's pages. Several failing calls at once cause one re-read.
  useEffect(() => {
    onBlocked.current = (code) => {
      // A profile read in flight comes first (it may be /app/me's own 403); the code is checked again right after it.
      if (profileLoading.current) {
        pendingBlock.current = code;
        return;
      }
      if (code === "support_expired") void leaveSupport(true);
      else void loadMe();
    };
    setBlockedHandler((code) => onBlocked.current(code));
    return () => setBlockedHandler(() => {});
  }, [loadMe, leaveSupport]);

  // The access ends at expires_at even with no call to notice it (P-50). The device clock may be off, so at that time
  // the server is asked (the profile is re-read): it answers 403 support_expired, or that the access is still on.
  const supportEnd = me?.support?.expires_at;
  useEffect(() => {
    if (!supportEnd) return;
    const ms = Date.parse(supportEnd) - Date.now() + SUPPORT_END_MARGIN_MS;
    const timer = setTimeout(() => void loadMe(), Math.min(Math.max(ms, 0), 2 ** 31 - 1));
    return () => clearTimeout(timer);
  }, [supportEnd, loadMe]);

  useEffect(() => {
    if (env.authMode === "dev") {
      if (localStorage.getItem(DEV_KEY)) void loadMe();
      else setStatus("anonymous");
      return;
    }
    if (!firebaseConfigured) {
      setStatus("anonymous");
      return;
    }
    let unsub = () => {};
    void Promise.all([import("firebase/auth"), firebaseAuth()]).then(([{ onAuthStateChanged }, auth]) => {
      unsub = onAuthStateChanged(auth, (user) => {
        setProviders(user ? user.providerData.map((p) => p.providerId) : []);
        if (user) void loadMe();
        else {
          // Firebase says the session is over (another tab left, revoked): the person's shared-device key goes (R-1)
          if (lastUid.current) forgetShared(lastUid.current);
          signedOut();
        }
      });
    }).catch(() => {
      // E-29: a block of a previous release that no longer exists, as for the pages (lazyPage): one reload, then say so.
      if (!reloadOnce()) setStatus("unavailable");
    });
    return () => unsub();
  }, [loadMe, signedOut]);

  // F-15: on a shared device a tap, a key or scrolling (wheel, a finger moving; review S-7) is a use, and nothing else;
  // every minute, and on coming back to the page (visibility, focus, back-forward cache: second review R-3; before the
  // return counts as a use), more than 30 minutes since the last use means the automatic exit. A tab that started as
  // shared and no longer finds the key (another tab left and removed it: R-1) leaves too.
  const sharedUid = status === "authenticated" ? me?.user.uid : undefined;
  useEffect(() => {
    if (!sharedUid || !isShared(sharedUid)) return;
    const check = () => {
      if (!isShared(sharedUid)) {
        void leave(sharedUid, true).catch(() => undefined);
        return true;
      }
      if (sharedExpired(sharedUid, Date.now())) {
        void autoLeave.current(sharedUid);
        return true;
      }
      return false;
    };
    const used = () => {
      if (!check()) touchShared(sharedUid, Date.now());
    };
    const back = () => {
      if (document.visibilityState === "visible") check();
    };
    const every = setInterval(check, 60_000);
    const USE = ["pointerdown", "keydown", "wheel", "touchmove"] as const;
    for (const type of USE) window.addEventListener(type, used, { capture: true, passive: true });
    document.addEventListener("visibilitychange", back);
    window.addEventListener("focus", back);
    window.addEventListener("pageshow", back);
    return () => {
      clearInterval(every);
      for (const type of USE) window.removeEventListener(type, used, { capture: true });
      document.removeEventListener("visibilitychange", back);
      window.removeEventListener("focus", back);
      window.removeEventListener("pageshow", back);
    };
  }, [sharedUid, leave]);

  // E-29: without this a start that never answers is a loading state for ever, with no request and no message.
  useEffect(() => {
    // not while a sign-out hides the page (F-15 R-2): it ends in «anonymous» by itself
    if (status !== "loading" || exiting.current) return;
    const timer = setTimeout(() => setStatus("unavailable"), STARTUP_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [status]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      problem,
      me,
      providers,
      // F-15 (review S-1): the box is written here, at the moment of the sign-in, and nowhere else; a sign-in that
      // fails leaves nothing behind
      devLogin: async (email, shared = false) => {
        rememberSharedChoice(shared);
        localStorage.setItem(DEV_KEY, email);
        await loadMe();
      },
      emailLogin: async (email, password, shared = false) => {
        const { signInWithEmailAndPassword } = await import("firebase/auth");
        rememberSharedChoice(shared);
        try {
          await signInWithEmailAndPassword(await firebaseAuth(), email, password);
        } catch (err) {
          forgetSharedChoice();
          throw err;
        }
      },
      googleLogin: async (shared = false) => {
        const { signInWithPopup, GoogleAuthProvider } = await import("firebase/auth");
        rememberSharedChoice(shared);
        try {
          await signInWithPopup(await firebaseAuth(), new GoogleAuthProvider());
        } catch (err) {
          forgetSharedChoice();
          throw err;
        }
      },
      autoLoggedOut,
      logout: () => {
        setAutoLoggedOut(false);
        return leave();
      },
      refreshMe: loadMe,
      enterSupport: async (s) => {
        startSupportSession(s);
        clearUserData(queryClient);
        await loadMe();
      },
      leaveSupport: () => leaveSupport(false),
      resetPassword: async (email) => {
        const { sendPasswordResetEmail } = await import("firebase/auth");
        await sendPasswordResetEmail(await firebaseAuth(), email, continueUrl());
      },
      changePassword: async (current, next) => {
        const { updatePassword } = await import("firebase/auth");
        await updatePassword(await reauthenticate(current), next);
      },
      changeEmail: async (current, newEmail) => {
        // Firebase changes the address only when the link sent to the new mailbox is opened.
        const { verifyBeforeUpdateEmail } = await import("firebase/auth");
        await verifyBeforeUpdateEmail(await reauthenticate(current), newEmail, continueUrl());
      },
      logoutEverywhere: async () => {
        const uid = lastUid.current;
        await closeOwnSupport();
        await leaveDevice(); // before the revocation, which makes this session's token useless
        await bffFetch<void>("/app/me/revoke-sessions", { method: "POST" });
        if (env.authMode === "dev") localStorage.removeItem(DEV_KEY);
        else await firebaseSignOut();
        if (uid) forgetShared(uid);
        signedOut();
      },
      deleteAccount: async () => {
        // The BFF may refuse (409 last_admin / last_manager, D-73): the device keeps its push until the deletion is
        // accepted. DELETE /app/me drops the user's tokens on the server; signedOut then deletes this one at FCM.
        const uid = me?.user.uid;
        await closeOwnSupport(); // an assistance access in progress is closed first (D-89)
        await bffFetch<void>("/app/me", { method: "DELETE" });
        if (env.authMode === "dev") localStorage.removeItem(DEV_KEY);
        else await firebaseSignOut();
        if (uid) forgetShared(uid);
        signedOut();
        if (uid) forgetPushResume(uid); // the account is gone: nothing to bring back (P-44)
      },
    }),
    [status, problem, me, providers, loadMe, signedOut, leaveSupport, queryClient, leave, autoLoggedOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

/** What the profile allows. A suspended organization (seen only by a platform manager, P-50) counts as none. */
export function roleOf(me: Me | null) {
  const suspended = me?.tenant?.suspended === true;
  const role = suspended ? "viewer" : me?.role ?? "viewer";
  return {
    role,
    canWrite: !suspended && (role === "operator" || role === "admin"),
    isAdmin: !suspended && role === "admin",
    /** Platform manager (P-36): the Organizzazioni area, whatever the role inside an organization. */
    isPlatform: me?.user.platform_manager === true,
    /** False for a platform manager outside any organization, or whose organization is suspended: no apartments, no Amministrazione. */
    hasTenant: Boolean(me?.tenant) && !suspended,
  };
}

export function useRole() {
  return roleOf(useAuth().me);
}

/** Italian message for a Firebase Auth error code (falls back to a generic one). */
export function authErrorMessage(err: unknown): string {
  const code = (err as { code?: string })?.code ?? "";
  const key = {
    "auth/wrong-password": "wrongPassword",
    "auth/invalid-credential": "wrongPassword",
    "auth/invalid-login-credentials": "wrongPassword",
    "auth/weak-password": "weakPassword",
    "auth/email-already-in-use": "emailInUse",
    "auth/invalid-email": "invalidEmail",
    "auth/too-many-requests": "tooManyRequests",
    "auth/requires-recent-login": "recentLogin",
    "auth/network-request-failed": "network",
  }[code];
  if (err instanceof ApiError) return err.message;
  return t(`account.errors.${key ?? "generic"}`);
}
