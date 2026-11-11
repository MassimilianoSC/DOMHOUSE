import { useEffect } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { ApiError, authHeaders, buildUrl } from "@/api/bff";
import { instanceApi } from "@/api/instance";
import { STREAM_EVENTS, type Approval, type StreamEnvelope } from "@/api/types";
import { useApartmentStore } from "@/store/apartmentStore";
import { isInProgress } from "@/store/streamReducer";
import { t } from "@/i18n";

const settle = <T,>(p: Promise<T>) => p.then((v) => v, () => undefined);
const EVENTS = new Set<string>(STREAM_EVENTS);

/** The server reached, the engine not (502 instance_unreachable, or another 5xx of the proxy). */
const engineUnreachable = (err: unknown) => err instanceof ApiError && err.status >= 500;

/**
 * Re-reads apartment, devices and health, as after a reconnection; also after a simulator reset (D-97).
 * current: false once a newer re-read has started (P-83, D46): this one's older photo is then dropped, it would undo
 * events applied meanwhile. Returns whether the photo was applied.
 */
export async function resync(aptId: string, current: () => boolean = () => true): Promise<boolean> {
  const api = instanceApi(aptId);
  let healthFailure: unknown;
  const [devices, apartment, health] = await Promise.all([
    settle(api.getDevices()),
    settle(api.getApartment()),
    api.getHealth().catch((err: unknown) => {
      healthFailure = err;
      return undefined;
    }),
  ]);
  if (!current()) return false;
  const store = useApartmentStore.getState();
  // P-83, D27: the server says it does not reach the engine: the health kept from before («In salute») is void.
  if (engineUnreachable(healthFailure)) store.setUnreachable(aptId);
  store.setSnapshot({
    devices: devices?.devices,
    rooms: devices?.rooms,
    apartment: apartment ?? undefined,
    health: health ?? undefined,
  }, aptId);
  void rereadCommands(aptId);
  return true;
}

/**
 * P-83, D48: a command still «in corso» here may have ended while the stream was closed (phone locked over the
 * server's replay window, another server instance): its outcome is read again, so the card does not stay busy.
 */
async function rereadCommands(aptId: string) {
  const { commands } = useApartmentStore.getState();
  const open = Object.values(commands).filter((c) => isInProgress(c.status));
  if (!open.length) return;
  const api = instanceApi(aptId);
  await Promise.all(open.map(async (c) => {
    const cmd = await settle(api.getCommand(c.command_id));
    const store = useApartmentStore.getState();
    if (!cmd || store.apartmentId !== aptId || !isInProgress(store.commands[c.command_id]?.status)) return;
    store.apply({ event: "command.updated", data: { command_id: cmd.command_id, device_id: cmd.device_id, status: cmd.status, reason: cmd.reason ?? null } } as unknown as StreamEnvelope);
  }));
}

class FatalStreamError extends Error {}
/** The server ended the stream normally (it does so by itself after STREAM_MAX_S): to be reopened, not an error. */
class StreamClosedError extends Error {}

/** How long a hidden page keeps its stream before closing it (E-27). 0 = at once. */
const HIDDEN_CLOSE_DELAY_MS = 0;
/** A stream that lasted at least this long was healthy: the next wait starts again from the shortest. */
const STABLE_STREAM_MS = 30_000;

/** Between half and all of the wait, so that the browsers of a stream closed for everybody do not come back together. */
export const jittered = (ms: number) => Math.round(ms * (0.5 + Math.random() * 0.5));

