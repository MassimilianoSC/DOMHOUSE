import type { Decision } from "@/api/types";

// Search in the whole decision log (P-32, D-49) with the contract as it is: GET /decisions has no text filter, so the
// site reads the log backwards in batches and filters by word itself; a pasted request ID uses the exact
// correlation_id filter instead. Limits approved with D-49: pages of 200 (the contract maximum), 5 pages per batch,
// a batch stops early at 50 new results, at most 3,000 results kept in memory (rows that do not match are dropped).

export const PAGE_SIZE = 200;
export const BATCH_PAGES = 5;
export const STOP_AT = 50;
export const MAX_RESULTS = 3000;

/** A full request ID, as copied by the "ID richiesta" button. */
export const isCorrelationId = (s: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s.trim());

export interface SearchProgress {
  results: Decision[];
  scanned: number;
  /** Time of the oldest decision examined so far: "cercato fino al …". */
  oldestTs: string | null;
  cursor: string | null;
  /** The log has no older decisions (or the period is exhausted). */
  done: boolean;
  /** MAX_RESULTS reached: the user must narrow the search. */
  limited: boolean;
}

export const NO_PROGRESS: SearchProgress = { results: [], scanned: 0, oldestTs: null, cursor: null, done: false, limited: false };

export type PageFetcher = (cursor: string | undefined) => Promise<{ items: Decision[]; next_cursor?: string | null }>;

/**
 * One batch: pages are read one after the other (never in parallel, to spare the engine) from where the previous
 * batch stopped. `isCancelled` drops the batch when the word or a filter changed meanwhile.
 */
export async function runBatch(
  fetchPage: PageFetcher,
  test: (d: Decision) => boolean,
  from: SearchProgress,
  opts: { isCancelled?: () => boolean; onPage?: (p: SearchProgress) => void } = {},
): Promise<SearchProgress> {
  let p = from;
  let found = 0;
  for (let i = 0; i < BATCH_PAGES && !p.done && !p.limited; i++) {
    const page = await fetchPage(p.cursor ?? undefined);
    if (opts.isCancelled?.()) return p;
    const hits = page.items.filter(test);
    const total = p.results.length + hits.length;
    p = {
      results: [...p.results, ...hits].slice(0, MAX_RESULTS),
      scanned: p.scanned + page.items.length,
      oldestTs: page.items.at(-1)?.ts ?? p.oldestTs,
      cursor: page.next_cursor ?? null,
      done: !page.next_cursor,
      limited: total >= MAX_RESULTS,
    };
    found += hits.length;
    opts.onPage?.(p);
    if (found >= STOP_AT) break;
  }
  return p;
}

/** Case-insensitive match on everything the row shows, ids included (a partial request ID is found here). */
export function matchesDecision(d: Decision, needle: string, labels: { actor: string; target: string; action?: string }): boolean {
  const n = needle.trim().toLowerCase();
  if (!n) return true;
  return [d.reasoning, d.action, labels.action, d.actor, labels.actor, labels.target, d.old_value, d.new_value, d.correlation_id, d.command_id, d.approval_id]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
    .includes(n);
}

/** Period menu → `from` for GET /decisions (undefined = the whole log). */
export function periodFrom(days: number, now = Date.now()): string | undefined {
  return days > 0 ? new Date(now - days * 86_400_000).toISOString() : undefined;
}
