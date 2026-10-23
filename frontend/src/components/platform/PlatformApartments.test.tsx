import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";
import type { MockInstance } from "vitest";
import { ApiError } from "@/api/bff";
import { t } from "@/i18n";
import { PlatformApartments } from "./PlatformApartments";

// Organizzazioni > an organization > Appartamenti (D-64, API shape D-66): the platform creates the apartment with its
// id, owns the connection, verifies and deletes; name and enabled stay with the organization admin.
const s = vi.hoisted(() => ({
  mode: "real",
  apartments: vi.fn(),
  createApartment: vi.fn(async (_tid: string, body: { apartment_id: string }) => ({ ...body })),
  patchConnection: vi.fn(async (_tid: string, _aid: string, _body: Record<string, unknown>) => ({})),
  verifyApartment: vi.fn(async (_tid: string, aid: string) => ({ apartment_id: aid, reachable: true, health: null, version: null, error: null, contract_version: "1.0.4", features: [], ok: true })),
  deleteApartment: vi.fn(async () => undefined),
}));

vi.mock("@/api/platform", () => ({
  platformApi: { apartments: s.apartments, createApartment: s.createApartment, patchConnection: s.patchConnection, verifyApartment: s.verifyApartment, deleteApartment: s.deleteApartment },
}));
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ me: { env: { instance_mode: s.mode } }, refreshMe: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const APTS = [
  { apartment_id: "apt-001", name: "Milano Centro", instance_url: "http://10.198.0.2:8101", port: null, enabled: true, timezone: "Europe/Rome", last_check: { ok: true, checked_at: "2026-10-16T08:00:00Z", error: null } },
  { apartment_id: "apt-002", name: "Rimini Mare", instance_url: "http://10.198.0.2:8102", port: 8102, enabled: false, timezone: "Europe/Rome", last_check: { ok: false, checked_at: "2026-10-16T09:00:00Z", error: "Istanza non raggiungibile" } },
  { apartment_id: "apt-003", name: "Nuovo", instance_url: "http://10.198.0.2:8103", port: null, enabled: true, timezone: "Europe/Rome", last_check: null },
];

let confirm: MockInstance<(message?: string) => boolean>;

async function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <PlatformApartments tenantId="t-1" tenantName="Flat Sharing" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await screen.findByTestId("platform-apt-apt-001");
}

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});
const type = (testId: string, value: string) => fireEvent.change(screen.getByTestId(testId), { target: { value } });

beforeEach(() => {
  vi.clearAllMocks();
  s.mode = "real";
  s.apartments.mockResolvedValue(APTS);
  confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  confirm.mockRestore();
});

