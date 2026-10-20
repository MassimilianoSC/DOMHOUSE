import { t } from "@/i18n";
import { describeActor, personLabel } from "./describe";

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
