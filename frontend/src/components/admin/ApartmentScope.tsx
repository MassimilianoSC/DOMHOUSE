import type { ApartmentScope } from "@/api/admin";
import { t } from "@/i18n";
import { cn } from "@/lib/utils";

// Which apartments an operator or viewer sees (P-18, API shape D-43): "all" (no restriction, as before) or the list of
// apartment ids; [] = none. Admins always see everything, so the picker is never shown for them.
export type { ApartmentScope };

interface AptRef {
  apartment_id: string;
  name: string;
  address?: string;
}

/** Readable summary for the users list; ids of apartments that no longer exist are ignored. */
export function scopeSummary(scope: ApartmentScope, apartments: AptRef[]): { text: string; names: string[] } {
  if (scope === "all") return { text: t("admin.users.scopeAll"), names: [] };
  const names = apartments.filter((a) => scope.includes(a.apartment_id)).map((a) => a.name);
  if (names.length === 0) return { text: t("admin.users.scopeNone"), names };
  if (names.length <= 2) return { text: names.join(", "), names };
  return { text: t("admin.users.scopeCount", { count: names.length }), names };
}

/** "None" is allowed (it suspends an access without deleting the user) but always asks for confirmation. */
export const isNoneScope = (scope: ApartmentScope) => scope !== "all" && scope.length === 0;

export function ApartmentScopePicker({ value, onChange, apartments, testId }: { value: ApartmentScope; onChange: (v: ApartmentScope) => void; apartments: AptRef[]; testId: string }) {
  const all = value === "all";
  const toggle = (id: string, on: boolean) => {
    const list = all ? [] : value;
    onChange(on ? [...new Set([...list, id])] : list.filter((x) => x !== id));
  };
  return (
    <fieldset className="space-y-2" data-testid={testId}>
      <legend className="mb-1 text-sm font-semibold">{t("admin.users.scopeLabel")}</legend>
      <label className="flex min-h-[40px] items-center gap-3 rounded-xl bg-secondary/60 px-3 py-2 text-sm font-semibold">
        <input
          type="checkbox"
          className="h-4 w-4 accent-[hsl(var(--primary))]"
          checked={all}
          onChange={(e) => onChange(e.target.checked ? "all" : [])}
          data-testid={`${testId}-all`}
        />
        {t("admin.users.scopeAllOption")}
      </label>
      <div className="grid gap-1.5 sm:grid-cols-2">
        {apartments.map((a) => (
          <label key={a.apartment_id} className={cn("flex min-h-[40px] items-center gap-3 rounded-xl border px-3 py-2 text-sm", all && "opacity-50")}>
            <input
              type="checkbox"
              className="h-4 w-4 accent-[hsl(var(--primary))]"
              checked={all || value.includes(a.apartment_id)}
              disabled={all}
              onChange={(e) => toggle(a.apartment_id, e.target.checked)}
              data-testid={`${testId}-${a.apartment_id}`}
            />
            <span className="min-w-0">
              <span className="block truncate font-semibold">{a.name}</span>
              {a.address && <span className="block truncate text-xs text-muted-foreground">{a.address}</span>}
            </span>
          </label>
        ))}
      </div>
      {isNoneScope(value) && <p className="text-xs font-medium text-destructive" data-testid={`${testId}-none-warning`}>{t("admin.users.scopeNoneWarning")}</p>}
    </fieldset>
  );
}
