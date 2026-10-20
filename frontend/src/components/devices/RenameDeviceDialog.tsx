import { useEffect, useState } from "react";
import type { Device, Room } from "@/api/types";
import { instanceApi } from "@/api/instance";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, Input, Label, NativeSelect } from "@/components/ui/primitives";
import { runAction } from "@/lib/actions";
import { useApartmentStore } from "@/store/apartmentStore";
import { t } from "@/i18n";

interface Props {
  aptId: string;
  device: Device;
  rooms: Room[];
  open: boolean;
  onOpenChange: (v: boolean) => void;
}

export function RenameDeviceDialog({ aptId, device, rooms, open, onOpenChange }: Props) {
  const [label, setLabel] = useState(device.label);
  const [roomId, setRoomId] = useState(device.room_id);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setLabel(device.label);
      setRoomId(device.room_id);
    }
  }, [open, device.label, device.room_id]);

  const save = async () => {
    const body: { label?: string; room_id?: string } = {};
    if (label.trim() !== device.label) body.label = label.trim();
    if (roomId !== device.room_id) body.room_id = roomId;
    if (!Object.keys(body).length) return onOpenChange(false);
    setSaving(true);
    const updated = await runAction((c) => instanceApi(aptId).updateDevice(device.device_id, body, c), { success: t("device.renamed") });
    setSaving(false);
    if (updated) {
      const store = useApartmentStore.getState();
      store.setSnapshot({ devices: store.devices.map((d) => (d.device_id === updated.device_id ? updated : d)) });
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid={`rename-dialog-${device.device_id}`}>
        <DialogTitle>{t("device.renameTitle")}</DialogTitle>
        <DialogDescription>{t("device.renameDesc")}</DialogDescription>
        <div className="mt-5 space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="device-label-input">{t("device.nameLabel")}</Label>
            <Input id="device-label-input" maxLength={60} value={label} onChange={(e) => setLabel(e.target.value)} data-testid="rename-label-input" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="device-room-select">{t("device.roomLabel")}</Label>
            <NativeSelect id="device-room-select" value={roomId} onChange={(e) => setRoomId(e.target.value)} data-testid="rename-room-select">
              {rooms.map((r) => (
                <option key={r.room_id} value={r.room_id}>
                  {r.name}
                </option>
              ))}
            </NativeSelect>
          </div>
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)} data-testid="rename-cancel-btn">
            {t("common.cancel")}
          </Button>
          <Button onClick={save} disabled={saving || !label.trim()} data-testid="rename-save-btn">
            {t("common.save")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
