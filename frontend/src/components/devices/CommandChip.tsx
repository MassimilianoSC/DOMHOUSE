import { Check, Loader2, TriangleAlert } from "lucide-react";
import { CopyableId } from "@/components/ui/CopyableId";
import { t, tOr } from "@/i18n";
import { cn } from "@/lib/utils";
import type { TrackedCommand, DeviceError } from "@/store/streamReducer";
import { isInProgress } from "@/store/streamReducer";

export function reasonText(reason: string | null | undefined): string {
  if (!reason) return "";
  return `${tOr(`command.reason.${reason}`, reason)} · ${reason}`;
}

/** Inline status of the last command of a device: in corso → eseguito, or the error with its reason. */
export function CommandChip({ command, error, testId }: { command?: TrackedCommand; error?: DeviceError; testId: string }) {
  if (error && !command) {
    return (
      <span data-testid={testId} data-status="error" role="status" className={chip("err")}>
        <TriangleAlert className="h-3.5 w-3.5" aria-hidden /> {error.message}
        {error.correlationId && <CopyableId id={error.correlationId} testId={`${testId}-correlation`} />}
      </span>
    );
  }
  if (!command) return null;
  if (isInProgress(command.status)) {
    return (
      <span data-testid={testId} data-status={command.status} role="status" className={chip("busy")}>
        <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> {t("command.pending")}
      </span>
    );
  }
  if (command.status === "acked") {
    return (
      <span data-testid={testId} data-status="acked" role="status" className={cn(chip("ok"), "animate-glow")}>
        <Check className="h-3.5 w-3.5" aria-hidden /> {t("command.acked")}
      </span>
    );
  }
  return (
    <span data-testid={testId} data-status={command.status} role="status" className={chip("err")}>
      <TriangleAlert className="h-3.5 w-3.5" aria-hidden />
      {t(`command.${command.status === "timeout" ? "timeout" : "failed"}`)}
      {command.reason ? `: ${reasonText(command.reason)}` : ""}
      {command.correlationId && <CopyableId id={command.correlationId} testId={`${testId}-correlation`} />}
    </span>
  );
}

function chip(kind: "busy" | "ok" | "err") {
  return cn(
    "inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold animate-fade-up",
    kind === "busy" && "border-warning-border bg-warning-bg text-warning-fg",
    kind === "ok" && "border-positive-border bg-positive-bg text-positive-fg",
    kind === "err" && "border-negative-border bg-negative-bg text-negative-fg",
  );
}
