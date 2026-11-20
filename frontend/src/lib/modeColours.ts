import type { ApartmentMode } from "@/api/types";

/** Semantic token classes for the three operating modes; their meaning stays stable across palettes and themes. */
export const MODE_BG: Record<ApartmentMode, string> = { comfort: "bg-mode-comfort-bg", eco: "bg-mode-eco-bg", empty: "bg-mode-empty-bg" };
export const MODE_FG: Record<ApartmentMode, string> = { comfort: "text-mode-comfort-fg", eco: "text-mode-eco-fg", empty: "text-mode-empty-fg" };
