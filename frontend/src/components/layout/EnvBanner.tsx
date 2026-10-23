import { FlaskConical } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

/** The test environment says so on every page (P-67, D-136): /app/me gives env.app_env "staging". Production and the
 *  developer's PC show nothing. */
export function useIsStaging(): boolean {
  return useAuth().me?.env.app_env === "staging";
}

/** A thin amber band; the caller decides where it sits (inside the phone's header, on top of the computer's content). */
export function EnvBanner({ className, testId }: { className?: string; testId: string }) {
  if (!useIsStaging()) return null;
  return (
    <div
      className={cn(
        "flex min-h-7 items-center justify-center gap-1.5 border-b border-warning-border bg-warning-bg px-3 py-1 text-center text-xs font-semibold text-warning-fg",
        className,
      )}
      data-testid={testId}
    >
      <FlaskConical className="h-3.5 w-3.5 shrink-0" aria-hidden />
      <span>
        {t("envBanner.staging")} <span className="font-normal">· {t("envBanner.stagingHint")}</span>
      </span>
    </div>
  );
}
