import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

/** The query parameter that holds the open tab of a page with tabs (Amministrazione, Organizzazioni). */
export const TAB_PARAM = "scheda";

/**
 * The open tab kept in the address as ?scheda=<Italian slug> (design lot 2): a reload, «indietro» and a bookmark
 * reopen the same tab. No route changes: the page stays on its path. The first tab is the default and leaves the
 * address clean; an unknown slug falls back to it.
 */
export function useTabParam<T extends string>(slugs: Record<T, string>, fallback: T): [T, (tab: T) => void] {
  const [params, setParams] = useSearchParams();
  const slug = params.get(TAB_PARAM);
  const tab = ((Object.keys(slugs) as T[]).find((k) => slugs[k] === slug) ?? fallback) as T;
  const setTab = useCallback(
    (next: T) => {
      setParams(
        (prev) => {
          const p = new URLSearchParams(prev);
          if (next === fallback) p.delete(TAB_PARAM);
          else p.set(TAB_PARAM, slugs[next]);
          return p;
        },
        { replace: false },
      );
    },
    [setParams, slugs, fallback],
  );
  return [tab, setTab];
}
