import { Suspense } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { t } from "@/i18n";
import { browser, lazyPage, reloadOnce } from "@/lib/lazyPage";
import { ErrorBoundary, ONLINE_RELOAD_DELAY_MS, PageProblem } from "./PageProblem";

// E-29: an error while drawing a screen, or a page block still missing after the automatic reload, must not leave the
// page white.
let reload: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  sessionStorage.clear();
  reload = vi.spyOn(browser, "reload").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {}); // React logs the error caught by the boundary
});

afterEach(() => {
  vi.restoreAllMocks();
});

function Bomb(): never {
  throw new Error("errore di disegno");
}

describe("protezione dalla pagina bianca (E-29)", () => {
  it("nessun errore: si vede la pagina e nessun avviso", () => {
    render(<ErrorBoundary><p data-testid="page">pagina</p></ErrorBoundary>);
    expect(screen.getByTestId("page")).toBeInTheDocument();
    expect(screen.queryByTestId("page-problem")).not.toBeInTheDocument();
  });

  it("errore di disegno: il messaggio con Ricarica al posto della pagina bianca; ricarica solo chi preme", () => {
    render(<ErrorBoundary><Bomb /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent(t("errors.pageProblem"));
    expect(screen.getByRole("alert")).toHaveTextContent(t("errors.pageProblemHint"));
    expect(reload).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId("page-problem-reload"));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("errore di disegno senza rete: anche qui «Sei senza connessione»", () => {
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    render(<ErrorBoundary><Bomb /></ErrorBoundary>);
    expect(screen.getByRole("alert")).toHaveTextContent(t("errors.offline"));
  });

  it("blocco di pagina ancora mancante dopo la ricarica automatica: il messaggio, non la pagina bianca", async () => {
    reloadOnce(Date.now() - 5_000); // the automatic reload that just happened
    reload.mockClear();
    const Page = lazyPage(() => Promise.reject(new TypeError("Failed to fetch dynamically imported module")));
    render(<ErrorBoundary><Suspense fallback={<p>caricamento</p>}><Page /></Suspense></ErrorBoundary>);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(screen.getByTestId("page-problem")).toBeInTheDocument();
    expect(reload).not.toHaveBeenCalled();
  });
});

// D-211: the text says what the app knows for sure; when the network comes back the page reloads by itself, once.
describe("il testo secondo la causa e il ritorno della rete (D-211)", () => {
  const online = (value: boolean) => vi.spyOn(navigator, "onLine", "get").mockReturnValue(value);
  const fire = (name: "online" | "offline") => act(() => {
    window.dispatchEvent(new Event(name));
  });
  const shown = () => screen.getByTestId("page-problem");

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("dispositivo senza rete: «Sei senza connessione», che si riapre da sola", () => {
    online(false);
    render(<PageProblem cause="network" />);
    expect(shown()).toHaveAttribute("data-kind", "offline");
    expect(shown()).toHaveTextContent(t("errors.offline"));
    expect(shown()).toHaveTextContent(t("errors.offlineHint"));
    expect(screen.getByTestId("page-problem-reload")).toHaveTextContent(t("errors.reload"));
  });

  it("il server ha risposto con un errore (5xx): «Il servizio non risponde, riprova fra poco»", () => {
    online(true);
    render(<PageProblem cause="server" />);
    expect(shown()).toHaveAttribute("data-kind", "server");
    expect(shown()).toHaveTextContent(t("errors.serverDown"));
    expect(shown()).toHaveTextContent(t("errors.serverDownHint"));
  });

  it("nessuna risposta con il dispositivo che si dice in rete: il testo prudente, perché la rete può mancare lo stesso", () => {
    online(true);
    render(<PageProblem cause="network" />);
    expect(shown()).toHaveAttribute("data-kind", "unknown");
    expect(shown()).toHaveTextContent(t("errors.pageProblem"));
    expect(shown()).toHaveTextContent(t("errors.pageProblemHint"));
  });

  it("la rete cade mentre il messaggio è aperto: il testo diventa «Sei senza connessione»", () => {
    online(true);
    render(<PageProblem cause="server" />);
    fire("offline");
    expect(shown()).toHaveAttribute("data-kind", "offline");
  });

  it("la rete torna: dopo un istante la pagina si ricarica da sola, una volta", async () => {
    online(false);
    render(<PageProblem cause="network" />);
    fire("online");
    await vi.advanceTimersByTimeAsync(ONLINE_RELOAD_DELAY_MS - 1);
    expect(reload).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(reload).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(10 * 60_000);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("la rete torna e ricade subito: nessuna ricarica", async () => {
    online(false);
    render(<PageProblem cause="network" />);
    fire("online");
    fire("offline");
    await vi.advanceTimersByTimeAsync(10 * ONLINE_RELOAD_DELAY_MS);
    expect(reload).not.toHaveBeenCalled();
  });

  it("server muto con la rete presente: nessuna ricarica da sola, mai (niente cicli)", async () => {
    online(true);
    render(<PageProblem cause="server" />);
    await vi.advanceTimersByTimeAsync(60 * 60_000);
    expect(reload).not.toHaveBeenCalled();
  });

  it("chiuso il messaggio, il ritorno della rete non ricarica più", async () => {
    online(false);
    const { unmount } = render(<PageProblem cause="network" />);
    unmount();
    fire("online");
    await vi.advanceTimersByTimeAsync(10 * ONLINE_RELOAD_DELAY_MS);
    expect(reload).not.toHaveBeenCalled();
  });

  it("il ritardo prima della ricarica: un secondo e mezzo", () => {
    expect(ONLINE_RELOAD_DELAY_MS).toBe(1_500);
  });
});
