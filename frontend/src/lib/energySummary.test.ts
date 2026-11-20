// @vitest-environment node
import type { ApartmentSummary } from "@/api/types";
import { energySummary } from "./energySummary";

// «Consumo registrato oggi» on the apartments page (PR #19 of Luca, retouched after the merge, 1187): the sum of each
// apartment's kwh_today (the engine's /energy from local midnight to now, bff/instances.py). A demonstration apartment
// has simulated numbers: next to real ones it stays out of the total and the box says so; alone, the box says the data
// are simulated.

const apt = (id: string, kwh: number | null, simulated = false) => ({ apartment_id: id, kwh_today: kwh, simulated }) as ApartmentSummary;

describe("energySummary", () => {
  it("somma solo i valori presenti e dice per quanti appartamenti c'è il dato", () => {
    expect(energySummary([apt("a", 4.9), apt("b", null), apt("c", 1.1)])).toEqual({ total: 6, withData: 2, counted: 3, demosExcluded: 0, demoOnly: false });
  });

  it("i dimostrativi accanto ai veri restano fuori dal totale, e si contano a parte", () => {
    expect(energySummary([apt("vero", 2.5), apt("demo-1", 4.9, true), apt("demo-2", 4.6, true)])).toEqual({ total: 2.5, withData: 1, counted: 1, demosExcluded: 2, demoOnly: false });
  });

  it("solo dimostrativi: il totale è il loro, segnalato come simulato", () => {
    expect(energySummary([apt("demo-1", 4.9, true), apt("demo-2", 4.6, true)])).toEqual({ total: 9.5, withData: 2, counted: 2, demosExcluded: 0, demoOnly: true });
  });

  it("nessun dato: totale null, mai zero", () => {
    expect(energySummary([apt("a", null)]).total).toBeNull();
    expect(energySummary([]).total).toBeNull();
  });

  it("valori non validi (negativi, NaN, infiniti) non entrano nella somma", () => {
    expect(energySummary([apt("a", -1), apt("b", Number.NaN), apt("c", Number.POSITIVE_INFINITY), apt("d", 3)])).toMatchObject({ total: 3, withData: 1, counted: 4 });
  });
});
