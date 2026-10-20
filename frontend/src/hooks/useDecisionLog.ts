import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { instanceApi } from "@/api/instance";
import type { Decision } from "@/api/types";

export const DECISIONS_PAGE = 30;

export interface DecisionFilters {
  actor?: string;
  device_id?: string;
  /** Start of the period (ISO), fixed when the period is chosen: never recomputed per render, it is part of the key. */
  from?: string;
}

export const decisionQuery = (f: DecisionFilters) => ({ actor: f.actor || undefined, device_id: f.device_id || undefined, from: f.from || undefined });

/**
 * Decision log of an apartment: the newest page is a query refreshed every 30 s and on decision.logged (the stream
 * invalidates ["decisions", aptId]); older pages, loaded with "Carica altri", live in local state and are never
 * re-fetched. A refresh therefore always costs one request to the engine, however many pages are on screen (with an
 * infinite query React Query re-fetched every loaded page on each refresh).
 */
export function useDecisionLog(aptId: string, filters: DecisionFilters) {
  const head = useQuery({
    queryKey: ["decisions", aptId, filters.actor ?? "", filters.device_id ?? "", filters.from ?? ""],
    queryFn: () => instanceApi(aptId).listDecisions({ ...decisionQuery(filters), limit: DECISIONS_PAGE }),
    refetchInterval: 30_000,
  });

  const [tail, setTail] = useState<{ items: Decision[]; cursor: string | null; started: boolean }>({ items: [], cursor: null, started: false });
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreError, setMoreError] = useState<unknown>(null);
  const generation = useRef(0);

  // New filters: a different log, so the older pages start again from the new first page.
  useEffect(() => {
    generation.current += 1;
    setTail({ items: [], cursor: null, started: false });
    setMoreError(null);
    setLoadingMore(false);
  }, [aptId, filters.actor, filters.device_id, filters.from]);

  // The tail continues from the cursor of the first page it followed, not from a refreshed head (which moves forward).
  const cursor = tail.started ? tail.cursor : head.data?.next_cursor ?? null;

  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return;
    const gen = generation.current;
    setLoadingMore(true);
    setMoreError(null);
    try {
      const page = await instanceApi(aptId).listDecisions({ ...decisionQuery(filters), limit: DECISIONS_PAGE, cursor });
      if (gen !== generation.current) return; // filters changed meanwhile: drop the stale page
      setTail((t) => ({ items: [...t.items, ...page.items], cursor: page.next_cursor ?? null, started: true }));
    } catch (err) {
      if (gen === generation.current) setMoreError(err);
    } finally {
      if (gen === generation.current) setLoadingMore(false);
    }
  }, [aptId, cursor, filters, loadingMore]);

  // Head first; a decision that slid from the head into the tail between refreshes is shown once.
  const items = useMemo(() => {
    const seen = new Set<string>();
    return [...(head.data?.items ?? []), ...tail.items].filter((d) => (seen.has(d.decision_id) ? false : (seen.add(d.decision_id), true)));
  }, [head.data, tail.items]);

  return { items, head, hasMore: Boolean(cursor), loadMore, loadingMore, moreError };
}
