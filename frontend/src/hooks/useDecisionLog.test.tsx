import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { useDecisionLog } from "./useDecisionLog";

// Decision log paging (P-32, step 1): a refresh asks the engine for the newest page only, however many older pages
// are on screen. Before, an infinite query re-fetched every loaded page on each 30 s refresh and on each new decision.
type Call = { cursor?: string; actor?: string; device_id?: string; limit?: number };
const s = vi.hoisted(() => ({ calls: [] as Call[], newest: 0 }));

const decision = (n: number) => ({ decision_id: `d-${n}`, ts: new Date(Date.UTC(2026, 9, 16, 12) - n * 60_000).toISOString(), actor: "brain", target: { type: "apartment" }, action: "mode", old_value: null, new_value: null, reasoning: `motivo ${n}`, outcome: "applied", correlation_id: `c-${n}`, command_id: null, approval_id: null });

vi.mock("@/api/instance", () => ({
  instanceApi: () => ({
    listDecisions: async (q: Call) => {
      s.calls.push(q);
      // 100 decisions, newest first, pages of q.limit; cursor = index of the next item. `newest` simulates new
      // decisions arriving at the top between refreshes.
      const all = Array.from({ length: 100 + s.newest }, (_, i) => decision(i - s.newest));
      const start = q.cursor ? Number(q.cursor) : 0;
      const items = all.slice(start, start + (q.limit ?? 30));
      return { items, next_cursor: start + items.length < all.length ? String(start + items.length) : null };
    },
  }),
}));

let client: QueryClient;
const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;

beforeEach(() => {
  s.calls = [];
  s.newest = 0;
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe("registro delle decisioni: pagine e aggiornamenti", () => {
  it("prima pagina, poi «Carica altri» dal cursore: le righe si accodano", async () => {
    const { result } = renderHook(() => useDecisionLog("apt-001", {}), { wrapper });
    await waitFor(() => expect(result.current.items).toHaveLength(30));
    await act(() => result.current.loadMore());
    await act(() => result.current.loadMore());
    expect(result.current.items).toHaveLength(90);
    expect(s.calls.map((c) => c.cursor)).toEqual([undefined, "30", "60"]);
    expect(result.current.hasMore).toBe(true);
  });

  it("aggiornamento con 3 pagine a video: UNA sola richiesta al motore, quella della prima pagina", async () => {
    const { result } = renderHook(() => useDecisionLog("apt-001", {}), { wrapper });
    await waitFor(() => expect(result.current.items).toHaveLength(30));
    await act(() => result.current.loadMore());
    await act(() => result.current.loadMore());
    s.calls = [];
    await act(() => client.invalidateQueries({ queryKey: ["decisions", "apt-001"] })); // what decision.logged does
    expect(s.calls).toEqual([{ actor: undefined, device_id: undefined, limit: 30 }]);
  });

  it("decisioni nuove in testa: compaiono in alto, nessuna riga doppia, le pagine vecchie restano", async () => {
    const { result } = renderHook(() => useDecisionLog("apt-001", {}), { wrapper });
    await waitFor(() => expect(result.current.items).toHaveLength(30));
    await act(() => result.current.loadMore());
    s.newest = 5;
    await act(() => client.invalidateQueries({ queryKey: ["decisions", "apt-001"] }));
    await waitFor(() => expect(result.current.items[0]?.decision_id).toBe("d--5"));
    const ids = result.current.items.map((d) => d.decision_id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain("d-59");
  });

  it("cambiando filtro si riparte dalla prima pagina del nuovo registro", async () => {
    const { result, rerender } = renderHook(({ actor }) => useDecisionLog("apt-001", { actor }), { wrapper, initialProps: { actor: "" } });
    await waitFor(() => expect(result.current.items).toHaveLength(30));
    await act(() => result.current.loadMore());
    rerender({ actor: "brain" });
    await waitFor(() => expect(s.calls.at(-1)).toEqual({ actor: "brain", device_id: undefined, limit: 30 }));
    await waitFor(() => expect(result.current.items).toHaveLength(30));
  });
});
