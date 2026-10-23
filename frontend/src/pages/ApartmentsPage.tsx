import { Link } from "react-router-dom";
import { Bell, CalendarArrowDown, CalendarArrowUp, Plus, WifiOff, Zap } from "lucide-react";
import type { ApartmentSummary } from "@/api/types";
import { useAuth, useRole } from "@/auth/AuthProvider";
import { DemoBadge } from "@/components/admin/apartmentForm";
import { OccupancyBadge } from "@/components/apartment/ApartmentControls";
import { Button } from "@/components/ui/button";
import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { useApartments } from "@/hooks/useFeatures";
import { t } from "@/i18n";
import { capitalizeFirst, fmtNumber, fmtShortDateTime } from "@/lib/format";
import { platformApartmentsUrl } from "@/lib/routes";
import { cn } from "@/lib/utils";

function Stat({ icon, label, value, testId }: { icon: React.ReactNode; label: string; value: React.ReactNode; testId: string }) {
  return (
    <div className="flex items-center gap-2.5" data-testid={testId}>
      <span className="text-muted-foreground [&_svg]:size-4">{icon}</span>
      <div className="min-w-0">
        <div className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">{label}</div>
        <div className="text-sm font-semibold tabular [overflow-wrap:anywhere]">{value}</div>
      </div>
    </div>
  );
}

function ApartmentCard({ a, index }: { a: ApartmentSummary; index: number }) {
  const apt = a.apartment;
  const offline = !a.online;
  return (
    <Link
      to={`/a/${a.apartment_id}`}
      aria-label={t("apartments.open", { name: a.name })}
      data-testid={`apartment-card-${a.apartment_id}`}
      className="group block rounded-3xl focus-ring"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <Card className={cn("h-full p-5 transition-[box-shadow,transform] duration-150 group-hover:-translate-y-0.5 group-hover:shadow-md animate-fade-up", offline && "bg-muted/60 grayscale")}>
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
          <div className="min-w-0">
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              <h2 className="text-lg font-extrabold [overflow-wrap:anywhere]">{a.name}</h2>
              {a.simulated && <DemoBadge testId={`apartment-demo-${a.apartment_id}`} />}
            </div>
            <p className="truncate text-xs text-muted-foreground">{a.address}</p>
          </div>
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
        {apt && (
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <OccupancyBadge occupancy={apt.occupancy} testId={`apartment-occupancy-${a.apartment_id}`} />
            <Badge className="border-primary/30 bg-primary/10 text-primary" data-testid={`apartment-mode-${a.apartment_id}`}>
              {capitalizeFirst(t(`mode.${apt.mode}`))}
            </Badge>
            {(a.pending_approvals ?? 0) > 0 && (
              <Badge className="animate-pulse border-primary bg-primary text-primary-foreground" data-testid={`apartment-approvals-${a.apartment_id}`}>
                <Bell className="h-3 w-3" /> {a.pending_approvals}
              </Badge>
            )}
          </div>
        )}
        <div className="mt-5 grid grid-cols-2 gap-4 border-t pt-4">
          <Stat icon={<CalendarArrowDown />} label={t("apartments.nextCheckin")} value={fmtShortDateTime(apt?.next_checkin, a.timezone)} testId={`apartment-checkin-${a.apartment_id}`} />
          <Stat icon={<CalendarArrowUp />} label={t("apartments.nextCheckout")} value={fmtShortDateTime(apt?.next_checkout, a.timezone)} testId={`apartment-checkout-${a.apartment_id}`} />
          <Stat icon={<Zap />} label={t("apartments.kwhToday")} value={a.kwh_today !== null ? `${fmtNumber(a.kwh_today, 1)} kWh` : "—"} testId={`apartment-kwh-${a.apartment_id}`} />
          <Stat icon={<Bell />} label={t("apartments.pendingApprovals")} value={a.pending_approvals ?? "—"} testId={`apartment-pending-${a.apartment_id}`} />
        </div>
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
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl" data-testid="apartments-title">{t("apartments.title")}</h1>
          {data && <p className="mt-1 text-sm text-muted-foreground">{t("apartments.subtitle", { count: data.length })}</p>}
        </div>
        {platformHere && tenantId ? (
          <Button asChild data-testid="add-apartment-btn">
            <Link to={platformApartmentsUrl(tenantId)}>
              <Plus /> {t("apartments.add")}
            </Link>
          </Button>
        ) : (
          isAdmin && Boolean(data?.length) && <p className="max-w-xs text-sm text-muted-foreground" data-testid="add-apartment-note">{t("apartments.emptyHint")}</p>
        )}
      </header>
      {isLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1].map((i) => <Skeleton key={i} className="h-60 rounded-3xl" />)}
        </div>
      )}
      {data && data.length === 0 && (
        <Card className="p-10 text-center" data-testid="apartments-empty">
          <p className="font-bold">{restricted ? t("apartments.emptyAssigned") : t("apartments.empty")}</p>
          <p className="mt-1 text-sm text-muted-foreground" data-testid="apartments-empty-hint">{emptyHint}</p>
        </Card>
      )}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data?.map((a, i) => <ApartmentCard key={a.apartment_id} a={a} index={i} />)}
      </div>
    </div>
  );
}
