import type { ReactNode } from "react";
import type { Apartment, Device, Room } from "@/api/types";
import { openWindowRooms } from "@/components/apartment/ApartmentControls";
import { t } from "@/i18n";
import { capitalizeFirst, fmtNumber, fmtShortDateTime, fmtTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function Cell({ label, value, sub, warn, testId }: { label: string; value: ReactNode; sub?: ReactNode; warn?: boolean; testId: string }) {
  return (
    <div className="min-w-0 bg-card px-4 py-3" data-testid={testId}>
      <div className="text-[13px] font-medium text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 text-lg font-semibold tabular [overflow-wrap:anywhere]", warn && "text-warning-fg")} data-testid={`${testId}-value`}>{value}</div>
      {sub && <div className="text-xs text-muted-foreground [overflow-wrap:anywhere]">{sub}</div>}
    </div>
  );
}

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
        testId="band-mode"
      />
      <Cell label={t("overview.band.occupancy")} value={t(`occupancy.${apartment.occupancy}`)} testId="band-occupancy" />
      <Cell
        label={next ? (next.kind === "checkin" ? t("overview.band.nextCheckin") : t("overview.band.nextCheckout")) : t("overview.band.nextNone")}
        value={next ? fmtShortDateTime(next.at, tz) : "—"}
        testId="band-next"
      />
      <Cell
        label={t("overview.band.windows")}
        value={contacts.length === 0 ? "—" : open === 0 ? t("overview.band.windowsClosed") : open === 1 ? t("overview.band.windowsOneOpen") : t("overview.band.windowsOpen", { count: open })}
        sub={open > 0 ? openRooms.join(", ") : contacts.length === 0 ? t("overview.band.windowsNone") : undefined}
        warn={open > 0}
        testId="band-windows"
      />
      <Cell
        label={t("overview.band.energy")}
        value={energyOn && kwh !== null ? `${fmtNumber(kwh, 1)} kWh` : "—"}
        testId="band-energy"
      />
      <Cell
        label={t("overview.band.devices")}
        value={`${apartment.devices_online}/${apartment.devices_total}`}
        sub={offline > 0 ? t("overview.band.offline", { count: offline }) : undefined}
        warn={offline > 0}
        testId="band-devices"
      />
    </section>
  );
}
