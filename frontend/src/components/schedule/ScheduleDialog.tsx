import { useEffect, useMemo, useRef, useState } from "react";
import type { ApartmentMode, ScheduleItem, ScheduledAction } from "@/api/types";
import { instanceApi } from "@/api/instance";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, Input, Label, NativeSelect } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { capitalizeFirst } from "@/lib/format";
import { runAction } from "@/lib/actions";
import { instantToWall, wallToInstant } from "@/lib/zonedTime";
import { useApartmentStore } from "@/store/apartmentStore";

interface Props {
  aptId: string;
  tz: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onDone: () => unknown;
  move?: ScheduleItem;
}

/** D-212: an hour from now, on the apartment's clock (the field is read in the apartment's time zone, not the browser's). */
function defaultLocal(tz: string): string {
  return instantToWall(new Date(Date.now() + 3600_000), tz);
}

/** D-212: on the nights the clocks change, what will really happen with the time chosen; nothing on the other days. */
function DstNote({ value, tz }: { value: string; tz: string }) {
  const resolved = wallToInstant(value, tz);
  if (!resolved || resolved.kind === "exact") return null;
  const [date, time] = value.split("T");
  const day = new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${date}T00:00:00Z`));
  const elided = /^(8|11) /.test(day); // «L'8 marzo», «L'11 marzo», not «Il 8»
  const onDay = elided ? t("schedule.onDayElided", { day }) : t("schedule.onDay", { day });
  const text = resolved.kind === "skipped"
    ? t("schedule.dstSkipped", { onDay, time: time.slice(0, 5), actual: instantToWall(resolved.at, tz).slice(11) })
    : t("schedule.dstRepeated", { onDay, time: time.slice(0, 5) });
  return <p className="text-xs font-medium text-foreground" role="status" data-testid="schedule-dst-note" data-kind={resolved.kind}>{text}</p>;
}

type Cmd = "turn_off" | "turn_on" | "setpoint";

export function ScheduleDialog({ aptId, tz, open, onOpenChange, onDone, move }: Props) {
  const devices = useApartmentStore((s) => s.devices);
  const controllable = useMemo(() => devices.filter((d) => d.capabilities.climate || d.capabilities.heating || d.capabilities.switch), [devices]);
  const [runAt, setRunAt] = useState(() => defaultLocal(tz));
  const [type, setType] = useState<ScheduledAction["type"]>("apartment_mode");
  const [mode, setMode] = useState<ApartmentMode>("comfort");
  const [deviceId, setDeviceId] = useState("");
  const [cmd, setCmd] = useState<Cmd>("turn_off");
  const [setpoint, setSetpoint] = useState("21");
  const [saving, setSaving] = useState(false);

  // The time is set once, when the window opens: the devices update live, and before this each update put back the time
  // proposed over the one being written. «Sposta» starts from the action's own time; a new action from an hour from now.
  const wasOpen = useRef(false);
  useEffect(() => {
    if (open && !wasOpen.current) setRunAt(move ? instantToWall(new Date(move.run_at), tz) : defaultLocal(tz));
    wasOpen.current = open;
  }, [open, move, tz]);

  useEffect(() => {
    if (open && !deviceId && controllable[0]) setDeviceId(controllable[0].device_id);
  }, [open, controllable, deviceId]);

  const device = controllable.find((d) => d.device_id === deviceId);
  const cap = device?.capabilities.climate ? "climate" : device?.capabilities.heating ? "heating" : "switch";
  const cmds: Cmd[] = cap === "switch" ? ["turn_off", "turn_on"] : ["turn_off", "setpoint"];
  // P-83, D21: what the menu shows is what is saved. A command chosen for another device (a socket's «Accendi», a
  // boiler's «Imposta temperatura») that this one does not have falls back to the first, as the menu shows it.
  const shownCmd: Cmd = cmds.includes(cmd) ? cmd : cmds[0];

  const buildAction = (): ScheduledAction => {
    if (type === "apartment_mode") return { type, mode };
    if (shownCmd === "setpoint") return { type, device_id: deviceId, capability: cap, action: cap === "climate" ? "set_climate" : "set_heating", params: { on: true, setpoint: Number(setpoint) } };
    return { type, device_id: deviceId, capability: cap, action: shownCmd };
  };

  const save = async () => {
    const iso = wallToInstant(runAt, tz)?.at.toISOString();
    if (!iso) return;
    setSaving(true);
    const api = instanceApi(aptId);
    const res = move
      ? await runAction((c) => api.moveSchedule(move.schedule_id, { run_at: iso }, c), { success: t("schedule.moved") })
      : await runAction((c) => api.createSchedule({ run_at: iso, action: buildAction() }, c), { success: t("schedule.created") });
    setSaving(false);
    if (res) {
      onOpenChange(false);
      void onDone();
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="schedule-dialog">
        <DialogTitle>{move ? t("schedule.moveTitle") : t("schedule.addTitle")}</DialogTitle>
        <DialogDescription>{t("schedule.addDesc", { tz })}</DialogDescription>
        <div className="mt-4 space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="schedule-run-at">{t("schedule.runAt")}</Label>
            <Input id="schedule-run-at" type="datetime-local" value={runAt} onChange={(e) => setRunAt(e.target.value)} data-testid="schedule-run-at-input" />
            <DstNote value={runAt} tz={tz} />
          </div>
          {!move && (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="schedule-type">{t("schedule.actionType")}</Label>
                <NativeSelect id="schedule-type" value={type} onChange={(e) => setType(e.target.value as ScheduledAction["type"])} data-testid="schedule-type-select">
                  <option value="apartment_mode">{t("schedule.typeMode")}</option>
                  <option value="device_command">{t("schedule.typeDevice")}</option>
                </NativeSelect>
              </div>
              {type === "apartment_mode" ? (
                <div className="space-y-1.5">
                  <Label htmlFor="schedule-mode">{t("mode.label")}</Label>
                  <NativeSelect id="schedule-mode" value={mode} onChange={(e) => setMode(e.target.value as ApartmentMode)} data-testid="schedule-mode-select">
                    {(["comfort", "eco", "empty"] as ApartmentMode[]).map((m) => <option key={m} value={m}>{capitalizeFirst(t(`mode.${m}`))}</option>)}
                  </NativeSelect>
                </div>
              ) : (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="schedule-device">{t("schedule.device")}</Label>
                    <NativeSelect id="schedule-device" value={deviceId} onChange={(e) => setDeviceId(e.target.value)} data-testid="schedule-device-select">
                      {controllable.map((d) => <option key={d.device_id} value={d.device_id}>{d.label}</option>)}
                    </NativeSelect>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="schedule-cmd">{t("schedule.command")}</Label>
                    <NativeSelect id="schedule-cmd" value={shownCmd} onChange={(e) => setCmd(e.target.value as Cmd)} data-testid="schedule-command-select">
                      {cmds.map((c) => <option key={c} value={c}>{t(`schedule.cmd${c === "turn_off" ? "TurnOff" : c === "turn_on" ? "TurnOn" : "Setpoint"}`)}</option>)}
                    </NativeSelect>
                  </div>
                  {shownCmd === "setpoint" && (
                    <div className="space-y-1.5">
                      <Label htmlFor="schedule-setpoint">{t("schedule.setpoint")}</Label>
                      <Input id="schedule-setpoint" type="number" step="0.5" value={setpoint} onChange={(e) => setSetpoint(e.target.value)} data-testid="schedule-setpoint-input" />
                    </div>
                  )}
                </>
              )}
            </>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="ghost" onClick={() => onOpenChange(false)} data-testid="schedule-dialog-cancel">{t("common.cancel")}</Button>
            <Button onClick={save} disabled={saving || !runAt || (type === "device_command" && !deviceId && !move)} data-testid="schedule-dialog-save">{t("common.save")}</Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