describe("Piattaforma > Appartamenti di un'organizzazione", () => {
  it("elenco tecnico con l'esito dell'ultima verifica; nessun collegamento alle pagine dell'appartamento", async () => {
    await open();
    expect(screen.getByTestId("platform-apt-apt-001")).toHaveTextContent("http://10.198.0.2:8101");
    expect(screen.getByTestId("platform-apt-apt-002")).toHaveTextContent(t("admin.apartments.disabled"));
    expect(screen.getByTestId("platform-apt-check-apt-001")).toHaveAttribute("data-ok", "true");
    expect(screen.getByTestId("platform-apt-check-apt-002")).toHaveTextContent("Istanza non raggiungibile");
    expect(screen.getByTestId("platform-apt-check-apt-003")).toHaveTextContent(t("admin.apartments.lastCheckNever"));
    expect(document.querySelectorAll('a[href^="/a/"]')).toHaveLength(0);
  });

  it("nuovo appartamento in produzione: id, nome e collegamento; poi il promemoria della chiave dell'istanza", async () => {
    await open();
    await click(screen.getByTestId("platform-apt-add-btn-t-1"));
    const save = screen.getByTestId("platform-apt-create-save");
    expect(screen.getByTestId("apt-form-instance_url")).toHaveValue("");
    type("apt-form-apartment_id", "Apt 9");
    type("apt-form-name", "Bologna");
    type("apt-form-instance_url", "http://10.198.0.2:8109");
    expect(save).toBeDisabled(); // id with capitals and a space
    type("apt-form-apartment_id", "apt-009");
    await click(save);
    expect(s.createApartment).toHaveBeenCalledWith("t-1", { apartment_id: "apt-009", name: "Bologna", instance_url: "http://10.198.0.2:8109", port: null, timezone: "Europe/Rome", enabled: true, italianway_id: null, simulated: false }, expect.any(String));
    expect(toast.success).toHaveBeenCalledWith(t("platform.aptCreated", { id: "apt-009" }));
    expect(toast.info).toHaveBeenCalledWith(t("platform.aptKeyFirst"), expect.anything());
    await waitFor(() => expect(s.apartments).toHaveBeenCalledTimes(2));
  });

  it("dimostrativo in produzione (D-188): mock://builtin scritto a mano, nessun promemoria della chiave", async () => {
    await open();
    await click(screen.getByTestId("platform-apt-add-btn-t-1"));
    expect(screen.getByTestId("apt-form-instance_url").closest("div")).toHaveTextContent(t("admin.apartments.instanceUrlHint"));
    type("apt-form-apartment_id", "apt-demo-01");
    type("apt-form-name", "Demo");
    type("apt-form-instance_url", "mock://builtin");
    await click(screen.getByTestId("platform-apt-create-save"));
    expect(s.createApartment).toHaveBeenCalledWith("t-1", expect.objectContaining({ instance_url: "mock://builtin", simulated: true }), expect.any(String));
    expect(toast.info).not.toHaveBeenCalledWith(t("platform.aptKeyFirst"), expect.anything());
  });

  it("nuovo appartamento in staging (mock): parte da mock://builtin, nessun promemoria della chiave", async () => {
    s.mode = "mock";
    await open();
    await click(screen.getByTestId("platform-apt-add-btn-t-1"));
    expect(screen.getByTestId("apt-form-instance_url")).toHaveValue("mock://builtin");
    type("apt-form-apartment_id", "apt-010");
    type("apt-form-name", "Prova");
    await click(screen.getByTestId("platform-apt-create-save"));
    expect(s.createApartment).toHaveBeenCalledWith("t-1", expect.objectContaining({ instance_url: "mock://builtin" }), expect.any(String));
    expect(toast.info).not.toHaveBeenCalled();
  });

  it("modifica: SOLO collegamento e porta (nome e attivo restano all'amministratore)", async () => {
    await open();
    await click(screen.getByTestId("platform-apt-edit-apt-002"));
    const dialog = screen.getByTestId("platform-apt-connection-dialog-apt-002");
    expect(within(dialog).queryByTestId("apt-form-name")).not.toBeInTheDocument();
    expect(within(dialog).queryByTestId("apt-form-enabled")).not.toBeInTheDocument();
    expect(within(dialog).getByTestId("apt-form-port")).toHaveValue(8102);
    type("apt-form-instance_url", "http://10.198.0.2:8202");
    type("apt-form-port", "");
    await click(within(dialog).getByTestId("platform-apt-connection-save"));
    expect(s.patchConnection).toHaveBeenCalledWith("t-1", "apt-002", { instance_url: "http://10.198.0.2:8202", port: null }, expect.any(String));
    expect(toast.success).toHaveBeenCalledWith(t("platform.aptSaved"));
  });

  it("verifica: esito mostrato e lista riletta (il server salva l'ultima verifica)", async () => {
    await open();
    await click(screen.getByTestId("platform-apt-verify-apt-003"));
    expect(s.verifyApartment).toHaveBeenCalledWith("t-1", "apt-003", expect.any(String));
    expect(screen.getByTestId("verify-result-apt-003")).toHaveAttribute("data-ok", "true");
    await waitFor(() => expect(s.apartments).toHaveBeenCalledTimes(2));
  });

  it("eliminazione con conferma che nomina appartamento e organizzazione; annullando non si elimina", async () => {
    confirm.mockReturnValueOnce(false);
    await open();
    await click(screen.getByTestId("platform-apt-delete-apt-002"));
    expect(confirm).toHaveBeenCalledWith(t("platform.aptDeleteConfirm", { id: "apt-002", name: "Rimini Mare", tenant: "Flat Sharing" }));
    expect(s.deleteApartment).not.toHaveBeenCalled();
    await click(screen.getByTestId("platform-apt-delete-apt-002"));
    expect(s.deleteApartment).toHaveBeenCalledWith("t-1", "apt-002", expect.any(String));
    expect(toast.success).toHaveBeenCalledWith(t("platform.aptDeleted", { id: "apt-002" }));
  });
});

