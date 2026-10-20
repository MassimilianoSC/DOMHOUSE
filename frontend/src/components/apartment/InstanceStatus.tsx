import { Cpu, PlugZap, Radio, ServerCrash } from "lucide-react";
import type { Health } from "@/api/types";
import { Badge } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";

interface Props {
  health: Health | null;
  contractVersion?: string | null;
  features?: string[];
  compact?: boolean;
}

const STATUS_TONE = {
  ok: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  degraded: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
  down: "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-300",
};

/** Reusable instance status: /health, plus the contract version and features of the apartment summary. */
export function InstanceStatus({ health, contractVersion, features, compact }: Props) {
  if (!health) {
    return (
      <div data-testid="instance-status" className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
        <ServerCrash className="h-4 w-4" aria-hidden /> {t("instance.unreachable")}
      </div>
    );
  }
  const items = [
    { icon: <PlugZap className="h-3.5 w-3.5" />, text: `${t("instance.connector")} ${health.connector.status === "up" ? t("instance.up") : t("instance.downLabel")}`, id: "connector" },
    { icon: <Radio className="h-3.5 w-3.5" />, text: t("instance.connected", { count: health.connector.connected_devices }), id: "devices" },
    { icon: <Cpu className="h-3.5 w-3.5" />, text: `${t("instance.model")} ${health.model_provider.provider} · ${health.model_provider.status}`, id: "model" },
  ];
  return (
    <div data-testid="instance-status" className={cn("flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border bg-card/70 px-4 py-3 text-xs backdrop-blur", compact && "py-2")}>
      <Badge data-testid="instance-health-status" className={STATUS_TONE[health.status]}>
        {t(`instance.status.${health.status}`)}
      </Badge>
      {items.map((i) => (
        <span key={i.id} className="flex items-center gap-1.5 text-muted-foreground" data-testid={`instance-${i.id}`}>
          {i.icon} {i.text}
        </span>
      ))}
      <span className="font-mono text-[11px] text-muted-foreground" data-testid="instance-version">
        {health.implementation.name} {health.implementation.version}
        {contractVersion ? ` · ${t("instance.contract")} ${contractVersion}` : ""}
      </span>
      {health.connector.last_event_at && !compact && (
        <span className="text-muted-foreground">{t("instance.lastEvent", { when: fmtRelative(health.connector.last_event_at) })}</span>
      )}
      {features && !compact && (
        <span className="flex flex-wrap gap-1" data-testid="instance-features">
          {features.map((f) => (
            <span key={f} className="rounded-md bg-secondary px-1.5 py-0.5 font-mono text-[10px]">
              {f}
            </span>
          ))}
        </span>
      )}
    </div>
  );
}
