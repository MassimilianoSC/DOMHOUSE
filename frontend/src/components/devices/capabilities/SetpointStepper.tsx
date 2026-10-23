import { Minus, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { fmtNumber } from "@/lib/format";

const STEP = 0.5;

/** Setpoint stepper bounded by the engine's setpoint_min/max; shows the current state, never a draft. */
export function SetpointStepper(props: {
  value: number;
  min: number;
  max: number;
  disabled: boolean;
  onChange: (v: number) => void;
  testId: string;
}) {
  const { value, min, max, disabled, onChange, testId } = props;
  // Always inside min..max (D-174): a boiler the frost protection keeps at 8 °C under a minimum of 16 goes to 16 with
  // «+», never to 8.5, which the engine refuses; the same for «−» above the maximum.
  const clamp = (v: number) => Math.min(max, Math.max(min, v));
  const dec = clamp(Math.round((value - STEP) * 2) / 2);
  const inc = clamp(Math.round((value + STEP) * 2) / 2);
  return (
    <div className="flex items-center gap-2" data-testid={testId}>
      <Button
        variant="outline"
        size="iconSm"
        aria-label={t("cap.decrease")}
        data-testid={`${testId}-dec`}
        disabled={disabled || value <= min}
        onClick={() => onChange(dec)}
      >
        <Minus />
      </Button>
      <div className="min-w-[4.5rem] text-center">
        <div className="text-xl font-semibold tabular" data-testid={`${testId}-value`}>
          {fmtNumber(value)}°
        </div>
        <div className="text-xs text-muted-foreground">{t("cap.range", { min: fmtNumber(min), max: fmtNumber(max) })}</div>
      </div>
      <Button
        variant="outline"
        size="iconSm"
        aria-label={t("cap.increase")}
        data-testid={`${testId}-inc`}
        disabled={disabled || value >= max}
        onClick={() => onChange(inc)}
      >
        <Plus />
      </Button>
    </div>
  );
}
