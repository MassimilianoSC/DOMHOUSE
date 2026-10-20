import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useApartmentStream } from "./useApartmentStream";

// The stream's headers are computed at every (re)connection (D-89): a renewed token, and the assistance header of
// that moment, never the ones of the first connection.
const s = vi.hoisted(() => ({
  opts: null as null | {
    fetch?: (input: string, init?: RequestInit) => Promise<Response>;
    onopen?: (resp: Response) => Promise<void>;
    onmessage?: (msg: { event: string; data: string }) => void;
  },
  headers: [] as Record<string, string>[],
}));

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: vi.fn(async (_url: string, opts: typeof s.opts) => {
    s.opts = opts;
  }),
}));
vi.mock("@/api/bff", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/bff")>()),
  authHeaders: vi.fn(async () => s.headers.shift() ?? {}),
}));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getDevices: async () => ({ devices: [], rooms: [] }), getApartment: async () => null, getHealth: async () => null }) }));

let client: QueryClient;
const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;

beforeEach(() => {
  client = new QueryClient();
  s.opts = null;
});

describe("stream dell'appartamento: intestazioni a ogni connessione", () => {
  it("la riconnessione usa le intestazioni del momento, non quelle della prima connessione", async () => {
    s.headers = [{ Authorization: "Bearer vecchio", "X-Support-Tenant": "t-2" }, { Authorization: "Bearer nuovo" }];
    const seen: Record<string, string>[] = [];
    vi.stubGlobal("fetch", vi.fn(async (_input: string, init?: RequestInit) => {
      seen.push(init?.headers as Record<string, string>);
      return new Response("", { status: 200 });
    }));
    renderHook(() => useApartmentStream("apt-1"), { wrapper });
    await waitFor(() => expect(s.opts?.fetch).toBeDefined());
    await s.opts!.fetch!("http://x/app/apartments/apt-1/stream", { headers: { accept: "text/event-stream" } });
    await s.opts!.fetch!("http://x/app/apartments/apt-1/stream", { headers: { accept: "text/event-stream", "last-event-id": "7" } });
    expect(seen[0]).toMatchObject({ Authorization: "Bearer vecchio", "X-Support-Tenant": "t-2", accept: "text/event-stream" });
    expect(seen[1]).toMatchObject({ Authorization: "Bearer nuovo", "last-event-id": "7" });
    expect(seen[1]["X-Support-Tenant"]).toBeUndefined();
  });
});


describe("stream: approvazione scaduta (D-118)", () => {
  /** The stream opened and the first resync done, so events are applied at once. */
  async function connected(aptId = "apt-1") {
    s.headers = [{ Authorization: "Bearer x" }];
    renderHook(() => useApartmentStream(aptId), { wrapper });
    await waitFor(() => expect(s.opts?.onopen).toBeDefined());
    await act(async () => {
      await s.opts!.onopen!(new Response("", { status: 200, headers: { "content-type": "text/event-stream" } }));
    });
  }

  const decision = (over: Record<string, unknown>) => ({
    event: "decision.logged",
    data: JSON.stringify({
      event_id: "7", event: "decision.logged", apartment_id: "apt-1", ts: "2026-10-20T14:42:17Z", correlation_id: "c-1",
      data: { decision_id: "d-1", ts: "2026-10-20T14:42:17Z", actor: "system", target: { type: "device", device_id: "dev-1" }, action: "expire", old_value: "pending", new_value: "expired", reasoning: "Approvazione scaduta senza risposta: respinta", outcome: "informational", correlation_id: "c-1", ...over },
    }),
  });

  it("decisione legata a un'approvazione (scaduta, o decisa da un altro dispositivo): la lista delle approvazioni si rilegge", async () => {
    await connected();
    const spy = vi.spyOn(client, "invalidateQueries");
    act(() => s.opts!.onmessage!(decision({ approval_id: "apr-03ed" })));
    expect(spy).toHaveBeenCalledWith({ queryKey: ["approvals", "apt-1"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["decisions", "apt-1"] });
  });

  it("decisione senza approvazione: le approvazioni non si rileggono, le decisioni sì", async () => {
    await connected();
    const spy = vi.spyOn(client, "invalidateQueries");
    act(() => s.opts!.onmessage!(decision({ action: "set_mode", approval_id: null })));
    expect(spy).not.toHaveBeenCalledWith({ queryKey: ["approvals", "apt-1"] });
    expect(spy).toHaveBeenCalledWith({ queryKey: ["decisions", "apt-1"] });
  });
});
