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

/** A booking in course for the site: not cancelled, not checked out; with a check-in (occupied), or inside its window. */
const inCourse = (b: BookingRecord, occupancy: string | undefined, now: number) =>
  b.status !== "cancelled" && b.status !== "checked_out" &&
  (occupancy === "occupied" || (new Date(b.checkin_at).getTime() <= now && now < new Date(b.checkout_at).getTime()));

/**
 * Current stay = booking archived by the BFF whose id is GET /apartment.current_booking_id; hidden when unknown.
 * D18 (P-83): «occupied» comes only with a check-in event, which Italianway may never send; a booking in course without
 * it is «reserved» with its current_booking_id, and it is a stay all the same (as the engine's approvals now count it).
 */
export function useCurrentStay(aptId: string) {
  const occupancy = useApartmentStore((s) => s.apartment?.occupancy);
  const currentId = useApartmentStore((s) => s.apartment?.current_booking_id);
  const q = useQuery({ queryKey: ["bookings", aptId], queryFn: () => bookings(aptId), enabled: Boolean(aptId), staleTime: 60_000 });
  const items = q.data?.items ?? [];
  const now = Date.now();
  const current = occupancy !== "vacant" && currentId ? items.find((b) => b.booking_id === currentId && inCourse(b, occupancy, now)) : undefined;
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
