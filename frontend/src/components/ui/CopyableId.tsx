import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

/** Correlation id shown next to every error: short mono label, full id on hover, one tap to copy. `label` names
 *  something else (a Firebase code, D-156) and `full` shows it whole instead of its first 8 characters. */
export function CopyableId({ id, testId, className, label, full = false }: { id: string; testId?: string; className?: string; label?: string; full?: boolean }) {
  const name = label ?? t("common.correlationId");
  const [copied, setCopied] = useState(false);
  const copy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(id);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable: the full id stays visible in the title */
    }
  };
  return (
    <button
      type="button"
      onClick={copy}
      title={`${name}: ${id}`}
      aria-label={`${t("common.copy")} ${name} ${id}`}
      data-testid={testId ?? "correlation-id"}
      data-correlation-id={id}
      className={cn("inline-flex max-w-full items-center gap-1 rounded-md border border-dashed border-current/40 px-1.5 py-0.5 font-mono text-xs opacity-80 transition-opacity hover:opacity-100 focus-ring", className)}
    >
      {copied ? <Check className="h-3 w-3" aria-hidden /> : <Copy className="h-3 w-3" aria-hidden />}
      <span className="truncate">{copied ? t("common.copied") : full ? id : id.slice(0, 8)}</span>
    </button>
  );
}
