import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { PlugZap } from "lucide-react";
import { adminApi, type AdminApartment, type VerifyResult } from "@/api/admin";
import { useRole } from "@/auth/AuthProvider";
import { DemoBadge, Field, LastCheck, VerifyBadge } from "@/components/admin/apartmentForm";
import { ErrorNotice } from "@/components/apartment/ErrorNotice";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Badge, Card, Dialog, DialogContent, DialogTitle, Input, Label, Skeleton, Switch } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { runAction } from "@/lib/actions";
import { fmtPrice, parsePrice, priceInput } from "@/lib/price";

/**
 * Editing an apartment of the organization. Creating, relinking and deleting apartments is the platform manager's, in
 * every mode (D-77): the connection to the engine and the Italianway code are shown read-only and never sent (D-64, D-72).
 */
/** Price of energy shown to the admin: "0,25 €/kWh", or "non impostato". */
const priceText = (n: number | null | undefined) => (n === null || n === undefined ? t("admin.price.notSet") : t("admin.price.value", { price: fmtPrice(n) }));

function ApartmentDialog({ apt, orgPrice, onClose, onSaved }: { apt: AdminApartment; orgPrice: number | null; onClose: () => void; onSaved: () => void }) {
  // D-183: the time zone is set on the engine, not here: shown, never sent
  const [f, setF] = useState({ name: apt.name, address: apt.address, enabled: apt.enabled });
  const [price, setPrice] = useState(priceInput(apt.energy_price_eur_kwh));
  const [saving, setSaving] = useState(false);
  const set = (k: "name" | "address") => (v: string) => setF((s) => ({ ...s, [k]: v }));
  const parsed = parsePrice(price);
  const save = async () => {
    setSaving(true);
    // The exception is sent only when it changed (empty = back to the organization's price).
    const body = parsed !== undefined && parsed !== (apt.energy_price_eur_kwh ?? null) ? { ...f, energy_price_eur_kwh: parsed } : f;
    const res = await runAction((c) => adminApi.patchApartment(apt.apartment_id, body, c), { success: t("admin.apartments.saved") });
    setSaving(false);
    if (res) {
      onClose();
      onSaved();
    }
  };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90vh] overflow-y-auto" data-testid="apartment-dialog">
        <DialogTitle>{t("admin.apartments.edit")}</DialogTitle>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Field id="name" label={t("admin.apartments.name")} value={f.name} onChange={set("name")} />
          <Field id="address" label={t("admin.apartments.address")} value={f.address} onChange={set("address")} />
          <div className="space-y-1 rounded-xl border border-dashed px-3 py-2 sm:col-span-2" data-testid="apt-form-timezone-locked">
            <div className="text-sm font-semibold">{t("admin.apartments.timezone")}</div>
            <div className="font-mono text-xs text-muted-foreground">{apt.timezone}</div>
            <p className="text-xs text-muted-foreground">{t("admin.apartments.timezoneOnEngine")}</p>
          </div>
          <div className="space-y-1 rounded-xl border border-dashed px-3 py-2 sm:col-span-2" data-testid="apt-form-connection-locked">
            <div className="text-sm font-semibold">{t("admin.apartments.connection")}</div>
            <div className="font-mono text-xs text-muted-foreground">{apt.instance_url}{apt.port ? `:${apt.port}` : ""}</div>
            <p className="text-xs text-muted-foreground">{t("admin.apartments.connectionByPlatform")}</p>
          </div>
          <div className="space-y-1 rounded-xl border border-dashed px-3 py-2 sm:col-span-2" data-testid="apt-form-italianway-locked">
            <div className="text-sm font-semibold">{t("admin.apartments.italianway")}</div>
            <div className="font-mono text-xs text-muted-foreground">{apt.italianway_id || "—"}</div>
            <p className="text-xs text-muted-foreground">{t("admin.apartments.italianwayByPlatform")}</p>
          </div>
          <div className="space-y-1 sm:col-span-2">
            <Label htmlFor="apt-price">{t("admin.price.aptLabel")}</Label>
            <Input id="apt-price" inputMode="decimal" value={price} placeholder={t("admin.price.placeholder")} onChange={(e) => setPrice(e.target.value)} data-testid="apt-form-price" />
            <p className={parsed === undefined ? "text-[11px] text-destructive" : "text-[11px] text-muted-foreground"} data-testid="apt-form-price-hint">
              {parsed === undefined ? t("admin.price.invalid") : t("admin.price.aptHint", { price: priceText(orgPrice) })}
            </p>
          </div>
          <div className="flex items-center justify-between rounded-xl bg-secondary/60 px-3 py-2 sm:col-span-2">
            <Label htmlFor="apt-enabled">{t("admin.apartments.enabled")}</Label>
            <Switch id="apt-enabled" checked={f.enabled} onCheckedChange={(v) => setF((s) => ({ ...s, enabled: v }))} data-testid="apt-form-enabled" />
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} data-testid="apartment-dialog-cancel">{t("common.cancel")}</Button>
          <Button onClick={save} disabled={saving || !f.name.trim() || parsed === undefined} data-testid="apartment-dialog-save">{t("common.save")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** The organization's price per kWh (P-52, D-92): the amount in euro of the Excel reports, for every apartment. */
function PriceCard({ current }: { current: number | null }) {
  const qc = useQueryClient();
  const [text, setText] = useState<string | null>(null); // null = not edited: shows the saved price
  const [saving, setSaving] = useState(false);
  const value = text ?? priceInput(current);
  const parsed = parsePrice(value);
  const save = async () => {
    if (parsed === undefined) return;
    setSaving(true);
    const res = await runAction((c) => adminApi.patchTenant({ energy_price_eur_kwh: parsed }, c), { success: t("admin.price.saved") });
    setSaving(false);
    if (res) {
      setText(null);
      void qc.invalidateQueries({ queryKey: ["admin", "tenant"] });
    }
  };
  return (
    <Card className="space-y-2 p-5" data-testid="admin-price-card">
      <h3 className="text-base font-bold">{t("admin.price.title")}</h3>
      <p className="text-sm text-muted-foreground">{t("admin.price.hint")}</p>
      <div className="flex flex-wrap items-end gap-2">
        <div className="space-y-1">
          <Label htmlFor="org-price">{t("admin.price.label")}</Label>
          <Input id="org-price" inputMode="decimal" className="w-40" value={value} placeholder={t("admin.price.placeholder")} onChange={(e) => setText(e.target.value)} data-testid="admin-price-input" />
        </div>
        <Button onClick={() => void save()} disabled={saving || parsed === undefined || parsed === current} data-testid="admin-price-save">{t("admin.price.save")}</Button>
      </div>
      {parsed === undefined && <p className="text-xs text-destructive" data-testid="admin-price-invalid">{t("admin.price.invalid")}</p>}
    </Card>
  );
}

export function AdminApartments() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "apartments"], queryFn: adminApi.apartments });
  const tenant = useQuery({ queryKey: ["admin", "tenant"], queryFn: adminApi.tenant });
  const orgPrice = tenant.data?.energy_price_eur_kwh ?? null;
  // A platform manager adds apartments from Organizzazioni: no "write to the support" note for them (D-82).
  const { isPlatform } = useRole();
  const [editing, setEditing] = useState<AdminApartment | null>(null);
  const [verify, setVerify] = useState<Record<string, VerifyResult | "loading">>({});
  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["admin", "apartments"] });
    void qc.invalidateQueries({ queryKey: ["apartments"] });
  };

  const check = async (id: string) => {
    setVerify((s) => ({ ...s, [id]: "loading" }));
    const res = await runAction((c) => adminApi.verify(id, c));
    setVerify((s) => {
      const next = { ...s };
      if (res) next[id] = res;
      else delete next[id];
      return next;
    });
    refresh(); // the BFF stores the outcome as last_check
  };

  const toggle = async (a: AdminApartment, enabled: boolean) => {
    const res = await runAction((c) => adminApi.patchApartment(a.apartment_id, { enabled }, c), { success: t("admin.apartments.saved") });
    if (res) refresh();
  };

  return (
    <div className="space-y-4">
      {!isPlatform && <p className="text-sm text-muted-foreground" data-testid="admin-apartments-note">{t("admin.apartments.createdByPlatform")}</p>}
      {tenant.data && <PriceCard current={orgPrice} />}
      {q.error && <ErrorNotice error={q.error} onRetry={() => void q.refetch()} testId="admin-apartments-error" />}
      {q.isLoading ? <Skeleton className="h-48 rounded-2xl" /> : q.data?.map((a) => {
        const v = verify[a.apartment_id];
        return (
          <Card key={a.apartment_id} className="space-y-3 p-5 animate-fade-up" data-testid={`admin-apartment-${a.apartment_id}`} data-enabled={a.enabled}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-base font-bold">{a.name}</h3>
                  <CopyableId id={a.apartment_id} testId={`admin-apartment-id-${a.apartment_id}`} />
                  {a.simulated && <DemoBadge testId={`admin-apartment-demo-${a.apartment_id}`} />}
                  {!a.enabled && <Badge className="border-stone-300 bg-stone-100 text-stone-600">{t("admin.apartments.disabled")}</Badge>}
                </div>
                <p className="text-sm text-muted-foreground">{a.address || "—"} · {a.timezone}</p>
                <p className="font-mono text-xs text-muted-foreground">{a.instance_url}{a.port ? `:${a.port}` : ""}{a.italianway_id ? ` · IW ${a.italianway_id}` : ""}</p>
                <p className="text-xs text-muted-foreground">{t("admin.apartments.lastCheck")}: <LastCheck check={a.last_check} testId={`admin-apartment-check-${a.apartment_id}`} /></p>
                <p className="text-xs text-muted-foreground" data-testid={`admin-apartment-price-${a.apartment_id}`}>
                  {a.energy_price_eur_kwh != null ? t("admin.price.lineApt", { price: priceText(a.energy_price_eur_kwh) }) : t("admin.price.lineOrg", { price: priceText(orgPrice) })}
                </p>
                <p className="text-xs text-muted-foreground">{t("admin.features.scope")}: {a.enabled_features === null ? t("admin.features.inherit") : a.enabled_features.join(", ") || t("admin.features.none")}</p>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={a.enabled} aria-label={t("admin.apartments.enabled")} onCheckedChange={(v) => toggle(a, v)} data-testid={`admin-apartment-enabled-${a.apartment_id}`} />
                <Button variant="outline" size="sm" onClick={() => setEditing(a)} data-testid={`admin-apartment-edit-${a.apartment_id}`}>{t("common.edit")}</Button>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-3 border-t pt-3">
              <Button size="sm" variant="secondary" onClick={() => check(a.apartment_id)} disabled={v === "loading"} data-testid={`admin-verify-btn-${a.apartment_id}`}>
                <PlugZap /> {v === "loading" ? t("common.loading") : t("admin.apartments.verify")}
              </Button>
              {v && v !== "loading" && <VerifyBadge r={v} />}
              <span className="text-xs text-muted-foreground" data-testid={`admin-verify-help-${a.apartment_id}`}>{t("admin.apartments.verifyHelp")}</span>
            </div>
          </Card>
        );
      })}
      {editing && <ApartmentDialog key={editing.apartment_id} apt={editing} orgPrice={orgPrice} onClose={() => setEditing(null)} onSaved={refresh} />}
    </div>
  );
}
