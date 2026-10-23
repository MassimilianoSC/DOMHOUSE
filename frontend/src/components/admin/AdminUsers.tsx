import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Mail, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { adminApi, type AdminApartment, type AdminUser, type ApartmentScope, type InviteResult, type Role } from "@/api/admin";
import { useAuth } from "@/auth/AuthProvider";
import { ApartmentScopePicker, isNoneScope, scopeSummary } from "@/components/admin/ApartmentScope";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { Button } from "@/components/ui/button";
import { Badge, Card, Dialog, DialogContent, DialogDescription, DialogTitle, Input, Label, NativeSelect } from "@/components/ui/primitives";
import { RowMenu, RowMenuItem } from "@/components/ui/RowMenu";
import { RowsSkeleton } from "@/components/ui/Skeletons";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";

const ROLES: Role[] = ["admin", "operator", "viewer"];

function notifyEmail(res: InviteResult) {
  const email = res.email;
  if (res.email_status === "sent") toast.success(t("admin.users.emailSent", { email }));
  else if (res.email_status === "failed") toast.warning(t("admin.users.emailFailed", { email }), { duration: 10000 });
  else if (res.email_status === "not_configured") toast.warning(t("admin.users.emailOff", { email }), { duration: 10000 });
  else toast.success(t("admin.users.invited", { email }));
}

/** "None" hides every apartment from the user: allowed (it suspends an access) but only after a confirmation. */
const confirmScope = (scope: ApartmentScope, email: string) => !isNoneScope(scope) || window.confirm(t("admin.users.scopeNoneConfirm", { email }));

