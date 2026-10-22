import { useEffect, useMemo, useState } from "react";
import type { ApartmentMode, ScheduleItem, ScheduledAction } from "@/api/types";
import { instanceApi } from "@/api/instance";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, Input, Label, NativeSelect } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { capitalizeFirst } from "@/lib/format";
import { runAction } from "@/lib/actions";
import { useApartmentStore } from "@/store/apartmentStore";

interface Props {
  aptId: string;
  tz: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onDone: () => unknown;
  move?: ScheduleItem;
}

/** Local wall-clock (apartment tz) → ISO UTC. The input value is interpreted in the apartment timezone. */
function localToIso(value: string, tz: string): string | null {
  if (!value) return null;
  const [date, time] = value.split("T");
  const [y, m, d] = date.split("-").map(Number);
  const [hh, mm] = time.split(":").map(Number);
  const guess = Date.UTC(y, m - 1, d, hh, mm);
  const parts = new Intl.DateTimeFormat("en-US", { timeZone: tz, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).formatToParts(new Date(guess));
  const get = (k: string) => Number(parts.find((p) => p.type === k)?.value);
  const asIfUtc = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"));
  return new Date(guess - (asIfUtc - guess)).toISOString();
}

function defaultLocal(): string {
  const d = new Date(Date.now() + 3600_000);
  d.setSeconds(0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type Cmd = "turn_off" | "turn_on" | "setpoint";

export function ScheduleDialog({ aptId, tz, open, onOpenChange, onDone, move }: Props) {
  const devices = useApartmentStore((s) => s.devices);
  const controllable = useMemo(() => devices.filter((d) => d.capabilities.climate || d.capabilities.heating || d.capabilities.switch), [devices]);
  const [runAt, setRunAt] = useState(defaultLocal);
  const [type, setType] = useState<ScheduledAction["type"]>("apartment_mode");
  const [mode, setMode] = useState<ApartmentMode>("comfort");
  const [deviceId, setDeviceId] = useState("");
  const [cmd, setCmd] = useState<Cmd>("turn_off");
  const [setpoint, setSetpoint] = useState("21");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) {
      setRunAt(defaultLocal());
      if (!deviceId && controllable[0]) setDeviceId(controllable[0].device_id);
    }
  }, [open, controllable, deviceId]);

  const device = controllable.find((d) => d.device_id === deviceId);
  const cap = device?.capabilities.climate ? "climate" : device?.capabilities.heating ? "heating" : "switch";
  const cmds: Cmd[] = cap === "switch" ? ["turn_off", "turn_on"] : ["turn_off", "setpoint"];

  const buildAction = (): ScheduledAction => {
    if (type === "apartment_mode") return { type, mode };
    if (cmd === "setpoint") return { type, device_id: deviceId, capability: cap, action: cap === "climate" ? "set_climate" : "set_heating", params: { on: true, setpoint: Number(setpoint) } };
    return { type, device_id: deviceId, capability: cap, action: cmd };
  };

  const save = async () => {
    const iso = localToIso(runAt, tz);
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
                    <NativeSelect id="schedule-cmd" value={cmds.includes(cmd) ? cmd : cmds[0]} onChange={(e) => setCmd(e.target.value as Cmd)} data-testid="schedule-command-select">
                      {cmds.map((c) => <option key={c} value={c}>{t(`schedule.cmd${c === "turn_off" ? "TurnOff" : c === "turn_on" ? "TurnOn" : "Setpoint"}`)}</option>)}
                    </NativeSelect>
                  </div>
                  {cmd === "setpoint" && cmds.includes("setpoint") && (
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
