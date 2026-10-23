import { t } from "@/i18n";
import { fmtDateTime } from "@/lib/format";
import { AUDIT_ACTIONS, actorLabel, describeEntry, type AuditEntry } from "./auditLog";

// «Registro attività» (P-47): every action reads as an Italian sentence; removed people read «Utente rimosso» (P-48).
const ANNA = { kind: "user" as const, uid: "u1", email: "anna@fs.it", display_name: "Anna Rossi", removed: false };

const entry = (over: Partial<AuditEntry>): AuditEntry => ({
  audit_id: "a1", at: "2026-10-16T08:00:00Z", tenant_id: "t-1", action: "user_removed", actor: ANNA,
  target: { type: "user", id: "u2", label: "bruno@fs.it" }, details: {}, ...over,
});

const sentence = (over: Partial<AuditEntry>) => describeEntry(entry(over)).sentence;

describe("registro attività: chi ha fatto l'azione", () => {
  it("una persona: il nome, oppure l'email se il nome manca", () => {
    expect(actorLabel(ANNA)).toBe("Anna Rossi");
    expect(actorLabel({ ...ANNA, display_name: null })).toBe("anna@fs.it");
  });

  it("persona eliminata (GDPR): «Utente rimosso», senza email né nome", () => {
    expect(actorLabel({ ...ANNA, email: null, display_name: null, removed: true })).toBe(t("audit.removedUser"));
  });

  it("pseudonimo arrivato per errore al posto dell'email (D-87): mai il codice grezzo", () => {
    expect(actorLabel({ ...ANNA, display_name: null, email: "p-0123456789abcdef0123@pseudo.hqe.it" })).toBe(t("audit.removedUser"));
    expect(sentence({ action: "user_removed", target: { type: "user", id: "u2", label: "p-0123456789abcdef0123@pseudo.hqe.it" } })).toBe("Anna Rossi ha rimosso un utente rimosso");
  });

  it("gestore della piattaforma: nel registro dell'admin senza identità, in quello della piattaforma con l'email", () => {
    expect(actorLabel({ kind: "platform", uid: null, email: null, display_name: null, removed: false })).toBe("Gestore della piattaforma (HQE)");
    expect(actorLabel({ kind: "platform", uid: "m1", email: "m@hqe.it", display_name: null, removed: false })).toBe("m@hqe.it (gestore della piattaforma)");
  });

  it("assistenza: sempre con l'identità vera dell'operatore (P-50); il sistema come «Sistema»", () => {
    expect(actorLabel({ kind: "support", uid: "m1", email: "m@hqe.it", display_name: "Marco", removed: false })).toBe("Assistenza HQE (Marco)");
    expect(actorLabel({ kind: "system", uid: null, email: null, display_name: null, removed: false })).toBe(t("audit.system"));
  });
});

