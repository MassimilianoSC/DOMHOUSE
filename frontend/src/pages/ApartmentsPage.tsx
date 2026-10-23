import { Link } from "react-router-dom";
import { Plus, WifiOff } from "lucide-react";
import type { ApartmentSummary } from "@/api/types";
import { useAuth, useRole } from "@/auth/AuthProvider";
import { DemoBadge } from "@/components/admin/apartmentForm";
import { OccupancyBadge } from "@/components/apartment/ApartmentControls";
import { Button } from "@/components/ui/button";
import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { useApartments } from "@/hooks/useFeatures";
import { PageHeader } from "@/components/layout/PageHeader";
import { t } from "@/i18n";
import { capitalizeFirst, fmtNumber, fmtShortDateTime } from "@/lib/format";
import { platformApartmentsUrl } from "@/lib/routes";
import { cn } from "@/lib/utils";

/** One datum of the card's strip (design lot 2): label 12 px above the value, no icon; grey when the apartment is offline. */
function Stat({ label, value, muted, testId }: { label: string; value: React.ReactNode; muted?: boolean; testId: string }) {
  return (
    <div className="min-w-0 bg-card px-3 py-2" data-testid={testId}>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className={cn("text-sm font-semibold tabular [overflow-wrap:anywhere]", muted && "text-muted-foreground")}>{value}</div>
    </div>
  );
}

function ApartmentCard({ a }: { a: ApartmentSummary }) {
  const apt = a.apartment;
  const offline = !a.online;
  const pending = a.pending_approvals ?? 0;
  return (
    <Link to={`/a/${a.apartment_id}`} aria-label={t("apartments.open", { name: a.name })} data-testid={`apartment-card-${a.apartment_id}`} className="group block rounded-lg focus-ring">
      {/* no grey filter when offline (design lot 2): the badge says it, the data turn grey */}
      <Card className="flex h-full flex-col gap-4 p-5 transition-colors group-hover:border-foreground/20">
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <h2 className="text-base font-semibold [overflow-wrap:anywhere]">{a.name}</h2>
              {a.simulated && <DemoBadge testId={`apartment-demo-${a.apartment_id}`} />}
            </div>
            <p className="truncate text-xs text-muted-foreground">{a.address}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {apt && <OccupancyBadge occupancy={apt.occupancy} testId={`apartment-occupancy-${a.apartment_id}`} />}
            {offline ? (
              <Badge data-testid={`apartment-offline-${a.apartment_id}`} className="border-neutral-border bg-neutral-bg text-neutral-fg">
                <WifiOff className="h-3 w-3" /> {a.enabled ? t("apartments.unreachable") : t("apartments.disabled")}
              </Badge>
            ) : (
              <Badge className="border-positive-border bg-positive-bg text-positive-fg" data-testid={`apartment-online-${a.apartment_id}`}>
                <span className="h-1.5 w-1.5 rounded-full bg-positive" /> {t("apartments.online")}
              </Badge>
            )}
          </div>
        </div>
        {/* the data as one strip divided by 1 px lines (design lot 2) */}
        <div className="grid grid-cols-2 gap-px overflow-hidden rounded-md border bg-border">
          <Stat label={t("mode.label")} value={apt ? capitalizeFirst(t(`mode.${apt.mode}`)) : "—"} muted={offline} testId={`apartment-mode-${a.apartment_id}`} />
          <Stat label={t("apartments.kwhToday")} value={a.kwh_today !== null ? `${fmtNumber(a.kwh_today, 1)} kWh` : "—"} muted={offline} testId={`apartment-kwh-${a.apartment_id}`} />
          <Stat label={t("apartments.nextCheckin")} value={fmtShortDateTime(apt?.next_checkin, a.timezone)} muted={offline} testId={`apartment-checkin-${a.apartment_id}`} />
          <Stat label={t("apartments.nextCheckout")} value={fmtShortDateTime(apt?.next_checkout, a.timezone)} muted={offline} testId={`apartment-checkout-${a.apartment_id}`} />
        </div>
        {/* the approvals in one place, as the card's action line, without pulsing (design lot 2) */}
        {pending > 0 && (
          <p className="mt-auto text-sm font-semibold text-warning-fg" data-testid={`apartment-approvals-${a.apartment_id}`}>
            {pending === 1 ? t("apartments.pendingOne") : t("apartments.pendingMany", { count: pending })} →
          </p>
        )}
      </Card>
    </Link>
  );
}

export default function ApartmentsPage() {
  const { data, isLoading } = useApartments();
  const { isAdmin, isPlatform } = useRole();
  const { me } = useAuth();
  // An operator or viewer limited to some apartments (P-18) is told to ask for one, not that an admin can add one.
  const restricted = !isAdmin && (me?.user.apartment_ids ?? "all") !== "all";
  // Apartments are created only by the platform manager, from Organizzazioni (D-77): a manager goes there, an admin
  // asks the HQE support, anyone else asks an admin.
  const tenantId = me?.tenant?.tenant_id;
  const platformHere = isPlatform && Boolean(tenantId);
  const emptyHint = restricted ? t("apartments.emptyAssignedHint") : platformHere ? t("apartments.emptyHintPlatform") : isAdmin ? t("apartments.emptyHint") : t("apartments.emptyHintMember");
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title={t("apartments.title")}
        titleTestId="apartments-title"
        subtitle={data ? t("apartments.subtitle", { count: data.length }) : undefined}
        testId="apartments-header"
        actions={platformHere && tenantId ? (
          <Button asChild data-testid="add-apartment-btn">
            <Link to={platformApartmentsUrl(tenantId)}>
              <Plus /> {t("apartments.add")}
            </Link>
          </Button>
        ) : (
          isAdmin && Boolean(data?.length) && <p className="max-w-xs text-sm text-muted-foreground" data-testid="add-apartment-note">{t("apartments.emptyHint")}</p>
        )}
      />
      {isLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1].map((i) => <Skeleton key={i} className="h-52 rounded-lg" />)}
        </div>
      )}
      {data && data.length === 0 && (
        <Card className="p-10 text-center" data-testid="apartments-empty">
          <p className="font-bold">{restricted ? t("apartments.emptyAssigned") : t("apartments.empty")}</p>
          <p className="mt-1 text-sm text-muted-foreground" data-testid="apartments-empty-hint">{emptyHint}</p>
        </Card>
      )}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data?.map((a) => <ApartmentCard key={a.apartment_id} a={a} />)}
      </div>
    </div>
  );
}
