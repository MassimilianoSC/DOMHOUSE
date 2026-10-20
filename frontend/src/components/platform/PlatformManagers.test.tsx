import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";
import type { MockInstance } from "vitest";
import { ApiError } from "@/api/bff";
import { t } from "@/i18n";
import OrganizationsPage from "@/pages/OrganizationsPage";

// Organizzazioni > Gestori della piattaforma and Webhook non attribuiti (P-36, D-61a), with the BFF simulated.
const s = vi.hoisted(() => ({
  managers: vi.fn(),
  addManager: vi.fn(async (email: string) => ({ email, display_name: "", active: false })),
  removeManager: vi.fn(async (_email: string) => undefined),
  webhookLogs: vi.fn(async () => []),
  refreshMe: vi.fn(async () => {}),
}));

vi.mock("@/api/platform", () => ({
  platformApi: { tenants: async () => [], managers: s.managers, addManager: s.addManager, removeManager: s.removeManager, webhookLogs: s.webhookLogs },
}));
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ me: { user: { email: "Io@HQE.it" } }, refreshMe: s.refreshMe }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const MANAGERS = [
  { email: "io@hqe.it", display_name: "Io", active: true },
  { email: "sol@hqe.it", display_name: "", active: false },
];

let confirm: MockInstance<(message?: string) => boolean>;

async function openManagers() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <OrganizationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByTestId("platform-tab-managers"));
  await screen.findByTestId("platform-managers-list");
}

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

beforeEach(() => {
  vi.clearAllMocks();
  s.managers.mockResolvedValue(MANAGERS);
  confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  confirm.mockRestore();
});

describe("Gestori della piattaforma", () => {
  it("elenco: chi è già entrato e chi no; «tu» accanto a sé (email senza badare alle maiuscole)", async () => {
    await openManagers();
    expect(screen.getByTestId("platform-manager-state-io@hqe.it")).toHaveTextContent(t("platform.managerActive"));
    expect(screen.getByTestId("platform-manager-state-sol@hqe.it")).toHaveTextContent(t("platform.managerPending"));
    expect(within(screen.getByTestId("platform-manager-io@hqe.it")).getByText(t("admin.users.you"))).toBeInTheDocument();
    expect(within(screen.getByTestId("platform-manager-sol@hqe.it")).queryByText(t("admin.users.you"))).not.toBeInTheDocument();
  });

  it("aggiunta per email: pulsante attivo solo con un'email valida, avviso che il ruolo vale all'ingresso", async () => {
    await openManagers();
    const btn = screen.getByTestId("platform-manager-add-btn");
    fireEvent.change(screen.getByTestId("platform-manager-email"), { target: { value: "nuovo@" } });
    expect(btn).toBeDisabled();
    fireEvent.change(screen.getByTestId("platform-manager-email"), { target: { value: " nuovo@hqe.it " } });
    await click(btn);
    expect(s.addManager).toHaveBeenCalledWith("nuovo@hqe.it", expect.any(String));
    expect(toast.success).toHaveBeenCalledWith(t("platform.managerAdded", { email: "nuovo@hqe.it" }));
    expect(screen.getByTestId("platform-manager-email")).toHaveValue("");
    await waitFor(() => expect(s.managers).toHaveBeenCalledTimes(2));
  });

  it("togliere un altro gestore: conferma con la sua email, poi DELETE e avviso", async () => {
    await openManagers();
    await click(screen.getByTestId("platform-manager-remove-sol@hqe.it"));
    expect(confirm).toHaveBeenCalledWith(t("platform.removeConfirm", { email: "sol@hqe.it" }));
    expect(s.removeManager).toHaveBeenCalledWith("sol@hqe.it", expect.any(String));
    expect(toast.success).toHaveBeenCalledWith(t("platform.removed", { email: "sol@hqe.it" }));
    expect(s.refreshMe).not.toHaveBeenCalled();
  });

  it("annullando la conferma non si toglie nulla", async () => {
    confirm.mockReturnValue(false);
    await openManagers();
    await click(screen.getByTestId("platform-manager-remove-sol@hqe.it"));
    expect(s.removeManager).not.toHaveBeenCalled();
  });

  it("togliersi il ruolo: avviso che si perde l'accesso, poi il profilo viene ricaricato", async () => {
    await openManagers();
    await click(screen.getByTestId("platform-manager-remove-io@hqe.it"));
    expect(confirm).toHaveBeenCalledWith(t("platform.removeSelfConfirm"));
    expect(s.refreshMe).toHaveBeenCalledTimes(1);
  });

  it("ultimo gestore (409 last_manager): messaggio del server, nessuna ricarica del profilo", async () => {
    s.removeManager.mockRejectedValueOnce(new ApiError(409, "last_manager", "Serve almeno un gestore della piattaforma", "c-1"));
    await openManagers();
    await click(screen.getByTestId("platform-manager-remove-io@hqe.it"));
    expect(toast.error).toHaveBeenCalledWith("Serve almeno un gestore della piattaforma", expect.anything());
    expect(s.refreshMe).not.toHaveBeenCalled();
  });
});

describe("Prenotazioni non attribuite (D-81)", () => {
  it("la scheda legge i log della piattaforma, con la sua spiegazione", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter>
          <OrganizationsPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("platform-tab-webhooks")).toHaveTextContent(/^Prenotazioni non attribuite$/);
    fireEvent.click(screen.getByTestId("platform-tab-webhooks"));
    expect(await screen.findByTestId("admin-webhooks-hint")).toHaveTextContent(t("platform.unattributedHint"));
    expect(screen.getByTestId("organizations-header").parentElement).not.toHaveTextContent(/webhook/i); // D-81: never in the visible texts
    expect(await screen.findByTestId("admin-webhooks-empty")).toBeInTheDocument();
    expect(s.webhookLogs).toHaveBeenCalledTimes(1);
  });
});
