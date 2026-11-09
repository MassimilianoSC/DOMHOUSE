import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useApartmentStore } from "@/store/apartmentStore";
import { jittered, useApartmentStream } from "./useApartmentStream";

// E-27: the server closes the stream by itself after a few minutes, so the page must reopen it; and a hidden page keeps
// no stream open. With the real fetch-event-source and a fake network, because the defects were in how the two meet.
vi.mock("@/api/bff", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/api/bff")>()), authHeaders: vi.fn(async () => ({})) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getDevices: async () => ({ devices: [], rooms: [] }), getApartment: async () => null, getHealth: async () => null }) }));

interface Conn {
  headers: Record<string, string>;
  signal: AbortSignal;
  send: (text: string) => void;
  /** The server ends the response normally. */
  end: () => void;
}

let conns: Conn[];
let status: number;
let hidden: boolean;
let client: QueryClient;
const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
const sleep = (ms: number) => act(() => new Promise<void>((r) => setTimeout(r, ms)));
const live = () => conns.filter((c) => !c.signal.aborted);

function setHidden(value: boolean) {
  hidden = value;
  act(() => {
    document.dispatchEvent(new Event("visibilitychange"));
  });
}

beforeEach(() => {
  client = new QueryClient();
  conns = [];
  status = 200;
  hidden = false;
  Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
  // the shortest wait: half of 1000 ms, then half of 2000 ms
  vi.spyOn(Math, "random").mockReturnValue(0);
  vi.stubGlobal("fetch", vi.fn(async (_input: string, init: RequestInit) => {
    if (status !== 200) return new Response("", { status });
    let ctrl!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({ start: (c) => { ctrl = c; } });
    const signal = init.signal as AbortSignal;
    let done = false;
    signal.addEventListener("abort", () => {
      if (!done) ctrl.error(new DOMException("Aborted", "AbortError"));
      done = true;
    });
    conns.push({
      headers: init.headers as Record<string, string>,
      signal,
      send: (text) => ctrl.enqueue(new TextEncoder().encode(text)),
      end: () => {
        done = true;
        ctrl.close();
      },
    });
    return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
  }));
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete (document as unknown as { hidden?: boolean }).hidden;
});

async function opened(count: number) {
  await waitFor(() => expect(conns).toHaveLength(count));
  await waitFor(() => expect(useApartmentStore.getState().connected).toBe(true));
}

describe("stream dell'appartamento: riapertura e scheda nascosta (E-27)", () => {
  it("il ritardo varia fra metà e tutto il valore", () => {
    vi.spyOn(Math, "random").mockReturnValue(0);
    expect(jittered(2000)).toBe(1000);
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    expect(jittered(2000)).toBe(1500);
  });

  it("chiusura normale del server: lo stream si riapre, e l'indicatore non passa a «Riconnessione…»", async () => {
    renderHook(() => useApartmentStream("apt-1"), { wrapper });
    await opened(1);
    const seen: boolean[] = [];
    const off = useApartmentStore.subscribe((st) => seen.push(st.connected));
    act(() => conns[0].end());
    await waitFor(() => expect(conns).toHaveLength(2));
    await opened(2);
    off();
    expect(seen).not.toContain(false);
  });

  it("uno stream chiuso subito raddoppia l'attesa invece di martellare il server", async () => {
    renderHook(() => useApartmentStream("apt-1"), { wrapper });
    await opened(1);
    act(() => conns[0].end());
    await sleep(700); // half of 1000 ms has passed
    expect(conns).toHaveLength(2);
    act(() => conns[1].end());
    await sleep(700); // half of 2000 ms has not
    expect(conns).toHaveLength(2);
    await sleep(500);
    expect(conns).toHaveLength(3);
  });

  it("401: non si riapre, nemmeno quando la scheda torna visibile", async () => {
    status = 401;
    const f = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    renderHook(() => useApartmentStream("apt-1"), { wrapper });
    await waitFor(() => expect(f).toHaveBeenCalledTimes(1));
    await sleep(800);
    expect(f).toHaveBeenCalledTimes(1);
    expect(useApartmentStore.getState().connected).toBe(false);
    setHidden(true);
    setHidden(false);
    await sleep(800);
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("scheda nascosta: lo stream si chiude subito", async () => {
    renderHook(() => useApartmentStream("apt-1"), { wrapper });
    await opened(1);
    setHidden(true);
    expect(conns[0].signal.aborted).toBe(true);
    expect(useApartmentStore.getState().connected).toBe(false);
  });

  it("scheda nascosta con una riprova in attesa: non si apre nulla", async () => {
    renderHook(() => useApartmentStream("apt-1"), { wrapper });
    await opened(1);
    act(() => conns[0].end());
    await sleep(50); // the retry is scheduled, 500 ms from now
    setHidden(true);
    await sleep(800);
    expect(conns).toHaveLength(1);
  });

  it("ritorno con una riprova in attesa: una sola connessione, con l'ultimo Last-Event-ID", async () => {
    renderHook(() => useApartmentStream("apt-1"), { wrapper });
    await opened(1);
    await act(async () => {
      conns[0].send('id: 42\nevent: ping\ndata: {}\n\n');
      await new Promise((r) => setTimeout(r, 20));
    });
    act(() => conns[0].end());
    await sleep(50);
    setHidden(true);
    setHidden(false);
    await opened(2);
    await sleep(800); // the old retry would have fired by now
    expect(conns).toHaveLength(2);
    expect(live()).toHaveLength(1);
    expect(conns[1].headers["last-event-id"]).toBe("42");
  });

  it("evento di visibilità a scheda già visibile: nessuna seconda connessione", async () => {
    renderHook(() => useApartmentStream("apt-1"), { wrapper });
    await opened(1);
    setHidden(false);
    await sleep(50);
    expect(conns).toHaveLength(1);
    expect(conns[0].signal.aborted).toBe(false);
  });

  it("aperta già nascosta: nessuno stream finché non diventa visibile", async () => {
    hidden = true;
    renderHook(() => useApartmentStream("apt-1"), { wrapper });
    await sleep(100);
    expect(conns).toHaveLength(0);
    setHidden(false);
    await opened(1);
  });

  it("uscendo dalla pagina non resta né lo stream né una riprova", async () => {
    const { unmount } = renderHook(() => useApartmentStream("apt-1"), { wrapper });
    await opened(1);
    act(() => conns[0].end());
    await sleep(50);
    unmount();
    await sleep(800);
    expect(conns).toHaveLength(1);
  });
});
