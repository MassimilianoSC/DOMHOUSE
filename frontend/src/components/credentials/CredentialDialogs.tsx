import { useEffect, useState } from "react";
import { Ban, Check, Copy, KeyRound, Plus, TriangleAlert } from "lucide-react";
import type { CredentialWithPassword, DeviceCredential } from "@/api/deviceCredentials";
import { Button } from "@/components/ui/button";
import { CopyableId } from "@/components/ui/CopyableId";
import { Dialog, DialogContent, DialogDescription, DialogTitle, Input, Label } from "@/components/ui/primitives";
import { t } from "@/i18n";
import { deviceIdProblem } from "@/lib/deviceCredentials";
import { cn } from "@/lib/utils";

// A3, the windows of «Credenziali dei dispositivi» (docs/proposta-a3-sito.md §2; screens approved by the committente,
// 1182). The values to copy come from the server (credential.connection, password): the site writes none of them.

const nameOf = (c: DeviceCredential) => c.name ?? c.device_id;

function CopyButton({ value, testId }: { value: string; testId: string }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 1500);
    return () => clearTimeout(timer);
  }, [copied]);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
    } catch {
      /* clipboard refused: the value stays on screen to copy by hand */
    }
  };
  return (
    <Button size="sm" variant="outline" className="h-8 px-2.5" onClick={() => void copy()} data-testid={testId}>
      {copied ? <Check /> : <Copy />} {copied ? t("common.copied") : t("common.copy")}
    </Button>
  );
}

type FieldRow = { key: string; site: string; shelly: string; value: string; copy: boolean; strong?: boolean; plain?: boolean };

/**
 * The values to write in the Shelly's MQTT page, in its order, each with the name of the field there (screens of the
 * committente, 17 November; to check again on firmware 2.2.0 with Youssouf for the guides, A9). `password` is the one
 * of «Registra» or «Rigenera», or, in «Dati di collegamento», the sentence that says it cannot be read again.
 */
function ConnectionTable({ c, password }: { c: DeviceCredential; password: { value: string } | { gone: string } }) {
  const k = c.connection;
  const rows: FieldRow[] = [
    { key: "ssl_ca", site: t("credentials.fields.type"), shelly: t("credentials.fields.typeShelly"), value: t("credentials.fields.typeValue"), copy: false, plain: true },
    { key: "topic_prefix", site: t("credentials.fields.prefix"), shelly: t("credentials.fields.prefixShelly"), value: k.topic_prefix, copy: true },
    { key: "server", site: t("credentials.fields.server"), shelly: t("credentials.fields.serverShelly"), value: k.server ?? t("credentials.fields.serverMissing"), copy: k.server !== null, plain: k.server === null },
    { key: "client_id", site: t("credentials.fields.clientId"), shelly: t("credentials.fields.clientIdShelly"), value: k.client_id, copy: true },
    { key: "user", site: t("credentials.fields.user"), shelly: t("credentials.fields.userShelly"), value: k.user, copy: true },
    "value" in password
      ? { key: "password", site: t("credentials.fields.password"), shelly: t("credentials.fields.passwordShelly"), value: password.value, copy: true, strong: true }
      : { key: "password", site: t("credentials.fields.password"), shelly: t("credentials.fields.passwordShelly"), value: password.gone, copy: false, plain: true },
    { key: "other", site: t("credentials.fields.other"), shelly: t("credentials.fields.otherShelly"), value: t("credentials.fields.otherValue"), copy: false, plain: true },
  ];
  return (
    <div className="overflow-hidden rounded-xl border text-sm">
      <div className="hidden grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,2fr)_auto] gap-3 bg-secondary/50 px-3 py-2 text-xs font-semibold text-muted-foreground sm:grid" aria-hidden>
        <div>{t("credentials.fields.site")}</div>
        <div>{t("credentials.fields.shelly")}</div>
        <div>{t("credentials.fields.value")}</div>
        <div />
      </div>
      <dl className="divide-y">
        {rows.map((r) => (
          <div key={r.key} className={cn("grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-0.5 px-3 py-2.5 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,2fr)_auto]", r.strong && "bg-warning-bg/60")}>
            <dt className={cn("col-span-2 sm:col-span-1", r.strong ? "font-bold" : "font-medium")}>
              {r.site}
              <span className="ml-1.5 text-xs font-normal text-muted-foreground sm:hidden">{r.shelly}</span>
            </dt>
            <div className="hidden text-muted-foreground sm:block">{r.shelly}</div>
            <dd className={cn("min-w-0 [overflow-wrap:anywhere]", r.plain ? "" : "font-mono", r.strong && "text-[15px] font-bold tracking-wide")} data-testid={`credential-value-${r.key}`}>
              {r.value}
            </dd>
            <div className="justify-self-end">{r.copy && <CopyButton value={r.value} testId={`credential-copy-${r.key}`} />}</div>
          </div>
        ))}
      </dl>
    </div>
  );
}

