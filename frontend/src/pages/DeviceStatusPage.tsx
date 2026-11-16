import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { adviceFor, batteryLow, batteryText, isSensor, sortForDiagnosis, statusOf, statusText, type DeviceStatus, type DiagnosisFacts, type StatusDevice } from "@/lib/deviceStatus";
import { DEFAULT_TZ, fmtShortDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApartmentStore } from "@/store/apartmentStore";

/** The time now, again every minute: «Offline da …» moves on while the page stays open. */
function useMinuteClock() {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const i = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(i);
  }, []);
  return now;
}

const BADGE: Record<DeviceStatus, string> = {
  online: "border-positive-border bg-positive-bg text-positive-fg",
  offline: "border-negative-border bg-negative-bg text-negative-fg",
  never: "border-warning-border bg-warning-bg text-warning-fg",
};

type Row = { device: StatusDevice; room: string; status: DeviceStatus };
type Ctx = { now: number; tz: string; facts: DiagnosisFacts };

/**
 * The columns, in one list: a later step adds «Segnale» (rssi), «Accessi rifiutati» or «Controlli» as one more entry here (with its own
 * width), and the advice reads the new facts from DiagnosisFacts; rows, header and phone layout follow by themselves.
 * `label: null` = no caption (the device's name heads its card on the phone); `phoneHidden` = only in the table.
 */
const COLUMNS: { key: string; header: () => string; label: (() => string) | null; width: string; phoneHidden?: boolean; cell: (r: Row, c: Ctx) => ReactNode }[] = [
  {
    key: "device", header: () => t("deviceStatus.columns.device"), label: null, width: "minmax(0,1.3fr)",
    cell: (r) => (
      <span className="min-w-0">
        <span className="block font-semibold [overflow-wrap:anywhere]">{r.device.label}</span>
        <span className="block truncate text-xs text-muted-foreground md:hidden">{r.room}</span>
      </span>
    ),
  },
  { key: "room", header: () => t("deviceStatus.columns.room"), label: null, width: "minmax(0,1fr)", phoneHidden: true, cell: (r) => <span className="block truncate">{r.room}</span> },
  {
    key: "status", header: () => t("deviceStatus.columns.status"), label: () => t("deviceStatus.columns.status"), width: "minmax(0,1fr)",
    cell: (r, c) => <Badge className={BADGE[r.status]}>{statusText(r.device, c.now)}</Badge>,
  },
  {
    key: "last-seen", header: () => t("deviceStatus.columns.lastSeen"), label: () => t("deviceStatus.columns.lastSeen"), width: "minmax(0,1fr)",
    cell: (r, c) => <span className="tabular">{r.device.last_seen ? fmtShortDateTime(r.device.last_seen, c.tz) : t("deviceStatus.lastSeenNever")}</span>,
  },
  {
    key: "battery", header: () => t("deviceStatus.columns.battery"), label: () => t("deviceStatus.columns.battery"), width: "minmax(0,1.4fr)",
    cell: (r) =>
      batteryLow(r.device) ? (
        // may wrap on a narrow table instead of spilling into «Cosa fare»
        <Badge className={cn(BADGE.never, "max-w-full shrink whitespace-normal rounded-xl")} data-battery="low">{batteryText(r.device)}</Badge>
      ) : (
        <span className={cn("tabular", !isSensor(r.device) && "text-muted-foreground")}>{batteryText(r.device)}</span>
      ),
  },
  {
    key: "advice", header: () => t("deviceStatus.columns.advice"), label: () => t("deviceStatus.columns.advice"), width: "minmax(0,2.2fr)",
    cell: (r, c) => {
      const advice = adviceFor(r.device, c.facts);
      return advice ? <span>{advice}</span> : <span className="text-muted-foreground">{t("deviceStatus.nothingToDo")}</span>;
    },
  },
];

const gridStyle = { "--cols": COLUMNS.map((c) => c.width).join(" ") } as CSSProperties;
const GRID = "md:grid md:items-center md:gap-4 md:[grid-template-columns:var(--cols)]";

export default function DeviceStatusPage() {
  const { rooms, devices, loaded, unreachable, health } = useApartmentStore();
  const tz = useApartmentStore((s) => s.apartment?.timezone) ?? DEFAULT_TZ;
  const now = useMinuteClock();
  const connectorDown = !unreachable && health?.connector.status === "down";
  const ctx: Ctx = { now, tz, facts: { connectorDown: unreachable || connectorDown } };
  const roomName = (d: StatusDevice) => rooms.find((r) => r.room_id === d.room_id)?.name ?? t("overview.otherRoom");
  const rows: Row[] = sortForDiagnosis(devices as StatusDevice[], roomName).map((d) => ({ device: d, room: roomName(d), status: statusOf(d) }));
  const count = (s: DeviceStatus) => rows.filter((r) => r.status === s).length;
  const lowBatteries = rows.filter((r) => batteryLow(r.device)).length;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader title={t("deviceStatus.title")} subtitle={t("deviceStatus.subtitle")} testId="device-status-header" />
      {unreachable && (
        <p role="status" className="rounded-xl border border-negative-border bg-negative-bg px-3 py-2 text-sm font-medium text-negative-fg" data-testid="device-status-unreachable">{t("deviceStatus.unreachable")}</p>
      )}
      {connectorDown && (
        <p role="status" className="rounded-xl border border-negative-border bg-negative-bg px-3 py-2 text-sm font-medium text-negative-fg" data-testid="device-status-connector-down">{t("deviceStatus.connectorDown")}</p>
      )}
      {!loaded ? (
        <Skeleton className="h-64 rounded-2xl" />
      ) : rows.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted-foreground" data-testid="device-status-empty">{t("deviceStatus.empty")}</Card>
      ) : (
        <>
          <p className="text-sm font-semibold" data-testid="device-status-summary">
            {t("deviceStatus.summary", { online: count("online"), offline: count("offline"), never: count("never") })}
            {lowBatteries > 0 && t("deviceStatus.summaryBattery", { count: lowBatteries })}
          </p>
          <Card className="px-4 md:px-5" style={gridStyle} data-testid="device-status-list">
            <div aria-hidden className={cn("hidden border-b py-3 text-xs font-semibold text-muted-foreground", GRID)}>
              {COLUMNS.map((c) => <span key={c.key}>{c.header()}</span>)}
            </div>
            <ul className="divide-y">
              {rows.map((r) => (
                <li key={r.device.device_id} className={cn("space-y-2 py-4 text-sm md:space-y-0 md:py-3", GRID)} data-testid={`device-status-row-${r.device.device_id}`} data-status={r.status}>
                  {COLUMNS.map((c) => (
                    <div key={c.key} className={cn("min-w-0", c.label && "flex flex-wrap items-baseline gap-x-2 md:block", c.phoneHidden && "hidden md:block")} data-testid={`device-status-${r.device.device_id}-${c.key}`}>
                      {c.label && <span className="text-xs font-medium text-muted-foreground md:sr-only">{c.label()}</span>}
                      {c.cell(r, ctx)}
                    </div>
                  ))}
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}
