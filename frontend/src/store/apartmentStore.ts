import { create } from "zustand";
import type { Apartment, Device, Health, Room, StreamEnvelope } from "@/api/types";
import { applyEvent, emptyLive, trackCommand, type DeviceError, type LiveState, type TrackedCommand } from "./streamReducer";

interface ApartmentStore extends LiveState {
  apartmentId: string | null;
  connected: boolean;
  loaded: boolean;
  reset: (apartmentId: string) => void;
  /** apartmentId: the snapshot is for that apartment only; one arriving after a reset (another apartment, or the tab
   *  emptied) is dropped (D-89). Without it (a local change) it always applies. */
  setSnapshot: (snap: { apartment?: Apartment | null; rooms?: Room[]; devices?: Device[]; health?: Health | null }, apartmentId?: string) => void;
  apply: (env: StreamEnvelope) => void;
  track: (cmd: TrackedCommand) => void;
  setDeviceError: (deviceId: string, err: DeviceError) => void;
  setConnected: (v: boolean) => void;
}

export const useApartmentStore = create<ApartmentStore>((set) => ({
  ...emptyLive(),
  apartmentId: null,
  connected: false,
  loaded: false,
  reset: (apartmentId) => set({ ...emptyLive(), apartmentId, connected: false, loaded: false }),
  setSnapshot: (snap, apartmentId) =>
    set((s) => (apartmentId !== undefined && s.apartmentId !== apartmentId ? s : {
      apartment: snap.apartment !== undefined ? snap.apartment : s.apartment,
      rooms: snap.rooms ?? s.rooms,
      devices: snap.devices ?? s.devices,
      health: snap.health !== undefined ? snap.health : s.health,
      loaded: true,
    })),
  apply: (env) => set((s) => applyEvent(s, env)),
  track: (cmd) => set((s) => trackCommand(s, cmd)),
  setDeviceError: (deviceId, err) => set((s) => ({ deviceErrors: { ...s.deviceErrors, [deviceId]: err } })),
  setConnected: (connected) => set({ connected }),
}));
