import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, DoorOpen, Footprints, RotateCcw, ShieldQuestion, WifiOff } from "lucide-react";
import { adminApi, simulatorApi, type SimBookingInput } from "@/api/admin";
import { useAuth } from "@/auth/AuthProvider";
import { DemoBadge, isBuiltinMock } from "@/components/admin/apartmentForm";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, Dialog, DialogContent, DialogDescription, DialogTitle, Input, Label, NativeSelect, Switch } from "@/components/ui/primitives";
import { useFeatures } from "@/hooks/useFeatures";
import { resync } from "@/hooks/useApartmentStream";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";
import { DEFAULT_TZ, fmtDateTime } from "@/lib/format";
import { useApartmentStore } from "@/store/apartmentStore";

const pad = (n: number) => String(n).padStart(2, "0");
const toLocal = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
/** A new event of the simulated booking: kept until a field of the form changes (see sendBooking). */
const newEventId = () => `sim-${crypto.randomUUID().slice(0, 8)}`;
const plusDays = (n: number, h: number) => {
  const d = new Date();
  d.setDate(d.getDate() + n);
  d.setHours(h, 0, 0, 0);
  return d;
};

function Section({ icon, title, hint, children, testId }: { icon: React.ReactNode; title: string; hint: string; children: React.ReactNode; testId: string }) {
  return (
    <Card className="space-y-4 p-5" data-testid={testId}>
      <div className="flex items-start gap-3">
        <span className="rounded-xl bg-accent/15 p-2 text-accent">{icon}</span>
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          <p className="text-sm text-muted-foreground">{hint}</p>
        </div>
      </div>
      {children}
    </Card>
  );
}

/**
 * Back to the initial state (D-97): only with the built-in simulated engine (the contract has no reset for a real one).
 * After it, everything of this apartment is read again, as after a reconnection; the server also closes the other
 * devices' streams, which reconnect and resync on their own.
 */
