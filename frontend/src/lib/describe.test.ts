import { t } from "@/i18n";
import { actionLabel, DECISION_ACTIONS, describeActor, personLabel } from "./describe";

// Who did something, as the site shows it (P-48, D-87): the email the BFF resolved, or «utente rimosso» for a deleted
// account; a pseudonym the BFF did not rewrite is never shown raw.
describe("persone: nome mostrato", () => {
  it("email risolta dal server: così com'è", () => {
    expect(personLabel("anna@fs.it")).toBe("anna@fs.it");
  });

  it("sentinella del server per un account eliminato: «utente rimosso»", () => {
    expect(personLabel("removed")).toBe(t("common.removedUser"));
  });

  it("pseudonimo non riscritto (rete di sicurezza): mai il codice grezzo", () => {
    expect(personLabel("p-3f9c0a1b2c3d4e5f6a7b@pseudo.hqe.it")).toBe(t("common.removedUser"));
    expect(personLabel("P-3F9C0A1B2C3D4E5F6A7B@PSEUDO.HQE.IT")).toBe(t("common.removedUser"));
  });

  it("vuoto: «utente rimosso» invece di niente", () => {
    expect(personLabel("  ")).toBe(t("common.removedUser"));
  });
});

describe("decisioni: chi ha agito", () => {
  it("persona: la sua email; account eliminato («user:removed»): «utente rimosso»", () => {
    expect(describeActor("user:anna@fs.it")).toEqual({ kind: "user", label: "anna@fs.it" });
    expect(describeActor("user:removed")).toEqual({ kind: "user", label: t("common.removedUser") });
  });

  it("pseudonimo arrivato per errore, con o senza «user:»: «utente rimosso»", () => {
    expect(describeActor("user:p-0123456789abcdef0123@pseudo.hqe.it")).toEqual({ kind: "user", label: t("common.removedUser") });
    expect(describeActor("p-0123456789abcdef0123@pseudo.hqe.it")).toEqual({ kind: "user", label: t("common.removedUser") });
  });

  it("gli altri attori non cambiano", () => {
    expect(describeActor("assistant").label).toBe(t("actor.assistant"));
    expect(describeActor("rule:window_open_off", { window_open_off: "Finestra aperta" }).label).toBe(t("actor.rule", { name: "Finestra aperta" }));
  });
});

describe("decisioni: il tipo di azione in italiano (D-125)", () => {
  it.each(DECISION_ACTIONS)("«%s» ha la sua etichetta, mai il codice", (code) => {
    const label = actionLabel(code);
    expect(label).not.toBe(code);
    expect(label).not.toMatch(/_|^decisions\./);
  });

  it("le etichette concordate", () => {
    expect(actionLabel("set_mode")).toBe("Modalità");
    expect(actionLabel("hold")).toBe("Forzatura");
    expect(actionLabel("hold_cancel")).toBe("Forzatura annullata");
    expect(actionLabel("hold_expired")).toBe("Forzatura scaduta");
    expect(actionLabel("expire")).toBe("Approvazione scaduta");
    expect(actionLabel("schedule_create")).toBe("Programma: aggiunta");
    expect(actionLabel("schedule_move")).toBe("Programma: spostata");
    expect(actionLabel("schedule_cancel")).toBe("Programma: annullata");
    expect(actionLabel("schedule_missed")).toBe("Programma: saltata");
    expect(actionLabel("schedule_deferred")).toBe("Azione rimandata");
    expect(actionLabel("booking_cancel_reset")).toBe("Disdetta dopo il pre-arrivo");
    expect(actionLabel("update_rules")).toBe("Regole aggiornate");
    expect(actionLabel("update_device")).toBe("Dispositivo modificato");
    expect(actionLabel("turn_on")).toBe("Accensione");
    expect(actionLabel("turn_off")).toBe("Spegnimento");
    expect(actionLabel("set_climate")).toBe("Clima");
    expect(actionLabel("set_heating")).toBe("Riscaldamento");
    // regole del motore, passo 5a (cde9881)
    expect(actionLabel("offline_alert")).toBe("Dispositivo offline");
    expect(actionLabel("mold_warning")).toBe("Avviso antimuffa");
    // termostato e antigelo, passo 5b (5f9db5c)
    expect(actionLabel("frost_heating_on")).toBe("Antigelo: caldaia accesa");
    expect(actionLabel("frost_heating_off")).toBe("Antigelo: caldaia spenta");
    expect(actionLabel("thermostat_sensor")).toBe("Termostato: sensore");
  });

  it("un'azione che il motore aggiungerà e il sito non conosce ancora: il codice, la pagina non si rompe", () => {
    expect(actionLabel("future_action")).toBe("future_action");
    expect(actionLabel("")).toBe("");
  });
});