describe("registro attività: la frase di ogni azione", () => {
  it.each(AUDIT_ACTIONS)("%s ha la sua frase, senza segnaposto rimasti", (action) => {
    const { sentence: s } = describeEntry(entry({ action, details: {} }));
    expect(s).not.toMatch(/[{}]/);
    expect(s).not.toContain("audit.");
  });

  it("invito: ruolo in parole; con alcuni appartamenti dice quanti", () => {
    expect(sentence({ action: "invite_sent", details: { role: "operator", apartment_ids: "all" } })).toBe("Anna Rossi ha invitato bruno@fs.it come «Operatore»");
    expect(sentence({ action: "invite_sent", details: { role: "viewer", apartment_ids: ["a", "b"] } })).toBe("Anna Rossi ha invitato bruno@fs.it come «Sola lettura», con accesso a 2 appartamenti");
  });

  it("un solo appartamento: al singolare", () => {
    expect(sentence({ action: "invite_sent", details: { role: "operator", apartment_ids: ["a"] } })).toBe("Anna Rossi ha invitato bruno@fs.it come «Operatore», con accesso a 1 appartamento");
  });

  it("email di invito non partita (P-49): nessuna parola sul limite, solo come rimediare", () => {
    const s = sentence({ action: "invite_email_deferred", actor: { kind: "system", uid: null, email: null, display_name: null, removed: false } });
    expect(s).toBe("L'email di invito a bruno@fs.it non è partita: si può riprovare più tardi con «Reinvia»");
    expect(s).not.toMatch(/limit|troppe|rimandat/i);
  });

  it("cambio di ruolo e di appartamenti visibili", () => {
    expect(sentence({ action: "role_changed", details: { from: "viewer", to: "operator" } })).toBe("Anna Rossi ha cambiato il ruolo di bruno@fs.it da «Sola lettura» a «Operatore»");
    expect(sentence({ action: "scope_changed", details: { to: "all" } })).toBe("Anna Rossi ha cambiato gli appartamenti di bruno@fs.it: ora vede tutti gli appartamenti");
    expect(sentence({ action: "scope_changed", details: { to: ["a"] } })).toBe("Anna Rossi ha cambiato gli appartamenti di bruno@fs.it: ora vede 1 appartamento");
  });

  it("persona destinataria eliminata: «un utente rimosso» al posto dell'email", () => {
    expect(sentence({ action: "role_changed", target: { type: "user", id: "u2", label: null, removed: true }, details: { from: "viewer", to: "operator" } })).toBe("Anna Rossi ha cambiato il ruolo di un utente rimosso da «Sola lettura» a «Operatore»");
  });

  it("appartamenti e organizzazioni tra «»; il nome resta anche dopo la cancellazione", () => {
    const apt = { type: "apartment" as const, id: "apt-001", label: "Milano Centro" };
    expect(sentence({ action: "apartment_deleted", target: apt })).toBe("Anna Rossi ha eliminato l'appartamento «Milano Centro»");
    expect(sentence({ action: "italianway_changed", target: apt, details: { from: null, to: "IW-7" } })).toBe("Anna Rossi ha cambiato il codice Italianway dell'appartamento «Milano Centro» da nessuno a IW-7");
    expect(sentence({ action: "features_changed", target: apt })).toBe("Anna Rossi ha cambiato le funzioni dell'appartamento «Milano Centro»");
    expect(sentence({ action: "features_changed", target: { type: "tenant", id: "t-1", label: "Flatsharing" } })).toBe("Anna Rossi ha cambiato le funzioni dell'organizzazione «Flatsharing»");
    expect(sentence({ action: "tenant_renamed", target: { type: "tenant", id: "t-1", label: "Flat Sharing" }, details: { from: "Flatsharing", to: "Flat Sharing" } })).toBe("Anna Rossi ha rinominato l'organizzazione «Flatsharing» in «Flat Sharing»");
  });

  it("sospensione e accesso di assistenza: il motivo come nota, la scadenza nella frase", () => {
    const tenant = { type: "tenant" as const, id: "t-1", label: "Flatsharing" };
    expect(describeEntry(entry({ action: "tenant_suspended", target: tenant, details: { reason: "fattura non pagata" } }))).toEqual({
      sentence: "Anna Rossi ha sospeso l'organizzazione «Flatsharing»",
      note: "Motivo: fattura non pagata",
    });
    const access = entry({ action: "support_access_opened", actor: { kind: "support", uid: "m1", email: "m@hqe.it", display_name: null, removed: false }, target: { type: "support_access", id: "sa-1", label: "Flatsharing" }, details: { hours: 2, expires_at: "2026-10-16T10:00:00Z", reason: "verifica" } });
    expect(describeEntry(access).sentence).toBe(`Assistenza HQE (m@hqe.it) ha aperto un accesso di assistenza a «Flatsharing» fino al ${fmtDateTime("2026-10-16T10:00:00Z")}`);
    expect(describeEntry(access).note).toBe("Motivo: verifica");
  });

  it("gestori della piattaforma e account eliminato", () => {
    expect(sentence({ action: "manager_added", target: { type: "manager", id: "u3", label: "carla@hqe.it" } })).toBe("Anna Rossi ha nominato carla@hqe.it gestore della piattaforma");
    expect(sentence({ action: "account_deleted", actor: { ...ANNA, email: null, display_name: null, removed: true } })).toBe("Utente rimosso ha eliminato il proprio account");
  });

  it("azione che questa versione non conosce: frase di riserva con il codice, la pagina non si rompe", () => {
    expect(sentence({ action: "tenant_merged" })).toBe("Anna Rossi: azione «tenant_merged» su bruno@fs.it");
  });

  it("dettagli mancanti o di tipo sbagliato: la frase resta leggibile", () => {
    expect(sentence({ action: "role_changed", details: { from: 3 } })).toBe("Anna Rossi ha cambiato il ruolo di bruno@fs.it da «3» a «—»");
    expect(sentence({ action: "invite_sent", details: { role: "superuser" } })).toBe("Anna Rossi ha invitato bruno@fs.it come «superuser»");
  });
});

