import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { useApartmentStore } from "@/store/apartmentStore";
import { useCurrentStay, type BookingRecord } from "./useStays";

// P-83, D18 (site side): the engine says «occupied» only after a check-in event, which Italianway may never send. A
// booking in course without it is «reserved», with its current_booking_id: the site hid «Soggiorno» on Consumi and the
// comparison with the previous stay. Now the stay in course is the booking in its window, not cancelled, not checked
// out, whether or not the check-in arrived.
const s = vi.hoisted(() => ({ items: [] as unknown[] }));
vi.mock("@/api/bff", async (orig) => ({ ...(await orig<typeof import("@/api/bff")>()), bffFetch: vi.fn(async () => ({ items: s.items })) }));

const HOUR = 3600_000;
const iso = (offsetH: number) => new Date(Date.now() + offsetH * HOUR).toISOString();
const booking = (id: string, fromH: number, toH: number, status: BookingRecord["status"]): BookingRecord =>
  ({ apartment_id: "apt-1", booking_id: id, checkin_at: iso(fromH), checkout_at: iso(toH), guests: 2, status });
const PREVIOUS = booking("bk-0", -100, -50, "checked_out");

function engineSays(occupancy: "occupied" | "reserved" | "vacant", currentId: string | null) {
  useApartmentStore.getState().reset("apt-1");
  useApartmentStore.getState().setSnapshot({
    apartment: {
      apartment_id: "apt-1", name: "Casa", timezone: "Europe/Rome", occupancy, mode: "comfort", hold: null,
      next_checkin: null, next_checkout: null, current_booking_id: currentId, online: true, devices_online: 1,
      devices_total: 1, updated_at: iso(0),
    },
  }, "apt-1");
}

function stay() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return renderHook(() => useCurrentStay("apt-1"), { wrapper });
}

async function loaded(view: ReturnType<typeof stay>) {
  await waitFor(() => expect(view.result.current.loading).toBe(false));
  return view.result.current;
}

describe("Soggiorno in corso anche senza check-in (P-83, D18)", () => {
  it("prenotazione in corso senza check-in («reserved»): il soggiorno c'è, con il precedente", async () => {
    s.items = [PREVIOUS, booking("bk-1", -5, 48, "booked")];
    engineSays("reserved", "bk-1");
    const r = await loaded(stay());
    expect(r.current?.booking_id).toBe("bk-1");
    expect(r.previous?.booking_id).toBe("bk-0");
  });

  it("con il check-in («occupied»): come prima", async () => {
    s.items = [PREVIOUS, booking("bk-1", -5, 48, "checked_in")];
    engineSays("occupied", "bk-1");
    expect((await loaded(stay())).current?.booking_id).toBe("bk-1");
  });

  it("prenotazione disdetta: nessun soggiorno", async () => {
    s.items = [booking("bk-1", -5, 48, "cancelled")];
    engineSays("reserved", "bk-1");
    expect((await loaded(stay())).current).toBeUndefined();
  });

  it("check-out già arrivato al server (il motore non l'ha ancora detto): nessun soggiorno", async () => {
    s.items = [booking("bk-1", -5, 48, "checked_out")];
    engineSays("occupied", "bk-1");
    expect((await loaded(stay())).current).toBeUndefined();
  });

  it("prenotazione «reserved» fuori dalla sua finestra (arrivo domani): nessun soggiorno", async () => {
    s.items = [booking("bk-1", 24, 72, "booked")];
    engineSays("reserved", "bk-1");
    expect((await loaded(stay())).current).toBeUndefined();
  });

  it("casa libera («vacant»): nessun soggiorno", async () => {
    s.items = [booking("bk-1", -5, 48, "booked")];
    engineSays("vacant", null);
    expect((await loaded(stay())).current).toBeUndefined();
  });
});
