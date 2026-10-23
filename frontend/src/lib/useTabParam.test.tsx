import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { Tabs } from "@/components/layout/PageHeader";
import { useTabParam } from "./useTabParam";

type Tab = "apartments" | "users" | "audit";
const SLUGS: Record<Tab, string> = { apartments: "appartamenti", users: "utenti", audit: "registro" };

function Page() {
  const [tab, setTab] = useTabParam<Tab>(SLUGS, "apartments");
  const loc = useLocation();
  return (
    <>
      <Tabs value={tab} onChange={setTab} testId="tab" options={[{ value: "apartments", label: "A" }, { value: "users", label: "U" }, { value: "audit", label: "R" }]} />
      <output data-testid="where">{loc.pathname + loc.search}</output>
    </>
  );
}

const open = (url: string) => render(<MemoryRouter initialEntries={[url]}><Page /></MemoryRouter>);

describe("scheda aperta nell'indirizzo (design, lotto 2)", () => {
  it("?scheda=utenti apre «Utenti»", () => {
    open("/admin?scheda=utenti");
    expect(screen.getByTestId("tab-users")).toHaveAttribute("aria-selected", "true");
  });

  it("uno sconosciuto torna alla prima scheda", () => {
    open("/admin?scheda=boh");
    expect(screen.getByTestId("tab-apartments")).toHaveAttribute("aria-selected", "true");
  });

  it("scegliere una scheda la scrive nell'indirizzo, la prima lo lascia pulito e gli altri parametri restano", () => {
    open("/organizzazioni?appartamenti=t1");
    fireEvent.click(screen.getByTestId("tab-audit"));
    expect(screen.getByTestId("where")).toHaveTextContent("/organizzazioni?appartamenti=t1&scheda=registro");
    fireEvent.click(screen.getByTestId("tab-apartments"));
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/organizzazioni\?appartamenti=t1$/);
  });
});
