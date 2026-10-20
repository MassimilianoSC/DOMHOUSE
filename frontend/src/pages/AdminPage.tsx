import { useState } from "react";
import { adminApi } from "@/api/admin";
import { AdminApartments } from "@/components/admin/AdminApartments";
import { AdminFeatures } from "@/components/admin/AdminFeatures";
import { AdminUsers } from "@/components/admin/AdminUsers";
import { AdminWebhookLogs } from "@/components/admin/AdminWebhookLogs";
import { AuditLog } from "@/components/audit/AuditLog";
import { PageHeader, SegmentedControl } from "@/components/layout/PageHeader";
import { t } from "@/i18n";

type Tab = "users" | "apartments" | "features" | "webhooks" | "audit";

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("apartments");
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        title={t("admin.title")}
        subtitle={t("admin.subtitle")}
        testId="admin-header"
        actions={<SegmentedControl value={tab} onChange={setTab} testId="admin-tab" options={[{ value: "apartments", label: t("admin.apartments.title") }, { value: "users", label: t("admin.users.title") }, { value: "features", label: t("admin.features.title") }, { value: "webhooks", label: t("admin.bookingsReceived.title") }, { value: "audit", label: t("audit.title") }]} />}
      />
      {tab === "webhooks" && <AdminWebhookLogs />}
      {tab === "audit" && <AuditLog load={adminApi.audit} queryKey={["admin", "audit"]} hint={t("audit.hint")} />}
      {tab === "users" && <AdminUsers />}
      {tab === "apartments" && <AdminApartments />}
      {tab === "features" && <AdminFeatures />}
    </div>
  );
}
