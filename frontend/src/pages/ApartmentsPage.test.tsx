import { act, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { HOME_IMAGE_ROTATION_MS, HOME_IMAGES } from "@/content/homeImages.it";
import ApartmentsPage from "./ApartmentsPage";

// The apartments page as Luca redid it (PR #19, merged 20 November, 1187) and the retouches after the merge: the mode
// written as the guide writes it («Casa vuota», not «Casa Vuota»), the demonstration apartments out of the total of
// «Consumo registrato oggi» (or the total said to be simulated), the photo that changes every 30 minutes only once the
// next one has loaded.
const s = vi.hoisted(() => ({ data: [] as unknown[], role: "admin" }));

vi.mock("@/hooks/useFeatures", () => ({ useApartments: () => ({ data: s.data, isLoading: false, isError: false }) }));
vi.mock("@/auth/AuthProvider", () => ({
  useAuth: () => ({ me: { user: { apartment_ids: "all" }, tenant: { tenant_id: "t1" } } }),
  useRole: () => ({ isAdmin: s.role === "admin", isPlatform: false }),
}));

const summary = (id: string, extra: object = {}) => ({
  apartment_id: id, name: `Appartamento ${id}`, address: "Via Prova 1", timezone: "Europe/Rome", enabled: true, online: true, simulated: false,
  apartment: { mode: "empty", occupancy: "vacant", next_checkin: null, next_checkout: null }, health: null, contract_version: "1.0.5", features: [], pending_approvals: 0, kwh_today: 2.5,
  ...extra,
});

function open() {
  render(
    <MemoryRouter>
      <ApartmentsPage />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  s.data = [];
  s.role = "admin";
});

describe("le tessere di ogni appartamento", () => {
  it("la modalità come nella guida: «Casa vuota», senza maiuscola a ogni parola", () => {
    s.data = [summary("a1")];
    open();
    const mode = screen.getByTestId("apartment-mode-a1");
    expect(mode).toHaveTextContent("Casa vuota");
    // CSS «capitalize» would show «Casa Vuota» whatever the text is
    for (const el of [mode, ...mode.querySelectorAll("*")]) expect(el.getAttribute("class") ?? "").not.toMatch(/(^|\s)capitalize(\s|$)/);
    expect(screen.getByTestId("apartment-occupancy-a1")).toHaveTextContent("Vuoto");
  });
});

describe("«Consumo registrato oggi»", () => {
  it("con appartamenti veri e dimostrativi: il totale dei soli veri, e lo dice", () => {
    s.data = [summary("vero", { kwh_today: 2.5 }), summary("demo", { kwh_today: 4.9, simulated: true })];
    open();
    const box = screen.getByTestId("home-energy-summary");
    expect(box).toHaveTextContent("2,5");
    expect(box).not.toHaveTextContent("7,4");
    expect(box).toHaveTextContent("Dato disponibile per 1 di 1 appartamenti");
    expect(within(box).getByTestId("home-energy-demos")).toHaveTextContent("Escluso 1 appartamento dimostrativo");
  });

  it("solo dimostrativi: il totale c'è, detto simulato", () => {
    s.data = [summary("d1", { kwh_today: 4.9, simulated: true }), summary("d2", { kwh_today: 4.6, simulated: true })];
    open();
    const box = screen.getByTestId("home-energy-summary");
    expect(box).toHaveTextContent("9,5");
    expect(within(box).getByTestId("home-energy-demos")).toHaveTextContent("Dati simulati degli appartamenti dimostrativi");
  });

  it("solo appartamenti veri: nessuna riga sui dimostrativi", () => {
    s.data = [summary("a1", { kwh_today: 1 }), summary("a2", { kwh_today: 2 })];
    open();
    expect(screen.getByTestId("home-energy-summary")).toHaveTextContent("3");
    expect(screen.queryByTestId("home-energy-demos")).toBeNull();
  });
});

describe("la foto in alto", () => {
  afterEach(() => vi.useRealTimers());

  it("cambia ogni 30 minuti, e solo quando la successiva è caricata", async () => {
    const start = new Date("2026-11-20T10:00:00Z").getTime();
    vi.useFakeTimers({ now: start });
    const loads: (() => void)[] = [];
    class FakeImage {
      onload: (() => void) | null = null;
      set src(_v: string) {
        loads.push(() => this.onload?.());
      }
    }
    vi.stubGlobal("Image", FakeImage);
    s.data = [summary("a1")];
    open();
    const first = Math.floor(start / HOME_IMAGE_ROTATION_MS) % HOME_IMAGES.length;
    const photo = () => screen.getByTestId("apartments-header").querySelector("img")!.getAttribute("src");
    expect(HOME_IMAGE_ROTATION_MS).toBe(30 * 60_000);
    expect(photo()).toBe(HOME_IMAGES[first].src);
    await act(async () => {
      vi.advanceTimersByTime(HOME_IMAGE_ROTATION_MS);
    });
    // asked, not loaded yet: the old one stays
    expect(loads).toHaveLength(1);
    expect(photo()).toBe(HOME_IMAGES[first].src);
    await act(async () => {
      loads[0]();
    });
    expect(photo()).toBe(HOME_IMAGES[(first + 1) % HOME_IMAGES.length].src);
  });
});
