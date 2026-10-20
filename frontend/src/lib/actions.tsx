import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { CopyableId } from "@/components/ui/CopyableId";
import { t } from "@/i18n";
import { newCorrelationId } from "./utils";

/** Runs a user action with a fresh correlation id; on failure shows the contract `message` and the copyable id. */
export async function runAction<T>(fn: (correlationId: string) => Promise<T>, opts: { success?: string } = {}): Promise<T | undefined> {
  const correlationId = newCorrelationId();
  try {
    const result = await fn(correlationId);
    if (opts.success) toast.success(opts.success);
    return result;
  } catch (err) {
    showError(err, correlationId);
    return undefined;
  }
}

export function showError(err: unknown, correlationId: string | null) {
  const message = err instanceof ApiError ? err.message : t("errors.generic");
  const id = (err instanceof ApiError ? err.correlationId : null) ?? correlationId;
  toast.error(message, {
    description: id ? (
      <span className="flex items-center gap-1.5" data-testid="toast-error-correlation">
        {t("common.correlationId")} <CopyableId id={id} testId="toast-correlation-id" />
      </span>
    ) : undefined,
    duration: 8000,
  });
}
