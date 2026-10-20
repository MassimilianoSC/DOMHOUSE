import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { t } from "@/i18n";
import { PlatformTenants } from "./PlatformTenants";

// Organizzazioni > list, creation, rename, resend (P-36, API shape D-61a), with the BFF simulated.
const s = vi.hoisted(() => ({
  tenants: vi.fn(),
  createTenant: vi.fn(),
  renameTenant: vi.fn(async (_id: string, name: string) => ({ tenant_id: "t-1", name, created_at: "", first_admin: null })),
  resendInvite: vi.fn(),
  refreshMe: vi.fn(async () => {}),
  suspendTenant: vi.fn(),
  reactivateTenant: vi.fn(),
  openSupport: vi.fn(),
  closeSupport: vi.fn(async () => undefined),
  enterSupport: vi.fn(async () => {}),
  leaveSupport: vi.fn(async () => {}),
  ownTenant: "t-0",
  ownSupport: null as null | { access_id: string },
}));

vi.mock("@/api/platform", () => ({ platformApi: { tenants: s.tenants, createTenant: s.createTenant, renameTenant: s.renameTenant, resendInvite: s.resendInvite, suspendTenant: s.suspendTenant, reactivateTenant: s.reactivateTenant, openSupport: s.openSupport, closeSupport: s.closeSupport } }));
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ refreshMe: s.refreshMe, enterSupport: s.enterSupport, leaveSupport: s.leaveSupport, me: { tenant: { tenant_id: s.ownTenant, name: "Mia" }, support: s.ownSupport } }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const LIST = [
  { tenant_id: "t-1", name: "Flat Sharing", created_at: "2026-10-01T08:00:00Z", first_admin: { email: "anna@fs.it", pending: true } },
  { tenant_id: "t-2", name: "Riviera Rent", created_at: "2026-10-02T08:00:00Z", first_admin: { email: "bruno@rr.it", pending: false } },
  { tenant_id: "t-3", name: "Senza admin", created_at: "2026-10-03T08:00:00Z", first_admin: null },
];

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

async function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/organizzazioni"]}>
        <PlatformTenants />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

beforeEach(() => {
  vi.clearAllMocks();
  s.ownTenant = "t-0";
  s.ownSupport = null;
  s.tenants.mockResolvedValue(LIST);
});

