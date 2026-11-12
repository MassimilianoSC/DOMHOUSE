import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useApartmentStore } from "@/store/apartmentStore";
import { isInProgress } from "@/store/streamReducer";
import { useApartmentStream } from "./useApartmentStream";

// P-83: the re-reads that follow a (re)connection. D46: two of them at once, the older must not win. D48: a command
// whose outcome arrived while the stream was closed is read again, it does not stay «in corso».
const s = vi.hoisted(() => ({
  opts: null as null | { onopen?: (r: Response) => Promise<void>; onmessage?: (m: { event: string; data: string; id?: string }) => void },
  pending: [] as ((v: unknown) => void)[],
  getCommand: vi.fn(),
  auto: false,
}));
vi.mock("@microsoft/fetch-event-source", () => ({ fetchEventSource: vi.fn(async (_u: string, o: typeof s.opts) => { s.opts = o; }) }));
vi.mock("@/api/bff", async (orig) => ({ ...(await orig<typeof import("@/api/bff")>()), authHeaders: vi.fn(async () => ({})) }));
const snap = (open: boolean) => ({ devices: [{ device_id: "w1", label: "W", room_id: null, online: true, last_seen: null, capabilities: { contact: { open, since: null } } }], rooms: [] });
vi.mock("@/api/instance", () => ({ instanceApi: () => ({
  getDevices: () => (s.auto ? Promise.resolve(snap(false)) : new Promise((res) => s.pending.push(res))),
  getApartment: async () => null,
  getHealth: async () => null,
  getCommand: s.getCommand,
}) }));

let client: QueryClient;
const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
const ev = (event: string, id: string, data: unknown) => ({ event, id, data: JSON.stringify({ event, id, data }) });
const contact = () => (useApartmentStore.getState().devices[0]?.capabilities as { contact?: { open: boolean } } | undefined)?.contact?.open;
const opened = () => new Response("", { status: 200, headers: { "content-type": "text/event-stream" } });

beforeEach(() => {
  client = new QueryClient();
  s.opts = null;
  s.pending = [];
  s.auto = false;
  s.getCommand.mockReset();
  s.getCommand.mockResolvedValue(null);
});

afterEach(() => {
  Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
});

it("D46: la rilettura più vecchia (all'apertura) che finisce dopo quella della connessione non cancella un evento già applicato", async () => {
  renderHook(() => useApartmentStream("apt-1"), { wrapper });
  await waitFor(() => expect(s.opts?.onopen).toBeDefined());
  expect(s.pending.length).toBe(1); // A: all'apertura
  await act(async () => { await s.opts!.onopen!(opened()); });
  expect(s.pending.length).toBe(2); // B: alla connessione
  await act(async () => { s.pending[1](snap(false)); }); // B finisce prima
  act(() => s.opts!.onmessage!(ev("device.state", "11", { device_id: "w1", capability: "contact", state: { open: true, since: null } })));
  expect(contact()).toBe(true);
  await act(async () => { s.pending[0](snap(false)); }); // A, la fotografia più vecchia, per ultima
  expect(contact()).toBe(true);
});

it("D46: la più vecchia che finisce per prima non apre la coda: gli eventi aspettano la più recente", async () => {
  renderHook(() => useApartmentStream("apt-1"), { wrapper });
  await waitFor(() => expect(s.opts?.onopen).toBeDefined());
  await act(async () => { await s.opts!.onopen!(opened()); });
  act(() => s.opts!.onmessage!(ev("device.state", "11", { device_id: "w1", capability: "contact", state: { open: true, since: null } })));
  await act(async () => { s.pending[0](snap(false)); }); // A per prima: l'evento resta in coda
  expect(contact()).not.toBe(true);
  await act(async () => { s.pending[1](snap(false)); }); // B: fotografia, poi l'evento
  expect(contact()).toBe(true);
});

it("D48: comando «sent», stream chiuso e riaperto senza ripetizione dell'esito: riletto con getCommand, non più «in corso»", async () => {
  s.auto = true;
  renderHook(() => useApartmentStream("apt-1"), { wrapper });
  await waitFor(() => expect(s.opts?.onopen).toBeDefined());
  await act(async () => { await s.opts!.onopen!(opened()); });
  act(() => useApartmentStore.getState().track({ command_id: "C1", device_id: "w1", status: "sent", reason: null }));
  s.getCommand.mockResolvedValue({ command_id: "C1", device_id: "w1", capability: "switch", action: "turn_on", status: "acked", reason: null });
  const first = s.opts;
  act(() => { Object.defineProperty(document, "hidden", { configurable: true, get: () => true }); document.dispatchEvent(new Event("visibilitychange")); });
  act(() => { Object.defineProperty(document, "hidden", { configurable: true, get: () => false }); document.dispatchEvent(new Event("visibilitychange")); });
  await waitFor(() => expect(s.opts).not.toBe(first));
  await act(async () => { await s.opts!.onopen!(opened()); });
  await waitFor(() => expect(s.getCommand).toHaveBeenCalledWith("C1"));
  await waitFor(() => {
    const st = useApartmentStore.getState();
    expect(isInProgress(st.commands[st.lastCommandByDevice.w1]?.status)).toBe(false);
  });
  expect(useApartmentStore.getState().commands.C1.status).toBe("acked");
});
