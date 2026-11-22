import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Link2, PlugZap, Plus, Power, PowerOff, Tag, Trash2, Waypoints } from "lucide-react";
import { toast } from "sonner";
import type { VerifyResult } from "@/api/admin";
import { platformApi, type PlatformApartment } from "@/api/platform";
import { APARTMENT_ID_RE, DemoBadge, defaultInstanceUrl, Field, isBuiltinMock, LastCheck, SimulatedField, useInstanceMode, useInstanceUrlHint, VerifyBadge } from "@/components/admin/apartmentForm";
import { useAuth } from "@/auth/AuthProvider";
import { CredentialsWorkspace } from "@/components/credentials/CredentialsWorkspace";
import { AgentTest, agentTestable } from "@/components/platform/AgentTest";
import { CancelCreationDialog, CreationRow, creationRowClass, ReadyInvite, showCreationError } from "@/components/platform/CreationRow";
import { DeleteDialog, DeletionRow, deletionRowClass, DisableDialog, DisabledInfo } from "@/components/platform/DeletionRow";
import { ItalianwayCodeDialog } from "@/components/platform/ItalianwayCodeDialog";
import { NewApartmentDialog, tenantKey } from "@/components/platform/NewApartmentDialog";
import { PlatformError } from "@/components/platform/PlatformError";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Badge, Dialog, DialogContent, DialogDescription, DialogTitle, Label, Skeleton, Switch } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";
import { creationSignature, isUsable, MAX_POLL_MS, POLL_MS, sortForPlatform } from "@/lib/apartmentCreation";
import { deletionOffer, deletionSignature } from "@/lib/apartmentDeletion";
import { pollWindow } from "@/lib/pollWindow";
import { instanceAddress } from "@/lib/instanceAddress";
import { cn, newCorrelationId } from "@/lib/utils";

const key = (tenantId: string) => ["platform", "apartments", tenantId];
/** A3, answer 1170: the platform manager opens the device credentials of a staging apartment (lab-…, test-…; never dev,
 *  never a client's) from here; the server answers the /app/platform/… routes only in dev and staging. */
const credentialsHere = (apartmentId: string) => /^(lab|test)-/.test(apartmentId);
const toPort = (v: string) => (v.trim() ? Number(v) : null);