function ScopeDialog({ user, apartments, onClose, onSaved }: { user: AdminUser; apartments: AdminApartment[]; onClose: () => void; onSaved: () => void }) {
  const [scope, setScope] = useState<ApartmentScope>(user.apartment_ids);
  const [saving, setSaving] = useState(false);
  const save = async () => {
    if (!confirmScope(scope, user.email)) return;
    setSaving(true);
    const res = await runAction((c) => adminApi.patchUser(user.uid, { apartment_ids: scope }, c), { success: t("admin.users.scopeSaved") });
    setSaving(false);
    if (res) {
      onSaved();
      onClose();
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid={`scope-dialog-${user.uid}`}>
        <DialogTitle>{t("admin.users.scopeDialogTitle", { email: user.email })}</DialogTitle>
        <DialogDescription>{t("admin.users.scopeDialogHint")}</DialogDescription>
        <div className="mt-4">
          <ApartmentScopePicker value={scope} onChange={setScope} apartments={apartments} testId={`scope-edit-${user.uid}`} />
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} data-testid="scope-dialog-cancel">{t("common.cancel")}</Button>
          <Button onClick={save} disabled={saving} data-testid="scope-dialog-save">{t("common.save")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function AdminUsers() {
  const { me } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "users"], queryFn: adminApi.users });
  const apts = useQuery({ queryKey: ["admin", "apartments"], queryFn: adminApi.apartments });
  const apartments = apts.data ?? [];
  const [form, setForm] = useState({ email: "", display_name: "", role: "operator" as Role, apartment_ids: "all" as ApartmentScope });
  const [scopeUser, setScopeUser] = useState<AdminUser | null>(null);
  const [busy, setBusy] = useState(false);
  const [resending, setResending] = useState<string | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "users"] });

  const invite = async () => {
    // Admins always see every apartment: no list is sent for them (the BFF would answer 422 admin_all_apartments).
    const { apartment_ids, ...rest } = form;
    if (form.role !== "admin" && !confirmScope(apartment_ids, form.email)) return;
    setBusy(true);
    const res = await runAction((c) => adminApi.invite(form.role === "admin" ? rest : form, c));
    setBusy(false);
    if (res) {
      notifyEmail(res);
      setForm({ email: "", display_name: "", role: "operator", apartment_ids: "all" });
      void refresh();
    }
  };

  const resend = async (u: AdminUser) => {
    setResending(u.uid);
    const res = await runAction((c) => adminApi.resendInvite(u.uid, c));
    setResending(null);
    if (res) notifyEmail(res);
  };

  const changeRole = async (u: AdminUser, role: Role) => {
    const res = await runAction((c) => adminApi.patchUser(u.uid, { role }, c), { success: t("admin.users.roleChanged") });
    if (res) void refresh();
  };

  const remove = async (u: AdminUser) => {
    if (!window.confirm(t("admin.users.deleteConfirm", { email: u.email }))) return;
    const ok = await runAction(async (c) => {
      await adminApi.deleteUser(u.uid, c);
      return true;
    }, { success: t("admin.users.deleted") });
    if (ok) void refresh();
  };

  return (
    <div className="space-y-6">
      <Card className="space-y-4 p-5" data-testid="admin-invite-card">
        <h2 className="flex items-center gap-2 text-base font-semibold"><UserPlus className="h-4 w-4" /> {t("admin.users.invite")}</h2>
        <p className="text-sm text-muted-foreground">{t("admin.users.inviteHint")}</p>
        <div className="grid gap-3 sm:grid-cols-[2fr_2fr_1fr_auto] sm:items-end">
          <div className="space-y-1">
            <Label htmlFor="inv-email">{t("common.email")}</Label>
            <Input id="inv-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder={t("admin.users.emailPlaceholder")} data-testid="admin-invite-email" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="inv-name">{t("admin.users.name")}</Label>
            <Input id="inv-name" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} data-testid="admin-invite-name" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="inv-role">{t("settings.role")}</Label>
            <NativeSelect id="inv-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })} data-testid="admin-invite-role">
              {ROLES.map((r) => <option key={r} value={r}>{t(`roles.${r}`)}</option>)}
            </NativeSelect>
          </div>
          <Button onClick={invite} disabled={busy || !/^\S+@\S+\.\S+$/.test(form.email)} data-testid="admin-invite-btn">{t("admin.users.inviteBtn")}</Button>
        </div>
        {form.role !== "admin" && (
          <ApartmentScopePicker value={form.apartment_ids} onChange={(apartment_ids) => setForm({ ...form, apartment_ids })} apartments={apartments} testId="admin-invite-scope" />
        )}
      </Card>
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="admin-users-error" />}
      {q.isLoading ? <RowsSkeleton rows={4} /> : (
        <Card className="divide-y px-4 sm:px-5" data-testid="admin-users-list">
          {q.data?.map((u) => {
            const self = u.uid === me?.user.uid;
            const scope = u.role !== "admin" ? scopeSummary(u.apartment_ids, apartments) : null;
            return (
              // two lines (design lot 2): email and state, then name, devices and apartments in grey; role and «⋯» at the end
              <div key={u.uid} className="flex flex-wrap items-start gap-x-3 gap-y-2 py-3" data-testid={`admin-user-${u.uid}`}>
                <div className="min-w-0 flex-1 basis-56">
                  <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
                    <span className="[overflow-wrap:anywhere]" data-testid={`admin-user-email-${u.uid}`}>{u.email}</span>
                    {u.pending && <Badge className="border-warning-border bg-warning-bg text-warning-fg" data-testid={`admin-user-pending-${u.uid}`}>{t("admin.users.pending")}</Badge>}
                    {self && <Badge>{t("admin.users.you")}</Badge>}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {u.display_name || "—"} · {t("admin.users.devices", { count: u.push_tokens })}
                    {scope && (
                      <>
                        {" · "}
                        <span title={scope.names.join(", ") || undefined} data-testid={`admin-user-scope-${u.uid}`}>{scope.text}</span>
                      </>
                    )}
                  </div>
                </div>
                <div className="ml-auto flex items-center gap-1">
                  <NativeSelect value={u.role} disabled={self} aria-label={t("settings.role")} onChange={(e) => changeRole(u, e.target.value as Role)} className="h-9 w-auto" data-testid={`admin-user-role-${u.uid}`}>
                    {ROLES.map((r) => <option key={r} value={r}>{t(`roles.${r}`)}</option>)}
                  </NativeSelect>
                  {!self ? (
                    <RowMenu label={t("admin.users.menu", { email: u.email })} testId={`admin-user-menu-${u.uid}`}>
                      {u.role !== "admin" && (
                        <RowMenuItem onSelect={() => setScopeUser(u)} testId={`admin-user-scope-btn-${u.uid}`}>
                          <Building2 /> {t("admin.users.scopeEdit")}
                        </RowMenuItem>
                      )}
                      {u.pending && (
                        <RowMenuItem disabled={resending === u.uid} onSelect={() => void resend(u)} testId={`admin-user-resend-${u.uid}`}>
                          <Mail /> {t("admin.users.resend")}
                        </RowMenuItem>
                      )}
                      <RowMenuItem danger onSelect={() => void remove(u)} testId={`admin-user-delete-${u.uid}`}>
                        <Trash2 /> {t("common.delete")}
                      </RowMenuItem>
                    </RowMenu>
                  ) : (
                    <span className="w-9 shrink-0" aria-hidden />
                  )}
                </div>
              </div>
            );
          })}
        </Card>
      )}
      {scopeUser && <ScopeDialog key={scopeUser.uid} user={scopeUser} apartments={apartments} onClose={() => setScopeUser(null)} onSaved={() => void refresh()} />}
    </div>
  );
}