describe("Organizzazioni: elenco", () => {
  it("nome e stato del primo amministratore; «Reinvia invito» solo per chi non è ancora entrato", async () => {
    await open();
    expect(await screen.findByTestId("tenant-name-t-1")).toHaveTextContent("Flat Sharing");
    expect(screen.getByTestId("tenant-admin-t-1")).toHaveTextContent(`anna@fs.it${t("platform.pending")}`);
    expect(screen.getByTestId("tenant-admin-t-2")).toHaveTextContent(`bruno@rr.it${t("platform.active")}`);
    expect(screen.getByTestId("tenant-admin-t-3")).toHaveTextContent(t("platform.noAdmin"));
    expect(screen.getByTestId("tenant-resend-btn-t-1")).toBeInTheDocument();
    expect(screen.queryByTestId("tenant-resend-btn-t-2")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tenant-resend-btn-t-3")).not.toBeInTheDocument();
  });

  it("ruolo tolto mentre la pagina è aperta (403): «Non hai più accesso» e il profilo viene ricaricato", async () => {
    s.tenants.mockRejectedValue(new ApiError(403, "forbidden", "Solo per i gestori della piattaforma", "c-1"));
    await open();
    expect(await screen.findByTestId("tenants-error-no-access")).toHaveTextContent(t("platform.noAccess"));
    expect(s.refreshMe).toHaveBeenCalledTimes(1);
  });
});

describe("Organizzazioni: creazione", () => {
  it("nome ed email obbligatori; una sola chiamata, senza il nome dell'amministratore se vuoto; avviso e chiusura", async () => {
    s.createTenant.mockResolvedValueOnce({ tenant_id: "t-9", name: "Nuova Srl", created_at: "", first_admin: { email: "capo@nuova.it", pending: true }, email_status: "sent" });
    await open();
    await click(await screen.findByTestId("tenant-add-btn"));
    const dialog = screen.getByTestId("tenant-create-dialog");
    const save = within(dialog).getByTestId("tenant-create-save");
    expect(save).toBeDisabled();
    fireEvent.change(within(dialog).getByTestId("tenant-form-name"), { target: { value: " Nuova Srl " } });
    fireEvent.change(within(dialog).getByTestId("tenant-form-email"), { target: { value: "capo@" } });
    expect(save).toBeDisabled();
    fireEvent.change(within(dialog).getByTestId("tenant-form-email"), { target: { value: "capo@nuova.it" } });
    await click(save);
    expect(s.createTenant).toHaveBeenCalledWith({ name: "Nuova Srl", admin_email: "capo@nuova.it" }, expect.any(String));
    expect(toast.success).toHaveBeenCalledWith(t("platform.created", { name: "Nuova Srl", email: "capo@nuova.it" }));
    expect(screen.queryByTestId("tenant-create-dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(s.tenants).toHaveBeenCalledTimes(2));
  });

  it("email non partita: l'organizzazione c'è, avviso di usare «Reinvia invito»", async () => {
    s.createTenant.mockResolvedValueOnce({ tenant_id: "t-9", name: "Nuova Srl", created_at: "", first_admin: { email: "capo@nuova.it", pending: true }, email_status: "failed" });
    await open();
    await click(await screen.findByTestId("tenant-add-btn"));
    fireEvent.change(screen.getByTestId("tenant-form-name"), { target: { value: "Nuova Srl" } });
    fireEvent.change(screen.getByTestId("tenant-form-email"), { target: { value: "capo@nuova.it" } });
    fireEvent.change(screen.getByTestId("tenant-form-admin-name"), { target: { value: "Carla" } });
    await click(screen.getByTestId("tenant-create-save"));
    expect(s.createTenant).toHaveBeenCalledWith({ name: "Nuova Srl", admin_email: "capo@nuova.it", admin_display_name: "Carla" }, expect.any(String));
    expect(toast.warning).toHaveBeenCalledWith(t("platform.createdEmailFailed", { name: "Nuova Srl", email: "capo@nuova.it" }), expect.anything());
  });

  it("nome già usato (409): messaggio del server, la finestra resta aperta", async () => {
    s.createTenant.mockRejectedValueOnce(new ApiError(409, "tenant_name_taken", "Esiste già un'organizzazione con questo nome", "c-2", { tenant_id: "t-1" }));
    await open();
    await click(await screen.findByTestId("tenant-add-btn"));
    fireEvent.change(screen.getByTestId("tenant-form-name"), { target: { value: "flat sharing" } });
    fireEvent.change(screen.getByTestId("tenant-form-email"), { target: { value: "x@y.it" } });
    await click(screen.getByTestId("tenant-create-save"));
    expect(toast.error).toHaveBeenCalledWith("Esiste già un'organizzazione con questo nome", expect.anything());
    expect(screen.getByTestId("tenant-create-dialog")).toBeInTheDocument();
  });
});

describe("Organizzazioni: rinomina e reinvio", () => {
  it("rinomina: PATCH con il nuovo nome e «Nome aggiornato»", async () => {
    await open();
    await click(await screen.findByTestId("tenant-rename-btn-t-1"));
    fireEvent.change(screen.getByTestId("tenant-rename-input"), { target: { value: "Flat Sharing Italia" } });
    await click(screen.getByTestId("tenant-rename-save"));
    expect(s.renameTenant).toHaveBeenCalledWith("t-1", "Flat Sharing Italia", expect.any(String));
    expect(toast.success).toHaveBeenCalledWith(t("platform.renamed"));
  });

  it("reinvio: «Invito inviato di nuovo»; se nel frattempo è entrato (409) messaggio del server e lista aggiornata", async () => {
    s.resendInvite.mockResolvedValueOnce({ ...LIST[0], first_admin: { email: "anna.nuova@fs.it", pending: true }, email_status: "sent" });
    await open();
    await click(await screen.findByTestId("tenant-resend-btn-t-1"));
    expect(s.resendInvite).toHaveBeenCalledWith("t-1", expect.any(String));
    expect(toast.success).toHaveBeenCalledWith(t("platform.resent", { email: "anna.nuova@fs.it" })); // read from the answer (row + email_status)
    s.resendInvite.mockRejectedValueOnce(new ApiError(409, "already_active", "Il primo amministratore è già entrato", "c-3"));
    await click(screen.getByTestId("tenant-resend-btn-t-1"));
    expect(toast.error).toHaveBeenCalledWith("Il primo amministratore è già entrato", expect.anything());
    await waitFor(() => expect(s.tenants.mock.calls.length).toBeGreaterThanOrEqual(3));
  });
});

describe("Organizzazioni: sospensione (P-50, D-85)", () => {
  const SUSP = { ...LIST[1], suspended: true, suspended_at: "2026-10-16T09:00:00Z", suspended_reason: "Contratto scaduto" };

  it("«Sospendi»: motivo obbligatorio (spazi esclusi), spiegazione delle conseguenze, POST con il motivo, avviso e lista aggiornata", async () => {
    s.suspendTenant.mockResolvedValueOnce({ ...LIST[0], suspended: true, suspended_at: "2026-10-16T09:00:00Z", suspended_reason: "Prova" });
    await open();
    await click(await screen.findByTestId("tenant-suspend-btn-t-1"));
    const dialog = screen.getByTestId("tenant-suspend-dialog-t-1");
    expect(dialog).toHaveTextContent(t("platform.suspendHint"));
    const confirm = within(dialog).getByTestId("tenant-suspend-confirm");
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByTestId("tenant-suspend-reason"), { target: { value: "   " } });
    expect(confirm).toBeDisabled();
    fireEvent.change(within(dialog).getByTestId("tenant-suspend-reason"), { target: { value: " Prova " } });
    await click(confirm);
    expect(s.suspendTenant).toHaveBeenCalledWith("t-1", "Prova", expect.any(String));
    expect(toast.success).toHaveBeenCalledWith(t("platform.suspendedDone", { name: "Flat Sharing" }));
    expect(screen.queryByTestId("tenant-suspend-dialog-t-1")).not.toBeInTheDocument();
    await waitFor(() => expect(s.tenants).toHaveBeenCalledTimes(2));
    expect(s.refreshMe).not.toHaveBeenCalled(); // not the manager's own organization
  });

  it("organizzazione sospesa: etichetta «Sospesa», data e motivo; «Riattiva» con conferma al posto di «Sospendi»", async () => {
    s.tenants.mockResolvedValue([LIST[0], SUSP]);
    s.reactivateTenant.mockResolvedValueOnce({ ...LIST[1], suspended: false, suspended_at: null, suspended_reason: null });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    await open();
    expect(await screen.findByTestId("tenant-suspended-t-2")).toHaveTextContent(t("platform.suspendedBadge"));
    expect(screen.getByTestId("tenant-suspended-info-t-2")).toHaveTextContent("Contratto scaduto");
    expect(screen.queryByTestId("tenant-suspended-t-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tenant-suspend-btn-t-2")).not.toBeInTheDocument();
    await click(screen.getByTestId("tenant-reactivate-btn-t-2"));
    expect(confirm).toHaveBeenCalledWith(t("platform.reactivateConfirm", { name: "Riviera Rent" }));
    expect(s.reactivateTenant).toHaveBeenCalledWith("t-2", expect.any(String));
    expect(toast.success).toHaveBeenCalledWith(t("platform.reactivated", { name: "Riviera Rent" }));
    confirm.mockRestore();
  });

  it("annullando la conferma non si riattiva nulla", async () => {
    s.tenants.mockResolvedValue([SUSP]);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await open();
    await click(await screen.findByTestId("tenant-reactivate-btn-t-2"));
    expect(s.reactivateTenant).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("la propria organizzazione del gestore: dopo la sospensione il profilo viene riletto", async () => {
    s.ownTenant = "t-1";
    s.suspendTenant.mockResolvedValueOnce({ ...LIST[0], suspended: true, suspended_at: "", suspended_reason: "x" });
    await open();
    await click(await screen.findByTestId("tenant-suspend-btn-t-1"));
    fireEvent.change(screen.getByTestId("tenant-suspend-reason"), { target: { value: "x" } });
    await click(screen.getByTestId("tenant-suspend-confirm"));
    expect(s.refreshMe).toHaveBeenCalledTimes(1);
  });

  it("errore del server (409 already_suspended): messaggio del server, la finestra resta aperta", async () => {
    s.suspendTenant.mockRejectedValueOnce(new ApiError(409, "already_suspended", "Organizzazione già sospesa", "c-9"));
    await open();
    await click(await screen.findByTestId("tenant-suspend-btn-t-1"));
    fireEvent.change(screen.getByTestId("tenant-suspend-reason"), { target: { value: "x" } });
    await click(screen.getByTestId("tenant-suspend-confirm"));
    expect(toast.error).toHaveBeenCalledWith("Organizzazione già sospesa", expect.anything());
    expect(screen.getByTestId("tenant-suspend-dialog-t-1")).toBeInTheDocument();
  });
});


describe("Organizzazioni: accesso di assistenza (P-50, D-86)", () => {
  const EXPIRES = "2026-10-16T16:30:00Z";
  const MINE = { access_id: "sa-1", operator_email: "m@hqe.it", operator_name: "Marco", expires_at: EXPIRES, reason: "verifica", mine: true };

  it("apertura: durata da 1 a 24 ore (2 proposte), motivo obbligatorio; POST {hours, reason}", async () => {
    s.openSupport.mockResolvedValueOnce({ ...MINE, tenant_id: "t-1", opened_at: "", closed_at: null, status: "active" });
    await open();
    await click(await screen.findByTestId("tenant-support-btn-t-1"));
    const dialog = screen.getByTestId("tenant-support-dialog-t-1");
    expect(dialog).toHaveTextContent(t("support.openHint"));
    const hours = within(dialog).getByTestId("tenant-support-hours") as HTMLSelectElement;
    expect(hours.value).toBe("2");
    expect([...hours.options].map((o) => o.value)).toEqual(Array.from({ length: 24 }, (_, i) => String(i + 1)));
    const confirm = within(dialog).getByTestId("tenant-support-confirm");
    expect(confirm).toBeDisabled();
    fireEvent.change(hours, { target: { value: "4" } });
    fireEvent.change(within(dialog).getByTestId("tenant-support-reason"), { target: { value: " verifica " } });
    await click(confirm);
    expect(s.openSupport).toHaveBeenCalledWith("t-1", { hours: 4, reason: "verifica" }, expect.any(String));
    expect(screen.queryByTestId("tenant-support-dialog-t-1")).not.toBeInTheDocument();
    await waitFor(() => expect(s.tenants).toHaveBeenCalledTimes(2));
  });

  it("accesso proprio aperto: «Entra come assistenza» porta dentro l'organizzazione; «Chiudi accesso» lo chiude", async () => {
    s.tenants.mockResolvedValue([{ ...LIST[0], support_access: MINE }]);
    await open();
    expect(await screen.findByTestId("tenant-support-info-t-1")).toHaveTextContent(t("support.openUntil", { until: "" }).trim());
    expect(screen.queryByTestId("tenant-support-btn-t-1")).not.toBeInTheDocument();
    await click(screen.getByTestId("tenant-support-enter-t-1"));
    expect(s.enterSupport).toHaveBeenCalledWith({ tenant_id: "t-1", tenant_name: "Flat Sharing", access_id: "sa-1", expires_at: EXPIRES });
    expect(screen.getByTestId("where")).toHaveTextContent(/^\/$/);
  });

  it("«Chiudi accesso» del gestore: DELETE e lista aggiornata", async () => {
    s.tenants.mockResolvedValue([{ ...LIST[0], support_access: MINE }]);
    await open();
    await click(await screen.findByTestId("tenant-support-close-t-1"));
    expect(s.closeSupport).toHaveBeenCalledWith("t-1", "sa-1", expect.any(String));
    await waitFor(() => expect(s.tenants).toHaveBeenCalledTimes(2));
  });

  it("accesso di un altro gestore: si vede chi e fino a quando, ma non si entra; si può aprirne uno proprio", async () => {
    s.tenants.mockResolvedValue([{ ...LIST[0], support_access: { ...MINE, mine: false, operator_name: "Carla", operator_email: "c@hqe.it" } }]);
    await open();
    expect(await screen.findByTestId("tenant-support-info-t-1")).toHaveTextContent("Carla");
    expect(screen.queryByTestId("tenant-support-enter-t-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tenant-support-close-t-1")).not.toBeInTheDocument();
    expect(screen.getByTestId("tenant-support-btn-t-1")).toBeInTheDocument();
  });

  it("organizzazione sospesa: nessun accesso di assistenza, neppure «Entra» con un accesso proprio ancora aperto", async () => {
    s.tenants.mockResolvedValue([{ ...LIST[0], suspended: true, suspended_at: "", suspended_reason: "x", support_access: MINE }]);
    await open();
    await screen.findByTestId("tenant-reactivate-btn-t-1");
    expect(screen.queryByTestId("tenant-support-btn-t-1")).not.toBeInTheDocument();
    expect(screen.queryByTestId("tenant-support-enter-t-1")).not.toBeInTheDocument();
  });
});

describe("Organizzazioni: rifiniture dell'assistenza (D-89)", () => {
  const MINE = { access_id: "sa-1", operator_email: "m@hqe.it", operator_name: "Marco", expires_at: "2026-10-16T16:30:00Z", reason: "verifica", mine: true };

  it("«Chiudi accesso» dell'accesso in cui si sta lavorando: si esce subito dall'assistenza", async () => {
    s.ownSupport = { access_id: "sa-1" };
    s.tenants.mockResolvedValue([{ ...LIST[0], support_access: MINE }]);
    await open();
    await click(await screen.findByTestId("tenant-support-close-t-1"));
    expect(s.closeSupport).toHaveBeenCalledWith("t-1", "sa-1", expect.any(String));
    expect(s.leaveSupport).toHaveBeenCalledTimes(1);
  });

  it("«Chiudi accesso» di un accesso in cui non si sta lavorando: si resta dove si è", async () => {
    s.tenants.mockResolvedValue([{ ...LIST[0], support_access: MINE }]);
    await open();
    await click(await screen.findByTestId("tenant-support-close-t-1"));
    expect(s.leaveSupport).not.toHaveBeenCalled();
  });

  it("accesso aperto da chi ha poi cancellato il proprio account: «utente rimosso», mai «null»", async () => {
    s.tenants.mockResolvedValue([{ ...LIST[0], support_access: { ...MINE, mine: false, operator_email: null, operator_name: null } }]);
    await open();
    const info = await screen.findByTestId("tenant-support-info-t-1");
    expect(info).toHaveTextContent(t("common.removedUser"));
    expect(info).not.toHaveTextContent("null");
  });
});
