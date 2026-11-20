import { fireEvent, render, screen } from "@testing-library/react";
import { AppearanceSettings } from "./AppearanceSettings";

// «Impostazioni › Aspetto» (PR #19): three palettes and three ways to show them, as real radio buttons. «Come il
// dispositivo» became «Come il telefono o il computer»: in this app a «dispositivo» is a Shelly (glossary of the guide).

beforeEach(() => {
  window.localStorage.clear();
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn() }));
});

describe("Aspetto", () => {
  it("la modalità che segue il sistema si chiama «Come il telefono o il computer», mai «dispositivo»", () => {
    render(<AppearanceSettings />);
    const panel = screen.getByTestId("appearance-settings");
    expect(screen.getByRole("radio", { name: /Come il telefono o il computer/ })).toBeInTheDocument();
    expect(panel.textContent).not.toMatch(/dispositivo/i);
  });

  it("scegliere una palette e il tema scuro: applicati, salvati e annunciati", () => {
    render(<AppearanceSettings />);
    fireEvent.click(screen.getByRole("radio", { name: /Bosco/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Scura/ }));
    expect(document.documentElement.dataset.palette).toBe("bosco");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(JSON.parse(window.localStorage.getItem("domhouse.appearance.v1")!)).toEqual({ palette: "bosco", mode: "dark" });
    expect(screen.getByRole("status")).toHaveTextContent("Aspetto aggiornato e salvato in questo browser.");
  });

  it("«Ripristina predefiniti» torna a Sorgente, come il telefono o il computer", () => {
    render(<AppearanceSettings />);
    fireEvent.click(screen.getByRole("radio", { name: /Aria/ }));
    fireEvent.click(screen.getByTestId("appearance-reset"));
    expect(document.documentElement.dataset.palette).toBe("sorgente");
    expect(screen.getByRole("radio", { name: /Come il telefono o il computer/ })).toBeChecked();
  });
});
