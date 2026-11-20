// @vitest-environment node
import { getDailyHomeQuote, HOME_QUOTES_IT } from "./homeQuotes.it";

// «Spunto del giorno» (PR #19): one thought per local calendar day, the same all day, round again after the last.
describe("getDailyHomeQuote", () => {
  it("lo stesso per tutto il giorno, dal mattino alla sera", () => {
    expect(getDailyHomeQuote(new Date(2026, 10, 20, 0, 5))).toBe(getDailyHomeQuote(new Date(2026, 10, 20, 23, 55)));
  });

  it("cambia il giorno dopo", () => {
    expect(getDailyHomeQuote(new Date(2026, 10, 21, 9))).not.toBe(getDailyHomeQuote(new Date(2026, 10, 20, 9)));
  });

  it("dopo l'ultimo ricomincia dal primo", () => {
    const n = HOME_QUOTES_IT.length;
    expect(getDailyHomeQuote(new Date(2026, 10, 20 + n, 9))).toBe(getDailyHomeQuote(new Date(2026, 10, 20, 9)));
  });

  it("frasi non vuote, tutte diverse", () => {
    expect(HOME_QUOTES_IT.every((q) => q.trim().length > 0)).toBe(true);
    expect(new Set(HOME_QUOTES_IT).size).toBe(HOME_QUOTES_IT.length);
  });
});
