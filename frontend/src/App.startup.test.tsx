import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

// E-29: which screen each state of the start shows on a protected page.
const s = vi.hoisted(() => ({ status: "loading" }));

vi.mock("@/auth/AuthProvider", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/AuthProvider")>()),
  useAuth: () => ({ status: s.status, me: null }),
}));
vi.mock("@/components/layout/AppShell", () => ({ AppShell: () => <p data-testid="shell">app</p> }));

function open() {
  render(
    <MemoryRouter initialEntries={["/impostazioni"]}>
      <App />
    </MemoryRouter>,
  );
}

describe("pagina protetta all'avvio (E-29)", () => {
  it("avvio non riuscito: il messaggio con Ricarica, non lo scheletro", () => {
    s.status = "unavailable";
    open();
    expect(screen.getByTestId("page-problem")).toBeInTheDocument();
    expect(screen.getByTestId("page-problem-reload")).toBeInTheDocument();
    expect(screen.queryByTestId("shell")).not.toBeInTheDocument();
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
