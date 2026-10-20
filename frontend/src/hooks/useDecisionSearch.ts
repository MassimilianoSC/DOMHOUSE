import { useCallback, useEffect, useRef, useState } from "react";
import { instanceApi } from "@/api/instance";
import type { Decision } from "@/api/types";
import { decisionQuery, type DecisionFilters } from "@/hooks/useDecisionLog";
import { isCorrelationId, NO_PROGRESS, PAGE_SIZE, runBatch, type SearchProgress } from "@/lib/decisionSearch";

const DEBOUNCE_MS = 400;

export interface DecisionSearch {
  /** idle = no word; searching = a batch is running; ready = batch over (more may follow); error = a page failed. */
  status: "idle" | "searching" | "ready" | "error";
  /** text = word read in batches; correlation = exact filter on a pasted request ID (whole log, one request). */
  mode: "text" | "correlation";
  progress: SearchProgress;
  error: unknown;
  /** Next batch, from where the previous one stopped ("Cerca più indietro"); also retries after an error. */
  more: () => void;
}

/**
 * Search in the whole decision log (P-32, D-49): starts by itself when the word settles, keeps the server filters
 * (Chi, Dispositivo, Periodo), and drops a running batch as soon as the word or a filter changes. New decisions that
 * arrive during a search are not part of it (the batches read backwards from where it started).
 */
export function useDecisionSearch(aptId: string, filters: DecisionFilters, text: string, test: (d: Decision, needle: string) => boolean): DecisionSearch {
  const [term, setTerm] = useState(text.trim());
  useEffect(() => {
    const id = setTimeout(() => setTerm(text.trim()), DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [text]);

  const [state, setState] = useState<Omit<DecisionSearch, "more">>({ status: "idle", mode: "text", progress: NO_PROGRESS, error: null });
  const generation = useRef(0);
  const testRef = useRef(test);
  testRef.current = test; // labels change while rules load: use the latest without restarting the search
  const progressRef = useRef(NO_PROGRESS);
  const [retry, setRetry] = useState(0);

  const batch = useCallback(
    async (from: SearchProgress, gen: number) => {
      const api = instanceApi(aptId);
      const query = decisionQuery(filters);
      setState((s) => ({ ...s, status: "searching", mode: "text", error: null }));
      try {
        const p = await runBatch((cursor) => api.listDecisions({ ...query, limit: PAGE_SIZE, cursor }), (d) => testRef.current(d, term), from, {
          isCancelled: () => gen !== generation.current,
          onPage: (pp) => {
            if (gen !== generation.current) return;
            progressRef.current = pp;
            setState((s) => ({ ...s, progress: pp }));
          },
        });
        if (gen !== generation.current) return;
        progressRef.current = p;
        setState({ status: "ready", mode: "text", progress: p, error: null });
      } catch (err) {
        if (gen === generation.current) setState((s) => ({ ...s, status: "error", error: err }));
      }
    },
    [aptId, filters, term],
  );

  useEffect(() => {
    const gen = ++generation.current;
    progressRef.current = NO_PROGRESS;
    if (!term) {
      setState({ status: "idle", mode: "text", progress: NO_PROGRESS, error: null });
      return;
    }
    if (isCorrelationId(term)) {
      setState({ status: "searching", mode: "correlation", progress: NO_PROGRESS, error: null });
      instanceApi(aptId)
        .listDecisions({ correlation_id: term, limit: PAGE_SIZE })
        .then((page) => {
          if (gen !== generation.current) return;
          const items = page.items;
          setState({ status: "ready", mode: "correlation", progress: { results: items, scanned: items.length, oldestTs: items.at(-1)?.ts ?? null, cursor: null, done: true, limited: false }, error: null });
        })
        .catch((err) => gen === generation.current && setState((s) => ({ ...s, status: "error", error: err })));
      return;
    }
    void batch(NO_PROGRESS, gen);
    // `batch` is deliberately left out: it changes with every render, the search must restart only on these.
  }, [aptId, term, filters.actor, filters.device_id, filters.from, retry]);

  const more = useCallback(() => {
    if (!term || state.status === "searching") return;
    if (isCorrelationId(term)) setRetry((n) => n + 1); // a single request: "Riprova" asks again
    else void batch(progressRef.current, generation.current);
  }, [batch, state.status, term]);

  return { ...state, more };
}