/** New apartment: the platform chooses the id (unique on the whole platform) and the connection (D-64, D-66). */
function CreateDialog({ tenantId, tenantName, onClose, onCreated }: { tenantId: string; tenantName: string; onClose: () => void; onCreated: () => void }) {
  const { mock, real } = useInstanceMode();
  const urlHint = useInstanceUrlHint();
  const [f, setF] = useState({ apartment_id: "", name: "", instance_url: defaultInstanceUrl(mock), port: "", timezone: "Europe/Rome", enabled: true, italianway_id: "", simulated: false });
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    const body = { apartment_id: f.apartment_id.trim(), name: f.name.trim(), instance_url: f.instance_url.trim(), port: toPort(f.port), timezone: f.timezone.trim() || "Europe/Rome", enabled: f.enabled, italianway_id: f.italianway_id.trim() || null, simulated: isBuiltinMock(f.instance_url) || f.simulated };
    const res = await runAction((c) => platformApi.createApartment(tenantId, body, c), { success: t("platform.aptCreated", { id: body.apartment_id }) });
    setSaving(false);
    if (res) {
      // In production the instance key langbrain-api-key-<id> is created by HQE outside the app (R1); a demonstration
      // apartment (mock://, D-202: staging and development only, production refuses it) has no key to create.
      if (real && !isBuiltinMock(body.instance_url)) toast.info(t("platform.aptKeyFirst"), { duration: 15000 });
      onCreated();
      onClose();
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="platform-apt-create-dialog">
        <DialogTitle>{t("platform.aptAddTitle", { name: tenantName })}</DialogTitle>
        <DialogDescription>{t("platform.aptAddHint")}</DialogDescription>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field id="apartment_id" label={t("admin.apartments.id")} value={f.apartment_id} onChange={(v) => setF({ ...f, apartment_id: v })} placeholder={t("admin.apartments.idPlaceholder")} hint={t("admin.apartments.idHint")} />
          <Field id="name" label={t("admin.apartments.name")} value={f.name} onChange={(v) => setF({ ...f, name: v })} />
          <Field id="instance_url" label={t("admin.apartments.instanceUrl")} value={f.instance_url} onChange={(v) => setF({ ...f, instance_url: v })} placeholder={t("admin.apartments.instanceUrlPlaceholder")} hint={urlHint} />
          <Field id="port" label={t("admin.apartments.port")} value={f.port} onChange={(v) => setF({ ...f, port: v })} type="number" />
          <Field id="timezone" label={t("admin.apartments.timezone")} value={f.timezone} onChange={(v) => setF({ ...f, timezone: v })} hint={t("admin.apartments.timezoneInitial")} />
          <Field id="italianway_id" label={t("admin.apartments.italianway")} value={f.italianway_id} onChange={(v) => setF({ ...f, italianway_id: v })} hint={t("platform.italianwayHint")} />
          <SimulatedField url={f.instance_url} value={f.simulated} onChange={(v) => setF({ ...f, simulated: v })} />
          <div className="flex items-center justify-between rounded-xl bg-secondary/60 px-3 py-2">
            <Label htmlFor="papt-enabled">{t("admin.apartments.enabled")}</Label>
            <Switch id="papt-enabled" checked={f.enabled} onCheckedChange={(v) => setF({ ...f, enabled: v })} data-testid="apt-form-enabled" />
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={save} disabled={saving || !APARTMENT_ID_RE.test(f.apartment_id.trim()) || !f.name.trim() || !f.instance_url.trim()} data-testid="platform-apt-create-save">{t("common.save")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Connection only: name and enabled belong to the organization admin (D-64), so they are not in this form. */
function ConnectionDialog({ tenantId, apt, onClose, onSaved }: { tenantId: string; apt: PlatformApartment; onClose: () => void; onSaved: () => void }) {
  const urlHint = useInstanceUrlHint();
  const [url, setUrl] = useState(apt.instance_url);
  const [port, setPort] = useState(apt.port ? String(apt.port) : "");
  const [code, setCode] = useState(apt.italianway_id ?? "");
  // «Istanza simulata» (N4, D-100): sent only when touched. Untouched, the server's rule applies (mock:// = simulated;
  // leaving mock:// = back to real unless asked), and the box shows what that rule will give.
  const [touched, setTouched] = useState<boolean | null>(null);
  const savedSimulated = apt.simulated ?? isBuiltinMock(apt.instance_url);
  const ruleSimulated = isBuiltinMock(url) || (!isBuiltinMock(apt.instance_url) && savedSimulated);
  const simulated = touched ?? ruleSimulated;
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    // The code is sent only when it changes: the BFF frees and claims codes, no need to repeat an unchanged one.
    const codeChanged = code.trim() !== (apt.italianway_id ?? "");
    const body = { instance_url: url.trim(), port: toPort(port), ...(touched !== null && !isBuiltinMock(url) ? { simulated: touched } : {}), ...(codeChanged ? { italianway_id: code.trim() || null } : {}) };
    const res = await runAction((c) => platformApi.patchConnection(tenantId, apt.apartment_id, body, c), { success: t("platform.aptSaved") });
    setSaving(false);
    if (res) {
      onSaved();
      onClose();
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid={`platform-apt-connection-dialog-${apt.apartment_id}`}>
        <DialogTitle>{t("platform.aptEditTitle", { name: apt.name })}</DialogTitle>
        <DialogDescription>{t("platform.aptEditHint")}</DialogDescription>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field id="instance_url" label={t("admin.apartments.instanceUrl")} value={url} onChange={setUrl} placeholder={t("admin.apartments.instanceUrlPlaceholder")} hint={urlHint} />
          <Field id="port" label={t("admin.apartments.port")} value={port} onChange={setPort} type="number" />
          <Field id="italianway_id" label={t("admin.apartments.italianway")} value={code} onChange={setCode} hint={t("platform.italianwayHint")} />
          <SimulatedField url={url} value={simulated} onChange={setTouched} />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={save} disabled={saving || !url.trim()} data-testid="platform-apt-connection-save">{t("common.save")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Apartments of one organization, as the platform manages them (D-64, D-66): technical record only, creation with
 * the id, connection, verification and deletion. No link to the apartment's own pages: those belong to the
 * organization.
 */
export function PlatformApartments({ tenantId, tenantName, showStopped = 0 }: { tenantId: string; tenantName: string; showStopped?: number }) {
  const qc = useQueryClient();
  // A2 and A6: read again every 4 s while a creation, a cancellation or a deletion is on its way, for at most 20 minutes
  const pollOpen = useRef(pollWindow(MAX_POLL_MS));
  const q = useQuery({
    queryKey: key(tenantId),
    queryFn: () => platformApi.apartments(tenantId),
    refetchInterval: (query) => {
      const moving = [creationSignature(query.state.data), deletionSignature(query.state.data)].filter(Boolean).join("|");
      return pollOpen.current(moving, Date.now()) ? POLL_MS : false;
    },
  });
  const [disableOf, setDisableOf] = useState<PlatformApartment | null>(null);
  const [deleteOf, setDeleteOf] = useState<PlatformApartment | null>(null);
  const [cancelOf, setCancelOf] = useState<PlatformApartment | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [creatingNew, setCreatingNew] = useState(false);
  const [editing, setEditing] = useState<PlatformApartment | null>(null);
  // D-198: the Italianway code of an apartment created from the app
  const [codeOf, setCodeOf] = useState<PlatformApartment | null>(null);
  const [verify, setVerify] = useState<Record<string, VerifyResult | "loading">>({});
  const env = useAuth().me?.env;
  const notProd = env?.app_env !== "prod";
  // A2 §1: off before the click where the server says the creation is not there (absent = an older server: on, and its
  // 503 shows inside the form)
  const newOff = env?.creazione_disponibile === false;
  const [credentialsOf, setCredentialsOf] = useState<string | null>(null);
  const refresh = () => void qc.invalidateQueries({ queryKey: key(tenantId) });
  /** The organization's card counts the creations too (§4). */
  const refreshCounts = () => void qc.invalidateQueries({ queryKey: ["platform", "tenants"] });

  // A2: the notices at the end (§3.2, §3.4): ready after «In preparazione», gone after «Annullamento in corso»;
  // A6: gone after «Eliminazione in corso»
  const seen = useRef<Map<string, { stato: string | undefined; deleting: boolean; name: string }> | null>(null);
  useEffect(() => {
    if (!q.data) return;
    const now = new Map(q.data.map((a) => [a.apartment_id, { stato: a.creazione?.stato, deleting: a.eliminazione?.stato === "in_corso", name: a.name }]));
    const before = seen.current;
    if (before) {
      let changed = false;
      for (const [id, was] of before) {
        const is = now.get(id);
        if (was.stato === "in_preparazione" && is?.stato === "pronto") toast.success(t("platform.creation.ready", { name: is.name }));
        if (was.stato === "annullamento_in_corso" && !is) toast.success(t("platform.creation.cancelled", { name: was.name }));
        if (was.deleting && !is) toast.success(t("platform.deletion.deleted", { name: was.name }));
        if (was.stato !== is?.stato) changed = true;
      }
      if (changed) refreshCounts();
    }
    seen.current = now;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only a new list matters
  }, [q.data]);

  // «Vedi» on the organization's card (§4): the first stopped creation into view, with the focus on its row
  const shown = useRef(0);
  useEffect(() => {
    if (!showStopped || showStopped === shown.current || !q.data) return;
    shown.current = showStopped;
    const first = sortForPlatform(q.data).find((a) => a.creazione?.stato === "non_creato");
    const el = first && document.querySelector<HTMLElement>(`[data-testid="platform-apt-${CSS.escape(first.apartment_id)}"]`);
    if (!el) return;
    el.scrollIntoView({ block: "center", behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    el.focus({ preventScroll: true });
  }, [showStopped, q.data]);

  /** «Riprova» and «Annulla» (§3.2): never repeated by the site; every outcome ends with the list read again. */
  const creationAction = async (a: PlatformApartment, kind: "riprova" | "annulla") => {
    const c = a.creazione;
    if (!c) return;
    const correlationId = newCorrelationId();
    setBusyId(a.apartment_id);
    try {
      if (kind === "riprova") await platformApi.retryCreation(tenantId, a.apartment_id, c.version, correlationId);
      else {
        const res = await platformApi.cancelCreation(tenantId, a.apartment_id, c.version, correlationId);
        // nothing had reached the VM: closed at once, without «Annullamento in corso» (o1 cb3ee25)
        if (res?.creazione?.stato === "annullato") toast.success(t("platform.creation.cancelled", { name: a.name }));
      }
    } catch (err) {
      showCreationError(err, correlationId);
    } finally {
      setBusyId(null);
      refresh();
      refreshCounts();
    }
  };

  const check = async (id: string) => {
    setVerify((s) => ({ ...s, [id]: "loading" }));
    const res = await runAction((c) => platformApi.verifyApartment(tenantId, id, c));
    setVerify((s) => {
      const next = { ...s };
      if (res) next[id] = res;
      else delete next[id];
      return next;
    });
    refresh(); // the BFF stores the outcome as last_check
  };

  /** A6: «Disattiva» (after its window) and «Riattiva»; the list is read again whatever the outcome. */
  const setEnabled = async (a: PlatformApartment, on: boolean) => {
    setBusyId(a.apartment_id);
    await runAction((c) => (on ? platformApi.reenable(tenantId, a.apartment_id, c) : platformApi.disable(tenantId, a.apartment_id, c)), {
      success: t(on ? "platform.deletion.reenabled" : "platform.deletion.disabled", { name: a.name }),
    });
    setBusyId(null);
    refresh();
  };

  /** A6 «Riprova» of a stopped deletion, with its version; never repeated by the site. */
  const retryDeletion = async (a: PlatformApartment) => {
    const e = a.eliminazione;
    if (!e) return;
    const correlationId = newCorrelationId();
    setBusyId(a.apartment_id);
    try {
      await platformApi.retryDeletion(tenantId, a.apartment_id, e.version, correlationId);
    } catch (err) {
      showCreationError(err, correlationId);
    } finally {
      setBusyId(null);
      refresh();
    }
  };

  return (
    <div className="space-y-3" data-testid={`platform-apartments-${tenantId}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <h4 className="pt-1.5 text-sm font-bold">{t("platform.apartments")}</h4>
        <div className="flex flex-col items-end gap-1">
          <div className="flex flex-wrap justify-end gap-2">
            <Button size="sm" variant="outline" onClick={() => setCreating(true)} data-testid={`platform-apt-add-btn-${tenantId}`}><Link2 /> {t("platform.aptAdd")}</Button>
            <Button size="sm" onClick={() => setCreatingNew(true)} disabled={newOff} data-testid={`platform-apt-new-btn-${tenantId}`}><Plus /> {t("platform.creation.newButton")}</Button>
          </div>
          {newOff && (
            <p className="max-w-xs text-right text-xs text-muted-foreground" data-testid={`platform-apt-new-unavailable-${tenantId}`}>
              {t(notProd ? "platform.creation.notAvailable" : "platform.creation.notInProd")}
            </p>
          )}
        </div>
      </div>
      {q.error && <PlatformError error={q.error} onRetry={() => void q.refetch()} testId={`platform-apartments-error-${tenantId}`} />}
      {q.isLoading ? (
        <Skeleton className="h-20 rounded-2xl" />
      ) : q.data?.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid={`platform-apartments-empty-${tenantId}`}>{t("platform.aptEmpty")}</p>
      ) : (
        <ul className="divide-y rounded-2xl border">
          {sortForPlatform(q.data ?? []).map((a) => {
            const v = verify[a.apartment_id];
            if (a.eliminazione)
              return (
                <li key={a.apartment_id} className={cn("p-3", deletionRowClass(a.eliminazione))} data-testid={`platform-apt-${a.apartment_id}`} data-deletion={a.eliminazione.stato}>
                  <DeletionRow a={a} busy={busyId === a.apartment_id} onRetry={() => void retryDeletion(a)} />
                </li>
              );
            const offer = deletionOffer(a, Date.now());
            if (!isUsable(a))
              return (
                <li
                  key={a.apartment_id}
                  tabIndex={a.creazione?.stato === "non_creato" ? -1 : undefined}
                  className={cn("p-3 outline-none focus-visible:ring-2 focus-visible:ring-ring", creationRowClass(a.creazione))}
                  data-testid={`platform-apt-${a.apartment_id}`}
                  data-creation={a.creazione?.stato}
                >
                  <CreationRow a={a} busy={busyId === a.apartment_id} onRetry={() => void creationAction(a, "riprova")} onCancel={() => setCancelOf(a)} />
                </li>
              );
            return (
              <li key={a.apartment_id} className="space-y-2 p-3" data-testid={`platform-apt-${a.apartment_id}`} data-creation={a.creazione?.stato ?? "manuale"}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold [overflow-wrap:anywhere]">{a.name}</span>
                      {a.simulated && <DemoBadge testId={`platform-apt-demo-${a.apartment_id}`} />}
                      {!a.enabled && <Badge className="border-neutral-border bg-neutral-bg text-neutral-fg">{t("admin.apartments.disabled")}</Badge>}
                      <CopyableId id={a.apartment_id} full label={t("admin.apartments.id")} testId={`platform-apt-id-${a.apartment_id}`} />
                    </div>
                    <div className="tabular text-xs text-muted-foreground [overflow-wrap:anywhere]">{instanceAddress(a.instance_url, a.port)} · {a.timezone}{a.italianway_id ? ` · IW ${a.italianway_id}` : ""}</div>
                    <div className="text-xs">{t("admin.apartments.lastCheck")}: <LastCheck check={a.last_check} testId={`platform-apt-check-${a.apartment_id}`} /></div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {/* created from the app (o1 1f7d4b0): connection and deletion belong to its creation, and to A6 */}
                    {!a.creazione && <Button size="sm" variant="outline" onClick={() => setEditing(a)} data-testid={`platform-apt-edit-${a.apartment_id}`}><Waypoints /> {t("platform.aptEditConnection")}</Button>}
                    {/* D-198: created from the app, only its Italianway code can change after the creation */}
                    {a.creazione && <Button size="sm" variant="outline" onClick={() => setCodeOf(a)} data-testid={`platform-apt-italianway-${a.apartment_id}`}><Tag /> {t("platform.italianwayCode.button")}</Button>}
                    <Button size="sm" variant="outline" onClick={() => void check(a.apartment_id)} disabled={v === "loading"} data-testid={`platform-apt-verify-${a.apartment_id}`}>
                      <PlugZap /> {v === "loading" ? t("common.loading") : t("admin.apartments.verify")}
                    </Button>
                    {/* A6: Disattiva, then Elimina 7 days later (the server's eliminabile_dal); dev never */}
                    {offer.disable && (
                      <Button size="sm" variant="outline" onClick={() => setDisableOf(a)} disabled={busyId === a.apartment_id} data-testid={`platform-apt-disable-${a.apartment_id}`}>
                        <PowerOff /> {t("platform.deletion.disable")}
                      </Button>
                    )}
                    {offer.reenable && (
                      <Button size="sm" variant="outline" onClick={() => void setEnabled(a, true)} disabled={busyId === a.apartment_id} data-testid={`platform-apt-reenable-${a.apartment_id}`}>
                        <Power /> {t("platform.deletion.reenable")}
                      </Button>
                    )}
                    {offer.del !== "none" && (
                      <Button size="sm" variant="destructive" onClick={() => setDeleteOf(a)} disabled={offer.del !== "ready"} data-testid={`platform-apt-delete-${a.apartment_id}`}>
                        <Trash2 /> {t("platform.deletion.delete")}
                      </Button>
                    )}
                  </div>
                </div>
                {!a.enabled && <DisabledInfo a={a} offer={offer} />}
                {v && v !== "loading" && <VerifyBadge r={v} />}
                {/* strumento A, A1: the agent on the VM answers for the staging apartments and dev only */}
                {agentTestable(a.apartment_id) && (
                  <div className="flex flex-wrap items-center gap-2" data-testid={`platform-apt-agent-${a.apartment_id}`}>
                    <AgentTest apartmentId={a.apartment_id} />
                    {notProd && credentialsHere(a.apartment_id) && (
                      <Button
                        size="sm"
                        variant="outline"
                        aria-expanded={credentialsOf === a.apartment_id}
                        onClick={() => setCredentialsOf((v) => (v === a.apartment_id ? null : a.apartment_id))}
                        data-testid={`platform-apt-credentials-btn-${a.apartment_id}`}
                      >
                        <KeyRound /> {t("credentials.title")}
                      </Button>
                    )}
                  </div>
                )}
                {a.creazione?.stato === "pronto" && notProd && <ReadyInvite apartmentId={a.apartment_id} />}
                {credentialsOf === a.apartment_id && (
                  <div className="border-t pt-3">
                    <CredentialsWorkspace apartmentId={a.apartment_id} scope="platform" />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {disableOf && (
        <DisableDialog
          a={disableOf}
          onClose={() => setDisableOf(null)}
          onConfirm={() => {
            const a = disableOf;
            setDisableOf(null);
            void setEnabled(a, false);
          }}
        />
      )}
      {deleteOf && <DeleteDialog a={deleteOf} tenantId={tenantId} tenantName={tenantName} onClose={() => setDeleteOf(null)} onDone={refresh} />}
      {cancelOf && (
        <CancelCreationDialog
          a={cancelOf}
          onClose={() => setCancelOf(null)}
          onConfirm={() => {
            const a = cancelOf;
            setCancelOf(null);
            void creationAction(a, "annulla");
          }}
        />
      )}
      {creatingNew && (
        <NewApartmentDialog
          tenantId={tenantId}
          tenantName={tenantName}
          onClose={() => setCreatingNew(false)}
          onCreated={() => {
            refresh();
            void qc.invalidateQueries({ queryKey: tenantKey(tenantId) });
            void qc.invalidateQueries({ queryKey: ["platform", "tenants"] });
          }}
        />
      )}
      {creating && <CreateDialog tenantId={tenantId} tenantName={tenantName} onClose={() => setCreating(false)} onCreated={refresh} />}
      {editing && <ConnectionDialog key={editing.apartment_id} tenantId={tenantId} apt={editing} onClose={() => setEditing(null)} onSaved={refresh} />}
      {codeOf && <ItalianwayCodeDialog key={codeOf.apartment_id} tenantId={tenantId} apt={codeOf} onClose={() => setCodeOf(null)} onSaved={refresh} />}
    </div>
  );
}
