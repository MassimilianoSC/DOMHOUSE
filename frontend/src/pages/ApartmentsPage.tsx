import { Link } from "react-router-dom";
import { ArrowRight, CalendarDays, House, Plus, Thermometer, Wifi, WifiOff, Zap } from "lucide-react";
import { memo, useEffect, useRef, useState } from "react";
import type { ApartmentSummary, Occupancy } from "@/api/types";
import { useAuth, useRole } from "@/auth/AuthProvider";
import { DemoBadge } from "@/components/admin/apartmentForm";
import { Button } from "@/components/ui/button";
import { Badge, Card } from "@/components/ui/primitives";
import { useApartments } from "@/hooks/useFeatures";
import { t } from "@/i18n";
import { capitalizeFirst, fmtNumber, fmtShortDateTime } from "@/lib/format";
import { platformApartmentsUrl } from "@/lib/routes";
import { MODE_BG, MODE_FG } from "@/lib/modeColours";
import { HOME_IMAGES, HOME_IMAGE_ROTATION_MS } from "@/content/homeImages.it";
import { getDailyHomeQuote } from "@/content/homeQuotes.it";
import { energySummary } from "@/lib/energySummary";
import { cn } from "@/lib/utils";

function StateTile({ label, value, icon, muted, bg, fg, testId }: { label: string; value: string; icon: React.ReactNode; muted: boolean; bg: string; fg: string; testId: string }) {
  return (
    <div className={cn("min-w-0 rounded-xl border p-3", muted ? "border-border bg-background" : cn("border-transparent", bg, fg))} data-testid={testId}>
      {/* icon and label side by side when they fit, the label under the icon when not: words are never split */}
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className={cn("flex size-7 shrink-0 items-center justify-center rounded-lg max-[360px]:size-6", muted ? "bg-muted text-muted-foreground" : "bg-background/70")} aria-hidden="true">{icon}</span>
        <span className={cn("min-w-0 text-xs font-medium leading-4", muted ? "text-muted-foreground" : fg)}>{label}</span>
      </div>
      <div className={cn("mt-2 text-sm font-bold [overflow-wrap:anywhere]", muted ? "text-muted-foreground" : fg)}>{value}</div>
    </div>
  );
}

function DetailMetric({ label, value, icon, muted, wide, testId }: { label: string; value: string; icon: React.ReactNode; muted: boolean; wide?: boolean; testId: string }) {
  return (
    <div className={cn("flex min-h-[68px] min-w-0 flex-col justify-between gap-2 bg-background/70 px-3 py-2.5", wide && "col-span-2 border-t border-border/80")} data-testid={testId}>
      <div className={cn("flex min-w-0 flex-wrap items-start gap-x-2 gap-y-1 text-xs font-medium", muted ? "text-muted-foreground/70" : "text-muted-foreground")}>
        {icon}
        <span className="min-w-0 text-xs leading-4">{label}</span>
      </div>
      <div className={cn("text-sm font-semibold leading-snug tabular [overflow-wrap:anywhere]", muted && "text-muted-foreground")}>{value}</div>
    </div>
  );
}
/** Occupancy uses the same semantic colours as the apartment overview. */
const OCCUPANCY_BG: Record<Occupancy, string> = { occupied: "bg-positive-bg", reserved: "bg-warning-bg", vacant: "bg-neutral-bg" };
const OCCUPANCY_FG: Record<Occupancy, string> = { occupied: "text-positive-fg", reserved: "text-warning-fg", vacant: "text-neutral-fg" };

function useRotatingHomeImage() {
  const [imageIndex, setImageIndex] = useState(() => Math.floor(Date.now() / HOME_IMAGE_ROTATION_MS) % HOME_IMAGES.length);
  const indexRef = useRef(imageIndex);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const nextIndex = (indexRef.current + 1) % HOME_IMAGES.length;
      const nextImage = new window.Image();
      nextImage.onload = () => {
        indexRef.current = nextIndex;
        setImageIndex(nextIndex);
      };
      nextImage.src = HOME_IMAGES[nextIndex].src;
    }, HOME_IMAGE_ROTATION_MS);

    return () => window.clearInterval(timer);
  }, []);

  return HOME_IMAGES[imageIndex] ?? HOME_IMAGES[0];
}

