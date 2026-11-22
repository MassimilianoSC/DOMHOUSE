import { adoptSharedChoice, clearAutoLogout, isShared, markAutoLogout, rememberSharedChoice, SHARED_IDLE_MS, sharedExpired, touchShared, wasAutoLogout } from "./sharedDevice";

// F-15 (answer 1244 = a): the choice «Questo è un dispositivo condiviso», per device and per person, and its 30 minutes.

const T0 = 1_800_000_000_000;

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
    expect(sharedExpired("anna", T0 + 60_000)).toBe(false);
  });

  it("due persone sullo stesso dispositivo: ognuna ha la sua scelta", () => {
    rememberSharedChoice(true);
    adoptSharedChoice("anna", T0);
    rememberSharedChoice(false);
    adoptSharedChoice("bruno", T0 + 1000);
    expect(isShared("anna")).toBe(true);
    expect(isShared("bruno")).toBe(false);
    expect(sharedExpired("bruno", T0 + 2 * SHARED_IDLE_MS)).toBe(false);
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

  it("orologio del dispositivo tornato indietro di più di 30 minuti: si esce, non si resta dentro di più", () => {
    rememberSharedChoice(true);
    adoptSharedChoice("anna", T0);
    expect(sharedExpired("anna", T0 - SHARED_IDLE_MS - 1)).toBe(true);
  });
});

describe("l'avviso dopo l'uscita automatica", () => {
  it("si legge senza consumarlo (React disegna due volte in sviluppo), finché la pagina non lo toglie", () => {
    expect(wasAutoLogout()).toBe(false);
    markAutoLogout();
    expect(wasAutoLogout()).toBe(true);
    expect(wasAutoLogout()).toBe(true);
    clearAutoLogout();
    expect(wasAutoLogout()).toBe(false);
  });
});
