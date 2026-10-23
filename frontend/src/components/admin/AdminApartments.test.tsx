import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { t } from "@/i18n";
import { platformApartmentsUrl } from "@/lib/routes";
import ApartmentsPage from "@/pages/ApartmentsPage";
import { AdminApartments } from "./AdminApartments";

// Apartments are created, relinked and deleted only by the platform manager, in every mode (D-77): the organization
// admin edits name, address, time zone and enabled, and checks the connection.
const state = vi.hoisted(() => ({
  instanceMode: "mock",
  platform: false,
  list: [] as unknown[],
  patchApartment: vi.fn(async (_id: string, _body: Record<string, unknown>) => ({})),
  apartments: [] as unknown[],
  listCalls: 0,
  orgPrice: null as number | null,
  patchTenant: vi.fn(async (_body: Record<string, unknown>) => ({})),
  verify: vi.fn(async (id: string) => ({ apartment_id: id, reachable: false, health: null, version: null, error: "Istanza non raggiungibile", contract_version: null, features: [], ok: false })),
}));

vi.mock("@/auth/AuthProvider", () => ({
  useAuth: () => ({ me: { role: "admin", user: { apartment_ids: "all", platform_manager: state.platform }, tenant: { tenant_id: "t-1", name: "Demo" }, env: { app_env: "staging", auth_mode: "firebase", fcm_enabled: false, simulator: true, instance_mode: state.instanceMode } } }),
  useRole: () => ({ role: "admin", canWrite: true, isAdmin: true, isPlatform: state.platform, hasTenant: true }),
}));
vi.mock("@/hooks/useFeatures", () => ({ useApartments: () => ({ data: state.list, isLoading: false }) }));
vi.mock("@/api/admin", () => ({
  adminApi: { apartments: async () => { state.listCalls++; return state.apartments; }, patchApartment: state.patchApartment, verify: state.verify, tenant: async () => ({ tenant_id: "t-1", name: "Demo", enabled_features: null, all_features: [], energy_price_eur_kwh: state.orgPrice }), patchTenant: state.patchTenant },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

function renderAdmin(path = "/admin") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <AdminApartments />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const renderList = () => render(<MemoryRouter><ApartmentsPage /></MemoryRouter>);

async function openEdit(id = "apt-001") {
  renderAdmin();
  fireEvent.click(await screen.findByTestId(`admin-apartment-edit-${id}`));
  return screen.findByTestId("apartment-dialog");
}

const save = () => act(async () => {
  fireEvent.click(screen.getByTestId("apartment-dialog-save"));
});

const field = (id: string) => screen.getByTestId(`apt-form-${id}`) as HTMLInputElement;

const APT = { apartment_id: "apt-001", name: "Milano Centro", address: "Via Roma 1", timezone: "Europe/Rome", instance_url: "mock://builtin", port: null, enabled: true, italianway_id: null, enabled_features: null };
const SUMMARY = { apartment_id: "apt-001", name: "Milano Centro", address: "Via Roma 1", timezone: "Europe/Rome", online: true, enabled: true, apartment: null, kwh_today: null, pending_approvals: 0 };

beforeEach(() => {
  vi.clearAllMocks();
  state.instanceMode = "mock";
  state.platform = false;
  state.list = [];
  state.apartments = [APT];
  state.orgPrice = null;
});

describe.each(["mock", "real"])("Amministrazione > Appartamenti, ambiente %s: li crea e li collega la piattaforma (D-77)", (mode) => {
  beforeEach(() => {
    state.instanceMode = mode;
    state.apartments = [{ ...APT, instance_url: "http://10.198.0.2:8101", port: 8101, italianway_id: "IW-7" }];
  });

  it("niente «Nuovo appartamento» né cestino; al loro posto la nota; la verifica resta con il suo invito", async () => {
    renderAdmin();
    await screen.findByTestId("admin-apartment-apt-001");
    expect(screen.queryByTestId("admin-add-apartment-btn")).not.toBeInTheDocument();
    expect(screen.getByTestId("admin-apartments-note")).toHaveTextContent(t("admin.apartments.createdByPlatform"));
    expect(screen.queryByTestId("admin-apartment-delete-apt-001")).not.toBeInTheDocument();
    expect(screen.getByTestId("admin-verify-btn-apt-001")).toBeInTheDocument();
    expect(screen.getByTestId("admin-verify-help-apt-001")).toHaveTextContent(t("admin.apartments.verifyHelp"));
  });

  it("modifica: collegamento e codice Italianway in sola lettura con la nota; si salvano solo nome, indirizzo, fuso e attivo", async () => {
    const dialog = await openEdit();
    expect(screen.queryByTestId("apt-form-apartment_id")).not.toBeInTheDocument();
    expect(screen.queryByTestId("apt-form-instance_url")).not.toBeInTheDocument();
    expect(screen.queryByTestId("apt-form-port")).not.toBeInTheDocument();
    expect(screen.queryByTestId("apt-form-italianway_id")).not.toBeInTheDocument();
    expect(within(dialog).getByTestId("apt-form-connection-locked")).toHaveTextContent("http://10.198.0.2:8101:8101");
    expect(within(dialog).getByTestId("apt-form-connection-locked")).toHaveTextContent(t("admin.apartments.connectionByPlatform"));
    expect(within(dialog).getByTestId("apt-form-italianway-locked")).toHaveTextContent("IW-7");
    expect(within(dialog).getByTestId("apt-form-italianway-locked")).toHaveTextContent(t("admin.apartments.italianwayByPlatform"));
    // D-183: the time zone is shown, set on the engine, not editable here
    expect(screen.queryByTestId("apt-form-timezone")).not.toBeInTheDocument();
    expect(within(dialog).getByTestId("apt-form-timezone-locked")).toHaveTextContent("Europe/Rome");
    expect(within(dialog).getByTestId("apt-form-timezone-locked")).toHaveTextContent(t("admin.apartments.timezoneOnEngine"));
    fireEvent.change(field("name"), { target: { value: "Milano Duomo" } });
    await save();
    expect(state.patchApartment).toHaveBeenCalledTimes(1);
    expect(state.patchApartment.mock.calls[0][0]).toBe("apt-001");
    // D-183: the time zone is set on the engine, never sent from here
    expect(state.patchApartment.mock.calls[0][1]).toEqual({ name: "Milano Duomo", address: "Via Roma 1", enabled: true });
    expect(screen.queryByTestId("apartment-dialog")).not.toBeInTheDocument();
  });

  it("il vecchio indirizzo «?nuovo=appartamento» non apre nessun modulo", async () => {
    renderAdmin("/admin?nuovo=appartamento");
    await screen.findByTestId("admin-apartment-apt-001");
    expect(screen.queryByTestId("apartment-dialog")).not.toBeInTheDocument();
  });
});

describe("amministratore che è anche gestore della piattaforma (D-82)", () => {
  it("Amministrazione > Appartamenti: nessuna nota «scrivi all'assistenza»; per gli altri admin resta", async () => {
    state.platform = true;
    renderAdmin();
    await screen.findByTestId("admin-apartment-apt-001");
    expect(screen.queryByTestId("admin-apartments-note")).not.toBeInTheDocument();
  });

  it("pagina Appartamenti: niente «scrivi all'assistenza HQE», resta «+ Appartamento»", () => {
    state.platform = true;
    state.list = [SUMMARY];
    renderList();
    expect(screen.queryByTestId("add-apartment-note")).not.toBeInTheDocument();
    expect(screen.getByTestId("add-apartment-btn")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(t("apartments.emptyHint"));
  });
});

describe("modifica: campi che il server scrive da sé non vengono rimandati", () => {
  it("né il segreto dell'istanza (D-60) né l'esito della verifica (D-66), anche se la risposta li conteneva", async () => {
    state.apartments = [{ ...APT, instance_secret_name: "vecchio-segreto", last_check: { ok: true, checked_at: "2026-10-16T08:00:00Z", error: null } }];
    await openEdit();
    await save();
    const body = state.patchApartment.mock.calls[0][1];
    expect(body).not.toHaveProperty("instance_secret_name");
    expect(body).not.toHaveProperty("last_check");
  });
});

describe("Amministrazione: ultima verifica della connessione (D-66, C-1)", () => {
  const base = { address: "", timezone: "Europe/Rome", instance_url: "mock://builtin", port: null, enabled: true, italianway_id: null, enabled_features: null };

  beforeEach(() => {
    state.listCalls = 0;
    state.apartments = [
      { ...base, apartment_id: "apt-001", name: "Milano", last_check: { ok: false, checked_at: "2026-10-16T08:00:00Z", error: "Istanza non raggiungibile" } },
      { ...base, apartment_id: "apt-002", name: "Rimini", last_check: null },
    ];
  });

  it("esito mostrato per ogni appartamento: non riuscita con il motivo, oppure mai eseguita", async () => {
    renderAdmin();
    expect(await screen.findByTestId("admin-apartment-check-apt-001")).toHaveTextContent("Istanza non raggiungibile");
    expect(screen.getByTestId("admin-apartment-check-apt-001")).toHaveAttribute("data-ok", "false");
    expect(screen.getByTestId("admin-apartment-check-apt-002")).toHaveTextContent(t("admin.apartments.lastCheckNever"));
  });

  it("dopo «Verifica connessione» la lista viene riletta (il server salva l'esito)", async () => {
    renderAdmin();
    await screen.findByTestId("admin-apartment-apt-002");
    const before = state.listCalls;
    await act(async () => {
      fireEvent.click(screen.getByTestId("admin-verify-btn-apt-002"));
    });
    expect(state.verify).toHaveBeenCalledWith("apt-002", expect.any(String));
    await waitFor(() => expect(state.listCalls).toBeGreaterThan(before));
  });
});

describe("pagina Appartamenti: come si aggiunge un appartamento (D-77)", () => {
  it("amministratore: niente «+ Appartamento», al suo posto «scrivi all'assistenza HQE»", () => {
    state.list = [SUMMARY];
    renderList();
    expect(screen.queryByTestId("add-apartment-btn")).not.toBeInTheDocument();
    expect(screen.getByTestId("add-apartment-note")).toHaveTextContent(t("apartments.emptyHint"));
  });

  it("amministratore senza appartamenti: lo dice lo stato vuoto, una volta sola", () => {
    renderList();
    expect(screen.getByTestId("apartments-empty")).toHaveTextContent(t("apartments.empty"));
    expect(screen.getByTestId("apartments-empty-hint")).toHaveTextContent(t("apartments.emptyHint"));
    expect(screen.queryByTestId("add-apartment-note")).not.toBeInTheDocument();
    expect(screen.queryByTestId("add-apartment-btn")).not.toBeInTheDocument();
  });

  it("gestore della piattaforma: «+ Appartamento» porta a Organizzazioni, sugli appartamenti della sua organizzazione", () => {
    state.platform = true;
    state.list = [SUMMARY];
    renderList();
    expect(screen.getByTestId("add-apartment-btn")).toHaveAttribute("href", platformApartmentsUrl("t-1"));
    expect(platformApartmentsUrl("t-1")).toBe("/organizzazioni?appartamenti=t-1");
    expect(screen.queryByTestId("add-apartment-note")).not.toBeInTheDocument();
  });

  it("gestore senza appartamenti: lo stato vuoto rimanda a Organizzazioni, e il pulsante c'è", () => {
    state.platform = true;
    renderList();
    expect(screen.getByTestId("apartments-empty-hint")).toHaveTextContent(t("apartments.emptyHintPlatform"));
    expect(screen.getByTestId("add-apartment-btn")).toBeInTheDocument();
  });

  it.each(["mock", "real"])("ambiente %s: stesso comportamento", (mode) => {
    state.instanceMode = mode;
    state.list = [SUMMARY];
    renderList();
    expect(screen.queryByTestId("add-apartment-btn")).not.toBeInTheDocument();
    expect(screen.getByTestId("add-apartment-note")).toBeInTheDocument();
  });
});

describe("prezzo dell'energia (P-52, D-92)", () => {
  it("dell'organizzazione: «0,25» diventa 0.25; salvato con PATCH /app/admin/tenant", async () => {
    renderAdmin();
    const input = await screen.findByTestId("admin-price-input");
    expect(screen.getByTestId("admin-price-save")).toBeDisabled(); // nothing changed yet
    fireEvent.change(input, { target: { value: "0,25" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("admin-price-save"));
    });
    expect(state.patchTenant).toHaveBeenCalledWith({ energy_price_eur_kwh: 0.25 }, expect.any(String));
  });

  it("valore non valido (oltre 10, troppi decimali): spiegazione e pulsante disattivato", async () => {
    renderAdmin();
    fireEvent.change(await screen.findByTestId("admin-price-input"), { target: { value: "12" } });
    expect(screen.getByTestId("admin-price-invalid")).toHaveTextContent(t("admin.price.invalid"));
    expect(screen.getByTestId("admin-price-save")).toBeDisabled();
  });

  it("campo svuotato: il prezzo dell'organizzazione viene tolto (null)", async () => {
    state.orgPrice = 0.22;
    renderAdmin();
    const input = await screen.findByTestId("admin-price-input");
    await waitFor(() => expect(input).toHaveValue("0,22"));
    fireEvent.change(input, { target: { value: "" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("admin-price-save"));
    });
    expect(state.patchTenant).toHaveBeenCalledWith({ energy_price_eur_kwh: null }, expect.any(String));
  });

  it("ogni appartamento dice quale prezzo vale: quello dell'organizzazione o il suo", async () => {
    state.orgPrice = 0.22;
    state.apartments = [APT, { ...APT, apartment_id: "apt-002", name: "Rimini", energy_price_eur_kwh: 0.3 }];
    renderAdmin();
    await waitFor(() => expect(screen.getByTestId("admin-apartment-price-apt-001")).toHaveTextContent(t("admin.price.lineOrg", { price: t("admin.price.value", { price: "0,22" }) })));
    expect(screen.getByTestId("admin-apartment-price-apt-002")).toHaveTextContent(t("admin.price.lineApt", { price: t("admin.price.value", { price: "0,3" }) }));
  });

  it("eccezione dell'appartamento in «Modifica»: mandata solo se cambia; vuota = di nuovo quello dell'organizzazione", async () => {
    state.apartments = [{ ...APT, energy_price_eur_kwh: 0.3 }];
    await openEdit();
    expect(field("price")).toHaveValue("0,3");
    await save();
    expect(state.patchApartment.mock.calls[0][1]).not.toHaveProperty("energy_price_eur_kwh");
    fireEvent.click(await screen.findByTestId("admin-apartment-edit-apt-001"));
    await screen.findByTestId("apartment-dialog");
    fireEvent.change(field("price"), { target: { value: "" } });
    await save();
    expect(state.patchApartment.mock.calls[1][1]).toMatchObject({ energy_price_eur_kwh: null });
  });

  it("eccezione non valida: spiegazione e «Salva» disattivato", async () => {
    await openEdit();
    fireEvent.change(field("price"), { target: { value: "0,123456" } });
    expect(screen.getByTestId("apt-form-price-hint")).toHaveTextContent(t("admin.price.invalid"));
    expect(screen.getByTestId("apartment-dialog-save")).toBeDisabled();
  });
});

describe("appartamenti dimostrativi (D-97, D-98)", () => {
  it("Amministrazione e pagina Appartamenti: etichetta «Dimostrativo» solo sui simulati", async () => {
    state.apartments = [{ ...APT, simulated: true }, { ...APT, apartment_id: "apt-002", name: "Rimini" }];
    renderAdmin();
    expect(await screen.findByTestId("admin-apartment-demo-apt-001")).toHaveTextContent(t("apartments.demo"));
    expect(screen.queryByTestId("admin-apartment-demo-apt-002")).not.toBeInTheDocument();
  });

  it("pagina Appartamenti: l'etichetta si vede nella scheda dell'appartamento", () => {
    state.list = [{ ...SUMMARY, simulated: true }, { ...SUMMARY, apartment_id: "apt-002" }];
    renderList();
    expect(screen.getByTestId("apartment-demo-apt-001")).toHaveTextContent(t("apartments.demo"));
    expect(screen.queryByTestId("apartment-demo-apt-002")).not.toBeInTheDocument();
  });
});
