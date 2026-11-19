export type ColorScheme = "light" | "dark";
export type ThemePreference = ColorScheme | "system";

type ThemeColors = Record<string, string>;
type PaletteDefinition = {
  nameKey: string;
  descriptionKey: string;
  swatches: readonly string[];
  themeColor: Record<ColorScheme, string>;
  tokens: Record<ColorScheme, ThemeColors>;
};

/** The only list of visual presets. Keep theme values here; components consume semantic CSS tokens. */
export const PALETTES = {
  sorgente: {
    nameKey: "appearance.paletteNames.sorgente",
    descriptionKey: "appearance.paletteDescriptions.sorgente",
    swatches: ["#E6F1ED", "#0D6B61", "#31B8C3", "#173A36"],
    themeColor: { light: "#0D6B61", dark: "#0E1715" },
    tokens: {
      light: {
        frame: "#E6F1ED", background: "#F5FAF8", foreground: "#173A36",
        card: "#FFFFFF", cardForeground: "#173A36", popover: "#FFFFFF", popoverForeground: "#173A36",
        heroOverlay: "#073D37",
        primary: "#0D6B61", primaryForeground: "#FFFFFF", secondary: "#E5F5F7", secondaryForeground: "#173A36",
        muted: "#EDF4F1", mutedForeground: "#536B67", accent: "#31B8C3", accentForeground: "#173A36",
        destructive: "#A6403B", destructiveForeground: "#FFFFFF", border: "#D6E4DF", input: "#C7D8D3", ring: "#0D6B61",
        chart1: "#0D6B61", chart2: "#31B8C3", chart3: "#C0812D", chart4: "#547FA6", chart5: "#A84E48",
        neutralBg: "#EEF4F1", neutralFg: "#536B67", neutralBorder: "#D6E4DF",
      },
      dark: {
        frame: "#0B1210", background: "#0E1715", foreground: "#EDF5F2",
        card: "#172622", cardForeground: "#EDF5F2", popover: "#172622", popoverForeground: "#EDF5F2",
        heroOverlay: "#073D37",
        primary: "#4DC4B2", primaryForeground: "#062C26", secondary: "#1A2C27", secondaryForeground: "#EDF5F2",
        muted: "#1D302B", mutedForeground: "#A9BDB8", accent: "#68D5DB", accentForeground: "#0B3437",
        destructive: "#FFAAA0", destructiveForeground: "#432421", border: "#344541", input: "#4C625B", ring: "#4DC4B2",
        chart1: "#4DC4B2", chart2: "#68D5DB", chart3: "#E2B45B", chart4: "#85B5D6", chart5: "#E08A7E",
        neutralBg: "#1D302B", neutralFg: "#C1D2CC", neutralBorder: "#435951",
      },
    },
  },
  aria: {
    nameKey: "appearance.paletteNames.aria",
    descriptionKey: "appearance.paletteDescriptions.aria",
    swatches: ["#E5EEF4", "#195C7A", "#56B7D2", "#1C3443"],
    themeColor: { light: "#195C7A", dark: "#101821" },
    tokens: {
      light: {
        frame: "#E5EEF4", background: "#F4F8FB", foreground: "#1C3443",
        card: "#FFFFFF", cardForeground: "#1C3443", popover: "#FFFFFF", popoverForeground: "#1C3443",
        heroOverlay: "#10384D",
        primary: "#195C7A", primaryForeground: "#FFFFFF", secondary: "#E4F2F7", secondaryForeground: "#1C3443",
        muted: "#EAF2F5", mutedForeground: "#506776", accent: "#56B7D2", accentForeground: "#173A47",
        destructive: "#A6403B", destructiveForeground: "#FFFFFF", border: "#D7E3EA", input: "#C4D5DF", ring: "#195C7A",
        chart1: "#195C7A", chart2: "#56B7D2", chart3: "#C2853A", chart4: "#587CB8", chart5: "#A84D51",
        neutralBg: "#ECF3F6", neutralFg: "#506776", neutralBorder: "#D7E3EA",
      },
      dark: {
        frame: "#0B1219", background: "#101821", foreground: "#EDF4F9",
        card: "#192532", cardForeground: "#EDF4F9", popover: "#192532", popoverForeground: "#EDF4F9",
        heroOverlay: "#10384D",
        primary: "#66BDE0", primaryForeground: "#082D3F", secondary: "#203245", secondaryForeground: "#EDF4F9",
        muted: "#1E2A35", mutedForeground: "#AABBC8", accent: "#63C1DB", accentForeground: "#10333E",
        destructive: "#FFAAA0", destructiveForeground: "#432421", border: "#354653", input: "#4C606E", ring: "#66BDE0",
        chart1: "#66BDE0", chart2: "#63C1DB", chart3: "#E0B85E", chart4: "#9AB8ED", chart5: "#E29191",
        neutralBg: "#222F3A", neutralFg: "#C1D0DC", neutralBorder: "#455967",
      },
    },
  },
  bosco: {
    nameKey: "appearance.paletteNames.bosco",
    descriptionKey: "appearance.paletteDescriptions.bosco",
    swatches: ["#E9EDE2", "#3F6346", "#B8C69A", "#2A352B"],
    themeColor: { light: "#3F6346", dark: "#171C17" },
    tokens: {
      light: {
        frame: "#E9EDE2", background: "#F7F8F2", foreground: "#2A352B",
        card: "#FFFFFF", cardForeground: "#2A352B", popover: "#FFFFFF", popoverForeground: "#2A352B",
        heroOverlay: "#2D432E",
        primary: "#3F6346", primaryForeground: "#FFFFFF", secondary: "#EEF0E6", secondaryForeground: "#2A352B",
        muted: "#EDF0E9", mutedForeground: "#566256", accent: "#B8C69A", accentForeground: "#273426",
        destructive: "#A6403B", destructiveForeground: "#FFFFFF", border: "#D8DFD2", input: "#C6CEBA", ring: "#3F6346",
        chart1: "#3F6346", chart2: "#829A67", chart3: "#B8A15E", chart4: "#547A83", chart5: "#A05C4D",
        neutralBg: "#F0F1E9", neutralFg: "#566256", neutralBorder: "#D8DFD2",
      },
      dark: {
        frame: "#111610", background: "#171C17", foreground: "#F1F2E9",
        card: "#202820", cardForeground: "#F1F2E9", popover: "#202820", popoverForeground: "#F1F2E9",
        heroOverlay: "#2D432E",
        primary: "#93B290", primaryForeground: "#1A2A1C", secondary: "#2A3429", secondaryForeground: "#F1F2E9",
        muted: "#252D24", mutedForeground: "#B5BCAC", accent: "#C4BA82", accentForeground: "#322C19",
        destructive: "#FFAAA0", destructiveForeground: "#432421", border: "#414A3E", input: "#596451", ring: "#93B290",
        chart1: "#93B290", chart2: "#C4BA82", chart3: "#D7B776", chart4: "#7DB6B9", chart5: "#E19D8C",
        neutralBg: "#283126", neutralFg: "#CAD1C2", neutralBorder: "#495547",
      },
    },
  },
} as const satisfies Record<string, PaletteDefinition>;

