import "@/i18n/pages";
import { useParams } from "react-router-dom";
import { CredentialsWorkspace } from "@/components/credentials/CredentialsWorkspace";
import { PageHeader } from "@/components/layout/PageHeader";
import { t } from "@/i18n";

/** «Credenziali dei dispositivi» of an apartment (A3, docs/proposta-a3-sito.md §1): admins only, through the route. */
export default function DeviceCredentialsPage() {
  const { aptId = "" } = useParams();
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader title={t("credentials.title")} subtitle={t("credentials.subtitle")} testId="credentials-header" />
      <CredentialsWorkspace apartmentId={aptId} scope="apartment" />
    </div>
  );
}
