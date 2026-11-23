import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/primitives";
import RulesPage from "./RulesPage";

// Item 15 (o1, option A): the heating season inside «Limiti del setpoint» (four numbers, valid also with the rule off),
// the shortcuts of the climatic zones (DPR 74/2013, art. 4), the minutes of the «not rising» warning in «Antigelo».
// Texts agreed with the memoria storica (A1–A7, B1–B3).
const SETPOINT = () => ({
  rule_id: "setpoint_limits", label: "Limiti del setpoint", enabled: s.enabled, editable: s.editable,
  params: { min: 16, max: 24, comfort_celsius: 21, eco_celsius: 18, comfort_cool_celsius: 25, summer_min: 18, summer_max: 28, ...s.season },
  limits: {
    min: { min: 7, max: 20 }, max: { min: 20, max: 28 }, comfort_celsius: { min: 16, max: 26 }, eco_celsius: { min: 10, max: 22 },
    comfort_cool_celsius: { min: 22, max: 28 }, summer_min: { min: 16, max: 28 }, summer_max: { min: 22, max: 30 },
    ...(s.season ? { season_start_month: { min: 1, max: 12 }, season_start_day: { min: 1, max: 31 }, season_end_month: { min: 1, max: 12 }, season_end_day: { min: 1, max: 31 } } : {}),
  },
});
// an engine from before item 15 (s.noRise false) has neither the minutes nor the season
const FROST = () => (s.noRise
  ? { rule_id: "frost_protection", label: "Antigelo", enabled: true, editable: true, params: { celsius: 8, no_rise_minutes: 120 }, limits: { celsius: { min: 5, max: 12 }, no_rise_minutes: { min: 30, max: 480 } } }
  : { rule_id: "frost_protection", label: "Antigelo a casa vuota", enabled: true, editable: true, params: { celsius: 8 }, limits: { celsius: { min: 5, max: 12 } } });
const ZONE_E = { season_start_month: 10, season_start_day: 15, season_end_month: 4, season_end_day: 15 };

const s = vi.hoisted(() => ({
  canWrite: true,
  enabled: true,
  editable: true,
  noRise: true,
  season: null as Record<string, number> | null,
  update: vi.fn(),
}));