function LoadingApartments() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2" role="status" aria-label={t("common.loading")}>
      {[0, 1].map((item) => (
        <div
          key={item}
          className="min-h-[270px] animate-pulse space-y-4 rounded-2xl border bg-card p-5 motion-reduce:animate-none"
        >
          <div className="flex items-center justify-between gap-4">
            <div className="h-5 w-2/5 rounded bg-muted" />
            <div className="h-6 w-20 rounded-full bg-muted" />
          </div>
          <div className="h-3 w-3/5 rounded bg-muted" />
          <div className="grid grid-cols-2 gap-1 overflow-hidden rounded-xl border bg-border">
            {[0, 1, 2, 3, 4].map((cell) => <div key={cell} className={cn("h-16 bg-card", cell === 4 && "col-span-2")} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

const ApartmentCard = memo(function ApartmentCard({ a }: { a: ApartmentSummary }) {
  const apt = a.apartment;
  const offline = !a.online;
  const pending = a.pending_approvals;
  const mode = apt ? capitalizeFirst(t(`mode.${apt.mode}`)) : "\u2014";
  const occupancy = apt ? t(`occupancy.${apt.occupancy}`) : "\u2014";

  return (
    <Link to={"/a/" + a.apartment_id} aria-label={t("apartments.open", { name: a.name })} data-testid={"apartment-card-" + a.apartment_id} className="group block h-full rounded-2xl focus-ring">
      <Card className="flex h-full flex-col gap-3 rounded-2xl border-border/80 bg-card p-4 transition-[transform,background-color,border-color,box-shadow] duration-200 group-hover:-translate-y-0.5 group-hover:border-primary/50 group-hover:bg-card/95 group-hover:shadow-lg group-hover:shadow-primary/5 group-focus-visible:border-primary/60 group-active:scale-[.99] group-active:bg-secondary/45 motion-reduce:transition-none sm:p-4">
        <div className="min-w-0">
          <div className="flex min-w-0 items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <h2 className="text-base font-bold tracking-tight [overflow-wrap:anywhere]">{a.name}</h2>
                {a.simulated && <DemoBadge testId={"apartment-demo-" + a.apartment_id} />}
              </div>
              <p className="mt-1 text-xs leading-relaxed text-muted-foreground [overflow-wrap:anywhere]">{a.address}</p>
            </div>
            <ArrowRight className="mt-1 size-4 shrink-0 text-muted-foreground transition-[color,transform] duration-200 group-hover:translate-x-1 group-hover:text-primary" aria-hidden="true" />
          </div>
          <div className="mt-3 flex min-h-8 flex-wrap items-center gap-2">
            {offline ? (
              <Badge data-testid={"apartment-offline-" + a.apartment_id} className="border-neutral-border bg-neutral-bg text-neutral-fg">
                <WifiOff className="size-3" aria-hidden="true" /> {a.enabled ? t("apartments.unreachable") : t("apartments.disabled")}
              </Badge>
            ) : (
              <Badge className="border-positive-border bg-positive-bg text-positive-fg" data-testid={"apartment-online-" + a.apartment_id}>
                <Wifi className="size-3" aria-hidden="true" /> {t("apartments.online")}
              </Badge>
            )}
          </div>
        </div>

        <div className="min-w-0">
          <div className="grid grid-cols-2 gap-2">
            <StateTile label={t("mode.label")} value={mode} icon={<Thermometer className="size-4" />} muted={offline || !apt} bg={apt ? MODE_BG[apt.mode] : "bg-card"} fg={apt ? MODE_FG[apt.mode] : "text-muted-foreground"} testId={"apartment-mode-" + a.apartment_id} />
            <StateTile label={t("overview.band.occupancy")} value={occupancy} icon={<House className="size-4" />} muted={offline || !apt} bg={apt ? OCCUPANCY_BG[apt.occupancy] : "bg-card"} fg={apt ? OCCUPANCY_FG[apt.occupancy] : "text-muted-foreground"} testId={"apartment-occupancy-" + a.apartment_id} />
          </div>
          <div className="mt-2 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border/80 bg-border/80">
            <DetailMetric label={t("apartments.kwhToday")} value={a.kwh_today !== null ? fmtNumber(a.kwh_today, 1) + " kWh" : "\u2014"} icon={<Zap className="size-4 shrink-0" aria-hidden="true" />} muted={offline || a.kwh_today === null} testId={"apartment-kwh-" + a.apartment_id} />
            <DetailMetric label={t("apartments.nextCheckin")} value={fmtShortDateTime(apt?.next_checkin, a.timezone)} icon={<CalendarDays className="size-4 shrink-0" aria-hidden="true" />} muted={offline || !apt?.next_checkin} testId={"apartment-checkin-" + a.apartment_id} />
            <DetailMetric label={t("apartments.nextCheckout")} value={fmtShortDateTime(apt?.next_checkout, a.timezone)} icon={<CalendarDays className="size-4 shrink-0" aria-hidden="true" />} muted={offline || !apt?.next_checkout} wide testId={"apartment-checkout-" + a.apartment_id} />
          </div>
          {pending !== null && pending > 0 && (
              <div className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-warning-border bg-warning-bg px-3 py-2.5 text-sm font-semibold text-warning-fg" data-testid={"apartment-approvals-" + a.apartment_id}>
                {pending === 1 ? t("apartments.pendingOne") : t("apartments.pendingMany", { count: pending })}
                <ArrowRight className="size-4 shrink-0" aria-hidden="true" />
              </div>
            )}
        </div>
      </Card>
    </Link>
  );
});

export default function ApartmentsPage() {
  const { data, isLoading, isError } = useApartments();
  const { isAdmin, isPlatform } = useRole();
  const { me } = useAuth();
  const homeImage = useRotatingHomeImage();
  const homeQuote = getDailyHomeQuote();
  // An operator or viewer limited to some apartments (P-18) is told to ask for one, not that an admin can add one.
  const restricted = !isAdmin && (me?.user.apartment_ids ?? "all") !== "all";
  // Apartments are created only by the platform manager, from Organizzazioni (D-77): a manager goes there, an admin
  // asks the HQE support, anyone else asks an admin.
  const tenantId = me?.tenant?.tenant_id;
  const platformHere = isPlatform && Boolean(tenantId);
  const emptyHint = restricted ? t("apartments.emptyAssignedHint") : platformHere ? t("apartments.emptyHintPlatform") : isAdmin ? t("apartments.emptyHint") : t("apartments.emptyHintMember");
  // demonstration apartments stay out of the total next to real ones, or the total is said to be simulated (1187)
  const energy = energySummary(data ?? []);
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <header
        data-testid="apartments-header"
        className="apartments-hero-layout relative isolate w-full"
        style={{ "--hero-image-ratio": `${homeImage.width} / ${homeImage.height}` } as React.CSSProperties}
      >
        <div
          className="apartments-hero-photo relative isolate min-w-0 w-full overflow-hidden rounded-[1.5rem] border border-border/70"
        >
          <img
            src={homeImage.src}
            alt=""
            width={homeImage.width}
            height={homeImage.height}
            {...({ fetchpriority: "high" } as React.ImgHTMLAttributes<HTMLImageElement>)}
            decoding="async"
            className="apartments-hero-image absolute inset-0 z-0 h-full w-full object-cover object-center"
          />
          <div className="apartments-hero-haze pointer-events-none absolute inset-0 z-[1]" aria-hidden="true" />
          <div className="apartments-hero-copy">
            <div className="apartments-hero-copy-content">
              <h1 className="text-[clamp(1.25rem,1.9vw,1.625rem)] font-bold leading-tight tracking-tight text-white drop-shadow-[0_1px_3px_rgba(0,0,0,0.42)] [overflow-wrap:anywhere]" data-testid="apartments-title">{t("apartments.title")}</h1>
              {data && <p className="mt-1 text-xs text-white/90 drop-shadow-[0_1px_2px_rgba(0,0,0,0.45)] sm:text-sm">{t("apartments.subtitle", { count: data.length })}</p>}
              <p className="mt-2.5 max-w-xl border-l-2 border-accent/80 pl-2.5 text-xs leading-[1.4] text-white drop-shadow-[0_1px_2px_rgba(0,0,0,0.55)] sm:mt-4 sm:pl-3 sm:text-sm">
                <span className="mb-1 block text-xs font-bold uppercase tracking-[0.08em] text-white/85">{t("apartments.dailyQuote")}</span>
                <span className="italic">{"\u201C"}{homeQuote}{"\u201D"}</span>
              </p>
            </div>
          </div>
        </div>
        {platformHere && tenantId ? (
          <Button asChild variant="outline" className="apartments-hero-action relative z-10 border-white/55 bg-primary text-primary-foreground hover:border-white/75 hover:bg-primary/90 hover:text-primary-foreground" data-testid="add-apartment-btn">
            <Link to={platformApartmentsUrl(tenantId)}>
              <Plus /> {t("apartments.add")}
            </Link>
          </Button>
        ) : (
          isAdmin && (isLoading || isError || Boolean(data?.length)) && (
            <div className="apartments-hero-energy grid min-w-0 grid-cols-1 items-center gap-1 rounded-xl border border-white/20 text-white shadow-md shadow-black/10 sm:gap-0 sm:rounded-2xl" style={{ backgroundColor: "hsl(var(--hero-overlay) / 0.9)" }} data-testid="home-energy-summary" role="group" aria-label={t("apartments.energyToday")}>
              {isLoading && !data ? (
                <div className="grid grid-cols-1 gap-1.5" role="status" aria-label={t("common.loading")}>
                  <div className="h-3.5 w-36 max-w-full animate-pulse rounded bg-white/20 motion-reduce:animate-none" />
                  <div className="h-6 w-20 max-w-full animate-pulse rounded bg-white/20 motion-reduce:animate-none" />
                  <div className="h-2.5 w-40 max-w-full animate-pulse rounded bg-white/15 motion-reduce:animate-none" />
                </div>
              ) : (
                <>
                  <div className="flex min-w-0 items-center gap-1.5 text-xs font-semibold leading-tight sm:gap-2"><span className="flex size-[22px] shrink-0 items-center justify-center rounded-lg bg-accent/15 text-accent sm:size-[26px] sm:rounded-lg"><Zap className="size-3.5 sm:size-4" aria-hidden="true" /></span><span className="min-w-0 leading-snug">{t("apartments.energyToday")}</span></div>
                  {isError && !data ? (
                    <p className="m-0 text-xs leading-tight text-white/80 sm:mt-1">{t("apartments.energyUnavailable")}</p>
                  ) : data && data.length > 0 ? (
                    <>
                      <p className="m-0 flex min-w-0 items-baseline gap-1 sm:mt-1.5 sm:gap-1.5">
                        <span className="text-[1.3rem] font-bold tracking-tight tabular sm:text-2xl">{energy.total !== null ? fmtNumber(energy.total, 1) : "\u2014"}</span>
                        <span className="text-xs font-medium text-white/80">{t("energy.kwh")}</span>
                      </p>
                      <p className="m-0 min-w-0 text-xs leading-snug text-white/80 sm:mt-0.5">{energy.total !== null ? t("apartments.energyCoverage", { count: energy.withData, total: energy.counted }) : t("apartments.energyNoData")}</p>
                      {(energy.demosExcluded > 0 || energy.demoOnly) && (
                        <p className="m-0 min-w-0 text-xs leading-snug text-white/80" data-testid="home-energy-demos">
                          {energy.demoOnly ? t("apartments.energyDemoOnly") : energy.demosExcluded === 1 ? t("apartments.energyDemoExcludedOne") : t("apartments.energyDemoExcludedMany", { count: energy.demosExcluded })}
                        </p>
                      )}
                    </>
                  ) : null}
                </>
              )}
            </div>
          )
        )}
      </header>
      {isAdmin && !platformHere && Boolean(data?.length) && (
        <p className="max-w-xs text-sm text-muted-foreground" data-testid="add-apartment-note">{t("apartments.emptyHint")}</p>
      )}
      {isLoading && <LoadingApartments />}
      {data && data.length === 0 && (
        <Card className="rounded-2xl p-8 text-center sm:p-10" data-testid="apartments-empty">
          <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-secondary text-secondary-foreground"><Wifi className="size-6" aria-hidden="true" /></div>
          <p className="mt-4 font-bold">{restricted ? t("apartments.emptyAssigned") : t("apartments.empty")}</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground" data-testid="apartments-empty-hint">{emptyHint}</p>
        </Card>
      )}
      <div className="grid grid-cols-1 items-stretch gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {data?.map((a) => <ApartmentCard key={a.apartment_id} a={a} />)}
      </div>
    </div>
  );
}
