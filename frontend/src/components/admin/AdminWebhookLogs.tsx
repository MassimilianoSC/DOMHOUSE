import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, ChevronUp, ShieldCheck, ShieldX, XCircle } from "lucide-react";
import { adminApi, type AdminApartment, type WebhookLog } from "@/api/admin";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { eventOf, outcomeOf, summary24h, type Outcome, type ReadEvent } from "@/lib/bookingLog";
import { fmtDate, fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const OK = "border-positive-border bg-positive-bg text-positive-fg";
const KO = "border-negative-border bg-negative-bg text-negative-fg";
const WARN = "border-warning-border bg-warning-bg text-warning-fg";
const OK_TEXT = "text-positive-fg";

/**
 * Apartment name of a call: the one the BFF matched (apartment_id), otherwise the one carrying the Italianway code of
 * the body. apartments: undefined while loading; null where there is no list (platform area): there the code is shown.
 */
function apartmentLabel(log: WebhookLog, ev: ReadEvent, apartments: AdminApartment[] | null | undefined): string {
  if (apartments === undefined) return "…";
  if (apartments === null) return ev.externalId ? t("admin.bookingsReceived.externalCode", { code: ev.externalId }) : t("admin.bookingsReceived.unknownApartment");
  const match = apartments.find((a) => a.apartment_id === log.apartment_id) ?? (ev.externalId ? apartments.find((a) => a.italianway_id === ev.externalId) : undefined);
  return match?.name ?? t("admin.bookingsReceived.unknownApartment");
}

/** "Prenotazione creata · Milano Centro · dal 1 dic 2026 al 3 dic 2026"; a body in an unknown format says so. */
function sentence(log: WebhookLog, apartments: AdminApartment[] | null | undefined): string {
  const ev = eventOf(log);
  if (!ev) return t("admin.bookingsReceived.unreadable");
  const checkin = fmtDate(ev.checkin);
  const checkout = fmtDate(ev.checkout);
  const dates = checkin && checkout ? t("admin.bookingsReceived.dates", { checkin, checkout }) : "";
  return [t(`admin.bookingsReceived.events.${ev.type}`), apartmentLabel(log, ev, apartments), dates].filter(Boolean).join(" · ");
}

/** "Ultime 24 ore: 2 ricevute, 1 trasmessa, 1 con problemi": singular for 1 («con problemi» never changes). */
function summaryText(s: { received: number; sent: number; problems: number }): string {
  const received = s.received === 1 ? t("admin.bookingsReceived.receivedOne") : t("admin.bookingsReceived.received", { count: s.received });
  const sent = s.sent === 1 ? t("admin.bookingsReceived.sentOne") : t("admin.bookingsReceived.sent", { count: s.sent });
  return t("admin.bookingsReceived.summary", { received, sent, problems: s.problems });
}

function outcomeText(o: Outcome): string {
  if (o.kind === "engine" && o.retries === 1) return t("admin.bookingsReceived.outcomes.engineRetriedOnce");
  if (o.kind === "engine" && o.retries > 1) return t("admin.bookingsReceived.outcomes.engineRetried", { count: o.retries });
  return t(`admin.bookingsReceived.outcomes.${o.kind}`);
}

function Row({ log, apartments }: { log: WebhookLog; apartments: AdminApartment[] | null | undefined }) {
  const [open, setOpen] = useState(false);
  const o = outcomeOf(log);
  const httpOk = log.status_code === 200;
  return (
    <li className="py-3" data-testid={`webhook-log-${log.log_id}`} data-outcome={log.outcome} data-ok={o.ok}>
      <div className="flex items-start gap-3">
        <span className={cn("mt-0.5 [&_svg]:size-5", o.ok ? OK_TEXT : "text-destructive")} aria-hidden>{o.ok ? <CheckCircle2 /> : <XCircle />}</span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold" data-testid={`webhook-log-sentence-${log.log_id}`}>{sentence(log, apartments)}</p>
          <p className={cn("text-sm", o.ok ? OK_TEXT : "text-destructive")} data-testid={`webhook-log-result-${log.log_id}`}>{outcomeText(o)}</p>
          <p className="text-xs tabular text-muted-foreground">{fmtDateTime(log.received_at)}</p>
        </div>
        <Button variant="ghost" size="sm" className="h-7 shrink-0 px-2" onClick={() => setOpen((v) => !v)} aria-expanded={open} data-testid={`webhook-log-toggle-${log.log_id}`}>
          {open ? <ChevronUp /> : <ChevronDown />} {t("admin.bookingsReceived.details")}
        </Button>
      </div>
      {open && (
        <div className="mt-2 space-y-2 pl-8" data-testid={`webhook-log-details-${log.log_id}`}>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <Badge className={log.signature_ok ? OK : KO} data-testid={`webhook-log-signature-${log.log_id}`}>
              {log.signature_ok ? <ShieldCheck className="h-3 w-3" /> : <ShieldX className="h-3 w-3" />} {log.signature_ok ? t("admin.bookingsReceived.hmacOk") : t("admin.bookingsReceived.hmacKo")}
            </Badge>
            <Badge className={httpOk ? OK : log.outcome === "duplicate" ? WARN : KO} data-testid={`webhook-log-outcome-${log.log_id}`}>
              {t("admin.bookingsReceived.response")}: {log.status_code} · {log.outcome}
            </Badge>
            {log.apartment_id && <span className="font-mono">{log.apartment_id}</span>}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span>{t("admin.bookingsReceived.eventId")}: <span className="font-mono text-foreground" data-testid={`webhook-log-event-${log.log_id}`}>{log.event_id ?? "—"}</span></span>
            {log.booking_id && <span>{t("admin.bookingsReceived.booking")}: <span className="font-mono text-foreground">{log.booking_id}</span></span>}
            {log.external_id && <span>{t("admin.bookingsReceived.externalId")}: <span className="font-mono text-foreground" data-testid={`webhook-log-external-${log.log_id}`}>{log.external_id}</span></span>}
            {log.guests != null && <span>{t("admin.bookingsReceived.guests")}: <span className="font-mono text-foreground" data-testid={`webhook-log-guests-${log.log_id}`}>{log.guests}</span></span>}
            <span className="inline-flex items-center gap-1">{t("common.correlationId")}: <CopyableId id={log.correlation_id} testId={`webhook-log-correlation-${log.log_id}`} /></span>
            <span data-testid={`webhook-log-forward-${log.log_id}`}>
              {t("admin.bookingsReceived.forward")}: <span className={cn("font-semibold", log.forward_status === null ? "" : log.forward_status < 400 ? OK_TEXT : "text-destructive")}>
                {log.forward_status === null ? t("admin.bookingsReceived.notForwarded") : `${log.forward_status} · ${t("admin.bookingsReceived.attempts", { count: log.forward_attempts })}`}
              </span>
            </span>
          </div>
          <div className="text-xs font-semibold text-muted-foreground">{t("admin.bookingsReceived.rawBody")}</div>
          <pre className="max-h-64 overflow-auto rounded-xl bg-secondary/70 p-3 font-mono text-[11px] leading-relaxed" data-testid={`webhook-log-body-${log.log_id}`}>{log.raw_body || "∅"}</pre>
        </div>
      )}
    </li>
  );
}

/**
 * «Prenotazioni ricevute» (D-79): the webhook calls of the admin's organization, each read as a sentence with its
 * outcome. The platform area passes the unattributed ones and no apartment list (P-36): there the Italianway code shows.
 */
export function AdminWebhookLogs({ load = adminApi.webhookLogs, queryKey = ["admin", "webhook-logs"], hint, apartmentNames = true }: { load?: () => Promise<WebhookLog[]>; queryKey?: string[]; hint?: string; apartmentNames?: boolean } = {}) {
  const q = useQuery({ queryKey, queryFn: load, refetchInterval: 30_000 });
  const apts = useQuery({ queryKey: ["admin", "apartments"], queryFn: adminApi.apartments, enabled: apartmentNames });
  // Names unknown until the list arrives; a list that cannot be read leaves every apartment "non riconosciuto".
  const apartments = !apartmentNames ? null : apts.data ?? (apts.isLoading ? undefined : []);
  const s = q.data ? summary24h(q.data) : null;
  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground" data-testid="admin-webhooks-hint">{hint ?? t("admin.bookingsReceived.hint")}</p>
      {s && <p className="text-sm font-semibold" data-testid="admin-webhooks-summary">{summaryText(s)}</p>}
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="admin-webhooks-error" />}
      {q.isLoading ? <Skeleton className="h-48 rounded-2xl" /> : q.data?.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted-foreground" data-testid="admin-webhooks-empty">{t("admin.bookingsReceived.empty")}</Card>
      ) : (
        <Card className="px-5">
          <ul className="divide-y" data-testid="admin-webhooks-list">{q.data?.map((l) => <Row key={l.log_id} log={l} apartments={apartments} />)}</ul>
        </Card>
      )}
    </div>
  );
}
