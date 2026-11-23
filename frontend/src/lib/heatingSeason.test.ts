import { SEASON_KEYS, ZONES, dayExists, dayName, elides, seasonOf, seasonParams, zoneOf } from "./heatingSeason";

// Item 15: the heating season of «Limiti del setpoint», four numbers in the engine's rule (o1, option A), the legal dates
// of the climatic zones (DPR 74/2013, art. 4, comma 2) as shortcuts, and whether a day exists in its month.

describe("le date di legge per zona climatica (DPR 74/2013, art. 4)", () => {
  it("le sei zone, con la E di Rimini e Bologna dal 15 ottobre al 15 aprile e la F tutto l'anno", () => {
    expect(ZONES).toEqual({
      A: { start: { month: 12, day: 1 }, end: { month: 3, day: 15 } },
      B: { start: { month: 12, day: 1 }, end: { month: 3, day: 31 } },
      C: { start: { month: 11, day: 15 }, end: { month: 3, day: 31 } },
      D: { start: { month: 11, day: 1 }, end: { month: 4, day: 15 } },
      E: { start: { month: 10, day: 15 }, end: { month: 4, day: 15 } },
      F: { start: { month: 1, day: 1 }, end: { month: 12, day: 31 } },
    });
  });

  it("la zona di una stagione, se le date sono quelle di legge; altrimenti nessuna", () => {
    expect(zoneOf(ZONES.E)).toBe("E");
    expect(zoneOf(ZONES.F)).toBe("F");
    expect(zoneOf({ start: { month: 10, day: 16 }, end: { month: 4, day: 15 } })).toBeNull();
    expect(zoneOf(null)).toBeNull();
  });
});

describe("un giorno esiste nel suo mese", () => {
  it.each([
    [4, 30, true], [4, 31, false], [2, 28, true], [2, 29, true], [2, 30, false], [12, 31, true], [1, 1, true],
    [1, 0, false], [13, 1, false], [0, 10, false], [6, 31, false], [10, 15.5, false],
  ])("mese %s, giorno %s: %s", (month, day, ok) => {
    expect(dayExists(month, day)).toBe(ok);
  });
});

describe("le date in italiano (rilettura, punto 6)", () => {
  it("«1º» per il primo del mese, il resto in cifre", () => {
    expect(dayName({ month: 12, day: 1 })).toBe("1º dicembre");
    expect(dayName({ month: 4, day: 15 })).toBe("15 aprile");
  });

  it("l'apostrofo davanti all'8 e all'11 («dall'8», «all'11»), non davanti agli altri", () => {
    expect([1, 8, 11, 18, 21].map(elides)).toEqual([false, true, true, false, false]);
  });
});

describe("i quattro parametri della regola", () => {
  it("i nomi del motore", () => {
    expect(SEASON_KEYS).toEqual({
      startMonth: "season_start_month",
      startDay: "season_start_day",
      endMonth: "season_end_month",
      endDay: "season_end_day",
    });
  });

  it("dai parametri alla stagione; senza uno dei quattro, nessuna stagione (un motore di prima)", () => {
    expect(seasonOf({ season_start_month: 10, season_start_day: 15, season_end_month: 4, season_end_day: 15, min: 7 })).toEqual(ZONES.E);
    expect(seasonOf({ season_start_month: 10, season_start_day: 15, season_end_month: 4 })).toBeNull();
  });

  it("dalla stagione ai parametri, per le scorciatoie", () => {
    expect(seasonParams(ZONES.C)).toEqual({ season_start_month: 11, season_start_day: 15, season_end_month: 3, season_end_day: 31 });
  });
});
