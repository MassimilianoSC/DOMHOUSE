import { useState } from "react";
import { ChevronDown, ChevronUp, Radio, ServerCrash } from "lucide-react";
import type { Health } from "@/api/types";
import { StatusBadge, type Tone } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { fmtRelative } from "@/lib/format";

interface Props {
  health: Health | null;
  contractVersion?: string | null;
}

const STATUS_TONE: Record<Health["status"], Tone> = { ok: "positive", degraded: "warning", down: "negative" };

/**
 * The state of the apartment's home system: the badge and the devices connected; connector, model, implementation and
 * contract only behind «Dettagli tecnici» (design lot 2: no jargon for whoever just wants to know how the house is).
 */
export function InstanceStatus({ health, contractVersion }: Props) {
  const [open, setOpen] = useState(false);
  if (!health) {
    return (
      <div data-testid="instance-status" className="flex items-center gap-2 rounded-lg border border-negative-border bg-negative-bg px-4 py-3 text-sm font-semibold text-negative-fg">
        <ServerCrash className="h-4 w-4" aria-hidden /> {t("instance.unreachable")}
      </div>
    );
  }
  return (
    <div data-testid="instance-status" className="space-y-2 text-xs">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <StatusBadge tone={STATUS_TONE[health.status]} data-testid="instance-health-status">
          {t(`instance.status.${health.status}`)}
        </StatusBadge>
        <span className="flex items-center gap-1.5 text-muted-foreground" data-testid="instance-devices">
          <Radio className="h-3.5 w-3.5" aria-hidden /> {t("instance.connected", { count: health.connector.connected_devices })}
        </span>
        <button
          type="button"
          className="flex items-center gap-1 font-medium text-muted-foreground hover:text-foreground focus-ring [&_svg]:size-3.5"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
          data-testid="instance-details-toggle"
        >
          {open ? <ChevronUp aria-hidden /> : <ChevronDown aria-hidden />} {t("instance.details")}
        </button>
      </div>
      {open && (
        <dl className="grid gap-x-4 gap-y-1 text-muted-foreground sm:grid-cols-[auto_1fr]" data-testid="instance-details">
          <dt className="font-medium">{t("instance.connector")}</dt>
          <dd data-testid="instance-connector">{health.connector.status === "up" ? t("instance.up") : t("instance.downLabel")}</dd>
          <dt className="font-medium">{t("instance.model")}</dt>
          <dd data-testid="instance-model">{health.model_provider.provider} · {health.model_provider.status}</dd>
          <dt className="font-medium">{t("instance.implementation")}</dt>
          <dd className="tabular [overflow-wrap:anywhere]" data-testid="instance-version">
            {health.implementation.name} {health.implementation.version}
            {contractVersion ? ` · ${t("instance.contract")} ${contractVersion}` : ""}
          </dd>
          {health.connector.last_event_at && (
            <>
              <dt className="font-medium">{t("instance.lastEventLabel")}</dt>
              <dd>{fmtRelative(health.connector.last_event_at)}</dd>
            </>
          )}
        </dl>
      )}
    </div>
  );
}
