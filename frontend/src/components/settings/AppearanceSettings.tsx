import { useState } from "react";
import { Monitor, Moon, RotateCcw, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SettingsSection } from "@/components/settings/SettingsSection";
import { t } from "@/i18n";
import { DEFAULT_APPEARANCE, setAppearance, useAppearance } from "@/theme/appearance";
import { PALETTES, type PaletteId, type ThemePreference } from "@/theme/palettes";

const paletteOptions = Object.entries(PALETTES) as [PaletteId, (typeof PALETTES)[PaletteId]][];
const paletteCopy: Record<PaletteId, { name: string; description: string }> = {
  sorgente: {
    name: t("appearance.paletteNames.sorgente"),
    description: t("appearance.paletteDescriptions.sorgente"),
  },
  aria: {
    name: t("appearance.paletteNames.aria"),
    description: t("appearance.paletteDescriptions.aria"),
  },
  bosco: {
    name: t("appearance.paletteNames.bosco"),
    description: t("appearance.paletteDescriptions.bosco"),
  },
};
const themeOptions: { value: ThemePreference; label: string; Icon: typeof Monitor }[] = [
  { value: "system", label: t("appearance.modes.system"), Icon: Monitor },
  { value: "light", label: t("appearance.modes.light"), Icon: Sun },
  { value: "dark", label: t("appearance.modes.dark"), Icon: Moon },
];

export function AppearanceSettings() {
  const appearance = useAppearance();
  const [announcement, setAnnouncement] = useState("");

  const updatePalette = (palette: PaletteId) => {
    const saved = setAppearance({ palette });
    setAnnouncement(t(saved ? "appearance.saved" : "appearance.sessionOnly"));
  };

  const updateMode = (mode: ThemePreference) => {
    const saved = setAppearance({ mode });
    setAnnouncement(t(saved ? "appearance.saved" : "appearance.sessionOnly"));
  };

  const reset = () => {
    const saved = setAppearance(DEFAULT_APPEARANCE);
    setAnnouncement(t(saved ? "appearance.reset" : "appearance.sessionOnly"));
  };

  return (
    <SettingsSection
      title={t("appearance.title")}
      hint={t("appearance.hint")}
      testId="appearance-settings"
    >
      <div className="space-y-6">
        <fieldset className="min-w-0">
          <legend className="text-sm font-semibold">{t("appearance.paletteLegend")}</legend>
          <p className="mt-1 text-sm text-muted-foreground">{t("appearance.paletteHint")}</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {paletteOptions.map(([id, palette]) => {
              const selected = appearance.palette === id;
              return (
                <label
                  key={id}
                  className={`flex min-h-24 cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background ${
                    selected ? "border-primary bg-secondary/60" : "border-border bg-card hover:bg-muted/50"
                  }`}
                  data-testid={`appearance-palette-${id}`}
                >
                  <input
                    className="mt-0.5 h-4 w-4 shrink-0 accent-[hsl(var(--primary))]"
                    type="radio"
                    name="appearance-palette"
                    value={id}
                    checked={selected}
                    onChange={() => updatePalette(id)}
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-semibold">{paletteCopy[id].name}</span>
                    <span className="mt-1 block text-xs leading-5 text-muted-foreground">{paletteCopy[id].description}</span>
                    <span className="mt-2 flex gap-1.5" aria-hidden="true">
                      {palette.swatches.map((color) => (
                        <span key={color} className="h-4 w-4 rounded-full border border-foreground/10" style={{ backgroundColor: color }} />
                      ))}
                    </span>
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <fieldset className="min-w-0 border-t pt-5">
          <legend className="px-0 text-sm font-semibold">{t("appearance.modeLegend")}</legend>
          <p className="mt-1 text-sm text-muted-foreground">{t("appearance.modeHint")}</p>
          <div className="mt-3 grid gap-2 sm:grid-cols-3">
            {themeOptions.map(({ value, label, Icon }) => {
              const selected = appearance.mode === value;
              return (
                <label
                  key={value}
                  className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-sm font-medium transition-colors focus-within:ring-2 focus-within:ring-ring focus-within:ring-offset-2 focus-within:ring-offset-background ${
                    selected ? "border-primary bg-secondary/60 text-foreground" : "border-border bg-card text-muted-foreground hover:bg-muted/50"
                  }`}
                >
                  <input
                    className="h-4 w-4 shrink-0 accent-[hsl(var(--primary))]"
                    type="radio"
                    name="appearance-mode"
                    value={value}
                    checked={selected}
                    onChange={() => updateMode(value)}
                  />
                  <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{label}</span>
                </label>
              );
            })}
          </div>
        </fieldset>

        <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
          <p className="max-w-md text-xs leading-5 text-muted-foreground">{t("appearance.localHint")}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={appearance.palette === DEFAULT_APPEARANCE.palette && appearance.mode === DEFAULT_APPEARANCE.mode}
            onClick={reset}
            data-testid="appearance-reset"
          >
            <RotateCcw aria-hidden="true" />
            {t("appearance.resetButton")}
          </Button>
        </div>
        <p className="min-h-5 text-sm text-muted-foreground" role="status" aria-live="polite">{announcement}</p>
      </div>
    </SettingsSection>
  );
}
