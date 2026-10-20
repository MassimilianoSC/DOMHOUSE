import { bffFetch, ApiError, type RequestOptions } from "./bff";
import type { ApartmentMode, Body, Command, Ok } from "./types";
import { featureForPath, useFeatureStore } from "@/store/featureStore";
import { newCorrelationId } from "@/lib/utils";

async function request<T>(aptId: string, path: string, opts: RequestOptions = {}): Promise<T> {
  const correlationId = opts.correlationId ?? newCorrelationId();
  try {
    return await bffFetch<T>(`/app/apartments/${encodeURIComponent(aptId)}/instance${path}`, { ...opts, correlationId });
  } catch (err) {
    if (err instanceof ApiError && err.status === 501) {
      const feature = featureForPath(opts.method ?? "GET", path);
      if (feature) useFeatureStore.getState().disable(aptId, feature);
    }
    throw err;
  }
}

/** Typed wrapper over the instance contract, proxied 1:1 by the BFF. */
export function instanceApi(aptId: string) {
  return {
    getApartment: () => request<Ok<"getApartment">>(aptId, "/apartment"),
    setMode: (mode: ApartmentMode, correlationId: string) =>
      request<Ok<"setApartmentMode", 202>>(aptId, "/apartment/mode", { method: "POST", body: { mode } satisfies Body<"setApartmentMode">, correlationId }),
    setHold: (body: Body<"holdApartment">, correlationId: string) =>
      request<Ok<"holdApartment", 202>>(aptId, "/apartment/hold", { method: "POST", body, correlationId }),
    getDevices: () => request<Ok<"listDevices">>(aptId, "/devices"),
    updateDevice: (deviceId: string, body: Body<"updateDevice">, correlationId: string) =>
      request<Ok<"updateDevice">>(aptId, `/devices/${encodeURIComponent(deviceId)}`, { method: "PATCH", body, correlationId }),
    sendCommand: (deviceId: string, body: Command, correlationId: string) =>
      request<Ok<"sendCommand", 202>>(aptId, `/devices/${encodeURIComponent(deviceId)}/commands`, { method: "POST", body, correlationId }),
    getCommand: (commandId: string) => request<Ok<"getCommand">>(aptId, `/commands/${encodeURIComponent(commandId)}`),
    getEnergy: (query: { from: string; to: string; bucket: "hour" | "day" }) => request<Ok<"getEnergy">>(aptId, "/energy", { query }),
    listSchedule: () => request<Ok<"listSchedule">>(aptId, "/schedule"),
    createSchedule: (body: Body<"createScheduleItem">, correlationId: string) =>
      request<Ok<"createScheduleItem", 201>>(aptId, "/schedule", { method: "POST", body, correlationId }),
    moveSchedule: (scheduleId: string, body: Body<"updateScheduleItem">, correlationId: string) =>
      request<Ok<"updateScheduleItem">>(aptId, `/schedule/${encodeURIComponent(scheduleId)}`, { method: "PATCH", body, correlationId }),
    cancelSchedule: (scheduleId: string, correlationId: string) =>
      request<void>(aptId, `/schedule/${encodeURIComponent(scheduleId)}`, { method: "DELETE", correlationId }),
    getRules: () => request<Ok<"getRules">>(aptId, "/rules"),
    updateRules: (body: Body<"updateRules">, correlationId: string) => request<Ok<"updateRules">>(aptId, "/rules", { method: "PUT", body, correlationId }),
    listApprovals: (status: "pending" | "all") => request<Ok<"listApprovals">>(aptId, "/approvals", { query: { status } }),
    decideApproval: (approvalId: string, body: Body<"decideApproval">, correlationId: string) =>
      request<Ok<"decideApproval">>(aptId, `/approvals/${encodeURIComponent(approvalId)}/decision`, { method: "POST", body, correlationId }),
    listDecisions: (query: { from?: string; to?: string; actor?: string; device_id?: string; correlation_id?: string; limit?: number; cursor?: string }) =>
      request<Ok<"listDecisions">>(aptId, "/decisions", { query }),
    ask: (text: string, correlationId: string) => request<Ok<"ask", 202>>(aptId, "/ask", { method: "POST", body: { text } satisfies Body<"ask">, correlationId }),
    getAsk: (askId: string) => request<Ok<"getAsk">>(aptId, `/ask/${encodeURIComponent(askId)}`),
    getHealth: () => request<Ok<"health">>(aptId, "/health"),
  };
}

export type InstanceApi = ReturnType<typeof instanceApi>;
