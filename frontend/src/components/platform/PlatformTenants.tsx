import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, LifeBuoy, LogIn, Mail, Pause, Pencil, Play, Plus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import type { EmailStatus } from "@/api/admin";
import { platformApi, type PlatformTenant } from "@/api/platform";
import { useAuth } from "@/auth/AuthProvider";
import { PlatformApartments } from "@/components/platform/PlatformApartments";
import { PlatformError } from "@/components/platform/PlatformError";
import { Button } from "@/components/ui/button";
import { Badge, Card, Dialog, DialogContent, DialogDescription, DialogTitle, Input, Label, NativeSelect, Skeleton } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";
import { fmtDateTime } from "@/lib/format";

const KEY = ["platform", "tenants"];
const isEmail = (s: string) => /^\S+@\S+\.\S+$/.test(s.trim());

/** Outcome of an invitation email, as in Amministrazione > Utenti: sent, failed (use "Reinvia invito"), not configured. */
function notifyCreated(name: string, email: string, status: EmailStatus | undefined) {
  if (status === "failed") toast.warning(t("platform.createdEmailFailed", { name, email }), { duration: 10000 });
  else if (status === "not_configured") toast.warning(t("platform.createdEmailOff", { name, email }), { duration: 10000 });
  else toast.success(t("platform.created", { name, email }));
}

function notifyResent(email: string, status: EmailStatus | undefined) {
  if (status === "failed") toast.warning(t("platform.resendFailed", { email }), { duration: 10000 });
  else if (status === "not_configured") toast.warning(t("platform.resendOff", { email }), { duration: 10000 });
  else toast.success(t("platform.resent", { email }));
}

function CreateDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [f, setF] = useState({ name: "", admin_email: "", admin_display_name: "" });
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    const body = { name: f.name.trim(), admin_email: f.admin_email.trim(), ...(f.admin_display_name.trim() ? { admin_display_name: f.admin_display_name.trim() } : {}) };
    const res = await runAction((c) => platformApi.createTenant(body, c));
    setSaving(false);
    if (res) {
      notifyCreated(res.name, body.admin_email, res.email_status);
      onCreated();
      onClose();
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="tenant-create-dialog">
        <DialogTitle>{t("platform.addTitle")}</DialogTitle>
        <DialogDescription>{t("platform.addHint")}</DialogDescription>
        <div className="mt-4 space-y-3">
          <div className="space-y-1">
            <Label htmlFor="tn-name">{t("platform.name")}</Label>
            <Input id="tn-name" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} data-testid="tenant-form-name" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tn-email">{t("platform.adminEmail")}</Label>
            <Input id="tn-email" type="email" value={f.admin_email} onChange={(e) => setF({ ...f, admin_email: e.target.value })} placeholder={t("admin.users.emailPlaceholder")} data-testid="tenant-form-email" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tn-admin-name">{t("platform.adminName")}</Label>
            <Input id="tn-admin-name" value={f.admin_display_name} onChange={(e) => setF({ ...f, admin_display_name: e.target.value })} data-testid="tenant-form-admin-name" />
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} data-testid="tenant-create-cancel">{t("common.cancel")}</Button>
          <Button onClick={save} disabled={saving || !f.name.trim() || !isEmail(f.admin_email)} data-testid="tenant-create-save">{t("platform.create")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RenameDialog({ tenant, onClose, onSaved }: { tenant: PlatformTenant; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(tenant.name);
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    const res = await runAction((c) => platformApi.renameTenant(tenant.tenant_id, name.trim(), c), { success: t("platform.renamed") });
    setSaving(false);
    if (res) {
      onSaved();
      onClose();
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid={`tenant-rename-dialog-${tenant.tenant_id}`}>
        <DialogTitle>{t("platform.renameTitle")}</DialogTitle>
        <div className="mt-4 space-y-1">
          <Label htmlFor="tn-rename">{t("platform.name")}</Label>
          <Input id="tn-rename" value={name} onChange={(e) => setName(e.target.value)} data-testid="tenant-rename-input" />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={save} disabled={saving || !name.trim() || name.trim() === tenant.name} data-testid="tenant-rename-save">{t("common.save")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

const REASON_MAX = 500;

/** Suspension (P-50, D-85): the reason is required and stays in the activity log; bookings keep reaching the engine. */
function SuspendDialog({ tenant, onClose, onDone }: { tenant: PlatformTenant; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    const res = await runAction((c) => platformApi.suspendTenant(tenant.tenant_id, reason.trim(), c), { success: t("platform.suspendedDone", { name: tenant.name }) });
    setSaving(false);
    if (res) {
      onDone();
      onClose();
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid={`tenant-suspend-dialog-${tenant.tenant_id}`}>
        <DialogTitle>{t("platform.suspendTitle", { name: tenant.name })}</DialogTitle>
        <DialogDescription>{t("platform.suspendHint")}</DialogDescription>
        <div className="mt-4 space-y-1">
          <Label htmlFor="tn-suspend-reason">{t("platform.suspendReason")}</Label>
          <Input id="tn-suspend-reason" value={reason} maxLength={REASON_MAX} onChange={(e) => setReason(e.target.value)} data-testid="tenant-suspend-reason" />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button variant="destructive" onClick={save} disabled={saving || !reason.trim()} data-testid="tenant-suspend-confirm">{t("platform.suspendConfirm")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

const HOURS = Array.from({ length: 24 }, (_, i) => i + 1);

/** Assistance access (P-50, D-86): 1-24 hours with an operator's permissions; the admin sees it and can close it. */
function SupportDialog({ tenant, onClose, onDone }: { tenant: PlatformTenant; onClose: () => void; onDone: () => void }) {
  const [hours, setHours] = useState(2);
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);
  const save = async () => {
    setSaving(true);
    const res = await runAction((c) => platformApi.openSupport(tenant.tenant_id, { hours, reason: reason.trim() }, c));
    setSaving(false);
    if (res) {
      toast.success(t("support.opened", { name: tenant.name, until: fmtDateTime(res.expires_at) }));
      onDone();
      onClose();
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid={`tenant-support-dialog-${tenant.tenant_id}`}>
        <DialogTitle>{t("support.openTitle", { name: tenant.name })}</DialogTitle>
        <DialogDescription>{t("support.openHint")}</DialogDescription>
        <div className="mt-4 space-y-3">
          <div className="space-y-1">
            <Label htmlFor="tn-support-hours">{t("support.hours")}</Label>
            <NativeSelect id="tn-support-hours" value={String(hours)} onChange={(e) => setHours(Number(e.target.value))} data-testid="tenant-support-hours">
              {HOURS.map((h) => <option key={h} value={h}>{h === 1 ? t("support.hoursOne") : t("support.hoursMany", { count: h })}</option>)}
            </NativeSelect>
          </div>
          <div className="space-y-1">
            <Label htmlFor="tn-support-reason">{t("support.reasonLabel")}</Label>
            <Input id="tn-support-reason" value={reason} maxLength={REASON_MAX} onChange={(e) => setReason(e.target.value)} data-testid="tenant-support-reason" />
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={save} disabled={saving || !reason.trim()} data-testid="tenant-support-confirm">{t("support.openConfirm")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function AdminState({ tenant }: { tenant: PlatformTenant }) {
  const a = tenant.first_admin;
  if (!a) return <span className="text-muted-foreground" data-testid={`tenant-admin-${tenant.tenant_id}`}>{t("platform.noAdmin")}</span>;
  return (
    <span className="inline-flex flex-wrap items-center gap-2" data-testid={`tenant-admin-${tenant.tenant_id}`}>
      <span className="font-semibold text-foreground">{a.email}</span>
      <Badge className={a.pending ? "border-warning-border bg-warning-bg text-warning-fg" : "border-positive-border bg-positive-bg text-positive-fg"}>
        {a.pending ? t("platform.pending") : t("platform.active")}
      </Badge>
    </span>
  );
}

/** openTenant: organization whose apartments are shown at once (link from the Appartamenti page, D-77). */
export function PlatformTenants({ openTenant = null }: { openTenant?: string | null }) {
  const qc = useQueryClient();
  const { me, refreshMe, enterSupport, leaveSupport } = useAuth();
  const navigate = useNavigate();
  const [supporting, setSupporting] = useState<PlatformTenant | null>(null);
  const q = useQuery({ queryKey: KEY, queryFn: platformApi.tenants });
  const [suspending, setSuspending] = useState<PlatformTenant | null>(null);
  const [creating, setCreating] = useState(false);
  const [renaming, setRenaming] = useState<PlatformTenant | null>(null);
  const [resending, setResending] = useState<string | null>(null);
  const [openApts, setOpenApts] = useState<string | null>(openTenant);
  const refresh = () => void qc.invalidateQueries({ queryKey: KEY });
  /** After suspending or reactivating: the list, and the manager's own profile when it is their organization. */
  const changed = (tn: PlatformTenant) => {
    refresh();
    if (tn.tenant_id === me?.tenant?.tenant_id) void refreshMe();
  };

  const enter = async (tn: PlatformTenant) => {
    const a = tn.support_access;
    if (!a?.mine) return;
    await enterSupport({ tenant_id: tn.tenant_id, tenant_name: tn.name, access_id: a.access_id, expires_at: a.expires_at });
    navigate("/");
  };

  const closeSupport = async (tn: PlatformTenant) => {
    const a = tn.support_access;
    if (!a?.mine) return;
    const ok = await runAction(async (c) => {
      await platformApi.closeSupport(tn.tenant_id, a.access_id, c);
      return true;
    }, { success: t("support.closed") });
    if (!ok) return;
    refresh();
    if (me?.support?.access_id === a.access_id) await leaveSupport(); // the access this tab is working in (D-89)
  };

  const reactivate = async (tn: PlatformTenant) => {
    if (!window.confirm(t("platform.reactivateConfirm", { name: tn.name }))) return;
    const res = await runAction((c) => platformApi.reactivateTenant(tn.tenant_id, c), { success: t("platform.reactivated", { name: tn.name }) });
    if (res) changed(tn);
  };

  const resend = async (tn: PlatformTenant) => {
    setResending(tn.tenant_id);
    const res = await runAction((c) => platformApi.resendInvite(tn.tenant_id, c));
    setResending(null);
    if (res) notifyResent(res.first_admin?.email ?? tn.first_admin?.email ?? "", res.email_status);
    refresh(); // also after a 409 already_active: the list shows the administrator as active
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setCreating(true)} data-testid="tenant-add-btn"><Plus /> {t("platform.add")}</Button>
      </div>
      {q.error && <PlatformError error={q.error} onRetry={() => void q.refetch()} testId="tenants-error" />}
      {q.isLoading ? (
        <Skeleton className="h-40 rounded-2xl" />
      ) : q.data?.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted-foreground" data-testid="tenants-empty">{t("platform.empty")}</Card>
      ) : (
        q.data?.map((tn) => (
          <Card key={tn.tenant_id} className="space-y-3 p-5" data-testid={`tenant-${tn.tenant_id}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-semibold" data-testid={`tenant-name-${tn.tenant_id}`}>{tn.name}</h3>
                  {tn.suspended && <Badge className="border-negative-border bg-negative-bg text-negative-fg" data-testid={`tenant-suspended-${tn.tenant_id}`}>{t("platform.suspendedBadge")}</Badge>}
                </div>
                <p className="text-xs text-muted-foreground">{t("platform.createdAt", { when: fmtDateTime(tn.created_at) })}</p>
                {tn.support_access && (
                  <p className="text-xs font-medium text-warning-fg" data-testid={`tenant-support-info-${tn.tenant_id}`}>
                    {tn.support_access.mine
                      ? t("support.openUntil", { until: fmtDateTime(tn.support_access.expires_at) })
                      : t("support.openBy", { name: tn.support_access.operator_name || tn.support_access.operator_email || t("common.removedUser"), until: fmtDateTime(tn.support_access.expires_at) })}
                  </p>
                )}
                {tn.suspended && (
                  <p className="text-xs text-destructive" data-testid={`tenant-suspended-info-${tn.tenant_id}`}>
                    {t("platform.suspendedInfo", { when: fmtDateTime(tn.suspended_at), reason: tn.suspended_reason ?? "—" })}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant={openApts === tn.tenant_id ? "default" : "outline"} size="sm" aria-expanded={openApts === tn.tenant_id} onClick={() => setOpenApts((v) => (v === tn.tenant_id ? null : tn.tenant_id))} data-testid={`tenant-apartments-btn-${tn.tenant_id}`}>
                  <Building2 /> {t("platform.apartments")}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setRenaming(tn)} data-testid={`tenant-rename-btn-${tn.tenant_id}`}><Pencil /> {t("platform.rename")}</Button>
                {tn.support_access?.mine && !tn.suspended ? (
                  <>
                    <Button size="sm" onClick={() => void enter(tn)} data-testid={`tenant-support-enter-${tn.tenant_id}`}><LogIn /> {t("support.enter")}</Button>
                    <Button variant="outline" size="sm" onClick={() => void closeSupport(tn)} data-testid={`tenant-support-close-${tn.tenant_id}`}>{t("support.close")}</Button>
                  </>
                ) : (
                  !tn.suspended && <Button variant="outline" size="sm" onClick={() => setSupporting(tn)} data-testid={`tenant-support-btn-${tn.tenant_id}`}><LifeBuoy /> {t("support.open")}</Button>
                )}
                {tn.suspended ? (
                  <Button variant="outline" size="sm" onClick={() => void reactivate(tn)} data-testid={`tenant-reactivate-btn-${tn.tenant_id}`}><Play /> {t("platform.reactivate")}</Button>
                ) : (
                  <Button variant="outline" size="sm" className="text-destructive" onClick={() => setSuspending(tn)} data-testid={`tenant-suspend-btn-${tn.tenant_id}`}><Pause /> {t("platform.suspend")}</Button>
                )}
                {tn.first_admin?.pending && (
                  <Button variant="outline" size="sm" disabled={resending === tn.tenant_id} onClick={() => void resend(tn)} data-testid={`tenant-resend-btn-${tn.tenant_id}`}>
                    <Mail /> {t("platform.resend")}
                  </Button>
                )}
              </div>
            </div>
            <div className="border-t pt-3 text-sm text-muted-foreground">
              {t("platform.firstAdmin")}: <AdminState tenant={tn} />
            </div>
            {openApts === tn.tenant_id && (
              <div className="border-t pt-3">
                <PlatformApartments tenantId={tn.tenant_id} tenantName={tn.name} />
              </div>
            )}
          </Card>
        ))
      )}
      {creating && <CreateDialog onClose={() => setCreating(false)} onCreated={refresh} />}
      {supporting && <SupportDialog key={supporting.tenant_id} tenant={supporting} onClose={() => setSupporting(null)} onDone={refresh} />}
      {suspending && <SuspendDialog key={suspending.tenant_id} tenant={suspending} onClose={() => setSuspending(null)} onDone={() => changed(suspending)} />}
      {renaming && <RenameDialog key={renaming.tenant_id} tenant={renaming} onClose={() => setRenaming(null)} onSaved={refresh} />}
    </div>
  );
}
