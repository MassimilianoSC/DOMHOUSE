import type { QueryClient } from "@tanstack/react-query";
import { useApartmentStore } from "@/store/apartmentStore";
import { useFeatureStore } from "@/store/featureStore";

/**
 * Everything the previous user left in this tab (P-36): cached BFF answers, the live apartment store, the features
 * switched off at runtime and the assistant conversations. Called on every sign-out and when /app/me returns a
 * different user, so a second account (possibly of another organization) never sees, even for an instant, the data
 * of the first one. The service worker caches only the site's files, never BFF answers.
 */
export function clearUserData(queryClient: QueryClient) {
  queryClient.clear();
  useApartmentStore.getState().reset("");
  useFeatureStore.setState({ disabled: {} });
  try {
    for (const key of Object.keys(sessionStorage)) if (key.startsWith("assistant.")) sessionStorage.removeItem(key);
  } catch {
    /* storage unavailable: nothing was stored either */
  }
}
