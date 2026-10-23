import type { ApartmentMode } from "@/api/types";

/** One colour per mode (lot 34, D-194): comfort warm orange, eco sage, casa vuota slate. Background and its ink. */
export const MODE_BG: Record<ApartmentMode, string> = { comfort: "bg-mode-comfort-bg", eco: "bg-mode-eco-bg", empty: "bg-mode-empty-bg" };
export const MODE_FG: Record<ApartmentMode, string> = { comfort: "text-mode-comfort-fg", eco: "text-mode-eco-fg", empty: "text-mode-empty-fg" };
