/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        heading: ['"Plus Jakarta Sans"', "sans-serif"],
        sans: ["Manrope", "sans-serif"],
        mono: ['"JetBrains Mono"', "monospace"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
        // status pairs (lotto 32): bg, fg (text on bg) and border, plus a text green and red that pass 4.5:1
        positive: { DEFAULT: "hsl(var(--positive))", bg: "hsl(var(--positive-bg))", fg: "hsl(var(--positive-fg))", border: "hsl(var(--positive-border))" },
        warning: { bg: "hsl(var(--warning-bg))", fg: "hsl(var(--warning-fg))", border: "hsl(var(--warning-border))" },
        negative: { DEFAULT: "hsl(var(--negative))", bg: "hsl(var(--negative-bg))", fg: "hsl(var(--negative-fg))", border: "hsl(var(--negative-border))" },
        neutral: { bg: "hsl(var(--neutral-bg))", fg: "hsl(var(--neutral-fg))", border: "hsl(var(--neutral-border))" },
        chart: {
          1: "hsl(var(--chart-1))",
          2: "hsl(var(--chart-2))",
          3: "hsl(var(--chart-3))",
          4: "hsl(var(--chart-4))",
          5: "hsl(var(--chart-5))",
        },
      },
      borderRadius: { lg: "var(--radius)", md: "calc(var(--radius) - 2px)", sm: "calc(var(--radius) - 4px)" },
      keyframes: {
        "fade-up": { from: { opacity: "0", transform: "translateY(6px)" }, to: { opacity: "1", transform: "none" } },
        glow: { "0%": { boxShadow: "0 0 0 0 hsl(var(--accent) / 0.45)" }, "100%": { boxShadow: "0 0 0 8px hsl(var(--accent) / 0)" } },
      },
      animation: { "fade-up": "fade-up 0.35s ease-out both", glow: "glow 1.2s ease-out" },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
