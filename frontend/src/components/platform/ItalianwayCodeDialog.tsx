import { useState } from "react";
import { ApiError } from "@/api/bff";
import { platformApi, type PlatformApartment } from "@/api/platform";
import { FormField } from "@/components/platform/NewApartmentDialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, Input } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { showError } from "@/lib/actions";
import { newCorrelationId } from "@/lib/utils";
import { toast } from "sonner";

/**
 * D-198: the Italianway code of an apartment created from the app, added or changed after the creation (the creation
 * form says «Si può aggiungere anche dopo»). Only the code: the connection belongs to the creation, so these apartments
 * have no «Modifica collegamento». Empty = no code.
 */
export function ItalianwayCodeDialog({ tenantId, apt, onClose, onSaved }: { tenantId: string; apt: PlatformApartment; onClose: () => void; onSaved: () => void }) {
  const [code, setCode] = useState(apt.italianway_id ?? "");
  const [problem, setProblem] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const next = code.trim() || null;
  const changed = next !== (apt.italianway_id || null);

  const save = async () => {
    const correlationId = newCorrelationId();
    setSaving(true);
    try {
      await platformApi.setItalianwayCode(tenantId, apt.apartment_id, next, correlationId);
      toast.success(t(next ? "platform.italianwayCode.saved" : "platform.italianwayCode.removed", { name: apt.name }));
      onSaved();
      onClose();
    } catch (err) {
      // the code of another apartment: the server's sentence under the field, as in the creation form
      if (err instanceof ApiError && err.code === "external_id_in_use") setProblem(err.message);
      else showError(err, correlationId);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid={`platform-apt-italianway-dialog-${apt.apartment_id}`}>
        <DialogTitle>{t("platform.italianwayCode.title", { name: apt.name })}</DialogTitle>
        <DialogDescription>{t("platform.italianwayCode.hint")}</DialogDescription>
        <div className="mt-4">
          <FormField id="italianway_code" label={t("admin.apartments.italianway")} hint={t("platform.italianwayHint")} problem={problem} problemTestId="apt-italianway-problem">
            <Input
              id="italianway_code"
              value={code}
              onChange={(e) => {
                setCode(e.target.value);
                setProblem(null);
              }}
              data-testid="apt-italianway-code"
            />
          </FormField>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} data-testid="apt-italianway-cancel">{t("common.cancel")}</Button>
          <Button onClick={() => void save()} disabled={saving || !changed} data-testid="apt-italianway-save">{t("common.save")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
