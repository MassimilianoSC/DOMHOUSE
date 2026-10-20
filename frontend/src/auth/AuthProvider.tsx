import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ApiError, bffFetch, setAuthResolver, setBlockedHandler } from "@/api/bff";
import { platformApi } from "@/api/platform";
import type { Me } from "@/api/types";
import { t } from "@/i18n";
import { disablePush, forgetPushResume } from "@/lib/push";
import { clearUserData } from "@/lib/session";
import { endSupportSession, startSupportSession, supportSession, type SupportSession } from "@/lib/support";
import { env, newCorrelationId } from "@/lib/utils";
import { continueUrl, firebaseAuth, firebaseConfigured } from "./firebase";

const DEV_KEY = "domotica.devUser";
/** After the expected end of an assistance access, a little later the profile is re-read (P-50). */
const SUPPORT_END_MARGIN_MS = 5_000;

/** A deliberate sign-out also ends an assistance access on the server, so the admin stops seeing it (P-50). */
async function closeOwnSupport() {
  const s = supportSession();
  if (s) await platformApi.closeSupport(s.tenant_id, s.access_id, newCorrelationId()).catch(() => undefined);
}

type Status = "loading" | "anonymous" | "authenticated";

interface AuthContextValue {
  status: Status;
  me: Me | null;
  /** Firebase sign-in providers of the current user ("password", "google.com"); empty in dev mode. */
  providers: string[];
  devLogin: (email: string) => Promise<void>;
  emailLogin: (email: string, password: string) => Promise<void>;
  googleLogin: () => Promise<void>;
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
  const [providers, setProviders] = useState<string[]>([]);
  const queryClient = useQueryClient();
  const lastUid = useRef<string | null>(null);
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
    setMe(null);
    setStatus("anonymous");
    lastUid.current = null;
    endSupportSession();
    clearUserData(queryClient);
    if (sessionOver) void disablePush({ resume: true }).catch(() => undefined);
  }, [queryClient]);

  /** Leaving this device on purpose: it stops receiving that user's push (it would reach the next account too); back on
   *  at their own next sign-in here if it was on (P-44). */
  const leaveDevice = () => disablePush({ resume: true }).catch(() => undefined);

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
    // Only the BFF can say the session is over (401, 403); no network or a 5xx (cold start) is a hiccup (N2).
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
        try {
          const next = await bffFetch<Me>("/app/me");
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
        else signedOut();
      });
    });
    return () => unsub();
  }, [loadMe, signedOut]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      me,
      providers,
      devLogin: async (email) => {
        localStorage.setItem(DEV_KEY, email);
        await loadMe();
      },
      emailLogin: async (email, password) => {
        const { signInWithEmailAndPassword } = await import("firebase/auth");
        await signInWithEmailAndPassword(await firebaseAuth(), email, password);
      },
      googleLogin: async () => {
        const { signInWithPopup, GoogleAuthProvider } = await import("firebase/auth");
        await signInWithPopup(await firebaseAuth(), new GoogleAuthProvider());
      },
      logout: async () => {
        await closeOwnSupport();
        await leaveDevice(); // while still signed in: the BFF needs the user's token to drop the push registration
        if (env.authMode === "dev") localStorage.removeItem(DEV_KEY);
        else await firebaseSignOut();
        signedOut();
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
        await closeOwnSupport();
        await leaveDevice(); // before the revocation, which makes this session's token useless
        await bffFetch<void>("/app/me/revoke-sessions", { method: "POST" });
        if (env.authMode === "dev") localStorage.removeItem(DEV_KEY);
        else await firebaseSignOut();
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
        signedOut();
        if (uid) forgetPushResume(uid); // the account is gone: nothing to bring back (P-44)
      },
    }),
    [status, me, providers, loadMe, signedOut, leaveSupport, queryClient],
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
