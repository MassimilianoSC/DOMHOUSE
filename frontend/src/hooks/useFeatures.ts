import { useQuery } from "@tanstack/react-query";
import { ApiError, bffFetch } from "@/api/bff";
import type { AppFeature, ApartmentSummary } from "@/api/types";
import { useFeatureStore } from "@/store/featureStore";

export function useApartmentSummary(aptId: string | undefined) {
  return useQuery({
    queryKey: ["apartment-summary", aptId],
    queryFn: () => bffFetch<ApartmentSummary>(`/app/apartments/${encodeURIComponent(aptId!)}`),
    enabled: Boolean(aptId),
    refetchInterval: 30_000,
  });
}

/** enabled false: a person without an organization (a platform manager only) has no apartments, and the route would
 *  answer 403 (P-36): no call at all. */
export function useApartments(enabled = true) {
  return useQuery({
    queryKey: ["apartments"],
    queryFn: () => bffFetch<ApartmentSummary[]>("/app/apartments"),
    enabled,
    refetchInterval: 20_000,
  });
}

/** The BFF answers 404 (or 403) for an apartment that does not exist or is not assigned to this user (P-18). */
export const accessDenied = (err: unknown) => err instanceof ApiError && (err.status === 404 || err.status === 403);

/** Feature = enabled in our configuration AND listed by the instance, minus any that answered 501 at runtime. */
export function useFeatures(aptId: string | undefined) {
  const summary = useApartmentSummary(aptId);
  const disabled = useFeatureStore((s) => (aptId ? s.disabled[aptId] : undefined));
  const features = new Set<AppFeature>((summary.data?.features ?? []).filter((f) => !(disabled ?? []).includes(f)));
  const version = summary.data?.contract_version ?? null;
  const contractOk = version === null || version.split(".")[0] === "1";
  return {
    summary,
    features,
    has: (f: AppFeature) => features.has(f),
    contractVersion: version,
    contractOk,
    denied: accessDenied(summary.error),
    loading: summary.isLoading,
  };
}
