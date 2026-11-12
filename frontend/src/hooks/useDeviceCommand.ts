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
  const sending = useApartmentStore((s) => Boolean(s.sending[deviceId]));
  const busy = sending || isInProgress(status?.status);

  const send = useCallback(
    async (cmd: Command) => {
      // P-83, D72: a second tap before the server answers would start from the same value (21 → 21,5 and 20,5): the
      // store is read now, not at the last render, so even two taps in the same frame send one command.
      const store = useApartmentStore.getState();
      if (store.sending[deviceId]) return;
      store.setSending(deviceId, true);
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
      } finally {
        useApartmentStore.getState().setSending(deviceId, false);
      }
    },
    [aptId, deviceId],
  );

  return { send, status, error, busy };
}
