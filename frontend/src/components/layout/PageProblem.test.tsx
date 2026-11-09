import { Suspense } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { t } from "@/i18n";
import { browser, lazyPage, reloadOnce } from "@/lib/lazyPage";
import { ErrorBoundary } from "./PageProblem";

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
