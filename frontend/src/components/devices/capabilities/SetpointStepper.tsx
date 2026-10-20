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
  const dec = Math.max(min, Math.round((value - STEP) * 2) / 2);
  const inc = Math.min(max, Math.round((value + STEP) * 2) / 2);
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
        <div className="font-heading text-2xl font-extrabold tabular" data-testid={`${testId}-value`}>
          {fmtNumber(value)}°
        </div>
        <div className="text-[10px] text-muted-foreground">{t("cap.range", { min: fmtNumber(min), max: fmtNumber(max) })}</div>
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