function ResetSection({ aptId, name }: { aptId: string; name: string }) {
  const qc = useQueryClient();
  const admin = useQuery({ queryKey: ["admin", "apartments"], queryFn: adminApi.apartments });
  const url = admin.data?.find((a) => a.apartment_id === aptId)?.instance_url ?? "";
  const available = isBuiltinMock(url);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const reset = async () => {
    setBusy(true);
    const ok = await runAction(async (c) => {
      await simulatorApi(aptId).reset(c);
      return true;
    }, { success: t("simulator.resetDone") });
    setBusy(false);
    setConfirming(false);
    if (!ok) return;
    await qc.invalidateQueries({ predicate: (q) => q.queryKey.includes(aptId) });
    await resync(aptId);
  };
  return (
    <Section icon={<RotateCcw className="h-5 w-5" />} title={t("simulator.reset")} hint={t("simulator.resetHint")} testId="simulator-reset">
      <Button variant="destructive" disabled={!available || busy} onClick={() => setConfirming(true)} data-testid="sim-reset-btn">
        <RotateCcw /> {t("simulator.resetBtn")}
      </Button>
      {admin.data && !available && <p className="text-xs text-muted-foreground" data-testid="sim-reset-unavailable">{t("simulator.resetUnavailable")}</p>}
      {confirming && (
        <Dialog open onOpenChange={(open) => !open && setConfirming(false)}>
          <DialogContent data-testid="sim-reset-dialog">
            <DialogTitle>{t("simulator.resetTitle", { name })}</DialogTitle>
            <DialogDescription>{t("simulator.resetText")}</DialogDescription>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setConfirming(false)} data-testid="sim-reset-cancel">{t("common.cancel")}</Button>
              <Button variant="destructiveSolid" onClick={() => void reset()} disabled={busy} data-testid="sim-reset-confirm">{t("simulator.resetConfirm")}</Button>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </Section>
  );
}

export default function SimulatorPage() {
  const { aptId = "" } = useParams();
  const { me } = useAuth();
  const qc = useQueryClient();
  const devices = useApartmentStore((s) => s.devices);
  const api = useMemo(() => simulatorApi(aptId), [aptId]);
  const { summary } = useFeatures(aptId);
  const windows = devices.filter((d) => d.capabilities.contact);
  const motionSensors = devices.filter((d) => d.capabilities.motion);
  const tz = useApartmentStore((s) => s.apartment?.timezone) ?? DEFAULT_TZ;
  const [busy, setBusy] = useState<string | null>(null);
  const [booking, setBooking] = useState<{ type: SimBookingInput["type"]; booking_id: string; checkin: string; checkout: string; guests: string }>({
    type: "booking_created",
    booking_id: `bk-sim-${Date.now().toString(36).slice(-4)}`,
    checkin: toLocal(plusDays(1, 15)),
    checkout: toLocal(plusDays(3, 10)),
    guests: "2",
  });
  const [lastBooking, setLastBooking] = useState<{ schedule_ids: string[]; duplicate: boolean } | null>(null);
  // The same event sent again keeps its event_id, as Italianway does when it retries: the engine answers «duplicate»
  // and nothing is applied twice («Evento già elaborato»). Any change to the form makes it a new event.
  const [eventId, setEventId] = useState(newEventId);
  const change = (patch: Partial<typeof booking>) => {
    setBooking((b) => ({ ...b, ...patch }));
    setEventId(newEventId());
  };

  // Admins only, on a simulated apartment, in any environment (D-97); SimulatorOnly in App guards the address too.
  if (me?.role !== "admin" || summary.data?.simulated !== true) return null;

  const act = async (key: string, fn: (c: string) => Promise<unknown>, success: string) => {
    setBusy(key);
    await runAction(fn, { success });
    setBusy(null);
  };

  const sendBooking = async () => {
    const body: SimBookingInput = {
      event_id: eventId,
      type: booking.type,
      booking_id: booking.booking_id.trim(),
      checkin_at: new Date(booking.checkin).toISOString(),
      checkout_at: new Date(booking.checkout).toISOString(),
      guests: booking.guests === "" ? null : Number(booking.guests),
      ts: new Date().toISOString(),
    };
    setBusy("booking");
    const res = await runAction((c) => api.booking(body, c), { success: t("simulator.bookingSent") });
    setBusy(null);
    if (res) {
      setLastBooking(res);
      void qc.invalidateQueries({ queryKey: ["schedule", aptId] });
    }
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader title={t("simulator.title")} subtitle={t("simulator.subtitle")} testId="simulator-header" actions={<DemoBadge testId="simulator-demo-badge" />} />
      <div className="grid gap-4 md:grid-cols-2">
        <Section icon={<DoorOpen className="h-5 w-5" />} title={t("simulator.windows")} hint={t("simulator.windowsHint")} testId="simulator-windows">
          {windows.length === 0 && <p className="text-sm text-muted-foreground">{t("simulator.noWindows")}</p>}
          {windows.map((d) => (
            <div key={d.device_id} className="flex items-center justify-between gap-3 rounded-xl bg-secondary/50 px-3 py-2">
              <span className="text-sm font-semibold">{d.label} <span className="text-xs text-muted-foreground">· {d.capabilities.contact?.open ? t("simulator.open") : t("simulator.closed")}</span></span>
              <Switch
                checked={Boolean(d.capabilities.contact?.open)}
                disabled={busy !== null}
                aria-label={d.label}
                onCheckedChange={(open) => act(d.device_id, (c) => api.state({ device_id: d.device_id, capability: "contact", state: { open } }, c), open ? t("simulator.windowOpened") : t("simulator.windowClosed"))}
                data-testid={`sim-window-${d.device_id}`}
              />
            </div>
          ))}
        </Section>
        {/* D-140: a movement is an instant, so one button per sensor; the engine records its time (motion.last_seen). */}
        <Section icon={<Footprints className="h-5 w-5" />} title={t("simulator.motion")} hint={t("simulator.motionHint")} testId="simulator-motion">
          {motionSensors.length === 0 && <p className="text-sm text-muted-foreground">{t("simulator.noMotion")}</p>}
          {motionSensors.map((d) => {
            const last = d.capabilities.motion?.last_seen;
            return (
              <div key={d.device_id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-secondary/50 px-3 py-2">
                <span className="text-sm font-semibold">
                  {d.label} <span className="text-xs text-muted-foreground" data-testid={`sim-motion-last-${d.device_id}`}>· {last ? t("simulator.lastMotion", { when: fmtDateTime(last, tz) }) : t("simulator.noMotionYet")}</span>
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={busy !== null}
                  aria-label={`${t("simulator.simulateMotion")}: ${d.label}`}
                  onClick={() => act(`motion-${d.device_id}`, (c) => api.state({ device_id: d.device_id, capability: "motion", state: { detected: true } }, c), t("simulator.motionSimulated", { name: d.label }))}
                  data-testid={`sim-motion-${d.device_id}`}
                >
                  <Footprints /> {t("simulator.simulateMotion")}
                </Button>
              </div>
            );
          })}
        </Section>
        <Section icon={<WifiOff className="h-5 w-5" />} title={t("simulator.online")} hint={t("simulator.onlineHint")} testId="simulator-online">
          {devices.map((d) => (
            <div key={d.device_id} className="flex items-center justify-between gap-3 rounded-xl bg-secondary/50 px-3 py-2">
              <span className="text-sm font-semibold">{d.label} <span className={`text-xs ${d.online ? "text-positive-fg" : "text-destructive"}`}>· {d.online ? t("simulator.stateOnline") : t("simulator.stateOffline")}</span></span>
              <Switch
                checked={d.online}
                disabled={busy !== null}
                aria-label={d.label}
                onCheckedChange={(online) => act(`on-${d.device_id}`, (c) => api.state({ device_id: d.device_id, online }, c), online ? t("simulator.deviceOnline") : t("simulator.deviceOffline"))}
                data-testid={`sim-online-${d.device_id}`}
              />
            </div>
          ))}
        </Section>
        <Section icon={<ShieldQuestion className="h-5 w-5" />} title={t("simulator.approval")} hint={t("simulator.approvalHint")} testId="simulator-approval">
          <Button onClick={() => act("approval", (c) => api.state({ trigger: "approval" }, c), t("simulator.approvalTriggered"))} disabled={busy !== null} data-testid="sim-trigger-approval-btn">
            <ShieldQuestion /> {t("simulator.triggerApproval")}
          </Button>
        </Section>
        <Section icon={<CalendarPlus className="h-5 w-5" />} title={t("simulator.booking")} hint={t("simulator.bookingHint")} testId="simulator-booking">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="sim-type">{t("simulator.eventType")}</Label>
              <NativeSelect id="sim-type" value={booking.type} onChange={(e) => change({ type: e.target.value as SimBookingInput["type"] })} data-testid="sim-booking-type">
                {(["booking_created", "booking_changed", "booking_cancelled", "checkin", "checkout"] as const).map((v) => <option key={v} value={v}>{t(`simulator.types.${v}`)}</option>)}
              </NativeSelect>
            </div>
            <div className="space-y-1">
              <Label htmlFor="sim-bid">{t("simulator.bookingId")}</Label>
              <Input id="sim-bid" value={booking.booking_id} onChange={(e) => change({ booking_id: e.target.value })} data-testid="sim-booking-id" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sim-ci">{t("simulator.checkin")}</Label>
              <Input id="sim-ci" type="datetime-local" value={booking.checkin} onChange={(e) => change({ checkin: e.target.value })} data-testid="sim-booking-checkin" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sim-co">{t("simulator.checkout")}</Label>
              <Input id="sim-co" type="datetime-local" value={booking.checkout} onChange={(e) => change({ checkout: e.target.value })} data-testid="sim-booking-checkout" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sim-guests">{t("simulator.guests")}</Label>
              <Input id="sim-guests" type="number" min={0} value={booking.guests} onChange={(e) => change({ guests: e.target.value })} data-testid="sim-booking-guests" />
            </div>
          </div>
          <Button onClick={sendBooking} disabled={busy !== null || !booking.booking_id.trim() || !booking.checkin || !booking.checkout} data-testid="sim-booking-send-btn">
            <CalendarPlus /> {t("simulator.sendBooking")}
          </Button>
          {lastBooking && (
            <p className="text-xs text-muted-foreground" data-testid="sim-booking-result">
              {lastBooking.duplicate ? t("simulator.duplicate") : t("simulator.scheduled", { count: lastBooking.schedule_ids.length })}
              {lastBooking.schedule_ids.length > 0 && <span className="ml-1 tabular">{lastBooking.schedule_ids.join(", ")}</span>}
            </p>
          )}
        </Section>
      </div>
      <ResetSection aptId={aptId} name={summary.data?.name ?? aptId} />
    </div>
  );
}
