import { Activity, Droplets, Gauge, Thermometer, AppWindow } from "lucide-react";
import type { ReactNode } from "react";
import { t } from "@/i18n";
import { fmtDateTime, fmtNumber, fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { tid, type CapProps, type ContactState, type HumidityState, type MotionState, type PowerMeterState, type TemperatureState } from "./types";

function Reading({ icon, label, value, sub, testId, tone }: { icon: ReactNode; label: string; value: ReactNode; sub?: ReactNode; testId: string; tone?: "warn" }) {
  return (
    <div className="flex items-center gap-3 rounded-xl bg-secondary/60 px-3 py-2" data-testid={testId}>
      <span className={cn("text-muted-foreground", tone === "warn" && "text-primary")}>{icon}</span>
      <div className="min-w-0">
        <div className="text-[13px] font-medium text-muted-foreground">{label}</div>
        <div className={cn("text-sm font-bold tabular", tone === "warn" && "text-primary")}>{value}</div>
        {sub && <div className="truncate text-xs text-muted-foreground">{sub}</div>}
      </div>
    </div>
  );
}

export function PowerMeterView({ device, state }: CapProps<PowerMeterState>) {
  return (
    <Reading
      icon={<Gauge className="h-4 w-4" />}
      label={t("cap.watts")}
      value={`${fmtNumber(state.watts, 0)} W`}
      sub={`${t("cap.kwhToday")}: ${fmtNumber(state.kwh_today, 2)} kWh`}
      testId={tid(device, "power-meter")}
    />
  );
}

export function TemperatureView({ device, state }: CapProps<TemperatureState>) {
  return <Reading icon={<Thermometer className="h-4 w-4" />} label={t("cap.temperature")} value={`${fmtNumber(state.celsius)} °C`} testId={tid(device, "temperature")} />;
}

export function HumidityView({ device, state }: CapProps<HumidityState>) {
  return <Reading icon={<Droplets className="h-4 w-4" />} label={t("cap.humidity")} value={`${fmtNumber(state.percent, 0)} %`} testId={tid(device, "humidity")} />;
}

export function ContactView({ device, state, tz }: CapProps<ContactState>) {
  return (
    <Reading
      icon={<AppWindow className="h-4 w-4" />}
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
      icon={<Activity className="h-4 w-4" />}
      label={state.detected ? t("cap.motionDetected") : t("cap.motionNone")}
      value={state.last_seen ? <span title={fmtDateTime(state.last_seen, tz)}>{fmtRelative(state.last_seen)}</span> : "—"}
      testId={tid(device, "motion")}
    />
  );
}
