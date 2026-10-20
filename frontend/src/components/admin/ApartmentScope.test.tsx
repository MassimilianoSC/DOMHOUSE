import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { t } from "@/i18n";
import { ApartmentScopePicker, isNoneScope, scopeSummary, type ApartmentScope } from "./ApartmentScope";

// Apartments an operator or viewer may see (P-18, shape D-43): "all" or a list of ids, [] = none.
const APTS = [
  { apartment_id: "apt-bologna-01", name: "Bologna Centro", address: "Via Indipendenza 1" },
  { apartment_id: "apt-rimini-01", name: "Rimini Mare", address: "Viale Vespucci 9" },
  { apartment_id: "apt-milano-01", name: "Milano Navigli", address: "Alzaia 3" },
];

describe("sintesi degli appartamenti di un utente", () => {
  it("«all» → tutti gli appartamenti", () => {
    expect(scopeSummary("all", APTS).text).toBe(t("admin.users.scopeAll"));
  });

  it("lista vuota → nessun appartamento", () => {
    expect(scopeSummary([], APTS).text).toBe(t("admin.users.scopeNone"));
  });

  it("uno o due → i nomi; tre o più → «N appartamenti», con i nomi a parte", () => {
    expect(scopeSummary(["apt-rimini-01"], APTS).text).toBe("Rimini Mare");
    expect(scopeSummary(["apt-rimini-01", "apt-bologna-01"], APTS).text).toBe("Bologna Centro, Rimini Mare");
    const three = scopeSummary(["apt-rimini-01", "apt-bologna-01", "apt-milano-01"], APTS);
    expect(three.text).toBe(t("admin.users.scopeCount", { count: 3 }));
    expect(three.names).toEqual(["Bologna Centro", "Rimini Mare", "Milano Navigli"]);
  });

  it("id di un appartamento che non esiste più: ignorato", () => {
    expect(scopeSummary(["apt-cancellato"], APTS).text).toBe(t("admin.users.scopeNone"));
    expect(scopeSummary(["apt-cancellato", "apt-rimini-01"], APTS).text).toBe("Rimini Mare");
  });

  it("«nessuno» riconosciuto solo per la lista vuota", () => {
    expect(isNoneScope([])).toBe(true);
    expect(isNoneScope("all")).toBe(false);
    expect(isNoneScope(["apt-rimini-01"])).toBe(false);
  });
});

function Harness({ initial, onValue }: { initial: ApartmentScope; onValue: (v: ApartmentScope) => void }) {
  const [v, setV] = useState<ApartmentScope>(initial);
  return <ApartmentScopePicker value={v} onChange={(n) => { setV(n); onValue(n); }} apartments={APTS} testId="scope" />;
}

describe("scelta degli appartamenti", () => {
  it("«Tutti» spuntato: le singole caselle appaiono spuntate ma non si possono cambiare", () => {
    render(<Harness initial="all" onValue={() => {}} />);
    expect(screen.getByTestId("scope-all")).toBeChecked();
    for (const a of APTS) {
      expect(screen.getByTestId(`scope-${a.apartment_id}`)).toBeChecked();
      expect(screen.getByTestId(`scope-${a.apartment_id}`)).toBeDisabled();
    }
  });

  it("togliendo «Tutti» si parte da nessuno e compare l'avviso; scegliendone uno l'avviso sparisce", () => {
    const seen: ApartmentScope[] = [];
    render(<Harness initial="all" onValue={(v) => seen.push(v)} />);
    fireEvent.click(screen.getByTestId("scope-all"));
    expect(seen.at(-1)).toEqual([]);
    expect(screen.getByTestId("scope-none-warning")).toHaveTextContent(t("admin.users.scopeNoneWarning"));
    fireEvent.click(screen.getByTestId("scope-apt-rimini-01"));
    expect(seen.at(-1)).toEqual(["apt-rimini-01"]);
    expect(screen.queryByTestId("scope-none-warning")).not.toBeInTheDocument();
  });

  it("aggiunge e toglie appartamenti dalla lista; rimettere «Tutti» torna ad «all»", () => {
    const seen: ApartmentScope[] = [];
    render(<Harness initial={["apt-rimini-01"]} onValue={(v) => seen.push(v)} />);
    fireEvent.click(screen.getByTestId("scope-apt-bologna-01"));
    expect(seen.at(-1)).toEqual(["apt-rimini-01", "apt-bologna-01"]);
    fireEvent.click(screen.getByTestId("scope-apt-rimini-01"));
    expect(seen.at(-1)).toEqual(["apt-bologna-01"]);
    fireEvent.click(screen.getByTestId("scope-all"));
    expect(seen.at(-1)).toBe("all");
  });
});
