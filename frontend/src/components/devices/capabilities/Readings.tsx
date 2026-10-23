import type { ReactNode } from "react";
import { t } from "@/i18n";
import { fmtDateTime, fmtNumber, fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { tid, type CapProps, type ContactState, type HumidityState, type MotionState, type PowerMeterState, type TemperatureState } from "./types";

/** One reading as a row: «Temperatura … 21,5 °C», label left, value right, a note under the value (design lot 2). */
function Reading({ label, value, sub, testId, tone }: { label: string; value: ReactNode; sub?: ReactNode; testId: string; tone?: "warn" }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 text-sm" data-testid={testId}>
      <span className="min-w-0 text-muted-foreground [overflow-wrap:anywhere]">{label}</span>
      <span className="shrink-0 text-right">
        <span className={cn("font-semibold tabular", tone === "warn" && "text-warning-fg")}>{value}</span>
        {sub && <span className="block text-xs text-muted-foreground">{sub}</span>}
      </span>
    </div>
  );
}

export function PowerMeterView({ device, state }: CapProps<PowerMeterState>) {
  return (
    <Reading
      label={t("cap.watts")}
      value={`${fmtNumber(state.watts, 0)} W`}
      sub={`${t("cap.kwhToday")}: ${fmtNumber(state.kwh_today, 2)} kWh`}
      testId={tid(device, "power-meter")}
    />
  );
}

export function TemperatureView({ device, state }: CapProps<TemperatureState>) {
  return <Reading label={t("cap.temperature")} value={`${fmtNumber(state.celsius)} °C`} testId={tid(device, "temperature")} />;
}

export function HumidityView({ device, state }: CapProps<HumidityState>) {
  return <Reading label={t("cap.humidity")} value={`${fmtNumber(state.percent, 0)} %`} testId={tid(device, "humidity")} />;
}

export function ContactView({ device, state, tz }: CapProps<ContactState>) {
  return (
    <Reading
      label={device.label}
      value={state.open ? t("cap.contactOpen") : t("cap.contactClosed")}
      sub={state.since ? <span title={fmtDateTime(state.since, tz)}>{t("cap.since", { when: fmtRelative(state.since).replace(/ fa$/, "") })}</span> : undefined}
      tone={state.open ? "warn" : undefined}
      testId={tid(device, "contact")}
    />
  );
}

export function MotionView({ device, state, tz }: CapProps<MotionState>) {
  return (
    <Reading
      label={state.detected ? t("cap.motionDetected") : t("cap.motionNone")}
      value={state.last_seen ? <span title={fmtDateTime(state.last_seen, tz)}>{fmtRelative(state.last_seen)}</span> : "—"}
      testId={tid(device, "motion")}
    />
  );
}
