import { TriangleAlert } from "lucide-react";
import { ApiError } from "@/api/bff";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

interface Props {
  error: unknown;
  onRetry?: () => void;
  testId?: string;
  className?: string;
}

/** Inline error label with the contract message and the copyable correlation id. */
export function ErrorNotice({ error, onRetry, testId = "error-notice", className }: Props) {
  const api = error instanceof ApiError ? error : null;
  const message = api?.message ?? (error instanceof Error ? error.message : t("errors.generic"));
  return (
    <div role="alert" data-testid={testId} className={cn("flex flex-wrap items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300", className)}>
      <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden />
      <span className="font-medium">{message}</span>
      {api?.code && <span className="font-mono text-xs opacity-70">{api.code}</span>}
      {api?.correlationId && <CopyableId id={api.correlationId} testId={`${testId}-correlation`} />}
      {onRetry && (
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onRetry} data-testid={`${testId}-retry`}>
          {t("common.retry")}
        </Button>
      )}
    </div>
  );
}