describe("Piattaforma: codice Italianway (D-72)", () => {
  it("nuovo appartamento con il codice: mandato ripulito dagli spazi", async () => {
    await open();
    await click(screen.getByTestId("platform-apt-add-btn-t-1"));
    type("apt-form-apartment_id", "apt-011");
    type("apt-form-name", "Con codice");
    type("apt-form-instance_url", "http://10.198.0.2:8111");
    type("apt-form-italianway_id", "  IW-11 ");
    await click(screen.getByTestId("platform-apt-create-save"));
    expect(s.createApartment).toHaveBeenCalledWith("t-1", expect.objectContaining({ italianway_id: "IW-11" }), expect.any(String));
  });

  it("modifica: codice mandato solo se cambia; svuotato = null (toglie il codice)", async () => {
    s.apartments.mockResolvedValue(APTS.map((a) => (a.apartment_id === "apt-002" ? { ...a, italianway_id: "IW-2" } : { ...a, italianway_id: null })));
    await open();
    await click(screen.getByTestId("platform-apt-edit-apt-002"));
    expect(screen.getByTestId("apt-form-italianway_id")).toHaveValue("IW-2");
    await click(screen.getByTestId("platform-apt-connection-save"));
    expect(s.patchConnection.mock.calls[0][2]).not.toHaveProperty("italianway_id");
    await click(screen.getByTestId("platform-apt-edit-apt-002"));
    type("apt-form-italianway_id", "");
    await click(screen.getByTestId("platform-apt-connection-save"));
    expect(s.patchConnection.mock.calls[1][2]).toMatchObject({ italianway_id: null });
  });
});

describe("Piattaforma: istanza simulata (D-97)", () => {
  it("motore simulato integrato (mock://): casella accesa e bloccata, con la spiegazione; la creazione manda simulated true", async () => {
    s.mode = "mock";
    await open();
    await click(screen.getByTestId("platform-apt-add-btn-t-1"));
    expect(screen.getByTestId("apt-form-simulated")).toBeChecked();
    expect(screen.getByTestId("apt-form-simulated")).toBeDisabled();
    expect(screen.getByTestId("apt-form-simulated-hint")).toHaveTextContent(t("platform.simulatedLocked"));
    type("apt-form-apartment_id", "apt-010");
    type("apt-form-name", "Prova");
    await click(screen.getByTestId("platform-apt-create-save"));
    expect(s.createApartment).toHaveBeenCalledWith("t-1", expect.objectContaining({ instance_url: "mock://builtin", simulated: true }), expect.any(String));
  });

  it("motore vero: casella libera e spenta all'inizio; accesa a mano, l'URL resta visibile e si manda simulated true", async () => {
    await open();
    await click(screen.getByTestId("platform-apt-edit-apt-001"));
    const dialog = screen.getByTestId("platform-apt-connection-dialog-apt-001");
    const box = within(dialog).getByTestId("apt-form-simulated");
    expect(box).not.toBeChecked();
    expect(box).toBeEnabled();
    expect(within(dialog).getByTestId("apt-form-instance_url")).toHaveValue("http://10.198.0.2:8101");
    await click(box);
    await click(within(dialog).getByTestId("platform-apt-connection-save"));
    expect(s.patchConnection).toHaveBeenCalledWith("t-1", "apt-001", { instance_url: "http://10.198.0.2:8101", port: null, simulated: true }, expect.any(String));
  });

  it("nell'elenco gli appartamenti simulati hanno l'etichetta «Dimostrativo»", async () => {
    s.apartments.mockResolvedValue([{ ...APTS[0], simulated: true }, APTS[1]]);
    await open();
    expect(screen.getByTestId("platform-apt-demo-apt-001")).toHaveTextContent(t("apartments.demo"));
    expect(screen.queryByTestId("platform-apt-demo-apt-002")).not.toBeInTheDocument();
  });

  it("codice Italianway su un appartamento mock:// in produzione (409 del server): il suo messaggio", async () => {
    s.patchConnection.mockRejectedValueOnce(new ApiError(409, "italianway_on_demo", "In produzione un appartamento dimostrativo non può avere un codice Italianway", "c-1"));
    await open();
    await click(screen.getByTestId("platform-apt-edit-apt-001"));
    type("apt-form-italianway_id", "IW-1");
    await click(screen.getByTestId("platform-apt-connection-save"));
    expect(toast.error).toHaveBeenCalledWith("In produzione un appartamento dimostrativo non può avere un codice Italianway", expect.anything());
  });
});

