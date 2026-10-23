import { Outlet, useParams } from "react-router-dom";
import type { AppFeature } from "@/api/types";
import { ApartmentUnavailable, ContractBlocked, FeatureUnavailable } from "@/components/apartment/Notices";
import { PageSkeleton } from "@/components/ui/Skeletons";
import { useApartmentStream } from "@/hooks/useApartmentStream";
import { useFeatures } from "@/hooks/useFeatures";

export default function ApartmentLayout() {
  const { aptId } = useParams();
  const { contractOk, contractVersion, loading, denied, summary } = useFeatures(aptId);
  // The stream opens only once the BFF has answered for this apartment, never towards one it refuses (and it closes if
  // a later check refuses it). Keyed on the data, not on the last fetch, so a transient refetch error keeps it open.
  useApartmentStream(summary.data && contractOk && !denied ? aptId : undefined);
  if (loading) return <PageSkeleton />;
  if (denied) return <ApartmentUnavailable />;
  if (!contractOk && contractVersion) return <ContractBlocked version={contractVersion} />;
  return <Outlet />;
}

export function FeatureGate({ feature, children }: { feature: AppFeature; children: React.ReactNode }) {
  const { aptId } = useParams();
  const { has, loading } = useFeatures(aptId);
  if (loading) return <PageSkeleton />;
  return has(feature) ? <>{children}</> : <FeatureUnavailable />;
}
