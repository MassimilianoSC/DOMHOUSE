import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import type { Creazione, PlatformApartment } from "@/api/platform";
import { PlatformApartments } from "./PlatformApartments";

// D-198 (22 Nov): an apartment created from the app had no way to get its Italianway code after the creation, although
// the creation form says «Si può aggiungere anche dopo»: no «Modifica collegamento» for it, and the server refused. Now
// its row has «Codice Italianway», a window with that one field; the connection stays the creation's.

const s = vi.hoisted(() => ({
  env: { app_env: "staging", instance_mode: "real", creazione_disponibile: true as boolean | undefined },
  apartments: vi.fn(),
  tenant: vi.fn(),
  setItalianwayCode: vi.fn(),
  patchConnection: vi.fn(),
  credList: vi.fn(),
}));

vi.mock("@/api/platform", () => ({
  platformApi: { apartments: s.apartments, tenant: s.tenant, setItalianwayCode: s.setItalianwayCode, patchConnection: s.patchConnection },
}));
vi.mock("@/api/deviceCredentials", () => ({ credentialsApi: () => ({ list: s.credList }) }));
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ me: { env: s.env }, refreshMe: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const BY_HAND: PlatformApartment = { apartment_id: "apt-001", name: "Milano Centro", instance_url: "http://10.198.0.2:8101", port: null, enabled: true, timezone: "Europe/Rome", italianway_id: null, last_check: null, creazione: null };
const ready = (over: Partial<Creazione> = {}): Creazione => ({
  stato: "pronto", passo: "collegamento", version: 5, porta: 8153, op: null, codice: null, messaggio: null, fatti: ["id", "porta", "segreti", "motore", "collegamento"], updated_at: "2026-11-19T16:21:00Z", updated_by: "Giulia Rossi", ...over,
});
const CREATED: PlatformApartment = { ...BY_HAND, apartment_id: "lab-corte", name: "Monolocale Corte", instance_url: "http://10.198.0.2:8153", creazione: ready() };
const PREPARING: PlatformApartment = { ...CREATED, apartment_id: "lab-giardino", name: "Trilocale Giardino", instance_url: "", creazione: ready({ stato: "in_preparazione", passo: "motore" }) };

async function open(items: PlatformApartment[]) {
  s.apartments.mockResolvedValue(items);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <PlatformApartments tenantId="t-1" tenantName="Residenze Esempio" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByTestId(`platform-apt-${items[0].apartment_id}`);
}

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

async function openDialog(a: PlatformApartment = CREATED) {
  await open([a]);
  await click(screen.getByTestId(`platform-apt-italianway-${a.apartment_id}`));
  return screen.findByTestId(`platform-apt-italianway-dialog-${a.apartment_id}`);
}
const field = () => screen.getByTestId("apt-italianway-code") as HTMLInputElement;
const save = () => screen.getByTestId("apt-italianway-save");

beforeEach(() => {
  vi.clearAllMocks();
  s.credList.mockResolvedValue({ items: [] });
  s.tenant.mockResolvedValue({ tenant_id: "t-1", name: "Residenze Esempio", created_at: "", first_admin: null, creazioni_ultima_ora: { usate: 0, limite: 5, libera_dal: null } });
  s.setItalianwayCode.mockImplementation(async (_t: string, aptId: string, code: string | null) => ({ ...CREATED, apartment_id: aptId, italianway_id: code }));
});

