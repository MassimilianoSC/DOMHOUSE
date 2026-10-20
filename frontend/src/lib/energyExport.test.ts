import { downloadEnergyReport, monthLabel, recentMonths } from "./energyExport";

// Excel reports (P-52, D-92): which months can be chosen, and what is asked to the BFF.
const s = vi.hoisted(() => ({ download: vi.fn(async () => ({ blob: new Blob(["x"]), name: "consumi-apt-001-2026-10.xlsx" })), save: vi.fn() }));
vi.mock("@/api/bff", () => ({ bffDownload: s.download }));
vi.mock("@/lib/download", () => ({ saveFile: s.save }));

describe("rendiconti: mesi e richieste", () => {
  it("ultimi 12 mesi nel fuso dell'appartamento, dal corrente; attraversano l'anno", () => {
    const months = recentMonths("Europe/Rome", 12, new Date("2026-01-15T10:00:00Z"));
    expect(months).toHaveLength(12);
    expect(months[0]).toBe("2026-01");
    expect(months[1]).toBe("2025-12");
    expect(months[11]).toBe("2025-02");
  });

  it("il mese è quello locale: a Roma le 23:30 UTC del 31 ottobre sono già novembre", () => {
    expect(recentMonths("Europe/Rome", 1, new Date("2026-10-31T23:30:00Z"))).toEqual(["2026-11"]);
  });

  it("etichetta del mese in italiano", () => {
    expect(monthLabel("2026-10")).toBe("ottobre 2026");
  });

  it("mese: GET …/energy/export?month=…, e il file salvato con il nome del server", async () => {
    await downloadEnergyReport("apt-001", { month: "2026-10" }, "c-1");
    expect(s.download).toHaveBeenCalledWith("/app/apartments/apt-001/energy/export", { query: { month: "2026-10" }, correlationId: "c-1", fallbackName: "consumi-apt-001-2026-10.xlsx" });
    expect(s.save).toHaveBeenCalledWith(expect.any(Blob), "consumi-apt-001-2026-10.xlsx");
  });

  it("soggiorno: ?booking_id=…", async () => {
    await downloadEnergyReport("apt-001", { booking_id: "RES-1" }, "c-2");
    expect(s.download).toHaveBeenCalledWith("/app/apartments/apt-001/energy/export", expect.objectContaining({ query: { booking_id: "RES-1" }, fallbackName: "consumi-apt-001-RES-1.xlsx" }));
  });
});
