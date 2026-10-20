import type { ComponentType } from "react";
import type { Device } from "@/api/types";
import { ClimateControl, HeatingControl, SwitchControl } from "./Controls";
import { ContactView, HumidityView, MotionView, PowerMeterView, TemperatureView } from "./Readings";
import type { CapProps } from "./types";

type Renderer = { component: ComponentType<CapProps<never>>; kind: "control" | "reading" };

/** One renderer per contract capability; anything else is reported as "non supportata". */
export const CAPABILITY_RENDERERS: Record<string, Renderer> = {
  climate: { component: ClimateControl as ComponentType<CapProps<never>>, kind: "control" },
  heating: { component: HeatingControl as ComponentType<CapProps<never>>, kind: "control" },
  switch: { component: SwitchControl as ComponentType<CapProps<never>>, kind: "control" },
  power_meter: { component: PowerMeterView as ComponentType<CapProps<never>>, kind: "reading" },
  temperature: { component: TemperatureView as ComponentType<CapProps<never>>, kind: "reading" },
  humidity: { component: HumidityView as ComponentType<CapProps<never>>, kind: "reading" },
  contact: { component: ContactView as ComponentType<CapProps<never>>, kind: "reading" },
  motion: { component: MotionView as ComponentType<CapProps<never>>, kind: "reading" },
};

export function splitCapabilities(device: Device) {
  const entries = Object.entries(device.capabilities ?? {}).filter(([, v]) => v !== undefined && v !== null);
  return {
    controls: entries.filter(([k]) => CAPABILITY_RENDERERS[k]?.kind === "control"),
    readings: entries.filter(([k]) => CAPABILITY_RENDERERS[k]?.kind === "reading"),
    unknown: entries.filter(([k]) => !CAPABILITY_RENDERERS[k]).map(([k]) => k),
  };
}
