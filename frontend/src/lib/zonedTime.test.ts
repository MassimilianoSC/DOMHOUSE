import { instantToWall, wallDaysFromToday, wallToInstant, zonedToInstant } from "./zonedTime";

// D-212: the apartment's date and time ↔ an instant, right on the two nights the clocks change. The expected instants
// are those of Python's zoneinfo with the default fold=0 (the engine's and the server's rule), checked one by one.
const ROME = "Europe/Rome";
const at = (value: string, tz = ROME) => {
  const r = wallToInstant(value, tz);
  return r && { iso: r.at.toISOString(), kind: r.kind };
};

describe("ora dell'appartamento → istante (D-212)", () => {
  it("un giorno normale, d'inverno e d'estate", () => {
    expect(at("2027-01-15T10:00")).toEqual({ iso: "2027-01-15T09:00:00.000Z", kind: "exact" });
    expect(at("2027-07-15T10:00")).toEqual({ iso: "2027-07-15T08:00:00.000Z", kind: "exact" });
  });

  it("28 marzo 2027, gli orologi vanno avanti: prima del salto e dopo, l'ora giusta", () => {
    expect(at("2027-03-28T00:00")).toEqual({ iso: "2027-03-27T23:00:00.000Z", kind: "exact" });
    expect(at("2027-03-28T01:30")).toEqual({ iso: "2027-03-28T00:30:00.000Z", kind: "exact" });
    expect(at("2027-03-28T01:59")).toEqual({ iso: "2027-03-28T00:59:00.000Z", kind: "exact" });
    expect(at("2027-03-28T03:00")).toEqual({ iso: "2027-03-28T01:00:00.000Z", kind: "exact" });
    expect(at("2027-03-28T03:30")).toEqual({ iso: "2027-03-28T01:30:00.000Z", kind: "exact" });
    expect(at("2027-03-28T23:59")).toEqual({ iso: "2027-03-28T21:59:00.000Z", kind: "exact" });
  });

  it("28 marzo 2027, dalle 02:00 alle 02:59 non esistono: spostate avanti di un'ora", () => {
    expect(at("2027-03-28T02:00")).toEqual({ iso: "2027-03-28T01:00:00.000Z", kind: "skipped" });
    expect(at("2027-03-28T02:30")).toEqual({ iso: "2027-03-28T01:30:00.000Z", kind: "skipped" });
    expect(at("2027-03-28T02:59")).toEqual({ iso: "2027-03-28T01:59:00.000Z", kind: "skipped" });
    expect(instantToWall(new Date("2027-03-28T01:30:00Z"), ROME)).toBe("2027-03-28T03:30");
  });

  it("31 ottobre 2027, gli orologi tornano indietro: prima e dopo l'ora doppia, l'ora giusta", () => {
    expect(at("2027-10-31T00:00")).toEqual({ iso: "2027-10-30T22:00:00.000Z", kind: "exact" });
    expect(at("2027-10-31T01:30")).toEqual({ iso: "2027-10-30T23:30:00.000Z", kind: "exact" });
    expect(at("2027-10-31T03:00")).toEqual({ iso: "2027-10-31T02:00:00.000Z", kind: "exact" });
    expect(at("2027-10-31T03:30")).toEqual({ iso: "2027-10-31T02:30:00.000Z", kind: "exact" });
  });

  it("31 ottobre 2027, dalle 02:00 alle 02:59 capitano due volte: la prima, ancora con l'ora legale", () => {
    expect(at("2027-10-31T02:00")).toEqual({ iso: "2027-10-31T00:00:00.000Z", kind: "repeated" });
    expect(at("2027-10-31T02:30")).toEqual({ iso: "2027-10-31T00:30:00.000Z", kind: "repeated" });
    expect(at("2027-10-31T02:59")).toEqual({ iso: "2027-10-31T00:59:00.000Z", kind: "repeated" });
  });

  it("i casi trovati da o1: 01:30 e 02:30 di marzo, 01:30 di ottobre", () => {
    expect(instantToWall(wallToInstant("2027-03-28T01:30", ROME)!.at, ROME)).toBe("2027-03-28T01:30"); // era 00:30
    expect(instantToWall(wallToInstant("2027-03-28T02:30", ROME)!.at, ROME)).toBe("2027-03-28T03:30"); // era 01:30
    expect(instantToWall(wallToInstant("2027-10-31T01:30", ROME)!.at, ROME)).toBe("2027-10-31T01:30"); // era 02:30
  });

  it("ogni minuto dei quattro giorni di cambio del 2026 e del 2027, andata e ritorno: l'ora che si legge è quella scelta, salvo il salto di marzo", () => {
    for (const day of ["2027-03-28", "2027-10-31", "2026-03-29", "2026-10-25"]) {
      for (let m = 0; m < 24 * 60; m++) {
        const value = `${day}T${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
        const r = wallToInstant(value, ROME)!;
        const back = instantToWall(r.at, ROME);
        if (r.kind === "skipped") expect(back).toBe(`${day}T03:${value.slice(14)}`);
        else expect(back).toBe(value);
      }
    }
  });

  it("altri fusi: New York (cambio alle 02:00 locali), Lord Howe (salto di mezz'ora), Kolkata (mai cambio)", () => {
    expect(at("2027-03-14T02:30", "America/New_York")).toEqual({ iso: "2027-03-14T07:30:00.000Z", kind: "skipped" });
    expect(at("2027-11-07T01:30", "America/New_York")).toEqual({ iso: "2027-11-07T05:30:00.000Z", kind: "repeated" });
    expect(instantToWall(wallToInstant("2027-10-03T02:15", "Australia/Lord_Howe")!.at, "Australia/Lord_Howe")).toBe("2027-10-03T02:45");
    expect(at("2027-03-28T02:30", "Asia/Kolkata")).toEqual({ iso: "2027-03-27T21:00:00.000Z", kind: "exact" });
    expect(at("2027-03-28T02:30", "UTC")).toEqual({ iso: "2027-03-28T02:30:00.000Z", kind: "exact" });
  });

  it("valori non validi: nessun istante", () => {
    for (const v of ["", "abc", "2027-02-30T10:00", "2027-04-31T10:00", "2027-13-01T10:00", "2027-03-28T24:00", "2027-03-28T10:60", "2027-03-28"]) {
      expect(wallToInstant(v, ROME)).toBeNull();
    }
  });

  it("i secondi del campo, se il browser li mette, non cambiano il minuto", () => {
    expect(at("2027-01-15T10:00:00")).toEqual({ iso: "2027-01-15T09:00:00.000Z", kind: "exact" });
  });

  it("anche dai numeri: la stessa regola", () => {
    expect(zonedToInstant(2027, 3, 28, 2, 30, ROME)).toEqual({ at: new Date("2027-03-28T01:30:00Z"), kind: "skipped" });
  });
});

describe("istante → ora dell'appartamento, e i giorni da oggi (D-212)", () => {
  it("l'ora dell'appartamento, non quella del browser", () => {
    expect(instantToWall(new Date("2027-07-15T22:30:00Z"), ROME)).toBe("2027-07-16T00:30");
    expect(instantToWall(new Date("2027-07-15T22:30:00Z"), "America/New_York")).toBe("2027-07-15T18:30");
  });

  it("oggi è il giorno dell'appartamento: a Roma è già domani mentre a UTC è ancora oggi", () => {
    const now = new Date("2027-03-27T23:30:00Z"); // Rome: 28 March, 00:30
    expect(wallDaysFromToday(ROME, 0, 15, 0, now)).toBe("2027-03-28T15:00");
    expect(wallDaysFromToday(ROME, 1, 15, 0, now)).toBe("2027-03-29T15:00");
    expect(wallDaysFromToday(ROME, -29, 0, 0, now)).toBe("2027-02-27T00:00");
    expect(wallDaysFromToday("UTC", 0, 15, 0, now)).toBe("2027-03-27T15:00");
  });
});
