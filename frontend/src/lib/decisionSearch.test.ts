// @vitest-environment node
import type { Decision } from "@/api/types";
import { BATCH_PAGES, isCorrelationId, matchesDecision, MAX_RESULTS, NO_PROGRESS, PAGE_SIZE, periodFrom, runBatch, STOP_AT, type PageFetcher } from "./decisionSearch";

// Search in the whole decision log (P-32, D-49): batches of pages read backwards, limits approved with D-49.
const dec = (n: number, reasoning = `motivo ${n}`): Decision =>
  ({ decision_id: `d-${n}`, ts: new Date(Date.UTC(2026, 9, 16) - n * 60_000).toISOString(), actor: "brain", target: { type: "apartment" }, action: "mode", old_value: null, new_value: null, reasoning, outcome: "applied", correlation_id: `c-${n}`, command_id: null, approval_id: null }) as Decision;

/** A log of `total` decisions where those with n % every === 0 contain the word "finestra". */
function log(total: number, every: number) {
  const calls: (string | undefined)[] = [];
  let inFlight = 0;
  let maxInFlight = 0;
  const fetchPage: PageFetcher = async (cursor) => {
    calls.push(cursor);
    inFlight++;
    maxInFlight = Math.max(maxInFlight, inFlight);
    await new Promise((r) => setTimeout(r, 1));
    inFlight--;
    const start = cursor ? Number(cursor) : 0;
    const items = Array.from({ length: Math.min(PAGE_SIZE, total - start) }, (_, i) => dec(start + i, (start + i) % every === 0 ? "finestra aperta" : "altro"));
    return { items, next_cursor: start + items.length < total ? String(start + items.length) : null };
  };
  return { fetchPage, calls, maxInFlight: () => maxInFlight };
}
const hasWord = (d: Decision) => d.reasoning.includes("finestra");

describe("ricerca nelle decisioni: lotti", () => {
  it("un lotto legge al massimo 5 pagine da 200, una dopo l'altra, poi si ferma dicendo fin dove è arrivato", async () => {
    const l = log(5000, 1000); // few results: the batch ends by pages
    const p = await runBatch(l.fetchPage, hasWord, NO_PROGRESS);
    expect(l.calls).toEqual([undefined, "200", "400", "600", "800"]);
    expect(l.calls).toHaveLength(BATCH_PAGES);
    expect(l.maxInFlight()).toBe(1);
    expect(p).toMatchObject({ scanned: 1000, cursor: "1000", done: false, limited: false });
    expect(p.results.map((d) => d.decision_id)).toEqual(["d-0"]);
    expect(p.oldestTs).toBe(dec(999).ts);
  });

  it("«Cerca più indietro»: il lotto dopo riparte dal cursore e somma i risultati", async () => {
    const l = log(5000, 1000);
    const first = await runBatch(l.fetchPage, hasWord, NO_PROGRESS);
    const second = await runBatch(l.fetchPage, hasWord, first);
    expect(l.calls.slice(5)).toEqual(["1000", "1200", "1400", "1600", "1800"]);
    expect(second.results.map((d) => d.decision_id)).toEqual(["d-0", "d-1000"]);
    expect(second.scanned).toBe(2000);
  });

  it("si ferma prima appena un lotto trova 50 risultati", async () => {
    const l = log(5000, 2); // half the rows match: 100 per page
    const p = await runBatch(l.fetchPage, hasWord, NO_PROGRESS);
    expect(l.calls).toHaveLength(1);
    expect(p.results.length).toBeGreaterThanOrEqual(STOP_AT);
  });

  it("fine dello storico: «done», nessuna pagina in più", async () => {
    const l = log(450, 1000);
    const p = await runBatch(l.fetchPage, hasWord, NO_PROGRESS);
    expect(l.calls).toHaveLength(3);
    expect(p).toMatchObject({ done: true, cursor: null, scanned: 450 });
    expect(await runBatch(l.fetchPage, hasWord, p)).toBe(p);
    expect(l.calls).toHaveLength(3);
  });

  it("al massimo 3.000 risultati in memoria: poi «limited» e ci si ferma", async () => {
    const l = log(5000, 1); // every row matches
    const almost = { ...NO_PROGRESS, results: Array.from({ length: MAX_RESULTS - 10 }, (_, i) => dec(100_000 + i)), cursor: "0" };
    const p = await runBatch(l.fetchPage, hasWord, almost);
    expect(p.results).toHaveLength(MAX_RESULTS);
    expect(p.limited).toBe(true);
    expect(await runBatch(l.fetchPage, hasWord, p)).toBe(p);
  });

  it("cambiando parola durante un lotto, la pagina in arrivo viene scartata", async () => {
    const l = log(5000, 1000);
    let cancelled = false;
    const p = await runBatch(l.fetchPage, hasWord, NO_PROGRESS, { isCancelled: () => cancelled, onPage: () => (cancelled = true) });
    expect(l.calls).toHaveLength(2);
    expect(p.scanned).toBe(200);
  });
});

describe("ricerca nelle decisioni: cosa si cerca", () => {
  it("riconosce un ID richiesta completo, non un pezzo", () => {
    expect(isCorrelationId("3f2a9c1e-7b4d-4e8a-9c0f-1a2b3c4d5e6f")).toBe(true);
    expect(isCorrelationId(" 3F2A9C1E-7B4D-4E8A-9C0F-1A2B3C4D5E6F ")).toBe(true);
    expect(isCorrelationId("3f2a9c1e")).toBe(false);
    expect(isCorrelationId("finestra")).toBe(false);
  });

  it("cerca in motivo, azione, chi, dispositivo, valori e codici, senza badare alle maiuscole", () => {
    const d = { ...dec(1, "Finestra aperta da 20 minuti"), action: "turn_off", new_value: "spento", command_id: "cmd-77", correlation_id: "3f2a9c1e-7b4d" } as Decision;
    const labels = { actor: "Regola «Finestra aperta»", target: "Clima soggiorno" };
    for (const w of ["finestra", "TURN_OFF", "spento", "cmd-77", "3f2a9c1e", "soggiorno", "regola"]) expect(matchesDecision(d, w, labels)).toBe(true);
    expect(matchesDecision(d, "caldaia", labels)).toBe(false);
  });

  it("periodo: 0 = tutto lo storico, altrimenti N giorni fa", () => {
    expect(periodFrom(0)).toBeUndefined();
    expect(periodFrom(7, Date.UTC(2026, 9, 16))).toBe(new Date(Date.UTC(2026, 9, 9)).toISOString());
  });
});
