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
      <p role="alert" className="rounded-xl border border-warning-border bg-warning-bg px-3 py-2 text-sm font-medium text-warning-fg" data-testid={`${testId}-no-access`}>
        {t("platform.noAccess")}
      </p>
    );
  }
  return <ErrorNotice error={error} onRetry={onRetry} testId={testId} />;
}
