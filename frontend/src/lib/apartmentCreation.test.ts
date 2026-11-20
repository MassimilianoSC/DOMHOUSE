import { ApiError } from "@/api/bff";
import type { Creazione, PlatformApartment } from "@/api/platform";
import {
  CREATION_STEPS,
  creationRefetch,
  freeFromText,
  isUsable,
  MAX_POLL_MS,
  newIdProblem,
  POLL_MS,
  rateLimitOf,
  sortForPlatform,
  stepState,
  stoppedAt,
  tenantCreationLine,
  whatHappened,
} from "./apartmentCreation";

// A2, the rules of the new apartment and of its creation that do not depend on React (docs/proposta-a2-sito.md §2, §3,
// §4; server shapes in docs/proposta-a2.md §2.1, §2.2, §6).

const creazione = (over: Partial<Creazione> = {}): Creazione => ({
  stato: "in_preparazione", passo: "segreti", version: 3, porta: 8153, op: null, fatti: ["id", "porta"], updated_at: "2026-11-20T10:00:00Z", updated_by: "Giulia Rossi", ...over,
});
const apt = (apartment_id: string, c: Creazione | null): PlatformApartment => ({
  apartment_id, name: apartment_id, instance_url: "", port: null, enabled: true, timezone: "Europe/Rome", italianway_id: null, last_check: null, creazione: c,
});

describe("l'id di un appartamento nuovo (§2.1)", () => {
  it.each(["lab-prova", "test-1", "lab-a", "lab-casa-2", `lab-${"a".repeat(60)}`])("accetta %s", (id) => {
    expect(newIdProblem(id)).toBeNull();
  });
  it.each([
    ["", "empty"],
    ["   ", "empty"],
    ["prova", "invalid"],
    ["dev", "invalid"],
    ["lab-", "invalid"],
    ["lab-Prova", "invalid"],
    ["lab-prova-", "invalid"],
    ["lab--", "invalid"],
    ["lab_prova", "invalid"],
    ["apt-001", "invalid"],
    [`lab-${"a".repeat(61)}`, "invalid"],
    ["lab-casa-devices", "invalid"],
  ])("rifiuta «%s» (%s)", (id, problem) => {
    expect(newIdProblem(id)).toBe(problem);
  });
  it("gli spazi ai lati non contano", () => {
    expect(newIdProblem("  lab-prova ")).toBeNull();
  });
});

describe("i cinque passi (§3.3)", () => {
  it("nell'ordine della proposta", () => {
    expect(CREATION_STEPS).toEqual(["riserva", "segreti", "capienza", "motore", "collegamento"]);
  });
  it("in preparazione: quelli prima del passo raggiunto sono fatti, quello è in corso, gli altri da fare", () => {
    const c = creazione({ passo: "capienza" });
    expect(CREATION_STEPS.map((p) => stepState(c, p))).toEqual(["fatto", "fatto", "in_corso", "da_fare", "da_fare"]);
  });
  it("non creato: il passo raggiunto è quello fallito", () => {
    const c = creazione({ stato: "non_creato", passo: "motore" });
    expect(stepState(c, "motore")).toBe("fallito");
    expect(stepState(c, "capienza")).toBe("fatto");
    expect(stepState(c, "collegamento")).toBe("da_fare");
    expect(stoppedAt(c)).toEqual({ passo: "motore", n: 4, of: 5 });
  });
  it("pronto: tutti fatti", () => {
    const c = creazione({ stato: "pronto", passo: "collegamento" });
    expect(CREATION_STEPS.every((p) => stepState(c, p) === "fatto")).toBe(true);
  });
});

describe("chi è usabile e l'ordine nell'elenco della piattaforma (§3.1)", () => {
  it("usabile: collegato a mano (creazione null) o pronto", () => {
    expect(isUsable(apt("a", null))).toBe(true);
    expect(isUsable(apt("a", creazione({ stato: "pronto" })))).toBe(true);
    expect(isUsable(apt("a", creazione()))).toBe(false);
    expect(isUsable(apt("a", creazione({ stato: "non_creato" })))).toBe(false);
    expect(isUsable(apt("a", creazione({ stato: "annullamento_in_corso" })))).toBe(false);
  });
  it("prima i non creati, poi in preparazione e annullamento, poi gli altri nell'ordine del server", () => {
    const list = [
      apt("pronto-1", null),
      apt("prep", creazione()),
      apt("pronto-2", creazione({ stato: "pronto" })),
      apt("rotto", creazione({ stato: "non_creato" })),
      apt("via", creazione({ stato: "annullamento_in_corso" })),
      apt("pronto-3", null),
    ];
    expect(sortForPlatform(list).map((a) => a.apartment_id)).toEqual(["rotto", "prep", "via", "pronto-1", "pronto-2", "pronto-3"]);
  });
  it("non cambia l'elenco ricevuto", () => {
    const list = [apt("b", null), apt("a", creazione({ stato: "non_creato" }))];
    sortForPlatform(list);
    expect(list.map((a) => a.apartment_id)).toEqual(["b", "a"]);
  });
});

describe("rilettura ogni 4 secondi, al massimo 20 minuti (§3.3)", () => {
  const start = 1_000_000;
  it("con una creazione in preparazione o un annullamento in corso", () => {
    expect(creationRefetch([apt("a", creazione())], start, start + 1000)).toBe(POLL_MS);
    expect(creationRefetch([apt("a", creazione({ stato: "annullamento_in_corso" }))], start, start + 1000)).toBe(POLL_MS);
    expect(POLL_MS).toBe(4000);
  });
  it("si ferma senza niente in corso, o dopo 20 minuti", () => {
    expect(creationRefetch([apt("a", null), apt("b", creazione({ stato: "non_creato" }))], start, start)).toBe(false);
    expect(creationRefetch(undefined, start, start)).toBe(false);
    expect(creationRefetch([apt("a", creazione())], start, start + MAX_POLL_MS)).toBe(false);
    expect(MAX_POLL_MS).toBe(20 * 60_000);
  });
});

