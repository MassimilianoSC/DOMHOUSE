import { useEffect } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { authHeaders, buildUrl } from "@/api/bff";
import { instanceApi } from "@/api/instance";
import { STREAM_EVENTS, type Approval, type StreamEnvelope } from "@/api/types";
import { useApartmentStore } from "@/store/apartmentStore";
import { t } from "@/i18n";

const settle = <T,>(p: Promise<T>) => p.then((v) => v, () => undefined);
const EVENTS = new Set<string>(STREAM_EVENTS);

/** Re-reads apartment, devices and health, as after a reconnection; also after a simulator reset (D-97). */
export async function resync(aptId: string) {
  const api = instanceApi(aptId);
  const [devices, apartment, health] = await Promise.all([settle(api.getDevices()), settle(api.getApartment()), settle(api.getHealth())]);
  useApartmentStore.getState().setSnapshot({
    devices: devices?.devices,
    rooms: devices?.rooms,
    apartment: apartment ?? undefined,
    health: health ?? undefined,
  }, aptId);
}

class FatalStreamError extends Error {}

/** Owns the apartment SSE stream (fetch-based, auth and Last-Event-ID as headers): refetch on (re)connect, queue events meanwhile, then apply in order. */
export function useApartmentStream(aptId: string | undefined, onApproval?: (a: Approval) => void) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!aptId) {
      return;
    }
    const store = useApartmentStore.getState();
    store.reset(aptId);
    const controller = new AbortController();
    let ready = false;
    let queue: StreamEnvelope[] = [];
    let retry = 1000;
    let lastHealth: string | null = null;

    const dispatch = (env: StreamEnvelope) => {
      useApartmentStore.getState().apply(env);
      if (env.event === "approval.pending") {
        const approval = env.data as unknown as Approval;
        toast.info(t("notify.approvalPending"), { description: approval.description, duration: 10000 });
        onApproval?.(approval);
        void queryClient.invalidateQueries({ queryKey: ["approvals", aptId] });
      }
      if (env.event === "decision.logged") {
        void queryClient.invalidateQueries({ queryKey: ["decisions", aptId] });
        // An approval that expired (or was decided on another device) arrives only as a decision with its approval_id:
        // the contract has no approval.updated, so the list is read again (D-118), not left "in attesa" until the poll.
        if ((env.data as { approval_id?: string | null }).approval_id) void queryClient.invalidateQueries({ queryKey: ["approvals", aptId] });
      }
      if (env.event === "device.online") {
        const d = env.data as unknown as { device_id: string; online: boolean };
        const label = useApartmentStore.getState().devices.find((x) => x.device_id === d.device_id)?.label ?? d.device_id;
        if (!d.online) toast.warning(t("notify.deviceOffline", { name: label }), { duration: 8000 });
      }
      if (env.event === "instance.health") {
        const h = env.data as unknown as { status: string };
        if (h.status === "down" && lastHealth !== "down") toast.error(t("notify.instanceDown"), { duration: 10000 });
        else if (h.status !== "down" && lastHealth === "down") toast.success(t("notify.instanceUp"));
        lastHealth = h.status;
      }
      if (env.event === "apartment.changed") {
        void queryClient.invalidateQueries({ queryKey: ["schedule", aptId] });
        void queryClient.invalidateQueries({ queryKey: ["bookings", aptId] });
      }
      if (env.event === "apartment.changed" || env.event === "approval.pending" || env.event === "decision.logged") {
        void queryClient.invalidateQueries({ queryKey: ["apartment-summary", aptId] });
      }
    };

    const doResync = async () => {
      ready = false;
      await resync(aptId);
      ready = true;
      const pending = queue;
      queue = [];
      pending.forEach(dispatch);
    };

    const connect = async () => {
      const path = `/app/apartments/${encodeURIComponent(aptId)}/stream`;
      await fetchEventSource(buildUrl(path), {
        headers: { Accept: "text/event-stream" },
        // Headers computed at every (re)connection (D-89): a renewed token, and the assistance header of that moment.
        fetch: async (input, init) => fetch(input, { ...init, headers: { ...(init?.headers as Record<string, string>), ...(await authHeaders(path)) } }),
        signal: controller.signal,
        openWhenHidden: true,
        async onopen(resp) {
          if (resp.ok && resp.headers.get("content-type")?.includes("text/event-stream")) {
            retry = 1000;
            useApartmentStore.getState().setConnected(true);
            void doResync();
            return;
          }
          if (resp.status === 401 || resp.status === 403 || resp.status === 404) throw new FatalStreamError(String(resp.status));
          throw new Error(`stream status ${resp.status}`);
        },
        onmessage(msg) {
          if (!EVENTS.has(msg.event) || !msg.data) return;
          let env: StreamEnvelope;
          try {
            env = JSON.parse(msg.data) as StreamEnvelope;
          } catch {
            return;
          }
          if (ready) dispatch(env);
          else queue.push(env);
        },
        onclose() {
          useApartmentStore.getState().setConnected(false);
        },
        onerror(err) {
          useApartmentStore.getState().setConnected(false);
          if (err instanceof FatalStreamError) throw err;
          const wait = retry;
          retry = Math.min(retry * 2, 30000);
          return wait;
        },
      }).catch(() => undefined);
    };

    void doResync();
    void connect();
    return () => controller.abort();
  }, [aptId, queryClient, onApproval]);
}
