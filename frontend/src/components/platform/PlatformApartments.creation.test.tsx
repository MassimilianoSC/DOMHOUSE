import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { PlatformApartment } from "@/api/platform";
import { PlatformApartments } from "./PlatformApartments";

// A2 in Organizzazioni > an organization > Appartamenti (docs/proposta-a2-sito.md §1, §3): «Nuovo appartamento» next to
// «Collega un sistema esistente», off before the click where the creation is not available (production until the second
// VM), and the rows of the creations in their three states.

const s = vi.hoisted(() => ({
  env: { app_env: "staging", instance_mode: "real", creazione_disponibile: true as boolean | undefined },
  apartments: vi.fn(),
  tenant: vi.fn(),
  createNew: vi.fn(),
  retryCreation: vi.fn(),
  cancelCreation: vi.fn(),
}));

vi.mock("@/api/platform", () => ({
  platformApi: { apartments: s.apartments, tenant: s.tenant, createNew: s.createNew, retryCreation: s.retryCreation, cancelCreation: s.cancelCreation },
}));
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ me: { env: s.env }, refreshMe: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const READY: PlatformApartment = { apartment_id: "apt-001", name: "Milano Centro", instance_url: "http://10.198.0.2:8101", port: null, enabled: true, timezone: "Europe/Rome", italianway_id: null, last_check: null, creazione: null };

function renderList() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <PlatformApartments tenantId="t-1" tenantName="Residenze Esempio" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function open(items: PlatformApartment[] = [READY]) {
  s.apartments.mockResolvedValue(items);
  renderList();
  await screen.findByTestId(`platform-apt-${items[0].apartment_id}`);
}

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

beforeEach(() => {
  vi.clearAllMocks();
  s.env = { app_env: "staging", instance_mode: "real", creazione_disponibile: true };
  s.tenant.mockResolvedValue({ tenant_id: "t-1", name: "Residenze Esempio", created_at: "", first_admin: null, creazioni_ultima_ora: { usate: 0, limite: 5, libera_dal: null } });
});

describe("dove si crea (§1)", () => {
  it("due pulsanti: «Nuovo appartamento» principale e «Collega un sistema esistente» meno in evidenza", async () => {
    await open();
    const create = screen.getByTestId("platform-apt-new-btn-t-1");
    const link = screen.getByTestId("platform-apt-add-btn-t-1");
    expect(create).toHaveTextContent("Nuovo appartamento");
    expect(link).toHaveTextContent("Collega un sistema esistente");
    expect(create).toBeEnabled();
    expect(link.className).toMatch(/border/); // outline
    expect(screen.queryByTestId("platform-apt-new-unavailable-t-1")).toBeNull();
  });

  it("«Nuovo appartamento» apre il modulo della creazione; «Collega» quello di oggi", async () => {
    await open();
    await click(screen.getByTestId("platform-apt-new-btn-t-1"));
    expect(await screen.findByTestId("new-apt-dialog")).toBeInTheDocument();
    expect(screen.queryByTestId("platform-apt-create-dialog")).toBeNull();
  });

  it("il modulo di «Collega» ha il titolo nuovo", async () => {
    await open();
    await click(screen.getByTestId("platform-apt-add-btn-t-1"));
    expect(screen.getByTestId("platform-apt-create-dialog")).toHaveTextContent("Collega un sistema esistente a Residenze Esempio");
  });

  it("in produzione: «Nuovo appartamento» si vede ma è spento, con la riga della seconda macchina virtuale", async () => {
    s.env = { app_env: "prod", instance_mode: "real", creazione_disponibile: false };
    await open();
    expect(screen.getByTestId("platform-apt-new-btn-t-1")).toBeDisabled();
    expect(screen.getByTestId("platform-apt-new-unavailable-t-1")).toHaveTextContent("Non disponibile in produzione: arriverà con la seconda macchina virtuale.");
    expect(screen.getByTestId("platform-apt-add-btn-t-1")).toBeEnabled();
  });

  it("nello staging senza agente: spento, con la sua riga", async () => {
    s.env = { app_env: "staging", instance_mode: "real", creazione_disponibile: false };
    await open();
    expect(screen.getByTestId("platform-apt-new-btn-t-1")).toBeDisabled();
    expect(screen.getByTestId("platform-apt-new-unavailable-t-1")).toHaveTextContent("Non disponibile in questo ambiente: manca il collegamento con la macchina virtuale.");
  });

  it("un server che non manda il campo: acceso (il 503 resta come riserva dentro il modulo)", async () => {
    s.env = { app_env: "prod", instance_mode: "real", creazione_disponibile: undefined };
    await open();
    expect(screen.getByTestId("platform-apt-new-btn-t-1")).toBeEnabled();
  });
});
