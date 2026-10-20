import { Power } from "lucide-react";
import { Switch, Tip } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";
import { SetpointStepper } from "./SetpointStepper";
import { tid, type CapProps, type ClimateState, type HeatingState, type SwitchState } from "./types";

const CLIMATE_MODES = ["heat", "cool", "dry", "fan"] as const;
const FANS = ["auto", "low", "mid", "high"] as const;

function OnOff({ on, label, disabled, onToggle, testId }: { on: boolean; label: string; disabled: boolean; onToggle: (v: boolean) => void; testId: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className={cn("flex items-center gap-2 text-sm font-semibold", on ? "text-accent" : "text-muted-foreground")}>
        <span className={cn("h-2 w-2 rounded-full", on ? "bg-accent shadow-[0_0_8px_hsl(var(--accent))]" : "bg-muted-foreground/40")} />
        {on ? t("cap.on") : t("cap.off")}
      </span>
      <Switch
        checked={on}
        disabled={disabled}
        onCheckedChange={onToggle}
        aria-label={on ? t("cap.turnOff", { name: label }) : t("cap.turnOn", { name: label })}
        data-testid={testId}
      />
    </div>
  );
}

export function SwitchControl({ device, state, disabled, send }: CapProps<SwitchState>) {
  return (
    <OnOff
      on={state.on}
      label={device.label}
      disabled={disabled}
      testId={tid(device, "switch-toggle")}
      onToggle={(v) => send({ capability: "switch", action: v ? "turn_on" : "turn_off" })}
    />
  );
}

export function HeatingControl({ device, state, disabled, send }: CapProps<HeatingState>) {
  return (
    <div className="space-y-3">
      <OnOff
        on={state.on}
        label={device.label}
        disabled={disabled}
        testId={tid(device, "heating-toggle")}
        onToggle={(v) => send(v ? { capability: "heating", action: "set_heating", params: { on: true } } : { capability: "heating", action: "turn_off" })}
      />
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("cap.setpoint")}</span>
        <SetpointStepper
          value={state.setpoint}
          min={state.setpoint_min}
          max={state.setpoint_max}
          disabled={disabled}
          testId={tid(device, "heating-setpoint")}
          onChange={(v) => send({ capability: "heating", action: "set_heating", params: { setpoint: v } })}
        />
      </div>
    </div>
  );
}

function Pills<T extends string>({ value, options, label, disabled, onPick, testId, i18n }: { value: T; options: readonly T[]; label: string; disabled: boolean; onPick: (v: T) => void; testId: string; i18n: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1.5" data-testid={testId}>
      {options.map((o) => (
        <button
          key={o}
          type="button"
          role="radio"
          aria-checked={value === o}
          disabled={disabled}
          data-testid={`${testId}-${o}`}
          onClick={() => value !== o && onPick(o)}
          className={cn(
            "rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors focus-ring disabled:opacity-50",
            value === o ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-secondary",
          )}
        >
          {t(`${i18n}.${o}`)}
        </button>
      ))}
    </div>
  );
}

export function ClimateControl({ device, state, disabled, send }: CapProps<ClimateState>) {
  const set = (params: NonNullable<Parameters<CapProps<ClimateState>["send"]>[0]["params"]>) =>
    send({ capability: "climate", action: "set_climate", params });
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="flex-1">
          <OnOff
            on={state.on}
            label={device.label}
            disabled={disabled}
            testId={tid(device, "climate-toggle")}
            onToggle={(v) => (v ? set({ on: true }) : send({ capability: "climate", action: "turn_off" }))}
          />
        </div>
        {state.confirmation === "none" && (
          <Tip content={t("cap.notVerifiedHint")}>
            <span tabIndex={0} data-testid={tid(device, "climate-unverified")} className="rounded-full border border-dashed px-2 py-0.5 text-[10px] font-semibold uppercase text-muted-foreground focus-ring">
              {t("cap.notVerified")}
            </span>
          </Tip>
        )}
      </div>
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          <Power className="h-3 w-3" aria-hidden /> {t("cap.setpoint")}
        </span>
        <SetpointStepper
          value={state.setpoint}
          min={state.setpoint_min}
          max={state.setpoint_max}
          disabled={disabled}
          testId={tid(device, "climate-setpoint")}
          onChange={(v) => set({ setpoint: v })}
        />
      </div>
      <Pills value={state.mode} options={CLIMATE_MODES} label={t("cap.climateMode")} disabled={disabled} onPick={(m) => set({ mode: m })} testId={tid(device, "climate-mode")} i18n="cap.climateModes" />
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("cap.fan")}</span>
        <Pills value={state.fan} options={FANS} label={t("cap.fan")} disabled={disabled} onPick={(f) => set({ fan: f })} testId={tid(device, "climate-fan")} i18n="cap.fans" />
      </div>
    </div>
  );
}