describe("registro visto dalla piattaforma: solo il ruolo delle persone dell'organizzazione (P-51, D-90)", () => {
  const anon = (role: string | null) => ({ kind: "user" as const, uid: null, email: null, display_name: null, removed: false, role });

  it("chi ha agito: «Un amministratore», «Un operatore», «Un lettore»; voci vecchie senza ruolo: «Un utente»", () => {
    expect(actorLabel(anon("admin"))).toBe("Un amministratore");
    expect(actorLabel(anon("operator"))).toBe("Un operatore");
    expect(actorLabel(anon("viewer"))).toBe("Un lettore");
    expect(actorLabel(anon(null))).toBe("Un utente");
  });

  it("la persona su cui si agisce: «un utente», mai «utente rimosso» se non è stata rimossa", () => {
    const target = { type: "user" as const, id: "u2", label: null, removed: false, role: "viewer" };
    expect(sentence({ action: "invite_sent", actor: anon("admin"), target, details: { role: "viewer", apartment_ids: "all" } })).toBe("Un amministratore ha invitato un utente come «Sola lettura»");
    expect(sentence({ action: "role_changed", actor: anon("admin"), target, details: { from: "operator", to: "admin" } })).toBe("Un amministratore ha cambiato il ruolo di un utente da «Operatore» a «Amministratore»");
    expect(sentence({ action: "user_removed", actor: anon("admin"), target: { ...target, removed: true } })).toBe("Un amministratore ha rimosso un utente rimosso");
  });

  it("gestori, assistenza e sistema restano con la loro identità", () => {
    expect(actorLabel({ kind: "support", uid: null, email: "m@hqe.it", display_name: "Marco", removed: false })).toBe("Assistenza HQE (Marco)");
  });
});

describe("accesso di assistenza non aperto (P-52b)", () => {
  it("chiusura di sistema con not_opened: frase dedicata, senza «Sistema ha chiuso»", () => {
    const system = { kind: "system" as const, uid: null, email: null, display_name: null, removed: false };
    const target = { type: "support_access" as const, id: "sa-1", label: "Flatsharing" };
    expect(sentence({ action: "support_access_closed", actor: system, target, details: { not_opened: true } })).toBe("L'accesso di assistenza a «Flatsharing» non è stato aperto (errore)");
    expect(sentence({ action: "support_access_closed", actor: system, target, details: {} })).toBe("Sistema ha chiuso l'accesso di assistenza a «Flatsharing»");
  });
});

describe("prezzo dell'energia nel registro (P-52)", () => {
  const tenant = { type: "tenant" as const, id: "t-1", label: "Flatsharing" };
  const apt = { type: "apartment" as const, id: "apt-001", label: "Milano Centro" };

  it("impostato, cambiato, tolto", () => {
    expect(sentence({ action: "energy_price_changed", target: tenant, details: { from: null, to: 0.25 } })).toBe("Anna Rossi ha impostato il prezzo dell'energia dell'organizzazione «Flatsharing» a 0,25 €/kWh");
    expect(sentence({ action: "energy_price_changed", target: tenant, details: { from: 0.22, to: 0.25 } })).toBe("Anna Rossi ha cambiato il prezzo dell'energia dell'organizzazione «Flatsharing» da 0,22 a 0,25 €/kWh");
    expect(sentence({ action: "energy_price_changed", target: tenant, details: { from: 0.25, to: null } })).toBe("Anna Rossi ha tolto il prezzo dell'energia dell'organizzazione «Flatsharing»");
  });

  it("eccezione dell'appartamento: impostata, e tolta (vale quello dell'organizzazione)", () => {
    expect(sentence({ action: "energy_price_changed", target: apt, details: { from: null, to: 0.3 } })).toBe("Anna Rossi ha impostato il prezzo dell'energia dell'appartamento «Milano Centro» a 0,3 €/kWh");
    expect(sentence({ action: "energy_price_changed", target: apt, details: { from: 0.3, to: null } })).toBe("Anna Rossi ha tolto il prezzo dell'energia dell'appartamento «Milano Centro»: vale quello dell'organizzazione");
  });
});

