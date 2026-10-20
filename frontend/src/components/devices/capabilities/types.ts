import type { Command, Device, Schemas } from "@/api/types";

export interface CapProps<S> {
  device: Device;
  state: S;
  tz: string;
  disabled: boolean;
  send: (cmd: Command) => void;
}

export type ClimateState = Schemas["CapClimate"];
export type HeatingState = Schemas["CapHeating"];
export type SwitchState = Schemas["CapSwitch"];
export type PowerMeterState = Schemas["CapPowerMeter"];
export type TemperatureState = Schemas["CapTemperature"];
export type HumidityState = Schemas["CapHumidity"];
export type ContactState = Schemas["CapContact"];
export type MotionState = Schemas["CapMotion"];

export const tid = (device: Device, part: string) => `${device.device_id}-${part}`;
