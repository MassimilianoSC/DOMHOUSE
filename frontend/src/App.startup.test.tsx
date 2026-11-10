import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { t } from "@/i18n";
import App from "./App";

// E-29: which screen each state of the start shows on a protected page. D-211: the same message, with what the app
// knows of the cause, on the sign-in page too, instead of the form.
const s = vi.hoisted(() => ({ status: "loading", problem: undefined as undefined | "network" | "server" }));

vi.mock("@/auth/AuthProvider", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/AuthProvider")>()),
  useAuth: () => ({ status: s.status, problem: s.problem, me: null }),
}));
vi.mock("@/components/layout/AppShell", () => ({ AppShell: () => <p data-testid="shell">app</p> }));

function open(path = "/impostazioni") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  s.problem = undefined;
});

describe("pagina protetta all'avvio (E-29)", () => {
  it("avvio non riuscito: il messaggio con Ricarica, non lo scheletro", () => {
    s.status = "unavailable";
    open();
    expect(screen.getByTestId("page-problem")).toBeInTheDocument();
    expect(screen.getByTestId("page-problem-reload")).toBeInTheDocument();
    expect(screen.queryByTestId("shell")).not.toBeInTheDocument();
  });

  it("il server ha risposto con un errore: il testo «Il servizio non risponde»", () => {
    s.status = "unavailable";
    s.problem = "server";
    open();
    expect(screen.getByRole("alert")).toHaveTextContent(t("errors.serverDown"));
  });

  it("in caricamento: nessun messaggio", () => {
    s.status = "loading";
    open();
    expect(screen.queryByTestId("page-problem")).not.toBeInTheDocument();
  });

  it("dentro: l'app, nessun messaggio", () => {
    s.status = "authenticated";
    open();
    expect(screen.getByTestId("shell")).toBeInTheDocument();
    expect(screen.queryByTestId("page-problem")).not.toBeInTheDocument();
  });
});

describe("pagina di accesso (D-211)", () => {
  it("profilo non letto: il messaggio con Ricarica al posto del modulo", () => {
    s.status = "unavailable";
    s.problem = "server";
    open("/login");
    expect(screen.getByRole("alert")).toHaveTextContent(t("errors.serverDown"));
    expect(screen.queryByTestId("login-submit-btn")).not.toBeInTheDocument();
  });

  it("non ancora entrato: il modulo, nessun messaggio", () => {
    s.status = "anonymous";
    vi.stubGlobal("fetch", vi.fn(async () => new Response("[]", { status: 200, headers: { "Content-Type": "application/json" } })));
    open("/login");
    expect(screen.queryByTestId("page-problem")).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
