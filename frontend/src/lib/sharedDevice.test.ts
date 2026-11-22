import { adoptSharedChoice, CLOCK_BACK_MS, forgetShared, forgetSharedChoice, isShared, rememberSharedChoice, SHARED_IDLE_MS, sharedExpired, touchShared } from "./sharedDevice";

// F-15 (answer 1244 = a): the choice «Questo è un dispositivo condiviso», per device and per person, and its 30 minutes.

const T0 = 1_800_000_000_000;
const key = (uid: string) => localStorage.getItem(`domotica.shared.${uid}`);

beforeEach(() => localStorage.clear());

describe("la scelta a ogni accesso", () => {
  it("casella spuntata: da questo accesso il dispositivo è condiviso per quella persona", () => {
    rememberSharedChoice(true);
    adoptSharedChoice("anna", T0);
    expect(isShared("anna")).toBe(true);
    expect(sharedExpired("anna", T0 + SHARED_IDLE_MS)).toBe(false);
    expect(sharedExpired("anna", T0 + SHARED_IDLE_MS + 1)).toBe(true);
  });

  it("accesso senza casella: la scelta di quella persona si toglie", () => {
    rememberSharedChoice(true);
    adoptSharedChoice("anna", T0);
    rememberSharedChoice(false);
    adoptSharedChoice("anna", T0 + 1000);
    expect(isShared("anna")).toBe(false);
    expect(sharedExpired("anna", T0 + 2 * SHARED_IDLE_MS)).toBe(false);
  });

  it("senza un accesso nuovo (ricaricamento, sessione ripresa) la scelta resta com'era", () => {
    rememberSharedChoice(true);
    adoptSharedChoice("anna", T0);
    adoptSharedChoice("anna", T0 + 60_000); // nothing pending
    expect(isShared("anna")).toBe(true);
  });

  it("un accesso non riuscito non lascia la sua casella a nessuno", () => {
    rememberSharedChoice(false);
    forgetSharedChoice();
    rememberSharedChoice(true);
    adoptSharedChoice("anna", T0);
    forgetSharedChoice(); // nothing left
    adoptSharedChoice("anna", T0 + 1000);
    expect(isShared("anna")).toBe(true);
  });

  it("due persone sullo stesso dispositivo: ognuna ha la sua scelta", () => {
    rememberSharedChoice(true);
    adoptSharedChoice("anna", T0);
    rememberSharedChoice(false);
    adoptSharedChoice("bruno", T0 + 1000);
    expect(isShared("anna")).toBe(true);
    expect(isShared("bruno")).toBe(false);
  });

  it("dopo l'uscita la chiave della persona non resta sul dispositivo (S-6)", () => {
    rememberSharedChoice(true);
    adoptSharedChoice("anna", T0);
    forgetShared("anna");
    expect(key("anna")).toBeNull();
    expect(isShared("anna")).toBe(false);
  });
});

describe("i 30 minuti", () => {
  it("un uso fa ripartire i 30 minuti", () => {
    rememberSharedChoice(true);
    adoptSharedChoice("anna", T0);
    touchShared("anna", T0 + 20 * 60_000);
    expect(sharedExpired("anna", T0 + 45 * 60_000)).toBe(false);
    expect(sharedExpired("anna", T0 + 51 * 60_000)).toBe(true);
  });

  it("gli usi ravvicinati non riscrivono ogni volta (al massimo ogni 15 secondi)", () => {
    rememberSharedChoice(true);
    adoptSharedChoice("anna", T0);
    const set = vi.spyOn(Storage.prototype, "setItem");
    touchShared("anna", T0 + 5_000);
    touchShared("anna", T0 + 10_000);
    expect(set).not.toHaveBeenCalled();
    touchShared("anna", T0 + 16_000);
    expect(set).toHaveBeenCalledTimes(1);
    set.mockRestore();
  });

  it("un uso non accende la scelta per chi non l'ha", () => {
    touchShared("bruno", T0);
    expect(isShared("bruno")).toBe(false);
  });

  it("orologio tornato indietro (S-4): oltre 2 minuti si esce; un uso non riporta indietro l'ultimo uso", () => {
    rememberSharedChoice(true);
    adoptSharedChoice("anna", T0);
    expect(sharedExpired("anna", T0 - CLOCK_BACK_MS + 1)).toBe(false); // a small correction of the clock
    expect(sharedExpired("anna", T0 - CLOCK_BACK_MS - 1)).toBe(true);
    expect(sharedExpired("anna", T0 - 29 * 60_000)).toBe(true);
    touchShared("anna", T0 - 60 * 60_000);
    expect(key("anna")).toBe(String(T0));
  });

  it("un valore illeggibile vale come scaduto", () => {
    localStorage.setItem("domotica.shared.anna", "rotto");
    expect(sharedExpired("anna", T0)).toBe(true);
  });
});
