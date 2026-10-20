import { useEffect, useState } from "react";
import { Loader2, Timer, X } from "lucide-react";
import type { Apartment, ApartmentMode, Occupancy } from "@/api/types";
import { instanceApi } from "@/api/instance";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";
import { fmtRemaining, fmtTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const OCCUPANCY_STYLE: Record<Occupancy, string> = {
  vacant: "border-stone-300 bg-stone-100 text-stone-700 dark:border-stone-700 dark:bg-stone-800/60 dark:text-stone-300",
  occupied: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  reserved: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950/50 dark:text-amber-300",
};

export function OccupancyBadge({ occupancy, testId }: { occupancy: Occupancy; testId?: string }) {
  return (
    <Badge data-testid={testId ?? "occupancy-badge"} data-occupancy={occupancy} className={OCCUPANCY_STYLE[occupancy]}>
      {t(`occupancy.${occupancy}`)}
    </Badge>
  );
}

const MODES: ApartmentMode[] = ["comfort", "eco", "empty"];

export function ModeSelector({ aptId, apartment, canWrite }: { aptId: string; apartment: Apartment; canWrite: boolean }) {
  const [requested, setRequested] = useState<ApartmentMode | null>(null);
  useEffect(() => {
    setRequested(null);
  }, [apartment.mode, apartment.updated_at]);

  const pick = async (mode: ApartmentMode) => {
    setRequested(mode);
    const res = await runAction((c) => instanceApi(aptId).setMode(mode, c));
    if (!res) setRequested(null);
  };

  return (
    <div className="space-y-2">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("mode.label")}</div>
      <div role="radiogroup" aria-label={t("mode.label")} className="inline-flex rounded-full border bg-secondary/60 p-1" data-testid="mode-selector">
        {MODES.map((m) => (
          <button
            key={m}
            type="button"
            role="radio"
            aria-checked={apartment.mode === m}
            disabled={!canWrite || requested !== null}
            aria-disabled={!canWrite || requested !== null}
            title={!canWrite ? t("device.readOnlyHint") : undefined}
            onClick={() => apartment.mode !== m && pick(m)}
            data-testid={`mode-selector-${m}`}
            className={cn(
              "flex min-h-[40px] items-center gap-1.5 rounded-full px-4 text-sm font-bold capitalize transition-colors focus-ring disabled:cursor-not-allowed",
              apartment.mode === m ? "bg-card text-primary shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {requested === m && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
            {t(`mode.${m}`)}
          </button>
        ))}
      </div>
    </div>
  );
}

const HOLDS = [
  { minutes: 30, key: "m30" },
  { minutes: 120, key: "h2" },
  { minutes: 360, key: "h6" },
];

export function HoldControl({ aptId, apartment, canWrite }: { aptId: string; apartment: Apartment; canWrite: boolean }) {
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 15000);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    setBusy(false);
  }, [apartment.hold?.until, apartment.updated_at]);

  const hold = async (minutes: number) => {
    setBusy(true);
    const res = await runAction((c) => instanceApi(aptId).setHold({ minutes }, c));
    if (res === undefined) setBusy(false);
  };

  const h = apartment.hold;
  return (
    <div className="space-y-2" data-testid="hold-control">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{t("hold.label")}</div>
      {h ? (
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-primary/30 bg-primary/5 px-3 py-2" data-testid="hold-active">
          <Timer className="h-4 w-4 text-primary" aria-hidden />
          <span className="text-sm font-semibold">
            {t("hold.active", { mode: t(`mode.${h.mode}`), until: fmtTime(h.until, apartment.timezone) })}
          </span>
          <span className="text-xs text-muted-foreground tabular" data-testid="hold-remaining">
            {t("hold.remaining", { time: fmtRemaining(new Date(h.until).getTime() - now) })}
          </span>
          {canWrite && (
            <Button size="sm" variant="ghost" onClick={() => hold(0)} disabled={busy} data-testid="hold-cancel-btn">
              <X /> {t("hold.cancel")}
            </Button>
          )}
        </div>
      ) : (
        <div className="flex gap-2">
          {HOLDS.map((o) => (
            <Button key={o.key} size="sm" variant="outline" disabled={!canWrite || busy} onClick={() => hold(o.minutes)} data-testid={`hold-btn-${o.minutes}`}>
              {t(`hold.${o.key}`)}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}
