import { Ban, Construction, ShieldAlert, SearchX } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";

function Notice({ icon, title, text, testId, action }: { icon: ReactNode; title: string; text: string; testId: string; action?: ReactNode }) {
  return (
    <div data-testid={testId} className="mx-auto flex max-w-lg flex-col items-center gap-3 rounded-3xl border border-dashed bg-card/60 px-6 py-14 text-center">
      <span className="rounded-2xl bg-secondary p-3 text-muted-foreground">{icon}</span>
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="text-sm text-muted-foreground">{text}</p>
      {action}
    </div>
  );
}

export const FeatureUnavailable = () => (
  <Notice icon={<Ban className="h-6 w-6" />} title={t("features.unavailable")} text={t("features.unavailableHint")} testId="feature-unavailable" />
);

export const ComingSoon = ({ title }: { title: string }) => (
  <Notice icon={<Construction className="h-6 w-6" />} title={`${title} · ${t("phase.soon")}`} text={t("phase.soonHint")} testId="coming-soon" />
);

export const ContractBlocked = ({ version }: { version: string }) => (
  <Notice icon={<ShieldAlert className="h-6 w-6" />} title={t("contract.incompatibleTitle")} text={t("contract.incompatible", { version })} testId="contract-blocked" />
);

/** Apartment that does not exist or is not assigned to this user (P-18): never a half-rendered page. */
export const ApartmentUnavailable = () => (
  <Notice
    icon={<SearchX className="h-6 w-6" />}
    title={t("apartments.unavailable")}
    text={t("apartments.unavailableHint")}
    testId="apartment-unavailable"
    action={
      <Button asChild variant="outline" className="mt-2" data-testid="apartment-unavailable-back">
        <Link to="/">{t("apartments.backToList")}</Link>
      </Button>
    }
  />
);
