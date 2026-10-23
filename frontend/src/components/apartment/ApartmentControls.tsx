import { useEffect, useState } from "react";
import { Loader2, Timer, X } from "lucide-react";
import type { Apartment, ApartmentMode, Device, Occupancy, Room } from "@/api/types";
import { instanceApi } from "@/api/instance";
import { Button } from "@/components/ui/button";
import { Badge, Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";
import { capitalizeFirst, fmtRemaining, fmtTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApartmentStore } from "@/store/apartmentStore";

const OCCUPANCY_STYLE: Record<Occupancy, string> = {
  vacant: "border-neutral-border bg-neutral-bg text-neutral-fg",
  occupied: "border-positive-border bg-positive-bg text-positive-fg",
  reserved: "border-warning-border bg-warning-bg text-warning-fg",
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
              "flex min-h-[40px] items-center gap-1.5 rounded-full px-4 text-sm font-bold transition-colors focus-ring disabled:cursor-not-allowed",
              apartment.mode === m ? "bg-card text-primary shadow-sm" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {requested === m && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
            {capitalizeFirst(t(`mode.${m}`))}
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

/** Rooms with a window open (contact open), each once, in the order of the devices; a device without room by its name. */
export function openWindowRooms(devices: Device[], rooms: Room[]): string[] {
  const names = devices
    .filter((d) => d.capabilities.contact?.open === true)
    .map((d) => rooms.find((r) => r.room_id === d.room_id)?.name ?? d.label);
  return [...new Set(names)];
}

const listIt = (items: string[]) => new Intl.ListFormat("it", { style: "long", type: "conjunction" }).format(items);

export function HoldControl({ aptId, apartment, canWrite }: { aptId: string; apartment: Apartment; canWrite: boolean }) {
  const [now, setNow] = useState(Date.now());
  const [busy, setBusy] = useState(false);
  // D-127: during a hold the rules (window open → climate off) are suspended. With a window open the person is told
  // first, with the rooms, and may confirm anyway; without one the hold starts at once, as before.
  const devices = useApartmentStore((s) => s.devices);
  const rooms = useApartmentStore((s) => s.rooms);
  const [asking, setAsking] = useState<number | null>(null);
  const openRooms = openWindowRooms(devices, rooms);
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

  const choose = (minutes: number) => {
    if (openRooms.length) setAsking(minutes);
    else void hold(minutes);
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
            <Button key={o.key} size="sm" variant="outline" disabled={!canWrite || busy} onClick={() => choose(o.minutes)} data-testid={`hold-btn-${o.minutes}`}>
              {t(`hold.${o.key}`)}
            </Button>
          ))}
        </div>
      )}
      {asking !== null && (
        <Dialog open onOpenChange={(open) => !open && setAsking(null)}>
          <DialogContent data-testid="hold-window-warning">
            <DialogTitle>{t("hold.windowTitle")}</DialogTitle>
            <DialogDescription>
              {openRooms.length > 1 ? t("hold.windowsOpen", { rooms: listIt(openRooms) }) : t("hold.windowOpen", { rooms: openRooms[0] ?? "" })}
            </DialogDescription>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setAsking(null)} data-testid="hold-window-cancel">{t("common.cancel")}</Button>
              <Button
                onClick={() => {
                  const minutes = asking;
                  setAsking(null);
                  void hold(minutes);
                }}
                data-testid="hold-window-confirm"
              >
                {t("hold.windowConfirm")}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
