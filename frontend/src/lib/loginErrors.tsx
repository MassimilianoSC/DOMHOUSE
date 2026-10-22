import { toast } from "sonner";
import { CopyableId } from "@/components/ui/CopyableId";
import { t } from "@/i18n";

// What the person reads when signing in fails (D-156): a sentence of its own for the cases they or HQE can act on,
// and always the Firebase code on a second line, copyable, so whoever helps knows the exact cause at once.

export type LoginMethod = "google" | "email";

/** «auth/requests-from-referer-https://…-are-blocked.»: the web API key does not accept this site's address. */
const REFERER_BLOCKED = /^auth\/requests-from-referer-.*-are-blocked\.?$/;

/** The sentence for a failed sign-in and the code to show under it; null when there is nothing to say (the person
 *  closed Google's window). */
export function loginError(err: unknown, method: LoginMethod): { message: string; code: string | null } | null {
  const raw = (err as { code?: unknown })?.code;
  const code = typeof raw === "string" && raw.trim() ? raw : null;
  if (code === "auth/popup-closed-by-user" || code === "auth/cancelled-popup-request" || code === "auth/user-cancelled") return null;
  if (code === "auth/unauthorized-domain" || (code && REFERER_BLOCKED.test(code))) return { message: t("login.errors.domain"), code };
  if (method === "google") {
    if (code === "auth/popup-blocked") return { message: t("login.errors.popupBlocked"), code };
    if (code === "auth/operation-not-allowed") return { message: t("login.errors.googleDisabled"), code };
    return { message: t("login.errors.googleFailed"), code };
  }
  if (code === "auth/too-many-requests") return { message: t("account.errors.tooManyRequests"), code };
  if (code === "auth/network-request-failed") return { message: t("account.errors.network"), code };
  return { message: t("login.failed"), code };
}

/** The error as a notice: the sentence, and «Codice: auth/…» under it. Nothing when the person closed the window. */
export function showLoginError(err: unknown, method: LoginMethod) {
  const e = loginError(err, method);
  if (!e) return;
  toast.error(e.message, {
    description: e.code ? (
      <span className="flex flex-wrap items-center gap-1.5" data-testid="login-error-code">
        {t("login.errors.code")}: <CopyableId id={e.code} label={t("login.errors.code")} full testId="login-error-code-id" />
      </span>
    ) : undefined,
    duration: 10000,
  });
}
