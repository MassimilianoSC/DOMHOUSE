import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { CopyableId } from "@/components/ui/CopyableId";
import { t } from "@/i18n";
import { newCorrelationId } from "./utils";

/** F-11: a name or an address refused by the server (422 invalid_text): its field and the sentence to show under it. */
export function invalidText(err: unknown): { field: string; message: string } | null {
  if (!(err instanceof ApiError) || err.code !== "invalid_text") return null;
  const field = err.details?.field;
  return typeof field === "string" ? { field, message: err.message } : null;
}

/**
 * Runs a user action with a fresh correlation id; on failure shows the contract `message` and the copyable id.
 * fieldProblem: a refused name or address (F-11) goes under its field instead; it returns false for a field the form
 * does not have, and then the usual red notice is shown.
 */
export async function runAction<T>(
  fn: (correlationId: string) => Promise<T>,
  opts: { success?: string; fieldProblem?: (field: string, message: string) => boolean } = {},
): Promise<T | undefined> {
  const correlationId = newCorrelationId();
  try {
    const result = await fn(correlationId);
    if (opts.success) toast.success(opts.success);
    return result;
  } catch (err) {
    const refused = invalidText(err);
    if (!(refused && opts.fieldProblem?.(refused.field, refused.message))) showError(err, correlationId);
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
