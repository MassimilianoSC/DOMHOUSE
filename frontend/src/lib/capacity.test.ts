import type { Capienza, CapienzaView } from "@/api/platform";
import { capacityLine, readAge, refreshState } from "./capacity";

// A7 (docs/proposta-a7.md §2 n. 5, §3; answers 1201, 1203): the line of the free places in «Nuovo appartamento», from
// the last reading the server keeps. Times in Rome: 2026-11-20 15:00 UTC is 16:00.

const NOW = new Date("2026-11-20T15:00:00Z").getTime();
const reading = (over: Partial<Capienza> = {}): Capienza => ({
  ambiente: "staging", letta_at: "2026-11-20T14:58:00Z", vecchia: false, posti_liberi: 2, motivo: null,
  motori_ambiente: 2, massimo_motori: 4, mem_available_mb: 900, tetto_nuovo_mb: 120, somma_tetti_mb: 240, budget_mb: 500, ...over,
});
const view = (over: Partial<CapienzaView> = {}): CapienzaView => ({ capienza: reading(), aggiornamento: null, aggiornabile_dal: null, ...over });
const op = (stato: "inviato" | "riuscito" | "rifiutato" | "fallito", creato_at: string, messaggio: string | null = null) =>
  ({ op_id: "3f9c2a71-0000-4000-8000-000000000007", stato, codice: stato === "riuscito" || stato === "inviato" ? null : "errore", messaggio, creato_at });

describe("la riga dei posti liberi", () => {
  it("lettura recente: posti e ora della lettura", () => {
    expect(capacityLine(reading(), NOW)).toEqual({ kind: "places", text: "Posti liberi nello staging: 2 (letto alle 15:58)" });
  });

  it("zero posti: la frase decisa, con l'ora della lettura, in giallo", () => {
    expect(capacityLine(reading({ posti_liberi: 0, motivo: "staging_pieno" }), NOW)).toEqual({
      kind: "zero", text: "Nessun posto libero: serve una VM più grande o la seconda VM (letto alle 15:58)",
    });
  });

  it("nessuna lettura: nessun numero inventato", () => {
    expect(capacityLine(null, NOW)).toEqual({ kind: "unread", text: "Capienza non ancora letta" });
  });

  it("in produzione dice «in produzione»", () => {
    expect(capacityLine(reading({ ambiente: "prod", posti_liberi: 1 }), NOW).text).toBe("Posti liberi in produzione: 1 (letto alle 15:58)");
  });

  it("lettura con più di 10 minuti: quanto tempo fa, anche se il server l'aveva data per recente", () => {
    expect(capacityLine(reading({ letta_at: "2026-11-20T14:35:00Z" }), NOW).text).toBe("Posti liberi nello staging: 2 (letto 25 minuti fa)");
    expect(capacityLine(reading({ letta_at: "2026-11-20T13:00:00Z", vecchia: true }), NOW).text).toBe("Posti liberi nello staging: 2 (letto 2 ore fa)");
  });
});

describe("l'età della lettura", () => {
  it("fino a 10 minuti l'ora; poi minuti, ore, e oltre un giorno la data", () => {
    expect(readAge("2026-11-20T14:50:00Z", false, NOW)).toBe("letto alle 15:50");
    expect(readAge("2026-11-20T14:49:00Z", false, NOW)).toBe("letto 11 minuti fa");
    expect(readAge("2026-11-20T14:58:00Z", true, NOW)).toBe("letto 2 minuti fa");
    expect(readAge("2026-11-20T14:00:00Z", false, NOW)).toBe("letto 1 ora fa");
    expect(readAge("2026-11-20T13:59:00Z", false, NOW)).toBe("letto 1 ora fa");
    expect(readAge("2026-11-19T15:01:00Z", false, NOW)).toBe("letto 23 ore fa");
    expect(readAge("2026-11-19T14:10:00Z", false, NOW)).toBe("letto il 19/11 alle 15:10");
  });
});

describe("«Aggiorna»: lo stato dell'ultimo ordine", () => {
  it("nessun ordine, o un ordine riuscito: niente da dire", () => {
    expect(refreshState(view(), NOW)).toEqual({ kind: "none" });
    expect(refreshState(view({ aggiornamento: op("riuscito", "2026-11-20T14:57:00Z") }), NOW)).toEqual({ kind: "none" });
  });

  it("ordine inviato dopo l'ultima lettura: «Lettura in corso…»", () => {
    expect(refreshState(view({ aggiornamento: op("inviato", "2026-11-20T14:59:00Z") }), NOW)).toEqual({ kind: "running" });
    expect(refreshState(view({ capienza: null, aggiornamento: op("inviato", "2026-11-20T14:59:00Z") }), NOW)).toEqual({ kind: "running" });
  });

  it("ordine non riuscito dopo l'ultima lettura: il messaggio del server e l'ID richiesta", () => {
    expect(refreshState(view({ aggiornamento: op("fallito", "2026-11-20T14:59:00Z", "L'agente non risponde") }), NOW)).toEqual({
      kind: "failed", text: "Lettura non riuscita: L'agente non risponde", requestId: "3f9c2a71-0000-4000-8000-000000000007",
    });
    expect(refreshState(view({ capienza: null, aggiornamento: op("rifiutato", "2026-11-20T14:59:00Z") }), NOW)).toEqual({
      kind: "failed", text: "Lettura non riuscita.", requestId: "3f9c2a71-0000-4000-8000-000000000007",
    });
  });

  it("un errore più vecchio dell'ultima lettura buona non si mostra più", () => {
    expect(refreshState(view({ aggiornamento: op("fallito", "2026-11-20T14:50:00Z", "vecchio") }), NOW)).toEqual({ kind: "none" });
  });

  it("20 minuti senza risposta: non riuscita, come «Prova l'agente»", () => {
    const late = view({ capienza: null, aggiornamento: op("inviato", "2026-11-20T14:40:00Z") });
    expect(refreshState(late, NOW)).toEqual({
      kind: "failed", text: "Lettura non riuscita: nessuna risposta dalla macchina virtuale in 20 minuti.", requestId: "3f9c2a71-0000-4000-8000-000000000007",
    });
    expect(refreshState(view({ capienza: null, aggiornamento: op("inviato", "2026-11-20T14:40:01Z") }), NOW)).toEqual({ kind: "running" });
  });
});