vi.mock("@/auth/AuthProvider", () => ({ useRole: () => ({ canWrite: s.canWrite, isAdmin: false }) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ getRules: async () => ({ updated_at: "2026-11-23T08:00:00.000Z", rules: [SETPOINT(), FROST()] }), updateRules: s.update }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

async function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TooltipProvider>
        <MemoryRouter initialEntries={["/a/apt-001/regole"]}>
          <Routes>
            <Route path="/a/:aptId/regole" element={<RulesPage />} />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
  return screen.findByTestId("rule-card-setpoint_limits");
}
const box = (key: string) => screen.getByTestId(`rule-param-setpoint_limits-${key}`) as HTMLInputElement | HTMLSelectElement;
const set = (key: string, value: string) => fireEvent.change(box(key), { target: { value } });

beforeEach(() => {
  vi.clearAllMocks();
  s.canWrite = true;
  s.enabled = true;
  s.editable = true;
  s.noRise = true;
  s.season = { ...ZONE_E };
  s.update.mockImplementation(async () => ({ updated_at: "2026-11-23T08:01:00.000Z", rules: [SETPOINT(), FROST()] }));
});

describe("Regole: la stagione del riscaldamento (voce 15)", () => {
  it("nel gruppo «Inverno», sotto le temperature: titolo, inizio e fine con giorno e mese, riepilogo con la zona, nota", async () => {
    await open();
    const winter = screen.getByTestId("rule-group-setpoint_limits-winter");
    const season = within(winter).getByTestId("rule-season-setpoint_limits");
    expect(season).toHaveTextContent("Stagione del riscaldamento");
    expect(box("season_start_day")).toHaveValue(15);
    expect(box("season_start_month")).toHaveValue("10");
    expect(box("season_end_day")).toHaveValue(15);
    expect(box("season_end_month")).toHaveValue("4");
    expect(within(season).getByTestId("rule-season-start")).toHaveTextContent("Inizio");
    expect(within(season).getByTestId("rule-season-end")).toHaveTextContent("Fine");
    expect(box("season_start_day")).toHaveAccessibleName("Inizio: giorno");
    expect(box("season_start_month")).toHaveAccessibleName("Inizio: mese");
    expect(box("season_end_day")).toHaveAccessibleName("Fine: giorno");
    expect(box("season_end_month")).toHaveAccessibleName("Fine: mese");
    expect(within(box("season_start_month") as HTMLSelectElement).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    ]);
    expect(screen.getByTestId("rule-season-summary")).toHaveTextContent("Dal 15 ottobre al 15 aprile (zona E)");
    expect(screen.getByTestId("rule-season-note")).toHaveTextContent(
      "Fuori da queste date la caldaia resta solo sull'antigelo. Vale anche con la regola spenta. La zona del comune è nell'allegato A del DPR 412/1993; il sindaco può allungare il periodo con un'ordinanza.",
    );
    // the four numbers are not drawn a second time as plain boxes
    expect(screen.queryByText("season_start_month")).toBeNull();
  });

  it("riepilogo: tutto l'anno è la zona F; date di nessuna zona, niente parentesi", async () => {
    s.season = { season_start_month: 1, season_start_day: 1, season_end_month: 12, season_end_day: 31 };
    await open();
    expect(screen.getByTestId("rule-season-summary")).toHaveTextContent(/^Tutto l'anno \(zona F\)$/);
    set("season_start_day", "2");
    expect(screen.getByTestId("rule-season-summary")).toHaveTextContent(/^Dal 2 gennaio al 31 dicembre$/);
  });

  it("le scorciatoie A–F: le date di legge al passaggio, un tocco riempie le quattro caselle e si salva come sempre", async () => {
    await open();
    expect(screen.getByTestId("rule-season-zones")).toHaveTextContent("Date di legge per zona climatica:");
    const zones = ["A", "B", "C", "D", "E", "F"].map((z) => screen.getByTestId(`rule-season-zone-${z}`));
    expect(zones.map((z) => z.textContent)).toEqual(["A", "B", "C", "D", "E", "F"]);
    expect(zones[2]).toHaveAccessibleName("Zona C: dal 15 novembre al 31 marzo");
    expect(zones[5]).toHaveAccessibleName("Zona F: tutto l'anno");
    fireEvent.click(zones[2]);
    expect(box("season_start_day")).toHaveValue(15);
    expect(box("season_start_month")).toHaveValue("11");
    expect(box("season_end_day")).toHaveValue(31);
    expect(box("season_end_month")).toHaveValue("3");
    expect(screen.getByTestId("rule-season-summary")).toHaveTextContent("Dal 15 novembre al 31 marzo (zona C)");
    await act(async () => fireEvent.click(screen.getByTestId("rules-save-btn")));
    // only what changed: the start and end months, the end day (the start day was already 15)
    expect(s.update).toHaveBeenCalledWith({ rules: [{ rule_id: "setpoint_limits", params: { season_start_month: 11, season_end_month: 3, season_end_day: 31 } }] }, expect.any(String));
  });

  it("la zona di prima, ripresa: niente da salvare", async () => {
    await open();
    fireEvent.click(screen.getByTestId("rule-season-zone-A"));
    expect(screen.getByTestId("rules-save-bar")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("rule-season-zone-E"));
    expect(screen.queryByTestId("rules-save-bar")).toBeNull();
  });

  it.each([
    ["season_start", "31", "4", "Il 31 aprile non esiste: scegli un altro giorno."],
    ["season_end", "30", "2", "Il 30 febbraio non esiste: scegli un altro giorno."],
  ])("%s %s/%s: il rifiuto sotto la data, il giorno in rosso, niente salvataggio e il perché nella barra", async (which, day, month, message) => {
    await open();
    set(`${which}_month`, month);
    set(`${which}_day`, day);
    const side = which === "season_start" ? "start" : "end";
    expect(screen.getByTestId(`rule-season-error-${side}`)).toHaveTextContent(message);
    expect(box(`${which}_day`)).toHaveAttribute("aria-invalid", "true");
    expect(box(`${which}_day`)).toHaveAttribute("aria-describedby", `rule-season-error-${side}`);
    expect(screen.getByTestId("rules-save-btn")).toBeDisabled();
    expect(screen.getByTestId("rules-save-blocked")).toHaveTextContent("Correggi gli errori evidenziati");
  });

  it("il 29 febbraio e inizio uguale a fine sono accettati (o1)", async () => {
    await open();
    set("season_start_month", "2");
    set("season_start_day", "29");
    set("season_end_month", "2");
    set("season_end_day", "29");
    expect(screen.queryByTestId("rule-season-error-start")).toBeNull();
    expect(screen.queryByTestId("rule-season-error-end")).toBeNull();
    expect(screen.getByTestId("rules-save-btn")).toBeEnabled();
    expect(screen.getByTestId("rule-season-summary")).toHaveTextContent("Dal 29 febbraio al 29 febbraio");
  });

  it("giorno fuori dai limiti del motore: il solito messaggio dei limiti", async () => {
    await open();
    set("season_start_day", "0");
    expect(screen.getByTestId("rule-param-error-setpoint_limits-season_start_day")).toHaveTextContent("Valore fuori dai limiti (1–31)");
    expect(screen.getByTestId("rules-save-btn")).toBeDisabled();
  });

  it("anche con la regola spenta le date si cambiano (valgono comunque)", async () => {
    s.enabled = false;
    await open();
    expect(box("season_start_day")).toBeEnabled();
    expect(screen.getByTestId("rule-season-zone-D")).toBeEnabled();
  });

  it("sola lettura: le date si vedono, caselle e scorciatoie spente", async () => {
    s.canWrite = false;
    await open();
    expect(box("season_start_day")).toBeDisabled();
    expect(box("season_end_month")).toBeDisabled();
    expect(screen.getByTestId("rule-season-zone-E")).toBeDisabled();
    expect(screen.getByTestId("rule-season-summary")).toHaveTextContent("Dal 15 ottobre al 15 aprile (zona E)");
  });

  it("un motore di prima della voce 15, senza le date: nessuna stagione nella pagina", async () => {
    s.season = null;
    await open();
    expect(screen.queryByTestId("rule-season-setpoint_limits")).toBeNull();
  });

  it("la descrizione di «Limiti del setpoint» dice che cosa succede fuori stagione", async () => {
    const c = await open();
    expect(c).toHaveTextContent("Fuori dalla stagione del riscaldamento la caldaia resta solo sull'antigelo e il climatizzatore non scalda da solo.");
  });
});

describe("Regole › Antigelo: l'avviso «la temperatura non risale» (voce 15)", () => {
  it("il campo dei minuti con i limiti del motore, e la frase nella descrizione", async () => {
    await open();
    const c = screen.getByTestId("rule-card-frost_protection");
    expect(c).toHaveTextContent("Avviso se la temperatura non risale (minuti) (da 30 a 480)");
    expect(screen.getByTestId("rule-param-frost_protection-no_rise_minutes")).toHaveValue(120);
    expect(c).toHaveTextContent("Anche con la regola spenta, se la caldaia è accesa ma la temperatura resta sotto l'antigelo per i minuti indicati, lo registra nelle Decisioni e avvisa con una notifica.");
    // review point 4: out of season, comfort and eco too go to this temperature
    expect(c).toHaveTextContent("Con la casa vuota, e fuori dalla stagione del riscaldamento anche in comfort ed eco, la caldaia va a questa temperatura anche con la regola spenta.");
  });
});

// Review of a6498e2 (first independent reviewer): the points its mutations found without a test.
describe("rilettura della voce 15", () => {
  it("punto 1: con un motore di prima le descrizioni non parlano di stagione né dell'avviso", async () => {
    s.season = null;
    s.noRise = false;
    const sl = await open();
    const frost = screen.getByTestId("rule-card-frost_protection");
    expect(sl).not.toHaveTextContent("stagione");
    expect(frost).not.toHaveTextContent("stagione");
    expect(frost).not.toHaveTextContent("per i minuti indicati");
    expect(frost).toHaveTextContent("Con la casa vuota la caldaia va a questa temperatura anche con la regola spenta.");
  });

  it("punto 3: un giorno decimale si ferma prima del salvataggio, senza nessuna chiamata", async () => {
    await open();
    set("season_start_day", "15.5");
    expect(screen.getByTestId("rule-param-error-setpoint_limits-season_start_day")).toHaveTextContent("Valore fuori dai limiti (1–31)");
    expect(box("season_start_day")).toHaveAttribute("aria-invalid", "true");
    // second review N4: the box points to the limits message too, not only to the «does not exist» one
    expect(screen.getByTestId("rule-param-error-setpoint_limits-season_start_day")).toHaveAttribute("id", "rule-param-error-setpoint_limits-season_start_day");
    expect(box("season_start_day")).toHaveAttribute("aria-describedby", "rule-param-error-setpoint_limits-season_start_day");
    expect(screen.getByTestId("rules-save-btn")).toBeDisabled();
    fireEvent.click(screen.getByTestId("rules-save-btn"));
    expect(s.update).not.toHaveBeenCalled();
  });

  it("punto 5: il mese porta all'errore della data; «Stagione del riscaldamento» un livello sotto «Inverno»", async () => {
    await open();
    expect(screen.getByRole("heading", { level: 4, name: "Inverno (riscaldamento)" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 5, name: "Stagione del riscaldamento" })).toBeInTheDocument();
    expect(box("season_end_month")).not.toHaveAttribute("aria-describedby");
    set("season_end_month", "4");
    set("season_end_day", "31");
    expect(box("season_end_month")).toHaveAttribute("aria-describedby", "rule-season-error-end");
    expect(box("season_end_month")).toHaveAttribute("aria-invalid", "true");
  });

  it("punto 6: «1º» per il primo del mese, «dall'8» e «all'11»", async () => {
    await open();
    expect(screen.getByTestId("rule-season-zone-A")).toHaveAccessibleName("Zona A: dal 1º dicembre al 15 marzo");
    expect(screen.getByTestId("rule-season-zone-D")).toHaveAccessibleName("Zona D: dal 1º novembre al 15 aprile");
    set("season_start_month", "11");
    set("season_start_day", "8");
    set("season_end_month", "3");
    set("season_end_day", "11");
    expect(screen.getByTestId("rule-season-summary")).toHaveTextContent(/^Dall'8 novembre all'11 marzo$/);
    set("season_start_day", "11");
    set("season_end_day", "8");
    expect(screen.getByTestId("rule-season-summary")).toHaveTextContent(/^Dall'11 novembre all'8 marzo$/);
    set("season_start_day", "1");
    set("season_end_day", "1");
    expect(screen.getByTestId("rule-season-summary")).toHaveTextContent(/^Dal 1º novembre al 1º marzo$/);
  });

  it("punto 7 e prova mancante: niente riepilogo con il 31 aprile né con la casella del giorno vuota", async () => {
    await open();
    set("season_end_day", "31");
    expect(screen.queryByTestId("rule-season-summary")).toBeNull();
    set("season_end_day", "15");
    expect(screen.getByTestId("rule-season-summary")).toBeInTheDocument();
    set("season_start_day", "");
    expect(screen.queryByTestId("rule-season-summary")).toBeNull();
  });

  it("prova mancante: una regola bloccata dal motore ha caselle e pulsanti A–F spenti", async () => {
    s.editable = false;
    await open();
    expect(box("season_start_day")).toBeDisabled();
    expect(box("season_start_month")).toBeDisabled();
    expect(screen.getByTestId("rule-season-zone-A")).toBeDisabled();
    expect(screen.getByTestId("rule-season-zone-F")).toBeDisabled();
  });

  it("prova mancante: «Annulla le modifiche» dopo una scorciatoia rimette le date salvate", async () => {
    await open();
    fireEvent.click(screen.getByTestId("rule-season-zone-B"));
    expect(box("season_start_month")).toHaveValue("12");
    fireEvent.click(screen.getByTestId("rules-discard-btn"));
    expect(box("season_start_month")).toHaveValue("10");
    expect(box("season_end_day")).toHaveValue(15);
    expect(screen.getByTestId("rule-season-summary")).toHaveTextContent("Dal 15 ottobre al 15 aprile (zona E)");
    expect(screen.queryByTestId("rules-save-bar")).toBeNull();
  });
});
