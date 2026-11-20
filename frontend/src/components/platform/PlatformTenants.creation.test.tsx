import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { PlatformTenants } from "./PlatformTenants";

// A2 on the organization's card (docs/proposta-a2-sito.md §4, the committente's condition 1): a creation stopped half-way
// is in sight even with the apartments' list closed, with «Vedi» that opens the list at its row.

const s = vi.hoisted(() => ({ tenants: vi.fn(), apartments: vi.fn() }));

vi.mock("@/api/platform", () => ({ platformApi: { tenants: s.tenants, apartments: s.apartments } }));
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ refreshMe: vi.fn(), enterSupport: vi.fn(), leaveSupport: vi.fn(), me: { tenant: null, support: null, env: { app_env: "staging", instance_mode: "real", creazione_disponibile: true } } }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const tenant = (tenant_id: string, name: string, counts: { appartamenti_non_creati?: number; appartamenti_in_preparazione?: number }) => ({
  tenant_id, name, created_at: "2026-11-03T09:12:00Z", first_admin: { email: "amministrazione@esempio.it", pending: false }, ...counts,
});
const STOPPED = {
  apartment_id: "lab-ponte", name: "Bilocale Ponte", instance_url: "", port: null, enabled: true, timezone: "Europe/Rome", italianway_id: null, last_check: null,
  creazione: { stato: "non_creato", passo: "motore", version: 7, porta: 8152, op: null, fatti: ["id", "porta"], updated_at: "2026-11-19T16:05:00Z", updated_by: "Giulia Rossi" },
};
const READY = { ...STOPPED, apartment_id: "apt-001", name: "Milano Centro", instance_url: "http://10.198.0.2:8101", creazione: null };

const scrolled: string[] = [];

async function open(list: unknown[]) {
  s.tenants.mockResolvedValue(list);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/organizzazioni"]}>
        <PlatformTenants />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByTestId(`tenant-${(list[0] as { tenant_id: string }).tenant_id}`);
}

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

beforeEach(() => {
  vi.clearAllMocks();
  scrolled.length = 0;
  s.apartments.mockResolvedValue([READY, STOPPED]);
  Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
    scrolled.push(this.getAttribute("data-testid") ?? "");
  });
});

describe("la riga sulla scheda dell'organizzazione (§4)", () => {
  it("una creazione non riuscita: riga rossa con «Vedi», anche a elenco chiuso", async () => {
    await open([tenant("t-1", "Residenze Esempio", { appartamenti_non_creati: 1, appartamenti_in_preparazione: 1 })]);
    const line = screen.getByTestId("tenant-creations-t-1");
    expect(line).toHaveTextContent("1 appartamento non creato: serve «Riprova» o «Annulla»");
    expect(line).toHaveAttribute("data-tone", "negative");
    expect(line.className).toMatch(/negative/);
    expect(screen.getByTestId("tenant-creations-see-t-1")).toHaveTextContent("Vedi");
    expect(screen.queryByTestId("platform-apartments-t-1")).toBeNull();
  });

  it("più di una: al plurale", async () => {
    await open([tenant("t-1", "Residenze Esempio", { appartamenti_non_creati: 2 })]);
    expect(screen.getByTestId("tenant-creations-t-1")).toHaveTextContent("2 appartamenti non creati: serve «Riprova» o «Annulla»");
  });

  it("solo creazioni in corso: riga neutra, senza «Vedi»", async () => {
    await open([tenant("t-2", "Case Prova", { appartamenti_in_preparazione: 1 })]);
    const line = screen.getByTestId("tenant-creations-t-2");
    expect(line).toHaveTextContent("1 appartamento in preparazione");
    expect(line).toHaveAttribute("data-tone", "neutral");
    expect(screen.queryByTestId("tenant-creations-see-t-2")).toBeNull();
  });

  it("nessuna, o un server che non manda i conteggi: niente riga", async () => {
    await open([tenant("t-1", "A", { appartamenti_non_creati: 0, appartamenti_in_preparazione: 0 }), tenant("t-2", "B", {})]);
    expect(screen.queryByTestId("tenant-creations-t-1")).toBeNull();
    expect(screen.queryByTestId("tenant-creations-t-2")).toBeNull();
  });

  it("«Vedi» apre l'elenco e porta alla riga «Non creato»", async () => {
    await open([tenant("t-1", "Residenze Esempio", { appartamenti_non_creati: 1 })]);
    await click(screen.getByTestId("tenant-creations-see-t-1"));
    expect(screen.getByTestId("tenant-apartments-btn-t-1")).toHaveAttribute("aria-expanded", "true");
    await screen.findByTestId("platform-apt-lab-ponte");
    await waitFor(() => expect(scrolled).toContain("platform-apt-lab-ponte"));
    expect(document.activeElement).toBe(screen.getByTestId("platform-apt-lab-ponte"));
  });

  it("«Vedi» con l'elenco già aperto non lo chiude, e porta alla riga", async () => {
    await open([tenant("t-1", "Residenze Esempio", { appartamenti_non_creati: 1 })]);
    await click(screen.getByTestId("tenant-apartments-btn-t-1"));
    await screen.findByTestId("platform-apt-lab-ponte");
    expect(scrolled).toEqual([]);
    await click(screen.getByTestId("tenant-creations-see-t-1"));
    expect(screen.getByTestId("tenant-apartments-btn-t-1")).toHaveAttribute("aria-expanded", "true");
    await waitFor(() => expect(scrolled).toContain("platform-apt-lab-ponte"));
  });
});
