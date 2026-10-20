import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { useApartmentStream } from "./useApartmentStream";

// The stream's headers are computed at every (re)connection (D-89): a renewed token, and the assistance header of
// that moment, never the ones of the first connection.
const s = vi.hoisted(() => ({
  opts: null as null | { fetch?: (input: string, init?: RequestInit) => Promise<Response> },
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

const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;

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
