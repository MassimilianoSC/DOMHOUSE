import type { Device } from "@/api/types";
import { t } from "@/i18n";

/**
 * «Stato dei dispositivi» (activation by the client, §5, first step): what the site can say about each device of the
 * catalog with the data it already gets from the engine (online, last_seen), and what to check. Later steps add
 * their own facts (refused logins from the broker, model, firmware, bridge) through `DiagnosisFacts`, so the rows
 * and the advice grow without being redone.
 */
export type DeviceStatus = "online" | "offline" | "never";

/** Facts beyond the device itself. Today only the connector; refused logins, model, firmware and bridge come later. */
export interface DiagnosisFacts {
  /** The engine's link to the devices is down (or the engine does not answer): every device looks offline. */
  connectorDown: boolean;
}

/** Never seen = offline with no last_seen: the engine sends it empty until the connector has heard from the device
 *  once, and keeps the saved one across restarts (D12, engine/core.py _load). */
export function statusOf(d: Pick<Device, "online" | "last_seen">): DeviceStatus {
  if (d.online) return "online";
  return d.last_seen ? "offline" : "never";
}

/** A battery sensor behind a bridge: no relay, meter, climate or boiler, only readings. */
export function isSensor(d: Pick<Device, "capabilities">): boolean {
  const c = d.capabilities ?? {};
  return !c.switch && !c.power_meter && !c.climate && !c.heating;
}

/** «meno di un minuto», «1 minuto», «5 minuti», «1 ora», «3 ore», «1 giorno», «4 giorni». */
export function fmtElapsed(ms: number): string {
  const min = Math.floor(Math.max(0, ms) / 60_000);
  if (min < 1) return t("deviceStatus.elapsed.lessThanMinute");
  if (min < 60) return min === 1 ? t("deviceStatus.elapsed.minute") : t("deviceStatus.elapsed.minutes", { count: min });
  const h = Math.floor(min / 60);
  if (h < 24) return h === 1 ? t("deviceStatus.elapsed.hour") : t("deviceStatus.elapsed.hours", { count: h });
  const days = Math.floor(h / 24);
  return days === 1 ? t("deviceStatus.elapsed.day") : t("deviceStatus.elapsed.days", { count: days });
}

/** «In linea», «Offline da 2 ore», «Mai collegato». */
export function statusText(d: Pick<Device, "online" | "last_seen">, now: number): string {
  const s = statusOf(d);
  if (s === "online") return t("deviceStatus.status.online");
  if (s === "never") return t("deviceStatus.status.never");
  return t("deviceStatus.status.offline", { for: fmtElapsed(now - new Date(d.last_seen!).getTime()) });
}

/** What to check, in plain words; null when there is nothing to do. */
export function adviceFor(d: Pick<Device, "online" | "last_seen" | "capabilities">, facts: DiagnosisFacts): string | null {
  const s = statusOf(d);
  if (s === "online") return null;
  if (facts.connectorDown) return t("deviceStatus.advice.connectorDown");
  const sensor = isSensor(d);
  if (s === "never") return sensor ? t("deviceStatus.advice.neverSensor") : t("deviceStatus.advice.neverDevice");
  return sensor ? t("deviceStatus.advice.offlineSensor") : t("deviceStatus.advice.offlineDevice");
}

const ORDER: Record<DeviceStatus, number> = { never: 0, offline: 1, online: 2 };

/** Problems first (never connected, then offline), then by room and name: the list reads as a to-do. */
export function sortForDiagnosis<D extends Pick<Device, "online" | "last_seen" | "label">>(devices: D[], roomOf: (d: D) => string): D[] {
  return [...devices].sort((a, b) =>
    ORDER[statusOf(a)] - ORDER[statusOf(b)] || roomOf(a).localeCompare(roomOf(b), "it") || a.label.localeCompare(b.label, "it"));
}
