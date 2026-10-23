import type { ReactNode } from "react";
import type { Apartment, ApartmentMode, Device, Room } from "@/api/types";
import { openWindowRooms } from "@/components/apartment/ApartmentControls";
import { t } from "@/i18n";
import { capitalizeFirst, fmtNumber, fmtShortDateTime, fmtTime } from "@/lib/format";
import { MODE_BG, MODE_FG } from "@/lib/modeColours";
import { cn } from "@/lib/utils";

type Tint = "positive" | "warning" | "neutral" | "data" | ApartmentMode | undefined;
/** Lot 34: each cell takes the colour of what it says, on a full background (D-194), so the band reads at a glance. */
const TINT_BG: Record<string, string> = { positive: "bg-positive-bg", warning: "bg-warning-bg", neutral: "bg-neutral-bg", data: "bg-card", ...MODE_BG };
const TINT_FG: Record<string, string> = { positive: "text-positive-fg", warning: "text-warning-fg", neutral: "text-neutral-fg", data: "text-primary", ...MODE_FG };

function Cell({ label, value, sub, tint, testId }: { label: string; value: ReactNode; sub?: ReactNode; tint?: Tint; testId: string }) {
  return (
    <div className={cn("min-w-0 px-4 py-3", tint ? TINT_BG[tint] : "bg-card")} data-testid={testId} data-tint={tint ?? ""}>
      <div className={cn("text-[13px] font-medium", tint && tint !== "data" ? cn(TINT_FG[tint], "opacity-80") : "text-muted-foreground")}>{label}</div>
      <div className={cn("mt-0.5 text-lg font-semibold tabular [overflow-wrap:anywhere]", tint && TINT_FG[tint])} data-testid={`${testId}-value`}>{value}</div>
      {sub && <div className={cn("text-xs [overflow-wrap:anywhere]", tint && tint !== "data" ? TINT_FG[tint] : "text-muted-foreground")}>{sub}</div>}
    </div>
  );
}

const OCCUPANCY_TINT = { occupied: "positive", reserved: "warning", vacant: "neutral" } as const;

/** The next of check-in and check-out still to come, or null. */
function nextEvent(apartment: Apartment): { kind: "checkin" | "checkout"; at: string } | null {
  const now = Date.now();
  const all = [
    { kind: "checkin" as const, at: apartment.next_checkin },
    { kind: "checkout" as const, at: apartment.next_checkout },
  ].filter((e): e is { kind: "checkin" | "checkout"; at: string } => !!e.at && Date.parse(e.at) >= now);
  all.sort((a, b) => Date.parse(a.at) - Date.parse(b.at));
  return all[0] ?? null;
}

/**
 * «Come sta la casa adesso» (design lot 2): mode, occupancy, next check-in or check-out, windows, today's consumption
 * and devices online, in one band at the top of the Panoramica. Six cells divided by 1 px lines; the ones that need
 * attention (a window open, a device offline) in the warning ink.
 */
export function StatusBand({ apartment, devices, rooms, kwhToday, energyOn, tz }: { apartment: Apartment; devices: Device[]; rooms: Room[]; kwhToday: number | null; energyOn: boolean; tz: string }) {
  const next = nextEvent(apartment);
  const contacts = devices.filter((d) => d.capabilities.contact);
  const open = contacts.filter((d) => d.capabilities.contact?.open === true).length;
  const openRooms = openWindowRooms(devices, rooms);
  const offline = apartment.devices_total - apartment.devices_online;
  const metered = devices.filter((d) => d.capabilities.power_meter);
  const kwh = kwhToday ?? (metered.length ? metered.reduce((s, d) => s + (d.capabilities.power_meter?.kwh_today ?? 0), 0) : null);
  return (
    <section aria-label={t("overview.band.title")} className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border sm:grid-cols-3 2xl:grid-cols-6" data-testid="status-band">
      <Cell
        label={t("mode.label")}
        value={capitalizeFirst(t(`mode.${apartment.mode}`))}
        sub={apartment.hold ? t("overview.band.holdUntil", { until: fmtTime(apartment.hold.until, tz) }) : undefined}
        tint={apartment.mode}
        testId="band-mode"
      />
      <Cell label={t("overview.band.occupancy")} value={t(`occupancy.${apartment.occupancy}`)} tint={OCCUPANCY_TINT[apartment.occupancy]} testId="band-occupancy" />
      <Cell
        label={next ? (next.kind === "checkin" ? t("overview.band.nextCheckin") : t("overview.band.nextCheckout")) : t("overview.band.nextNone")}
        value={next ? fmtShortDateTime(next.at, tz) : "—"}
        testId="band-next"
      />
      <Cell
        label={t("overview.band.windows")}
        value={contacts.length === 0 ? "—" : open === 0 ? t("overview.band.windowsClosed") : open === 1 ? t("overview.band.windowsOneOpen") : t("overview.band.windowsOpen", { count: open })}
        sub={open > 0 ? openRooms.join(", ") : contacts.length === 0 ? t("overview.band.windowsNone") : undefined}
        tint={contacts.length === 0 ? undefined : open > 0 ? "warning" : "positive"}
        testId="band-windows"
      />
      <Cell
        label={t("overview.band.energy")}
        value={energyOn && kwh !== null ? `${fmtNumber(kwh, 1)} kWh` : "—"}
        tint={energyOn && kwh !== null ? "data" : undefined}
        testId="band-energy"
      />
      <Cell
        label={t("overview.band.devices")}
        value={`${apartment.devices_online}/${apartment.devices_total}`}
        sub={offline > 0 ? t("overview.band.offline", { count: offline }) : undefined}
        tint={apartment.devices_total === 0 ? undefined : offline > 0 ? "warning" : "positive"}
        testId="band-devices"
      />
    </section>
  );
}