export type PaletteId = keyof typeof PALETTES;

/** Shared status and temperature semantics stay recognizable across palettes. */
const SEMANTIC_TOKENS: Record<ColorScheme, ThemeColors> = {
  light: {
    positive: "#2D765A", positiveBg: "#E0F0E6", positiveFg: "#235A42", positiveBorder: "#BDDCC9",
    warning: "#87540C", warningBg: "#FFF0D3", warningFg: "#87540C", warningBorder: "#E6D2A7",
    negative: "#A6403B", negativeBg: "#FCE9E6", negativeFg: "#A6403B", negativeBorder: "#EDC5BE",
    info: "#355A72", infoBg: "#E6F1F6", infoFg: "#355A72", infoBorder: "#C4D9E5",
    modeComfortBg: "#FCE6D8", modeComfortFg: "#914D2A",
    modeEcoBg: "#DFF0E5", modeEcoFg: "#235A42",
    modeEmptyBg: "#E6F1F6", modeEmptyFg: "#355A72",
    temperatureFreezing: "#2E6FA6", temperatureCool: "#247A8B", temperatureComfort: "#1B795D",
    temperatureWarm: "#946009", temperatureHot: "#A84136",
  },
  dark: {
    positive: "#9ADCB1", positiveBg: "#1F3B2C", positiveFg: "#9ADCB1", positiveBorder: "#355C42",
    warning: "#FFD78A", warningBg: "#3B2D15", warningFg: "#FFD78A", warningBorder: "#614A27",
    negative: "#FFAAA0", negativeBg: "#432421", negativeFg: "#FFAAA0", negativeBorder: "#653532",
    info: "#AED4FF", infoBg: "#203248", infoFg: "#AED4FF", infoBorder: "#36516D",
    modeComfortBg: "#3C2A21", modeComfortFg: "#FFD0B0",
    modeEcoBg: "#1F3B2C", modeEcoFg: "#9ADCB1",
    modeEmptyBg: "#203248", modeEmptyFg: "#AED4FF",
    temperatureFreezing: "#78B8EA", temperatureCool: "#5BC6D6", temperatureComfort: "#66CDA5",
    temperatureWarm: "#E5BA66", temperatureHot: "#F09383",
  },
};

function toHslChannels(hex: string): string {
  const value = hex.slice(1);
  const red = Number.parseInt(value.slice(0, 2), 16) / 255;
  const green = Number.parseInt(value.slice(2, 4), 16) / 255;
  const blue = Number.parseInt(value.slice(4, 6), 16) / 255;
  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const lightness = (max + min) / 2;
  let hue = 0;
  let saturation = 0;

  if (max !== min) {
    const delta = max - min;
    saturation = lightness > 0.5 ? delta / (2 - max - min) : delta / (max + min);
    if (max === red) hue = (green - blue) / delta + (green < blue ? 6 : 0);
    else if (max === green) hue = (blue - red) / delta + 2;
    else hue = (red - green) / delta + 4;
    hue *= 60;
  }

  const format = (number: number) => Number(number.toFixed(2)).toString();
  return `${format(hue)} ${format(saturation * 100)}% ${format(lightness * 100)}%`;
}

function toCssVariable(token: string): string {
  const kebab = token.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`).replace(/^(chart)(\d)$/, "$1-$2");
  return `--${kebab}`;
}

export function themeTokens(palette: PaletteId, scheme: ColorScheme): Record<string, string> {
  const paletteTokens = PALETTES[palette].tokens[scheme] as ThemeColors;
  const semanticTokens = SEMANTIC_TOKENS[scheme];
  return Object.fromEntries(
    Object.entries({ ...paletteTokens, ...semanticTokens }).map(([key, value]) => [toCssVariable(key), toHslChannels(value)]),
  );
}