describe("codice Italianway di un appartamento creato dall'app (D-198)", () => {
  it("la riga ha «Codice Italianway» e non «Modifica collegamento»; quella collegata a mano resta com'era", async () => {
    await open([CREATED, BY_HAND]);
    const row = screen.getByTestId("platform-apt-lab-corte");
    expect(within(row).getByTestId("platform-apt-italianway-lab-corte")).toHaveTextContent("Codice Italianway");
    expect(within(row).queryByTestId("platform-apt-edit-lab-corte")).toBeNull();
    const byHand = screen.getByTestId("platform-apt-apt-001");
    expect(within(byHand).getByTestId("platform-apt-edit-apt-001")).toBeInTheDocument();
    expect(within(byHand).queryByTestId("platform-apt-italianway-apt-001")).toBeNull();
  });

  it("non c'è finché la creazione non è finita", async () => {
    await open([PREPARING]);
    expect(screen.queryByTestId("platform-apt-italianway-lab-giardino")).toBeNull();
  });

  it("aggiungere il codice: la finestra ha solo quel campo, si salva e la riga lo mostra", async () => {
    const dialog = await openDialog();
    expect(dialog).toHaveTextContent("Codice Italianway di «Monolocale Corte»");
    expect(within(dialog).getAllByRole("textbox")).toHaveLength(1);
    expect(dialog).toHaveTextContent("Decide a quale appartamento arrivano le prenotazioni di Italianway. Vuoto = nessun codice.");
    expect(save()).toBeDisabled(); // nothing changed yet
    fireEvent.change(field(), { target: { value: "  IW-4471  " } });
    s.apartments.mockResolvedValue([{ ...CREATED, italianway_id: "IW-4471" }]);
    await click(save());
    expect(s.setItalianwayCode).toHaveBeenCalledWith("t-1", "lab-corte", "IW-4471", expect.any(String));
    expect(s.patchConnection).not.toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalledWith("Codice Italianway di «Monolocale Corte» salvato.");
    await waitFor(() => expect(screen.queryByTestId("platform-apt-italianway-dialog-lab-corte")).toBeNull());
    await waitFor(() => expect(screen.getByTestId("platform-apt-lab-corte")).toHaveTextContent("IW IW-4471"));
  });

  it("cambiarlo: il campo parte dal codice di oggi", async () => {
    await openDialog({ ...CREATED, italianway_id: "IW-1000" });
    expect(field().value).toBe("IW-1000");
    fireEvent.change(field(), { target: { value: "IW-2000" } });
    await click(save());
    expect(s.setItalianwayCode).toHaveBeenCalledWith("t-1", "lab-corte", "IW-2000", expect.any(String));
  });

  it("toglierlo: campo vuoto = nessun codice", async () => {
    await openDialog({ ...CREATED, italianway_id: "IW-1000" });
    fireEvent.change(field(), { target: { value: "" } });
    await click(save());
    expect(s.setItalianwayCode).toHaveBeenCalledWith("t-1", "lab-corte", null, expect.any(String));
    expect(toast.success).toHaveBeenCalledWith("Codice Italianway di «Monolocale Corte» tolto.");
  });

  it("codice già usato da un altro appartamento: il messaggio del server sotto il campo, la finestra resta aperta", async () => {
    s.setItalianwayCode.mockRejectedValueOnce(new ApiError(409, "external_id_in_use", "Codice Italianway già in uso", "c-1"));
    await openDialog();
    fireEvent.change(field(), { target: { value: "IW-4471" } });
    await click(save());
    expect(screen.getByTestId("apt-italianway-problem")).toHaveTextContent("Codice Italianway già in uso");
    expect(screen.getByTestId("platform-apt-italianway-dialog-lab-corte")).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
    // writing again clears the message
    fireEvent.change(field(), { target: { value: "IW-4472" } });
    expect(screen.queryByTestId("apt-italianway-problem")).toBeNull();
  });

  it("un altro errore: l'avviso rosso con l'ID richiesta, la finestra resta aperta", async () => {
    s.setItalianwayCode.mockRejectedValueOnce(new ApiError(500, "error", "Errore interno del server", "c-2"));
    await openDialog();
    fireEvent.change(field(), { target: { value: "IW-4471" } });
    await click(save());
    expect(toast.error).toHaveBeenCalledWith("Errore interno del server", expect.anything());
    expect(screen.getByTestId("platform-apt-italianway-dialog-lab-corte")).toBeInTheDocument();
  });

  it("«Annulla» chiude senza salvare", async () => {
    await openDialog();
    fireEvent.change(field(), { target: { value: "IW-4471" } });
    await click(screen.getByTestId("apt-italianway-cancel"));
    expect(screen.queryByTestId("platform-apt-italianway-dialog-lab-corte")).toBeNull();
    expect(s.setItalianwayCode).not.toHaveBeenCalled();
  });
});
