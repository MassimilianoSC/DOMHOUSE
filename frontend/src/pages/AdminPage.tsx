import { adminApi } from "@/api/admin";
import { AdminApartments } from "@/components/admin/AdminApartments";
import { AdminAssistant } from "@/components/admin/AdminAssistant";
import { AdminFeatures } from "@/components/admin/AdminFeatures";
import { AdminUsers } from "@/components/admin/AdminUsers";
import { AdminWebhookLogs } from "@/components/admin/AdminWebhookLogs";
import { AuditLog } from "@/components/audit/AuditLog";
import { PageHeader, Tabs } from "@/components/layout/PageHeader";
import { t } from "@/i18n";
import { useTabParam } from "@/lib/useTabParam";

type Tab = "users" | "apartments" | "features" | "webhooks" | "audit" | "assistant";

/** ?scheda=… in the address (design lot 2). */
const SLUGS: Record<Tab, string> = { apartments: "appartamenti", users: "utenti", features: "funzioni", webhooks: "prenotazioni", audit: "registro", assistant: "assistente" };

export default function AdminPage() {
  const [tab, setTab] = useTabParam<Tab>(SLUGS, "apartments");
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title={t("admin.title")}
        subtitle={t("admin.subtitle")}
        testId="admin-header"
      />
      <Tabs value={tab} onChange={setTab} testId="admin-tab" options={[{ value: "apartments", label: t("admin.apartments.title") }, { value: "users", label: t("admin.users.title") }, { value: "features", label: t("admin.features.title") }, { value: "webhooks", label: t("admin.bookingsReceived.title") }, { value: "audit", label: t("audit.titleTenant") }, { value: "assistant", label: t("admin.assistant.title") }]} />
      {tab === "webhooks" && <AdminWebhookLogs />}
      {tab === "audit" && <AuditLog load={adminApi.audit} queryKey={["admin", "audit"]} hint={t("audit.hint")} title={t("audit.titleTenant")} />}
      {tab === "users" && <AdminUsers />}
      {tab === "apartments" && <AdminApartments />}
      {tab === "features" && <AdminFeatures />}
      {tab === "assistant" && <AdminAssistant />}
    </div>
  );
}
