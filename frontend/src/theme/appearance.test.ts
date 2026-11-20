// The appearance chosen in «Impostazioni › Aspetto» (PR #19): palette and light/dark/system, kept in this browser only
// (localStorage «domhouse.appearance.v1»), applied to <html> as data attributes and CSS variables, also when another
// tab changes it. Each test loads the module afresh: it keeps its state at module level.

const KEY = "domhouse.appearance.v1";

async function fresh() {
  vi.resetModules();
  return import("./appearance");
}

beforeEach(() => {
  window.localStorage.clear();
  const root = document.documentElement;
  root.removeAttribute("style");
  for (const k of ["palette", "theme", "themePreference"]) delete root.dataset[k];
  root.classList.remove("dark");
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: false, media: q, addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn() }));
});

describe("aspetto", () => {
  it("senza niente salvato: Sorgente, come il dispositivo, cioè chiaro qui", async () => {
    const a = await fresh();
    a.initializeAppearance();
    const root = document.documentElement;
    expect(root.dataset.palette).toBe("sorgente");
    expect(root.dataset.themePreference).toBe("system");
    expect(root.dataset.theme).toBe("light");
    expect(root.style.getPropertyValue("--background")).not.toBe("");
  });

  it("un valore salvato rovinato o sconosciuto torna ai predefiniti, senza errori", async () => {
    window.localStorage.setItem(KEY, "{non json");
    let a = await fresh();
    a.initializeAppearance();
    expect(document.documentElement.dataset.palette).toBe("sorgente");
    window.localStorage.setItem(KEY, JSON.stringify({ palette: "arcobaleno", mode: "viola" }));
    a = await fresh();
    a.initializeAppearance();
    expect(document.documentElement.dataset.palette).toBe("sorgente");
    expect(document.documentElement.dataset.themePreference).toBe("system");
  });

  it("scegliere Bosco scuro: salvato, applicato a <html> con la classe dark", async () => {
    const a = await fresh();
    a.initializeAppearance();
    expect(a.setAppearance({ palette: "bosco", mode: "dark" })).toBe(true);
    const root = document.documentElement;
    expect(JSON.parse(window.localStorage.getItem(KEY)!)).toEqual({ palette: "bosco", mode: "dark" });
    expect(root.dataset.palette).toBe("bosco");
    expect(root.dataset.theme).toBe("dark");
    expect(root.classList.contains("dark")).toBe(true);
  });

  it("il browser non lascia salvare: vale per questa sessione e lo dice (false)", async () => {
    const a = await fresh();
    a.initializeAppearance();
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("quota");
    });
    expect(a.setAppearance({ palette: "aria" })).toBe(false);
    expect(document.documentElement.dataset.palette).toBe("aria");
    setItem.mockRestore();
  });

  it("cambiato in un'altra scheda: si applica anche qui", async () => {
    const a = await fresh();
    a.initializeAppearance();
    window.dispatchEvent(new StorageEvent("storage", { key: KEY, newValue: JSON.stringify({ palette: "aria", mode: "light" }) }));
    expect(document.documentElement.dataset.palette).toBe("aria");
  });
});
