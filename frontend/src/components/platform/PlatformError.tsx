import { useEffect } from "react";
import { ApiError } from "@/api/bff";
import { useAuth } from "@/auth/AuthProvider";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { t } from "@/i18n";

/**
 * Error of a platform call. A 403 means the platform role was taken away while the page was open: say so and reload
 * the profile, so "Organizzazioni" disappears from the menu (and PlatformOnly closes the page). Other errors as usual.
 */
export function PlatformError({ error, onRetry, testId }: { error: unknown; onRetry?: () => void; testId: string }) {
  const { refreshMe } = useAuth();
  const lost = error instanceof ApiError && error.status === 403;
  useEffect(() => {
    if (lost) void refreshMe();
  }, [lost, refreshMe]);
  if (lost) {
    return (
      <p role="alert" className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300" data-testid={`${testId}-no-access`}>
        {t("platform.noAccess")}
      </p>
    );
  }
  return <ErrorNotice error={error} onRetry={onRetry} testId={testId} />;
}
