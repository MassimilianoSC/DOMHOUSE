import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import { t } from "@/i18n";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const env = {
  bffUrl: (import.meta.env.VITE_BFF_URL || "").replace(/\/$/, ""),
  appName: t("app.name"),
  authMode: import.meta.env.VITE_AUTH_MODE === "firebase" ? "firebase" : "dev",
  fcmEnabled: import.meta.env.VITE_FCM_ENABLED === "true",
} as const;

export const newCorrelationId = () => crypto.randomUUID();