describe("Piattaforma: istanza simulata nel ricollegamento (N4, D-100)", () => {
  const MOCK = { ...APTS[0], instance_url: "mock://builtin", simulated: true };

  it("da mock:// a un motore vero senza toccare la casella: si spegne da sola e simulated non si manda (torna reale)", async () => {
    s.apartments.mockResolvedValue([MOCK, APTS[1]]);
    await open();
    await click(screen.getByTestId("platform-apt-edit-apt-001"));
    const dialog = screen.getByTestId("platform-apt-connection-dialog-apt-001");
    expect(within(dialog).getByTestId("apt-form-simulated")).toBeChecked();
    type("apt-form-instance_url", "http://10.198.0.2:8101");
    expect(within(dialog).getByTestId("apt-form-simulated")).not.toBeChecked();
    expect(within(dialog).getByTestId("apt-form-simulated")).toBeEnabled();
    await click(within(dialog).getByTestId("platform-apt-connection-save"));
    const body = s.patchConnection.mock.calls[0][2];
    expect(body).toEqual({ instance_url: "http://10.198.0.2:8101", port: null });
  });

  it("da mock:// a un motore vero tenendolo simulato: casella riaccesa a mano, simulated true esplicito", async () => {
    s.apartments.mockResolvedValue([MOCK, APTS[1]]);
    await open();
    await click(screen.getByTestId("platform-apt-edit-apt-001"));
    const dialog = screen.getByTestId("platform-apt-connection-dialog-apt-001");
    type("apt-form-instance_url", "http://10.198.0.2:8101");
    await click(within(dialog).getByTestId("apt-form-simulated"));
    await click(within(dialog).getByTestId("platform-apt-connection-save"));
    expect(s.patchConnection.mock.calls[0][2]).toEqual({ instance_url: "http://10.198.0.2:8101", port: null, simulated: true });
  });

  it("motore vero già simulato, salvato senza toccare la casella: resta com'è (simulated non si manda)", async () => {
    s.apartments.mockResolvedValue([{ ...APTS[0], simulated: true }, APTS[1]]);
    await open();
    await click(screen.getByTestId("platform-apt-edit-apt-001"));
    const dialog = screen.getByTestId("platform-apt-connection-dialog-apt-001");
    expect(within(dialog).getByTestId("apt-form-simulated")).toBeChecked();
    await click(within(dialog).getByTestId("platform-apt-connection-save"));
    expect(s.patchConnection.mock.calls[0][2]).not.toHaveProperty("simulated");
  });
});
