import { useParams } from "react-router-dom";
import { Radio } from "lucide-react";
import type { Device, Room } from "@/api/types";
import { useRole } from "@/auth/AuthProvider";
import { HoldControl, ModeSelector } from "@/components/apartment/ApartmentControls";
import { InstanceStatus } from "@/components/apartment/InstanceStatus";
import { FeatureUnavailable } from "@/components/apartment/Notices";
import { StatusBand } from "@/components/apartment/StatusBand";
import { DeviceCard } from "@/components/devices/DeviceCard";
import { Card, Skeleton } from "@/components/ui/primitives";
import { useFeatures } from "@/hooks/useFeatures";
import { PageHeader } from "@/components/layout/PageHeader";
import { t } from "@/i18n";
import { DEFAULT_TZ } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useApartmentStore } from "@/store/apartmentStore";

function groupByRoom(rooms: Room[], devices: Device[]) {
  const known = new Set(rooms.map((r) => r.room_id));
  const groups = rooms.map((r) => ({ room: r, devices: devices.filter((d) => d.room_id === r.room_id) }));
  const orphans = devices.filter((d) => !known.has(d.room_id));
  if (orphans.length) groups.push({ room: { room_id: "_none", name: t("overview.otherRoom") }, devices: orphans });
  return groups.filter((g) => g.devices.length);
}

function Header({ aptId }: { aptId: string }) {
  const { summary, contractVersion } = useFeatures(aptId);
  const apartment = useApartmentStore((s) => s.apartment);
  const health = useApartmentStore((s) => s.health);
  const connected = useApartmentStore((s) => s.connected);
  return (
    <PageHeader
      title={summary.data?.name ?? apartment?.name ?? ""}
      titleTestId="apartment-title"
      testId="overview-header"
      badges={
        <span data-testid="stream-status" data-connected={connected} className={cn("flex items-center gap-1.5 text-xs font-semibold", connected ? "text-positive" : "text-muted-foreground")}>
          <Radio className="h-3.5 w-3.5" /> {connected ? t("overview.liveOn") : t("overview.liveOff")}
        </span>
      }
    >
      <InstanceStatus health={health ?? summary.data?.health ?? null} contractVersion={contractVersion} />
    </PageHeader>
  );
}

export default function OverviewPage() {
  const { aptId = "" } = useParams();
  const { has, summary } = useFeatures(aptId);
  const { canWrite } = useRole();
  const { apartment, rooms, devices, loaded } = useApartmentStore();
  const tz = apartment?.timezone ?? summary.data?.timezone ?? DEFAULT_TZ;
  const commandsOn = has("commands");

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <Header aptId={aptId} />
      {has("apartment") && apartment && (
        <StatusBand apartment={apartment} devices={devices} rooms={rooms} kwhToday={summary.data?.kwh_today ?? null} energyOn={has("energy")} tz={tz} />
      )}
      {has("apartment") && apartment && (
        <Card className="flex flex-col gap-5 p-5 sm:flex-row sm:items-end sm:justify-between">
          <ModeSelector aptId={aptId} apartment={apartment} canWrite={canWrite} />
          <HoldControl aptId={aptId} apartment={apartment} canWrite={canWrite} />
        </Card>
      )}
      <section className="space-y-6" aria-label={t("overview.devices")}>
        {!has("devices") ? (
          <FeatureUnavailable />
        ) : !loaded ? (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-48 rounded-2xl" />)}</div>
        ) : devices.length === 0 ? (
          <Card className="p-10 text-center text-sm text-muted-foreground" data-testid="devices-empty">{t("overview.noDevices")}</Card>
        ) : (
          groupByRoom(rooms, devices).map(({ room, devices: list }) => (
            <div key={room.room_id} className="space-y-3" data-testid={`room-${room.room_id}`}>
              <h2 className="text-base font-semibold">
                {room.name} <span className="font-normal text-muted-foreground tabular">{list.length}</span>
              </h2>
              {/* cards on the phone and the tablet, one compact list per room on a computer (design lot 2) */}
              <div className="grid gap-4 md:grid-cols-2 lg:block lg:divide-y lg:overflow-hidden lg:rounded-lg lg:border lg:bg-card">
                {list.map((d) => (
                  <DeviceCard key={d.device_id} aptId={aptId} device={d} rooms={rooms} tz={tz} canWrite={canWrite && commandsOn} canRename={canWrite} />
                ))}
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  );
}