describe("istanza simulata e ripristino nel registro (D-97)", () => {
  const apt = { type: "apartment" as const, id: "apt-001", label: "Milano Centro" };

  it("segnato come simulato o reale", () => {
    expect(sentence({ action: "apartment_simulated_changed", target: apt, details: { from: false, to: true } })).toBe("Anna Rossi ha segnato l'appartamento «Milano Centro» come istanza simulata");
    expect(sentence({ action: "apartment_simulated_changed", target: apt, details: { from: true, to: false } })).toBe("Anna Rossi ha segnato l'appartamento «Milano Centro» come istanza reale");
  });

  it("ripristino dello stato iniziale", () => {
    expect(sentence({ action: "simulator_reset", target: apt })).toBe("Anna Rossi ha ripristinato lo stato iniziale dell'appartamento simulato «Milano Centro»");
  });
});

describe("regole modificate nel registro (D-151)", () => {
  const apt = { type: "apartment" as const, id: "apt-001", label: "Milano Centro" };
  const WINDOW = { rule_id: "window_open_off", label: "Finestra aperta spegne il clima", field: "minutes", old: 5, new: 10 };

  it("su proposta dell'assistente, con i valori che cambiano", () => {
    expect(sentence({ action: "rules_changed", target: apt, details: { source: "assistant", changes: [WINDOW] } }))
      .toBe("Anna Rossi ha modificato le regole dell'appartamento «Milano Centro» su proposta dell'assistente: Finestra aperta spegne il clima, minuti da 5 a 10");
  });

  it("più valori separati da «;», una regola attivata o disattivata, un parametro con la sua etichetta", () => {
    const changes = [
      WINDOW,
      { rule_id: "mold_protection", label: "Antimuffa", field: "enabled", old: true, new: false },
      { rule_id: "checkout_eco", label: "Risparmio al check-out", field: "presence_minutes", old: 30, new: 45 },
    ];
    expect(sentence({ action: "rules_changed", target: apt, details: { source: "assistant", changes } }))
      .toBe("Anna Rossi ha modificato le regole dell'appartamento «Milano Centro» su proposta dell'assistente: Finestra aperta spegne il clima, minuti da 5 a 10; Antimuffa disattivata; Risparmio al check-out, minuti di presenza dopo il check-out da 30 a 45");
  });

  it("copiate da un altro appartamento, con i valori che cambiano", () => {
    expect(sentence({ action: "rules_changed", target: apt, details: { source: "copy", from_apartment: { id: "apt-bo", name: "Bologna" }, changes: [WINDOW] } }))
      .toBe("Anna Rossi ha copiato le regole da «Bologna» all'appartamento «Milano Centro»: Finestra aperta spegne il clima, minuti da 5 a 10");
    expect(sentence({ action: "rules_changed", target: apt, details: { source: "copy", from_apartment: { id: "apt-bo", name: "Bologna" } } }))
      .toBe("Anna Rossi ha copiato le regole da «Bologna» all'appartamento «Milano Centro»");
  });

  it("fonte sconosciuta o mancante: la frase semplice", () => {
    expect(sentence({ action: "rules_changed", target: apt, details: {} })).toBe("Anna Rossi ha modificato le regole dell'appartamento «Milano Centro»");
    expect(sentence({ action: "rules_changed", target: apt, details: { source: "futuro" } })).toBe("Anna Rossi ha modificato le regole dell'appartamento «Milano Centro»");
  });
});

describe("fuso orario cambiato sul motore (D-183)", () => {
  it("la frase con il vecchio e il nuovo fuso, scritta dal sistema", () => {
    const system = { kind: "system" as const, uid: null, email: null, display_name: null, removed: false };
    expect(sentence({ action: "timezone_changed", actor: system, target: { type: "apartment", id: "apt-001", label: "Milano Centro" }, details: { from: "Europe/Rome", to: "Europe/London" } }))
      .toBe("Fuso orario dell'appartamento «Milano Centro» cambiato sul motore: Europe/Rome → Europe/London");
  });
});
