import { useState, type FormEvent, type ReactNode } from "react";
import { KeyRound, LogOut, Mail, ShieldAlert, Trash2, UserRound } from "lucide-react";
import { toast } from "sonner";
import { bffFetch } from "@/api/bff";
import { authErrorMessage, useAuth } from "@/auth/AuthProvider";
import { Button } from "@/components/ui/button";
import { Card, Input, Label } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { env } from "@/lib/utils";

const MIN_PASSWORD = 8;

function Section({ icon, title, children, testId }: { icon: ReactNode; title: string; children: ReactNode; testId: string }) {
  return (
    <Card className="p-5" data-testid={testId}>
      <h2 className="mb-3 flex items-center gap-2 text-base font-semibold [&_svg]:h-4 [&_svg]:w-4">{icon} {title}</h2>
      {children}
    </Card>
  );
}

/** Runs an account action with a busy flag; Firebase and BFF errors become an Italian toast. */
function useAction() {
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>, success?: string) => {
    setBusy(true);
    try {
      await fn();
      if (success) toast.success(success);
      return true;
    } catch (err) {
      toast.error(authErrorMessage(err), { duration: 8000 });
      return false;
    } finally {
      setBusy(false);
    }
  };
  return { busy, run };
}

function DisplayName() {
  const { me, refreshMe } = useAuth();
  const [name, setName] = useState(me?.user.display_name ?? "");
  const { busy, run } = useAction();
  const save = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      await bffFetch("/app/me", { method: "PATCH", body: { display_name: name.trim() } });
      await refreshMe();
    }, t("account.nameSaved"));
  };
  return (
    <form onSubmit={save} className="flex flex-wrap items-end gap-3" data-testid="account-name-form">
      <div className="min-w-[200px] flex-1 space-y-1.5">
        <Label htmlFor="acc-name">{t("account.displayName")}</Label>
        <Input id="acc-name" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} data-testid="account-name-input" />
      </div>
      <Button type="submit" variant="outline" disabled={busy || name.trim() === (me?.user.display_name ?? "")} data-testid="account-name-save">{t("common.save")}</Button>
    </form>
  );
}

function ChangePassword() {
  const { changePassword } = useAuth();
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const { busy, run } = useAction();
  const tooShort = form.next.length > 0 && form.next.length < MIN_PASSWORD;
  const mismatch = form.confirm.length > 0 && form.next !== form.confirm;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (await run(() => changePassword(form.current, form.next), t("account.passwordChanged"))) setForm({ current: "", next: "", confirm: "" });
  };
  return (
    <form onSubmit={submit} className="space-y-3" data-testid="account-password-form">
      <div className="space-y-1.5">
        <Label htmlFor="pw-current">{t("account.currentPassword")}</Label>
        <Input id="pw-current" type="password" autoComplete="current-password" required value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} data-testid="account-pw-current" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="pw-new">{t("account.newPassword")}</Label>
          <Input id="pw-new" type="password" autoComplete="new-password" required value={form.next} onChange={(e) => setForm({ ...form, next: e.target.value })} aria-invalid={tooShort} data-testid="account-pw-new" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="pw-confirm">{t("account.confirmPassword")}</Label>
          <Input id="pw-confirm" type="password" autoComplete="new-password" required value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} aria-invalid={mismatch} data-testid="account-pw-confirm" />
        </div>
      </div>
      {(tooShort || mismatch) && <p className="text-xs text-destructive">{tooShort ? t("account.passwordTooShort", { min: MIN_PASSWORD }) : t("account.passwordMismatch")}</p>}
      <Button type="submit" disabled={busy || !form.current || form.next.length < MIN_PASSWORD || form.next !== form.confirm} data-testid="account-pw-submit">{t("account.changePassword")}</Button>
    </form>
  );
}

function ChangeEmail() {
  const { me, changeEmail } = useAuth();
  const [form, setForm] = useState({ current: "", email: "" });
  const { busy, run } = useAction();
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const email = form.email.trim();
    if (await run(() => changeEmail(form.current, email), t("account.emailLinkSent", { email }))) setForm({ current: "", email: "" });
  };
  return (
    <form onSubmit={submit} className="space-y-3" data-testid="account-email-form">
      <p className="text-sm text-muted-foreground">{t("account.emailHint", { email: me?.user.email ?? "" })}</p>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="em-new">{t("account.newEmail")}</Label>
          <Input id="em-new" type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="account-email-new" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="em-current">{t("account.currentPassword")}</Label>
          <Input id="em-current" type="password" autoComplete="current-password" required value={form.current} onChange={(e) => setForm({ ...form, current: e.target.value })} data-testid="account-email-pw" />
        </div>
      </div>
      <Button type="submit" variant="outline" disabled={busy || !form.current || !/^\S+@\S+\.\S+$/.test(form.email)} data-testid="account-email-submit">{t("account.changeEmail")}</Button>
    </form>
  );
}

export function AccountSettings() {
  const { providers, logoutEverywhere, deleteAccount } = useAuth();
  const { busy, run } = useAction();
  const hasPassword = providers.includes("password");
  const devMode = env.authMode === "dev";

  const signOutAll = () => {
    if (window.confirm(t("account.logoutAllConfirm"))) void run(logoutEverywhere, t("account.logoutAllDone"));
  };
  const remove = () => {
    if (window.confirm(t("account.deleteConfirm"))) void run(deleteAccount, t("account.deleted"));
  };

  return (
    <>
      <Section icon={<UserRound />} title={t("account.title")} testId="account-card">
        <DisplayName />
      </Section>

      <Section icon={<KeyRound />} title={t("account.passwordTitle")} testId="account-password-card">
        {hasPassword ? (
          <div className="space-y-6">
            <ChangePassword />
            <div className="border-t pt-5">
              <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Mail className="h-4 w-4" /> {t("account.emailTitle")}</h3>
              <ChangeEmail />
            </div>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground" data-testid="account-managed-elsewhere">
            {devMode ? t("account.devMode") : t("account.googleManaged")}
          </p>
        )}
      </Section>

      <Section icon={<ShieldAlert />} title={t("account.securityTitle")} testId="account-security-card">
        <div className="space-y-4">
          <div>
            <p className="mb-2 text-sm text-muted-foreground">{t("account.logoutAllHint")}</p>
            <Button variant="outline" disabled={busy} onClick={signOutAll} data-testid="account-logout-all"><LogOut /> {t("account.logoutAll")}</Button>
          </div>
          <div className="border-t pt-4">
            <p className="mb-2 text-sm text-muted-foreground">{t("account.deleteHint")}</p>
            <Button variant="destructiveSolid" disabled={busy} onClick={remove} data-testid="account-delete"><Trash2 /> {t("account.delete")}</Button>
          </div>
        </div>
      </Section>
    </>
  );
}
