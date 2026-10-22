import { CheckCircle2, Download, LogOut, Smartphone } from "lucide-react";
import { useAuth } from "@/auth/AuthProvider";
import { isIos, useInstallPrompt } from "@/hooks/useInstallPrompt";
import { Button } from "@/components/ui/button";
import { Card, NativeSelect } from "@/components/ui/primitives";
import { scopeSummary } from "@/components/admin/ApartmentScope";
import { AccountSettings } from "@/components/settings/AccountSettings";
import { useApartments } from "@/hooks/useFeatures";
import { NotificationSettings } from "@/components/settings/NotificationSettings";
import { t } from "@/i18n";

function Row({ label, value, testId }: { label: string; value: React.ReactNode; testId: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b py-3 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-right text-sm font-semibold" data-testid={testId}>{value}</span>
    </div>
  );
}

function InstallCard() {
  const { canInstall, installed, install } = useInstallPrompt();
  let body: React.ReactNode;
  if (installed) {
    body = <p className="flex items-center gap-2 text-sm text-muted-foreground" data-testid="settings-installed"><CheckCircle2 className="h-4 w-4 text-emerald-600" /> {t("settings.installed")}</p>;
  } else if (canInstall) {
    body = (
      <>
        <p className="mb-3 text-sm text-muted-foreground">{t("settings.installHint")}</p>
        <Button onClick={() => void install()} data-testid="settings-install-btn"><Download /> {t("settings.installBtn")}</Button>
      </>
    );
  } else if (isIos()) {
    body = <p className="text-sm text-muted-foreground">{t("settings.installIos")}</p>;
  } else {
    body = (
      <>
        <p className="text-sm text-muted-foreground">{t("settings.installAndroid")}</p>
        <p className="mt-2 text-sm text-muted-foreground">{t("settings.installIos")}</p>
      </>
    );
  }
  return (
    <Card className="p-5" data-testid="settings-install-card">
      <h2 className="mb-3 flex items-center gap-2 text-base font-bold md:text-lg"><Smartphone className="h-4 w-4" /> {t("settings.install")}</h2>
      {body}
    </Card>
  );
}

export default function SettingsPage() {
  const { me, logout } = useAuth();
  // Without an organization (a platform manager only) the organization routes answer 403 (P-36): no apartments to
  // count and no notifications, which come per apartment, so neither call is made.
  const withTenant = Boolean(me?.tenant);
  const apartments = useApartments(withTenant);
  if (!me) return null;
  // Admins always see every apartment; others see "all" or their list (P-18), named from the list the BFF gives them.
  const scope = me.role === "admin" ? "all" : (me.user.apartment_ids ?? "all");
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">{t("settings.title")}</h1>
      <Card className="p-5">
        <h2 className="mb-2 text-base font-bold md:text-lg">{t("settings.profile")}</h2>
        <Row label={t("common.email")} value={me.user.email} testId="settings-email" />
        <Row label={t("settings.role")} value={me.role ? t(`roles.${me.role}`) : "—"} testId="settings-role" />
        {me.user.platform_manager && <Row label={t("settings.platform")} value={t("roles.platform")} testId="settings-platform" />}
        <Row label={t("settings.tenant")} value={me.tenant?.name ?? "—"} testId="settings-tenant" />
        {me.tenant && <Row label={t("settings.apartments")} value={scopeSummary(scope, apartments.data ?? []).text} testId="settings-apartments" />}
        <Row label={t("settings.env")} value={<span className="font-mono text-xs">{me.env.app_env} · auth {me.env.auth_mode} · {me.env.instance_mode}</span>} testId="settings-env" />
      </Card>
      <AccountSettings />
      {withTenant && <NotificationSettings />}
      <InstallCard />
      <Card className="p-5">
        <label htmlFor="lang" className="mb-2 block text-base font-bold md:text-lg">{t("settings.language")}</label>
        <NativeSelect id="lang" value="it" disabled data-testid="settings-language">
          <option value="it">{t("settings.italian")}</option>
        </NativeSelect>
      </Card>
      <Button variant="outline" onClick={() => void logout()} data-testid="settings-logout-btn">
        <LogOut /> {t("nav.logout")}
      </Button>
    </div>
  );
}