describe("«Cosa è successo» (§6.2)", () => {
  const op = (codice: string | null, messaggio = "Frase del server") => ({ op_id: "op-1", stato: "fallito", codice, messaggio });
  it.each([
    ["capienza_insufficiente", "La macchina virtuale non ha memoria per un sistema domotico in più."],
    ["staging_pieno", "Lo staging ha già il numero massimo di sistemi domotici."],
    ["porta_occupata", "La porta scelta è occupata sulla macchina virtuale: «Riprova» ne prende un'altra."],
    ["porta_fuori_fascia", "Richiesta rifiutata dal sistema: serve un controllo (ID richiesta)."],
    ["immagine_non_approvata", "Richiesta rifiutata dal sistema: serve un controllo (ID richiesta)."],
    ["gia_esiste_diverso", "Richiesta rifiutata dal sistema: serve un controllo (ID richiesta)."],
    ["dati_presenti", "Richiesta rifiutata dal sistema: serve un controllo (ID richiesta)."],
    ["non_creato_da_agente", "Richiesta rifiutata dal sistema: serve un controllo (ID richiesta)."],
    ["firma_non_valida", "Richiesta rifiutata dal sistema: serve un controllo (ID richiesta)."],
    ["segreto_illeggibile", "I permessi sulle chiavi non sono ancora attivi: riprova fra qualche minuto."],
    ["motore_non_sano", "Il sistema domotico non è partito: «Riprova», e se succede ancora serve un controllo."],
    ["broker_fallito", "L'accesso dei dispositivi non è stato preparato: «Riprova»."],
    ["tempo_scaduto", "Nessuna risposta dalla macchina virtuale in 20 minuti: «Riprova»."],
  ])("%s", (codice, text) => {
    expect(whatHappened(creazione({ stato: "non_creato", op: op(codice) }))).toBe(text);
  });
  it("un codice che il sito non conosce: la frase del server", () => {
    expect(whatHappened(creazione({ stato: "non_creato", op: op("nuovo_codice", "Frase nuova del server") }))).toBe("Frase nuova del server");
  });
  it("senza ordine né frase: una frase generica, mai vuota", () => {
    expect(whatHappened(creazione({ stato: "non_creato", op: null }))).toBe("La creazione si è fermata prima della fine.");
    expect(whatHappened(creazione({ stato: "non_creato", op: op(null, "") }))).toBe("La creazione si è fermata prima della fine.");
  });
});

describe("il limite di 5 creazioni l'ora (§2.2)", () => {
  const now = new Date("2026-11-20T15:00:00Z"); // 16:00 a Roma
  it("lo stesso giorno a Roma: solo l'ora", () => {
    expect(freeFromText("2026-11-20T16:42:00Z", now)).toBe("dalle 17:42");
  });
  it("un altro giorno a Roma: con la data", () => {
    expect(freeFromText("2026-11-20T23:12:00Z", now)).toBe("dal 21/11 alle 00:12");
  });
  it("il 429 con limite e ora dentro details", () => {
    const err = new ApiError(429, "rate_limited", "Troppe", "c-1", { limite: 5, riprova_dal: "2026-11-20T16:42:00Z" });
    expect(rateLimitOf(err)).toEqual({ limite: 5, riprova_dal: "2026-11-20T16:42:00Z" });
  });
  it("il 429 senza ora, o un'ora illeggibile: null al posto dell'ora", () => {
    expect(rateLimitOf(new ApiError(429, "rate_limited", "Troppe", null))).toEqual({ limite: 5, riprova_dal: null });
    expect(rateLimitOf(new ApiError(429, "rate_limited", "Troppe", null, { limite: 5, riprova_dal: "domani" }))).toEqual({ limite: 5, riprova_dal: null });
  });
  it("un altro errore non è un limite", () => {
    expect(rateLimitOf(new ApiError(409, "already_exists", "Già", null))).toBeNull();
    expect(rateLimitOf(new Error("x"))).toBeNull();
  });
});

describe("la riga sotto il nome dell'organizzazione (§4)", () => {
  it("i non creati prima, in rosso, al singolare e al plurale", () => {
    expect(tenantCreationLine({ appartamenti_non_creati: 1, appartamenti_in_preparazione: 2 })).toEqual({ tone: "negative", text: "1 appartamento non creato: serve «Riprova» o «Annulla»" });
    expect(tenantCreationLine({ appartamenti_non_creati: 3 })).toEqual({ tone: "negative", text: "3 appartamenti non creati: serve «Riprova» o «Annulla»" });
  });
  it("solo in preparazione: neutra", () => {
    expect(tenantCreationLine({ appartamenti_non_creati: 0, appartamenti_in_preparazione: 1 })).toEqual({ tone: "neutral", text: "1 appartamento in preparazione" });
    expect(tenantCreationLine({ appartamenti_in_preparazione: 2 })).toEqual({ tone: "neutral", text: "2 appartamenti in preparazione" });
  });
  it("nessuna, o un server che non manda i conteggi: niente", () => {
    expect(tenantCreationLine({ appartamenti_non_creati: 0, appartamenti_in_preparazione: 0 })).toBeNull();
    expect(tenantCreationLine({})).toBeNull();
  });
});
