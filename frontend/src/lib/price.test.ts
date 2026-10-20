import { parsePrice, priceInput } from "./price";

// Price per kWh (P-52, D-92): what the admin may type; the BFF accepts 0-10 with at most 4 decimals.
describe("prezzo per kWh", () => {
  it("con la virgola o con il punto", () => {
    expect(parsePrice("0,25")).toBe(0.25);
    expect(parsePrice(" 0.2512 ")).toBe(0.2512);
    expect(parsePrice("0")).toBe(0);
    expect(parsePrice("10")).toBe(10);
  });

  it("vuoto: nessun prezzo (o quello dell'organizzazione)", () => {
    expect(parsePrice("")).toBeNull();
    expect(parsePrice("  ")).toBeNull();
  });

  it("non valido: troppi decimali, oltre 10, negativo, testo", () => {
    for (const bad of ["0,25123", "12", "100", "-1", "abc", "0,2,5", "1e2"]) expect(parsePrice(bad)).toBeUndefined();
  });

  it("il campo parte dal prezzo salvato, scritto all'italiana", () => {
    expect(priceInput(0.25)).toBe("0,25");
    expect(priceInput(null)).toBe("");
    expect(parsePrice(priceInput(0.1234))).toBe(0.1234);
  });
});