/** Owns the apartment SSE stream (fetch-based, auth and Last-Event-ID as headers): refetch on (re)connect, queue events meanwhile, then apply in order. */
export function useApartmentStream(aptId: string | undefined, onApproval?: (a: Approval) => void) {
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!aptId) {
      return;
    }
    const store = useApartmentStore.getState();
    store.reset(aptId);
    let ready = false;
    let queue: StreamEnvelope[] = [];
    let retry = 1000;
    let openedAt = 0;
    let lastHealth: string | null = null;
    // E-27: the page owns the stream's life. The library's own handling of hidden pages (openWhenHidden: false) aborts
    // the request but not a retry already scheduled, which then opens a stream in the background or a second one.
    let connection: AbortController | null = null;
    let refused = false; // 401, 403, 404: never reopened, not even when the page comes back
    let lastEventId: string | undefined;
    let hideTimer: number | undefined;
    let resyncs = 0; // P-83, D46: only the latest re-read applies its photo and opens the queue

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
      if (env.event === "apartment.changed" || env.event === "approval.pending" || env.event === "decision.logged" || env.event === "instance.health") {
        void queryClient.invalidateQueries({ queryKey: ["apartment-summary", aptId] });
      }
    };

    const doResync = async () => {
      const mine = ++resyncs;
      ready = false;
      if (!(await resync(aptId, () => mine === resyncs))) return;
      ready = true;
      const pending = queue;
      queue = [];
      pending.forEach(dispatch);
    };

    const connect = async (own: AbortController) => {
      const path = `/app/apartments/${encodeURIComponent(aptId)}/stream`;
      await fetchEventSource(buildUrl(path), {
        // lower case: the library keeps the same key up to date while the stream is open
        headers: { Accept: "text/event-stream", ...(lastEventId ? { "last-event-id": lastEventId } : {}) },
        // Headers computed at every (re)connection (D-89): a renewed token, and the assistance header of that moment.
        fetch: async (input, init) => fetch(input, { ...init, headers: { ...(init?.headers as Record<string, string>), ...(await authHeaders(path)) } }),
        signal: own.signal,
        openWhenHidden: true,
        async onopen(resp) {
          if (resp.ok && resp.headers.get("content-type")?.includes("text/event-stream")) {
            openedAt = Date.now();
            useApartmentStore.getState().setConnected(true);
            void doResync();
            return;
          }
          if (resp.status === 401 || resp.status === 403 || resp.status === 404) throw new FatalStreamError(String(resp.status));
          throw new Error(`stream status ${resp.status}`);
        },
        onmessage(msg) {
          if (msg.id) lastEventId = msg.id;
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
        // Thrown so that the library goes through onerror and retries: left alone, it stops at a normal end of the stream.
        onclose() {
          throw new StreamClosedError();
        },
        onerror(err) {
          // the planned close is not shown as «Riconnessione…»: a real failure of the reopening is
          if (!(err instanceof StreamClosedError)) useApartmentStore.getState().setConnected(false);
          if (err instanceof FatalStreamError) {
            refused = true;
            throw err;
          }
          // Only a stream that lasted resets the wait: one closed at once (a server shutting down) keeps doubling it.
          if (openedAt && Date.now() - openedAt >= STABLE_STREAM_MS) retry = 1000;
          openedAt = 0;
          const wait = retry;
          retry = Math.min(retry * 2, 30000);
          return jittered(wait);
        },
      }).catch(() => undefined);
    };

    const start = () => {
      if (connection || refused) return;
      retry = 1000;
      openedAt = 0;
      connection = new AbortController();
      void connect(connection);
    };
    /** Stops the whole fetchEventSource: the open request and any retry already scheduled. */
    const stop = () => {
      connection?.abort();
      connection = null;
      useApartmentStore.getState().setConnected(false);
    };
    const onVisibility = () => {
      window.clearTimeout(hideTimer);
      if (!document.hidden) start();
      else if (HIDDEN_CLOSE_DELAY_MS > 0) hideTimer = window.setTimeout(stop, HIDDEN_CLOSE_DELAY_MS);
      else stop(); // directly: a phone may freeze the page before a timer runs
    };

    document.addEventListener("visibilitychange", onVisibility);
    void doResync();
    if (!document.hidden) start();
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      window.clearTimeout(hideTimer);
      connection?.abort();
    };
  }, [aptId, queryClient, onApproval]);
}
