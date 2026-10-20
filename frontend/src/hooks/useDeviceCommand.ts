import { useCallback } from "react";
import { ApiError } from "@/api/bff";
import { instanceApi } from "@/api/instance";
import type { Command } from "@/api/types";
import { useApartmentStore } from "@/store/apartmentStore";
import { isInProgress } from "@/store/streamReducer";
import { showError } from "@/lib/actions";
import { newCorrelationId } from "@/lib/utils";

/** Sends a device command and tracks it; the UI changes only via device.state events. */
export function useDeviceCommand(aptId: string, deviceId: string) {
  const status = useApartmentStore((s) => {
    const id = s.lastCommandByDevice[deviceId];
    return id ? s.commands[id] : undefined;
  });
  const error = useApartmentStore((s) => s.deviceErrors[deviceId]);
  const busy = isInProgress(status?.status);

  const send = useCallback(
    async (cmd: Command) => {
      const correlationId = newCorrelationId();
      try {
        const res = await instanceApi(aptId).sendCommand(deviceId, cmd, correlationId);
        useApartmentStore.getState().track({
          command_id: res.command_id,
          device_id: deviceId,
          status: res.status,
          reason: res.reason,
          capability: res.capability,
          correlationId: res.correlation_id,
        });
      } catch (err) {
        if (err instanceof ApiError) {
          useApartmentStore.getState().setDeviceError(deviceId, { message: err.message, code: err.code, correlationId });
        }
        showError(err, correlationId);
      }
    },
    [aptId, deviceId],
  );

  return { send, status, error, busy };
}
