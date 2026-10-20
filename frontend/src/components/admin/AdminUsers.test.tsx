import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { toast } from "sonner";
import type { MockInstance } from "vitest";
import { t } from "@/i18n";
import { AdminUsers } from "./AdminUsers";

// Amministrazione > Utenti with per-apartment permissions (P-18, API shape D-43: "all" or a list, [] = none).
const s = vi.hoisted(() => ({
  users: [] as unknown[],
  invite: vi.fn(async (body: { email: string; role: string }) => ({ uid: "u-new", email: body.email, display_name: "", role: body.role, pending: true, push_tokens: 0, apartment_ids: "all", email_status: "sent" })),
  patchUser: vi.fn(async () => ({})),
}));

vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ me: { user: { uid: "u-admin" } } }) }));
vi.mock("@/api/admin", () => ({
  adminApi: {
    users: async () => s.users,
    apartments: async () => [
      { apartment_id: "apt-bologna-01", name: "Bologna Centro", address: "Via Indipendenza 1" },
      { apartment_id: "apt-rimini-01", name: "Rimini Mare", address: "Viale Vespucci 9" },
      { apartment_id: "apt-milano-01", name: "Milano Navigli", address: "Alzaia 3" },
    ],
    invite: s.invite,
    patchUser: s.patchUser,
    resendInvite: vi.fn(),
    deleteUser: vi.fn(),
  },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const user = (uid: string, role: string, apartment_ids: unknown, email = `${uid}@demo.it`) => ({ uid, email, display_name: "", role, pending: false, push_tokens: 0, apartment_ids });

async function renderUsers() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AdminUsers />
    </QueryClientProvider>,
  );
  await screen.findByTestId("admin-users-list");
  await screen.findAllByTestId(/admin-invite-scope-apt-/); // apartments loaded
}

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

let confirm: MockInstance<(message?: string) => boolean>;

beforeEach(() => {
  vi.clearAllMocks();
  s.users = [user("u-admin", "admin", "all", "admin@demo.it"), user("u-op", "operator", "all"), user("u-owner", "viewer", ["apt-rimini-01"], "proprietario@demo.it")];
  confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  confirm.mockRestore();
});

describe("Utenti: invito con gli appartamenti", () => {
  it("per operatori e lettori la scelta compare, con «Tutti» già spuntata; scegliendo amministratore sparisce", async () => {
    await renderUsers();
    expect(screen.getByTestId("admin-invite-scope-all")).toBeChecked();
    fireEvent.change(screen.getByTestId("admin-invite-role"), { target: { value: "admin" } });
    expect(screen.queryByTestId("admin-invite-scope")).not.toBeInTheDocument();
    fireEvent.change(screen.getByTestId("admin-invite-role"), { target: { value: "viewer" } });
    expect(screen.getByTestId("admin-invite-scope")).toBeInTheDocument();
  });

  it("lettore su un solo appartamento: l'invito porta la lista", async () => {
    await renderUsers();
    fireEvent.change(screen.getByTestId("admin-invite-email"), { target: { value: "nuovo@demo.it" } });
    fireEvent.change(screen.getByTestId("admin-invite-role"), { target: { value: "viewer" } });
    fireEvent.click(screen.getByTestId("admin-invite-scope-all"));
    fireEvent.click(screen.getByTestId("admin-invite-scope-apt-rimini-01"));
    await click(screen.getByTestId("admin-invite-btn"));
    expect(s.invite).toHaveBeenCalledWith(expect.objectContaining({ email: "nuovo@demo.it", role: "viewer", apartment_ids: ["apt-rimini-01"] }), expect.any(String));
    expect(confirm).not.toHaveBeenCalled();
  });

  it("amministratore: l'invito non porta nessuna lista", async () => {
    await renderUsers();
    fireEvent.change(screen.getByTestId("admin-invite-email"), { target: { value: "capo@demo.it" } });
    fireEvent.change(screen.getByTestId("admin-invite-role"), { target: { value: "admin" } });
    await click(screen.getByTestId("admin-invite-btn"));
    const body = s.invite.mock.calls[0][0] as Record<string, unknown>;
    expect(body).not.toHaveProperty("apartment_ids");
    expect(body.role).toBe("admin");
  });

  it("nessun appartamento: chiede conferma; annullando non invita", async () => {
    confirm.mockReturnValue(false);
    await renderUsers();
    fireEvent.change(screen.getByTestId("admin-invite-email"), { target: { value: "sospeso@demo.it" } });
    fireEvent.click(screen.getByTestId("admin-invite-scope-all"));
    await click(screen.getByTestId("admin-invite-btn"));
    expect(confirm).toHaveBeenCalledWith(t("admin.users.scopeNoneConfirm", { email: "sospeso@demo.it" }));
    expect(s.invite).not.toHaveBeenCalled();
  });
});

describe("Utenti: elenco e modifica degli appartamenti", () => {
  it("sintesi per operatori e lettori; niente per gli amministratori", async () => {
    await renderUsers();
    expect(screen.getByTestId("admin-user-scope-u-op")).toHaveTextContent(t("admin.users.scopeAll"));
    expect(screen.getByTestId("admin-user-scope-u-owner")).toHaveTextContent("Rimini Mare");
    expect(screen.queryByTestId("admin-user-scope-u-admin")).not.toBeInTheDocument();
    expect(screen.queryByTestId("admin-user-scope-btn-u-admin")).not.toBeInTheDocument();
  });

  it("«Appartamenti» apre la scelta con la lista attuale; «Tutti» e Salva → PATCH con «all» e avviso", async () => {
    await renderUsers();
    await click(screen.getByTestId("admin-user-scope-btn-u-owner"));
    const dialog = await screen.findByTestId("scope-dialog-u-owner");
    expect(within(dialog).getByTestId("scope-edit-u-owner-apt-rimini-01")).toBeChecked();
    expect(within(dialog).getByTestId("scope-edit-u-owner-apt-bologna-01")).not.toBeChecked();
    fireEvent.click(within(dialog).getByTestId("scope-edit-u-owner-all"));
    await click(within(dialog).getByTestId("scope-dialog-save"));
    expect(s.patchUser).toHaveBeenCalledWith("u-owner", { apartment_ids: "all" }, expect.any(String));
    expect(toast.success).toHaveBeenCalledWith(t("admin.users.scopeSaved"));
    expect(screen.queryByTestId("scope-dialog-u-owner")).not.toBeInTheDocument();
  });

  it("togliere l'ultimo appartamento chiede conferma; annullando non salva", async () => {
    confirm.mockReturnValue(false);
    await renderUsers();
    await click(screen.getByTestId("admin-user-scope-btn-u-owner"));
    const dialog = await screen.findByTestId("scope-dialog-u-owner");
    fireEvent.click(within(dialog).getByTestId("scope-edit-u-owner-apt-rimini-01"));
    expect(within(dialog).getByTestId("scope-edit-u-owner-none-warning")).toBeInTheDocument();
    await click(within(dialog).getByTestId("scope-dialog-save"));
    expect(confirm).toHaveBeenCalledWith(t("admin.users.scopeNoneConfirm", { email: "proprietario@demo.it" }));
    expect(s.patchUser).not.toHaveBeenCalled();
    expect(screen.getByTestId("scope-dialog-u-owner")).toBeInTheDocument();
  });

  it("confermando «nessuno» salva la lista vuota", async () => {
    await renderUsers();
    await click(screen.getByTestId("admin-user-scope-btn-u-owner"));
    const dialog = await screen.findByTestId("scope-dialog-u-owner");
    fireEvent.click(within(dialog).getByTestId("scope-edit-u-owner-apt-rimini-01"));
    await click(within(dialog).getByTestId("scope-dialog-save"));
    expect(s.patchUser).toHaveBeenCalledWith("u-owner", { apartment_ids: [] }, expect.any(String));
  });
});
