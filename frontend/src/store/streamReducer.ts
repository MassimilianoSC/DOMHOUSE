import type {
  Apartment,
  CommandReason,
  CommandState,
  Device,
  EventCommandUpdated,
  EventDeviceOnline,
  EventDeviceState,
  Health,
  Room,
  StreamEnvelope,
} from "@/api/types";

export interface TrackedCommand {
  command_id: string;
  device_id: string;
  status: CommandState;
  reason: CommandReason;
  capability?: string;
  correlationId?: string;
}

export interface DeviceError {
  message: string;
  code: string;
  correlationId: string | null;
}

export interface LiveState {
  apartment: Apartment | null;
  rooms: Room[];
  devices: Device[];
  health: Health | null;
  commands: Record<string, TrackedCommand>;
  lastCommandByDevice: Record<string, string>;
  deviceErrors: Record<string, DeviceError>;
  lastEventId: string | null;
  pendingApprovalEvents: number;
}

export const emptyLive = (): LiveState => ({
  apartment: null,
  rooms: [],
  devices: [],
  health: null,
  commands: {},
  lastCommandByDevice: {},
  deviceErrors: {},
  lastEventId: null,
  pendingApprovalEvents: 0,
});

function mapDevice(state: LiveState, deviceId: string, fn: (d: Device) => Device): Device[] {
  return state.devices.map((d) => (d.device_id === deviceId ? fn(d) : d));
}

export function trackCommand(state: LiveState, cmd: TrackedCommand): LiveState {
  const prev = state.commands[cmd.command_id];
  const errors = { ...state.deviceErrors };
  delete errors[cmd.device_id];
  return {
    ...state,
    deviceErrors: errors,
    commands: { ...state.commands, [cmd.command_id]: prev ? { ...cmd, ...prev, capability: cmd.capability ?? prev.capability } : cmd },
    lastCommandByDevice: { ...state.lastCommandByDevice, [cmd.device_id]: cmd.command_id },
  };
}

/** Pure reducer applying one contract stream envelope to the live apartment state. Unknown events are ignored. */
export function applyEvent(state: LiveState, env: StreamEnvelope): LiveState {
  const next = { ...state, lastEventId: env.id ?? state.lastEventId };
  switch (env.event) {
    case "device.state": {
      const data = env.data as unknown as EventDeviceState;
      return {
        ...next,
        devices: mapDevice(state, data.device_id, (d) => ({
          ...d,
          capabilities: { ...d.capabilities, [data.capability]: data.state },
        })),
      };
    }
    case "device.online": {
      const data = env.data as unknown as EventDeviceOnline;
      return {
        ...next,
        devices: mapDevice(state, data.device_id, (d) => ({ ...d, online: data.online, last_seen: data.last_seen })),
      };
    }
    case "command.updated": {
      const data = env.data as unknown as EventCommandUpdated;
      const prev = state.commands[data.command_id];
      const current = state.lastCommandByDevice[data.device_id];
      return {
        ...next,
        commands: {
          ...state.commands,
          [data.command_id]: { ...prev, command_id: data.command_id, device_id: data.device_id, status: data.status, reason: data.reason },
        },
        lastCommandByDevice: { ...state.lastCommandByDevice, [data.device_id]: prev && current ? current : data.command_id },
      };
    }
    case "apartment.changed":
      return { ...next, apartment: env.data as unknown as Apartment };
    case "instance.health":
      return { ...next, health: env.data as unknown as Health };
    case "approval.pending":
      return { ...next, pendingApprovalEvents: state.pendingApprovalEvents + 1 };
    default:
      return next;
  }
}

export const IN_PROGRESS: CommandState[] = ["pending", "sent", "verifying"];
export const isInProgress = (s?: CommandState) => !!s && IN_PROGRESS.includes(s);