/**
 * The password, shown once (§2.3): «Chiudi» stays off until «Ho copiato la password nello Shelly» is ticked; Esc, a
 * click outside and the «×» do not close it. The password lives only in the state of the caller, which drops it on close.
 */
export function PasswordDialog({ shown, onClose }: { shown: CredentialWithPassword; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const c = shown.credential;
  const keep = (e: Event) => e.preventDefault();
  return (
    <Dialog open onOpenChange={() => {}}>
      <DialogContent hideClose className="max-w-2xl" onEscapeKeyDown={keep} onPointerDownOutside={keep} onInteractOutside={keep} data-testid="credential-password-dialog">
        <DialogTitle>{t("credentials.password.title", { name: nameOf(c) })}</DialogTitle>
        {c.stato === "non_applicato" && c.op && (
          <div role="alert" className="mt-3 rounded-xl border border-negative-border bg-negative-bg px-3 py-2 text-sm text-negative-fg" data-testid="credential-password-not-applied">
            <p className="font-semibold">{c.op.messaggio}</p>
            <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
              {t("credentials.requestId")} <CopyableId id={c.op.op_id} testId="credential-password-op" label={t("credentials.requestId")} />
            </p>
          </div>
        )}
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-warning-border bg-warning-bg px-3 py-2 text-sm text-warning-fg">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            <strong>{t("credentials.password.onlyNow")}</strong> {t("credentials.password.onlyNowText")}
          </p>
        </div>
        <DialogDescription className="mt-3">{t("credentials.password.intro")}</DialogDescription>
        <div className="mt-3">
          <ConnectionTable c={c} password={{ value: shown.password }} />
        </div>
        <p className="mt-2 text-xs text-muted-foreground">{t("credentials.password.clipboard")}</p>
        <label className="mt-4 flex items-center gap-2 text-sm font-medium">
          <input type="checkbox" className="size-[18px] accent-foreground" checked={copied} onChange={(e) => setCopied(e.target.checked)} data-testid="credential-password-copied" />
          {t("credentials.password.copied")}
        </label>
        <div className="mt-4 flex justify-end">
          <Button onClick={onClose} disabled={!copied} data-testid="credential-password-close">{t("credentials.password.close")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function ConnectionDialog({ c, onClose }: { c: DeviceCredential; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl" data-testid="credential-connection-dialog">
        <DialogTitle className="pr-8">{t("credentials.connectionDialog.title", { name: nameOf(c) })}</DialogTitle>
        <DialogDescription className="mt-2">{t("credentials.password.intro")}</DialogDescription>
        <div className="mt-3">
          <ConnectionTable c={c} password={{ gone: c.stato === "revocato" ? t("credentials.fields.passwordRevoked") : t("credentials.fields.passwordGone") }} />
        </div>
        <div className="mt-4 flex justify-end">
          <Button variant="ghost" onClick={onClose}>{t("common.close")}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** «Registra un dispositivo»: one field, checked while typing with the project's rule; capitals are not converted. */
export function RegisterDialog({ busy, serverProblem, onSave, onClose }: { busy: boolean; serverProblem: string | null; onSave: (deviceId: string) => void; onClose: () => void }) {
  const [value, setValue] = useState("");
  const problem = deviceIdProblem(value);
  const message = problem === "invalid" ? t("credentials.registerDialog.invalid") : problem === "reserved" ? t("credentials.registerDialog.reserved") : serverProblem;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="credential-register-dialog">
        <DialogTitle className="pr-8">{t("credentials.registerDialog.title")}</DialogTitle>
        <DialogDescription>{t("credentials.registerDialog.hint")}</DialogDescription>
        <form
          className="mt-4 space-y-1"
          onSubmit={(e) => {
            e.preventDefault();
            if (!problem && !busy) onSave(value.trim());
          }}
        >
          <Label htmlFor="credential-code">{t("credentials.registerDialog.label")}</Label>
          <Input
            id="credential-code"
            className="font-mono"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={t("credentials.registerDialog.placeholder")}
            autoComplete="off"
            spellCheck={false}
            autoCapitalize="none"
            aria-invalid={Boolean(message)}
            aria-describedby={message ? "credential-code-problem" : undefined}
            data-testid="credential-register-input"
          />
          {message && (
            <p id="credential-code-problem" className="text-xs text-destructive" data-testid="credential-register-problem">{message}</p>
          )}
          <div className="flex justify-end gap-2 pt-3">
            <Button type="button" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
            <Button type="submit" disabled={Boolean(problem) || busy} data-testid="credential-register-save">
              <Plus /> {t("credentials.registerDialog.save")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function RegenerateDialog({ c, busy, onConfirm, onClose }: { c: DeviceCredential; busy: boolean; onConfirm: () => void; onClose: () => void }) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="credential-regenerate-dialog">
        <DialogTitle className="pr-8 [overflow-wrap:anywhere]">{t("credentials.regenerateDialog.title", { name: nameOf(c) })}</DialogTitle>
        <p className="mt-2 text-sm">{t("credentials.regenerateDialog.text")}</p>
        <p className="mt-2 text-sm text-muted-foreground">{t("credentials.regenerateDialog.once")}</p>
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          <Button variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button onClick={onConfirm} disabled={busy} data-testid="credential-regenerate-confirm">
            <KeyRound /> {t("credentials.regenerateDialog.confirm")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** «Revoca», confirmed by writing the device code again (answer 1171): the button lights up only with the same code. */
export function RevokeDialog({ c, busy, onConfirm, onClose }: { c: DeviceCredential; busy: boolean; onConfirm: () => void; onClose: () => void }) {
  const [value, setValue] = useState("");
  const same = value.trim() === c.device_id;
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent data-testid="credential-revoke-dialog">
        <DialogTitle className="pr-8 [overflow-wrap:anywhere]">{t("credentials.revokeDialog.title", { name: nameOf(c) })}</DialogTitle>
        <div className="mt-3 flex items-start gap-2 rounded-xl border border-negative-border bg-negative-bg px-3 py-2 text-sm text-negative-fg">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />
          <p>
            <strong>{t("credentials.revokeDialog.warningStrong")}</strong> {t("credentials.revokeDialog.warning")} <strong>{t("credentials.revokeDialog.comeBackStrong")}</strong> {t("credentials.revokeDialog.comeBack")}
          </p>
        </div>
        <p className="mt-3 text-sm">{t("credentials.revokeDialog.when")}</p>
        <form
          className="mt-4 space-y-1"
          onSubmit={(e) => {
            e.preventDefault();
            if (same && !busy) onConfirm();
          }}
        >
          <Label htmlFor="credential-revoke-code" className="[overflow-wrap:anywhere]">{t("credentials.revokeDialog.label", { code: c.device_id })}</Label>
          <Input id="credential-revoke-code" className="font-mono" value={value} onChange={(e) => setValue(e.target.value)} autoComplete="off" spellCheck={false} autoCapitalize="none" data-testid="credential-revoke-input" />
          {!same && <p className="text-xs text-muted-foreground">{t("credentials.revokeDialog.hint")}</p>}
          <div className="flex flex-wrap justify-end gap-2 pt-3">
            <Button type="button" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
            <Button type="submit" variant="destructive" disabled={!same || busy} data-testid="credential-revoke-confirm">
              <Ban /> {t("credentials.revokeDialog.confirm")}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
