import type { Eliminazione, PlatformApartment } from "@/api/platform";
import { deletionOffer, deletionSignature, deletionStepState, deletionStoppedAt, deletionWhat, nameMatches } from "./apartmentDeletion";
import { sortForPlatform } from "./apartmentCreation";

// A6 (docs/proposta-a6.md; bff/API.md «Eliminazione di un appartamento», o1-a6-eliminazione): what the row of a ready
// apartment offers (Disattiva, Riattiva, Elimina after 7 days), the steps of a deletion, its texts, and the polling.

const NOW = new Date("2026-11-20T16:00:00Z").getTime();
const APT: PlatformApartment = {
  apartment_id: "lab-ponte", name: "Bilocale Ponte", instance_url: "http://10.198.0.2:8151", port: null, enabled: true, timezone: "Europe/Rome",
  italianway_id: null, last_check: null, creazione: null, origine: "app", disattivato_at: null, disattivato_da: null, eliminabile_dal: null, eliminazione: null,
};
const apt = (over: Partial<PlatformApartment>): PlatformApartment => ({ ...APT, ...over });
const off = (over: Partial<PlatformApartment> = {}) =>
  apt({ enabled: false, disattivato_at: "2026-11-12T15:00:00Z", disattivato_da: { ruolo: "gestore", nome: "Giulia Rossi" }, eliminabile_dal: "2026-11-19T15:00:00Z", ...over });
const elim = (over: Partial<Eliminazione> = {}): Eliminazione => ({
  stato: "in_corso", passo: "segreti", codice: null, messaggio: null, op: null, version: 2, iniziata_at: "2026-11-20T15:50:00Z", updated_at: "2026-11-20T15:55:00Z", updated_by: "Giulia Rossi", ...over,
});

describe("cosa offre la riga", () => {
  it("attivo: solo «Disattiva»", () => {
    expect(deletionOffer(apt({}), NOW)).toEqual({ disable: true, reenable: false, del: "none" });
  });

  it("disattivato da meno di 7 giorni: «Riattiva», «Elimina» in attesa", () => {
    expect(deletionOffer(off({ eliminabile_dal: "2026-11-25T15:00:00Z" }), NOW)).toEqual({ disable: false, reenable: true, del: "wait" });
  });

  it("disattivato da 7 giorni: «Riattiva» ed «Elimina»", () => {
    expect(deletionOffer(off(), NOW)).toEqual({ disable: false, reenable: true, del: "ready" });
  });

  it("spento prima di A6 (senza ora): «Disattiva» fa partire i 7 giorni, «Elimina» spento", () => {
    expect(deletionOffer(off({ disattivato_at: null, disattivato_da: null, eliminabile_dal: null }), NOW)).toEqual({ disable: true, reenable: true, del: "noDate" });
  });

  it("dev: mai «Elimina» (D-118)", () => {
    expect(deletionOffer(off({ origine: "dev", eliminabile_dal: null }), NOW).del).toBe("none");
    expect(deletionOffer(off({ origine: "dev", disattivato_at: null, eliminabile_dal: null }), NOW).del).toBe("none");
  });

  it("con un'eliminazione partita: niente (la riga è quella dell'eliminazione)", () => {
    expect(deletionOffer(off({ eliminazione: elim() }), NOW)).toEqual({ disable: false, reenable: false, del: "none" });
  });
});

describe("i passi dell'eliminazione", () => {
  it("motore, chiavi, dati: fatto, in corso, da fare; fermo sul passo che non è riuscito", () => {
    const e = elim({ passo: "segreti" });
    expect(["motore", "segreti", "database"].map((p) => deletionStepState(e, p as Eliminazione["passo"]))).toEqual(["fatto", "in_corso", "da_fare"]);
    const stopped = elim({ stato: "non_riuscita", passo: "segreti" });
    expect(deletionStepState(stopped, "segreti")).toBe("fallito");
    expect(deletionStoppedAt(stopped)).toEqual({ passo: "segreti", n: 2, of: 3 });
  });

  it("«Cosa è successo»: il testo del sito per i codici noti, altrimenti la frase del server", () => {
    expect(deletionWhat(elim({ stato: "non_riuscita", codice: "tempo_scaduto" }))).toBe("Nessuna risposta dalla macchina virtuale in 20 minuti: «Riprova».");
    expect(deletionWhat(elim({ stato: "non_riuscita", codice: "non_inviato" }))).toBe("L'ordine non è partito verso la macchina virtuale: «Riprova».");
    expect(deletionWhat(elim({ stato: "non_riuscita", codice: "chiavi_non_distrutte" }))).toBe("Il sistema domotico è stato tolto, ma le chiavi no: «Riprova».");
    expect(deletionWhat(elim({ stato: "non_riuscita", codice: "non_creato_da_agente" }))).toBe("Il sistema domotico sulla macchina virtuale non risulta creato dall'app: serve il supporto (ID richiesta).");
    expect(deletionWhat(elim({ stato: "non_riuscita", codice: "errore_interno" }))).toBe("Errore interno del server: «Riprova», e se succede ancora serve un controllo (ID richiesta).");
    expect(deletionWhat(elim({ stato: "non_riuscita", codice: "nuovo", messaggio: "Frase del server" }))).toBe("Frase del server");
    expect(deletionWhat(elim({ stato: "non_riuscita", codice: null, messaggio: null }))).toBe("L'eliminazione si è fermata prima della fine: «Riprova».");
  });

  it("si rilegge solo mentre è in corso; «Riprova» cambia la version e riapre i 20 minuti", () => {
    expect(deletionSignature([apt({}), off({ eliminazione: elim({ stato: "non_riuscita" }) })])).toBe("");
    expect(deletionSignature([off({ eliminazione: elim({ version: 3 }) })])).toBe("lab-ponte:eliminazione:3");
    expect(deletionSignature(undefined)).toBe("");
  });

  it("nell'elenco: le eliminazioni non riuscite in alto, poi quelle in corso, poi gli altri", () => {
    const list = [apt({ apartment_id: "a" }), off({ apartment_id: "b", eliminazione: elim() }), off({ apartment_id: "c", eliminazione: elim({ stato: "non_riuscita" }) })];
    expect(sortForPlatform(list).map((a) => a.apartment_id)).toEqual(["c", "b", "a"]);
  });
});

describe("la conferma scrivendo il nome", () => {
  it("nome esatto, maiuscole comprese; gli spazi all'inizio e alla fine non contano; vuoto mai", () => {
    expect(nameMatches("Bilocale Ponte", "Bilocale Ponte")).toBe(true);
    expect(nameMatches("  Bilocale Ponte ", "Bilocale Ponte")).toBe(true);
    expect(nameMatches("bilocale ponte", "Bilocale Ponte")).toBe(false);
    expect(nameMatches("Bilocale", "Bilocale Ponte")).toBe(false);
    expect(nameMatches("   ", "")).toBe(false);
  });
});
