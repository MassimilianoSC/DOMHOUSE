import { useState } from "react";
import { MoreVertical, Pencil, WifiOff } from "lucide-react";
import type { Device, Room } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Badge, Card, DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, Tip } from "@/components/ui/primitives";
import { useDeviceCommand } from "@/hooks/useDeviceCommand";
import { t } from "@/i18n";
import { fmtRelative } from "@/lib/format";
import { cn } from "@/lib/utils";
import { CommandChip } from "./CommandChip";
import { RenameDeviceDialog } from "./RenameDeviceDialog";
import { CAPABILITY_RENDERERS, splitCapabilities } from "./capabilities/registry";

interface Props {
  aptId: string;
  device: Device;
  rooms: Room[];
  tz: string;
  canWrite: boolean;
  canRename: boolean;
}

export function DeviceCard({ aptId, device, rooms, tz, canWrite, canRename }: Props) {
  const { send, status, error, busy } = useDeviceCommand(aptId, device.device_id);
  const [renameOpen, setRenameOpen] = useState(false);
  const { controls, readings, unknown } = splitCapabilities(device);
  const disabled = !device.online || !canWrite || busy;
  const disabledHint = !device.online ? t("device.offlineTooltip") : !canWrite ? t("device.readOnlyHint") : null;

  return (
    <Card
      data-testid={`device-card-${device.device_id}`}
      className={cn("flex flex-col gap-3 p-4 transition-shadow hover:shadow-md animate-fade-up", !device.online && "opacity-70")}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-base font-bold" data-testid={`device-label-${device.device_id}`}>
            {device.label}
          </h3>
          <p className="text-xs text-muted-foreground">{t("device.lastSeen", { when: fmtRelative(device.last_seen) })}</p>
        </div>
        <div className="flex items-center gap-1">
          {!device.online && (
            <Tip content={t("device.offlineTooltip")}>
              <Badge tabIndex={0} data-testid={`device-offline-${device.device_id}`} className="border-neutral-border bg-neutral-bg text-neutral-fg">
                <WifiOff className="h-3 w-3" aria-hidden /> {t("device.offline")}
              </Badge>
            </Tip>
          )}
          {canRename && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="iconSm" aria-label={t("device.menu", { name: device.label })} data-testid={`device-menu-${device.device_id}`}>
                  <MoreVertical />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setRenameOpen(true)} data-testid={`device-rename-${device.device_id}`}>
                  <Pencil /> {t("device.rename")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      {controls.map(([cap, state]) => {
        const Comp = CAPABILITY_RENDERERS[cap].component;
        const body = <div><Comp device={device} state={state as never} tz={tz} disabled={disabled} send={send} /></div>;
        return <div key={cap}>{disabledHint && !busy ? <Tip content={disabledHint}>{body}</Tip> : body}</div>;
      })}

      {readings.length > 0 && (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {readings.map(([cap, state]) => {
            const Comp = CAPABILITY_RENDERERS[cap].component;
            return <Comp key={cap} device={device} state={state as never} tz={tz} disabled send={send} />;
          })}
        </div>
      )}

      {(unknown.length > 0 || status || error) && (
        <div className="flex flex-wrap items-center gap-1.5">
          <CommandChip command={status} error={error} testId={`command-status-${device.device_id}`} />
          {unknown.map((cap) => (
            <Badge key={cap} title={t("device.unsupportedTitle", { name: cap })} data-testid={`device-unsupported-${device.device_id}-${cap}`} className="border-dashed text-muted-foreground">
              {cap}: {t("device.unsupported")}
            </Badge>
          ))}
        </div>
      )}

      {canRename && <RenameDeviceDialog aptId={aptId} device={device} rooms={rooms} open={renameOpen} onOpenChange={setRenameOpen} />}
    </Card>
  );
}
