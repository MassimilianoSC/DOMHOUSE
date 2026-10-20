import { useQuery } from "@tanstack/react-query";
import { bffFetch } from "@/api/bff";
import { instanceApi } from "@/api/instance";
import { useApartmentStore } from "@/store/apartmentStore";

export interface BookingRecord {
  apartment_id: string;
  booking_id: string;
  checkin_at: string;
  checkout_at: string;
  guests: number | null;
  status: "booked" | "checked_in" | "checked_out" | "cancelled";
}

const bookings = (aptId: string) => bffFetch<{ items: BookingRecord[] }>(`/app/apartments/${encodeURIComponent(aptId)}/bookings`);

/** Current stay = booking archived by the BFF whose id is GET /apartment.current_booking_id; hidden when unknown. */
export function useCurrentStay(aptId: string) {
  const occupancy = useApartmentStore((s) => s.apartment?.occupancy);
  const currentId = useApartmentStore((s) => s.apartment?.current_booking_id);
  const q = useQuery({ queryKey: ["bookings", aptId], queryFn: () => bookings(aptId), enabled: Boolean(aptId), staleTime: 60_000 });
  const items = q.data?.items ?? [];
  const current = occupancy === "occupied" && currentId ? items.find((b) => b.booking_id === currentId && b.status !== "cancelled") : undefined;
  const previous = current
    ? items.filter((b) => b.status !== "cancelled" && b.booking_id !== current.booking_id && b.checkout_at <= current.checkin_at).sort((a, b) => b.checkout_at.localeCompare(a.checkout_at))[0]
    : undefined;
  return { current, previous, loading: q.isLoading };
}

const bucketFor = (from: string, to: string) => ((new Date(to).getTime() - new Date(from).getTime()) / 3600_000 < 48 ? "hour" : "day") as "hour" | "day";

/** Energy of the previous stay over its own [checkin, checkout]; only from BFF-archived bookings. */
export function usePreviousStayEnergy(aptId: string, previous: BookingRecord | undefined) {
  return useQuery({
    queryKey: ["energy", aptId, "previous-stay", previous?.booking_id],
    queryFn: () => instanceApi(aptId).getEnergy({ from: previous!.checkin_at, to: previous!.checkout_at, bucket: bucketFor(previous!.checkin_at, previous!.checkout_at) }),
    enabled: Boolean(previous),
    staleTime: 300_000,
  });
}
