import { create } from "zustand";
import type { AppFeature } from "@/api/types";

/** Contract x-features map, used to hide a feature when the instance answers 501 at runtime. */
const FEATURE_ROUTES: [string, RegExp, AppFeature][] = [
  ["GET", /^\/apartment$/, "apartment"],
  ["POST", /^\/apartment\/(mode|hold)$/, "apartment"],
  ["GET", /^\/devices$/, "devices"],
  ["PATCH", /^\/devices\/[^/]+$/, "devices"],
  ["POST", /^\/devices\/[^/]+\/commands$/, "commands"],
  ["GET", /^\/commands\/[^/]+$/, "commands"],
  ["GET", /^\/energy$/, "energy"],
  ["GET", /^\/schedule$/, "schedule"],
  ["POST", /^\/schedule$/, "schedule"],
  ["PATCH", /^\/schedule\/[^/]+$/, "schedule"],
  ["DELETE", /^\/schedule\/[^/]+$/, "schedule"],
  ["GET", /^\/rules$/, "rules"],
  ["PUT", /^\/rules$/, "rules"],
  ["GET", /^\/approvals$/, "approvals"],
  ["POST", /^\/approvals\/[^/]+\/decision$/, "approvals"],
  ["GET", /^\/decisions$/, "decisions"],
  ["POST", /^\/ask$/, "ask"],
  ["GET", /^\/ask\/[^/]+$/, "ask"],
];

export function featureForPath(method: string, path: string): AppFeature | null {
  const clean = path.split("?")[0];
  const hit = FEATURE_ROUTES.find(([m, re]) => m === method.toUpperCase() && re.test(clean));
  return hit ? hit[2] : null;
}

interface FeatureState {
  disabled: Record<string, AppFeature[]>;
  disable: (aptId: string, feature: AppFeature) => void;
}

export const useFeatureStore = create<FeatureState>((set) => ({
  disabled: {},
  disable: (aptId, feature) =>
    set((s) => {
      const cur = s.disabled[aptId] ?? [];
      return cur.includes(feature) ? s : { disabled: { ...s.disabled, [aptId]: [...cur, feature] } };
    }),
}));
