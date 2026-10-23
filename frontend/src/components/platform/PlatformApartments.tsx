import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PlugZap, Plus, Trash2, Waypoints } from "lucide-react";
import { toast } from "sonner";
import type { VerifyResult } from "@/api/admin";
import { platformApi, type PlatformApartment } from "@/api/platform";
import { APARTMENT_ID_RE, DemoBadge, defaultInstanceUrl, Field, isBuiltinMock, LastCheck, SimulatedField, useInstanceMode, VerifyBadge } from "@/components/admin/apartmentForm";
import { PlatformError } from "@/components/platform/PlatformError";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Badge, Dialog, DialogContent, DialogDescription, DialogTitle, Label, Skeleton, Switch } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";

const key = (tenantId: string) => ["platform", "apartments", tenantId];
const toPort = (v: string) => (v.trim() ? Number(v) : null);

/** New apartment: the platform chooses the id (unique on the whole platform) and the connection (D-64, D-66). */
function CreateDialog({ tenantId, tenantName, onClose, onCreated }: { tenantId: string; tenantName: string; onClose: () => void; onCreated: () => void }) {
  const { mock, real } = useInstanceMode();
  const [f, setF] = useState({ apartment_id: "", name: "", instance_url: defaultInstanceUrl(mock), port: "", timezone: "Europe/Rome", enabled: true, italianway_id: "", simulated: false });
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    const body = { apartment_id: f.apartment_id.trim(), name: f.name.trim(), instance_url: f.instance_url.trim(), port: toPort(f.port), timezone: f.timezone.trim() || "Europe/Rome", enabled: f.enabled, italianway_id: f.italianway_id.trim() || null, simulated: isBuiltinMock(f.instance_url) || f.simulated };
    const res = await runAction((c) => platformApi.createApartment(tenantId, body, c), { success: t("platform.aptCreated", { id: body.apartment_id }) });
    setSaving(false);
    if (res) {
      // In production the instance key langbrain-api-key-<id> is created by HQE outside the app (R1); a demonstration
      // apartment (mock://, D-188: also in production) has no key to create.
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
          <Field id="instance_url" label={t("admin.apartments.instanceUrl")} value={f.instance_url} onChange={(v) => setF({ ...f, instance_url: v })} placeholder={t("admin.apartments.instanceUrlPlaceholder")} hint={t(mock ? "admin.apartments.instanceUrlHintMock" : "admin.apartments.instanceUrlHint")} />
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
  const { mock } = useInstanceMode();
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
          <Field id="instance_url" label={t("admin.apartments.instanceUrl")} value={url} onChange={setUrl} placeholder={t("admin.apartments.instanceUrlPlaceholder")} hint={t(mock ? "admin.apartments.instanceUrlHintMock" : "admin.apartments.instanceUrlHint")} />
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
export function PlatformApartments({ tenantId, tenantName }: { tenantId: string; tenantName: string }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: key(tenantId), queryFn: () => platformApi.apartments(tenantId) });
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<PlatformApartment | null>(null);
  const [verify, setVerify] = useState<Record<string, VerifyResult | "loading">>({});
  const refresh = () => void qc.invalidateQueries({ queryKey: key(tenantId) });

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

  const remove = async (a: PlatformApartment) => {
    if (!window.confirm(t("platform.aptDeleteConfirm", { id: a.apartment_id, name: a.name, tenant: tenantName }))) return;
    const ok = await runAction(async (c) => {
      await platformApi.deleteApartment(tenantId, a.apartment_id, c);
      return true;
    }, { success: t("platform.aptDeleted", { id: a.apartment_id }) });
    if (ok) refresh();
  };

  return (
    <div className="space-y-3" data-testid={`platform-apartments-${tenantId}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-sm font-bold">{t("platform.apartments")}</h4>
        <Button size="sm" onClick={() => setCreating(true)} data-testid={`platform-apt-add-btn-${tenantId}`}><Plus /> {t("platform.aptAdd")}</Button>
      </div>
      {q.error && <PlatformError error={q.error} onRetry={() => void q.refetch()} testId={`platform-apartments-error-${tenantId}`} />}
      {q.isLoading ? (
        <Skeleton className="h-20 rounded-2xl" />
      ) : q.data?.length === 0 ? (
        <p className="text-sm text-muted-foreground" data-testid={`platform-apartments-empty-${tenantId}`}>{t("platform.aptEmpty")}</p>
      ) : (
        <ul className="divide-y rounded-2xl border">
          {q.data?.map((a) => {
            const v = verify[a.apartment_id];
            return (
              <li key={a.apartment_id} className="space-y-2 p-3" data-testid={`platform-apt-${a.apartment_id}`}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold [overflow-wrap:anywhere]">{a.name}</span>
                      {a.simulated && <DemoBadge testId={`platform-apt-demo-${a.apartment_id}`} />}
                      {!a.enabled && <Badge className="border-neutral-border bg-neutral-bg text-neutral-fg">{t("admin.apartments.disabled")}</Badge>}
                      <CopyableId id={a.apartment_id} testId={`platform-apt-id-${a.apartment_id}`} />
                    </div>
                    <div className="tabular text-xs text-muted-foreground [overflow-wrap:anywhere]">{a.instance_url}{a.port ? `:${a.port}` : ""} · {a.timezone}{a.italianway_id ? ` · IW ${a.italianway_id}` : ""}</div>
                    <div className="text-xs">{t("admin.apartments.lastCheck")}: <LastCheck check={a.last_check} testId={`platform-apt-check-${a.apartment_id}`} /></div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" onClick={() => setEditing(a)} data-testid={`platform-apt-edit-${a.apartment_id}`}><Waypoints /> {t("platform.aptEditConnection")}</Button>
                    <Button size="sm" variant="outline" onClick={() => void check(a.apartment_id)} disabled={v === "loading"} data-testid={`platform-apt-verify-${a.apartment_id}`}>
                      <PlugZap /> {v === "loading" ? t("common.loading") : t("admin.apartments.verify")}
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => void remove(a)} data-testid={`platform-apt-delete-${a.apartment_id}`}><Trash2 /> {t("platform.aptDelete")}</Button>
                  </div>
                </div>
                {v && v !== "loading" && <VerifyBadge r={v} />}
              </li>
            );
          })}
        </ul>
      )}
      {creating && <CreateDialog tenantId={tenantId} tenantName={tenantName} onClose={() => setCreating(false)} onCreated={refresh} />}
      {editing && <ConnectionDialog key={editing.apartment_id} tenantId={tenantId} apt={editing} onClose={() => setEditing(null)} onSaved={refresh} />}
    </div>
  );
}
