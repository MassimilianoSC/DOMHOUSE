import { Check, X } from "lucide-react";
import type { VerifyResult } from "@/api/admin";
import { useAuth } from "@/auth/AuthProvider";
import { Badge, Input, Label, Switch } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { fmtDateTime } from "@/lib/format";

// Pieces shared by the apartment forms of Amministrazione (organization admin) and Organizzazioni (platform manager,
// D-64/D-66): the rules on who edits what live in the two forms, the building blocks here.

/** Apartment id: lower case, digits and dashes; unique on the whole platform and never changed after creation. */
export const APARTMENT_ID_RE = /^[a-z0-9][a-z0-9-]{2,}$/;

/**
 * Engine mode of the BFF: "mock" (staging, built-in mock://builtin) or "real" (production). In both modes the platform
 * manager creates apartments and owns their connection to the engine (D-64, D-77).
 */
export function useInstanceMode() {
  const mode = useAuth().me?.env.instance_mode;
  return { mock: mode === "mock", real: mode === "real" };
}

/** The built-in simulated engine (D-28): with it the instance is always simulated (D-97). */
export const isBuiltinMock = (url: string) => url.trim().toLowerCase().startsWith("mock://");

/**
 * «Istanza simulata» (D-97), set by the platform. Locked on with the built-in mock; free with a real engine, which
 * may run in simulated mode. The Simulatore follows it, in every environment.
 */
export function SimulatedField({ url, value, onChange }: { url: string; value: boolean; onChange: (v: boolean) => void }) {
  const locked = isBuiltinMock(url);
  return (
    <div className="space-y-1 rounded-xl bg-secondary/60 px-3 py-2 sm:col-span-2">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor="apt-simulated">{t("platform.simulated")}</Label>
        <Switch id="apt-simulated" checked={locked || value} disabled={locked} onCheckedChange={onChange} data-testid="apt-form-simulated" />
      </div>
      <p className="text-xs text-muted-foreground" data-testid="apt-form-simulated-hint">{t(locked ? "platform.simulatedLocked" : "platform.simulatedHint")}</p>
    </div>
  );
}

/** Badge of a simulated apartment (D-98), the same word in every list: neutral and outlined (lotto 32), not a status. */
export function DemoBadge({ testId }: { testId: string }) {
  return <Badge className="border-neutral-border bg-card text-neutral-fg" data-testid={testId}>{t("apartments.demo")}</Badge>;
}

/** With INSTANCE_MODE=mock the BFF accepts only mock:// URLs (D-28): a new apartment starts with the built-in mock. */
export const defaultInstanceUrl = (mock: boolean) => (mock ? "mock://builtin" : "");

export function Field({ id, label, value, onChange, type = "text", placeholder, hint }: { id: string; label: string; value: string; onChange: (v: string) => void; type?: string; placeholder?: string; hint?: string }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type={type} value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} data-testid={`apt-form-${id}`} />
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

/** Outcome of the last "Verifica connessione" stored by the BFF, whoever ran it (D-66); null = never verified. */
export type LastCheckInfo = { ok: boolean; checked_at: string; error: string | null } | null;

/** "riuscita il …", "non riuscita il … · motivo" or "mai eseguita": tells the admin when to call the support (C-1). */
export function LastCheck({ check, testId }: { check: LastCheckInfo | undefined; testId: string }) {
  if (!check) return <span className="text-muted-foreground" data-testid={testId}>{t("admin.apartments.lastCheckNever")}</span>;
  return (
    <span className={check.ok ? "text-positive-fg" : "text-destructive"} data-testid={testId} data-ok={check.ok}>
      {check.ok ? <Check className="mr-1 inline h-3 w-3" /> : <X className="mr-1 inline h-3 w-3" />}
      {t(check.ok ? "admin.apartments.lastCheckOk" : "admin.apartments.lastCheckKo", { when: fmtDateTime(check.checked_at) })}
      {!check.ok && check.error ? ` · ${check.error}` : ""}
    </span>
  );
}

export function VerifyBadge({ r }: { r: VerifyResult }) {
  const health = (r.health?.body as { status?: string } | null)?.status;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs" data-testid={`verify-result-${r.apartment_id}`} data-ok={r.ok}>
      <Badge className={r.ok ? "border-positive-border bg-positive-bg text-positive-fg" : "border-negative-border bg-negative-bg text-negative-fg"}>
        {r.ok ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />} {r.ok ? t("admin.apartments.verifyOk") : t("admin.apartments.verifyKo")}
      </Badge>
      {health && <span>/health: <strong>{health}</strong> ({r.health?.status_code})</span>}
      {r.contract_version && (
        <span>
          /version: <strong>{r.contract_version}</strong>
          {r.features ? ` · ${r.features.length} ${t("admin.features.title").toLowerCase()}` : ""}
        </span>
      )}
      {r.error && <span className="tabular text-destructive">{r.error}</span>}
    </div>
  );
}
