import { changeValue, describeChange, fieldLabel } from "./ruleChanges";

// One changed value of a rule (D-151), as the assistant's proposal and the «Registro attività» write it. Item 15: the
// months of the heating season by their name, not as a number.

describe("una modifica di regola in italiano", () => {
  it("un numero resta un numero; lo stato è «attiva» o «spenta»", () => {
    expect(describeChange({ label: "Finestra aperta", field: "minutes", old: 5, new: 10 })).toBe("Finestra aperta, minuti da 5 a 10");
    expect(changeValue("enabled", true)).toBe("attiva");
  });

  it("voce 15: i mesi della stagione con il nome, i giorni come numero", () => {
    expect(describeChange({ label: "Limiti del setpoint", field: "season_start_month", old: 10, new: 11 })).toBe("Limiti del setpoint, inizio: mese da ottobre a novembre");
    expect(describeChange({ label: "Limiti del setpoint", field: "season_end_day", old: 15, new: 31 })).toBe("Limiti del setpoint, fine: giorno da 15 a 31");
    expect(changeValue("season_end_month", 4)).toBe("aprile");
    expect(changeValue("season_end_month", 13)).toBe("13");
  });

  it("le etichette dei campi nuovi, come nella pagina Regole", () => {
    expect(fieldLabel("season_start_day")).toBe("Inizio: giorno");
    expect(fieldLabel("season_end_month")).toBe("Fine: mese");
    expect(fieldLabel("no_rise_minutes")).toBe("Avviso se la temperatura non risale (minuti)");
  });
});
