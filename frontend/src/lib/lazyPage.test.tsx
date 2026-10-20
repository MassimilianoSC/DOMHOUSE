import { Component, Suspense, type ReactNode } from "react";
import { act, render, screen } from "@testing-library/react";
import { browser, lazyPage, reloadOnce } from "./lazyPage";

// A page block missing after a release (stale tab): one automatic reload, never a loop, never a blank screen while
// the reload is under way.
class Boundary extends Component<{ children: ReactNode }, { error: string | null }> {
  state = { error: null as string | null };
  static getDerivedStateFromError(e: Error) {
    return { error: e.message };
  }
  render() {
    return this.state.error ? <p data-testid="boundary-error">{this.state.error}</p> : this.props.children;
  }
}

function show(Page: ReturnType<typeof lazyPage>) {
  render(
    <Boundary>
      <Suspense fallback={<p data-testid="fallback">caricamento</p>}>
        <Page />
      </Suspense>
    </Boundary>,
  );
}

const flush = () => act(async () => {
  await new Promise((r) => setTimeout(r, 0));
});

let reload: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  sessionStorage.clear();
  reload = vi.spyOn(browser, "reload").mockImplementation(() => {});
  vi.spyOn(console, "error").mockImplementation(() => {}); // React logs the error caught by the boundary
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ricarica dopo una pubblicazione (blocco di pagina mancante)", () => {
  it("reloadOnce ricarica la prima volta, non di nuovo entro un minuto, di nuovo dopo", () => {
    expect(reloadOnce(1_000_000)).toBe(true);
    expect(reloadOnce(1_030_000)).toBe(false);
    expect(reloadOnce(1_061_000)).toBe(true);
    expect(reload).toHaveBeenCalledTimes(2);
  });

  it("pagina caricata: si vede la pagina, nessuna ricarica", async () => {
    show(lazyPage(async () => ({ default: () => <p data-testid="page">pagina</p> })));
    expect(await screen.findByTestId("page")).toBeInTheDocument();
    expect(reload).not.toHaveBeenCalled();
  });

  it("blocco mancante: ricarica una volta e intanto resta lo scheletro di caricamento, senza errore", async () => {
    show(lazyPage(() => Promise.reject(new TypeError("Failed to fetch dynamically imported module"))));
    await flush();
    expect(reload).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("fallback")).toBeInTheDocument();
    expect(screen.queryByTestId("boundary-error")).not.toBeInTheDocument();
  });

  it("blocco ancora mancante subito dopo la ricarica: niente secondo giro, l'errore emerge", async () => {
    reloadOnce(Date.now() - 5_000); // the reload that just happened
    reload.mockClear();
    show(lazyPage(() => Promise.reject(new TypeError("Failed to fetch dynamically imported module"))));
    expect(await screen.findByTestId("boundary-error")).toHaveTextContent("Failed to fetch dynamically imported module");
    expect(reload).not.toHaveBeenCalled();
  });
});
