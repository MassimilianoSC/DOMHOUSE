import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { t } from "@/i18n";
import ApartmentsPage from "./ApartmentsPage";
import SettingsPage from "./SettingsPage";

// What a user limited to some apartments sees (P-18): the empty list asks to be assigned one, the profile says which.
const s = vi.hoisted(() => ({ role: "viewer", scope: undefined as unknown, apartments: [] as unknown[] }));

vi.mock("@/auth/AuthProvider", () => ({
  useAuth: () => ({
    me: { user: { uid: "u1", email: "proprietario@demo.it", display_name: "", apartment_ids: s.scope }, role: s.role, tenant: { tenant_id: "t1", name: "Demo" }, env: { app_env: "dev", auth_mode: "dev", instance_mode: "mock", simulator: true } },
    logout: vi.fn(),
  }),
  useRole: () => ({ role: s.role, canWrite: s.role !== "viewer", isAdmin: s.role === "admin" }),
}));
vi.mock("@/hooks/useFeatures", () => ({ useApartments: () => ({ data: s.apartments, isLoading: false }) }));
vi.mock("@/components/settings/AccountSettings", () => ({ AccountSettings: ({ profile }: { profile?: React.ReactNode }) => <>{profile}</> }));
vi.mock("@/components/settings/NotificationSettings", () => ({ NotificationSettings: () => null }));

const RIMINI = { apartment_id: "apt-rimini-01", name: "Rimini Mare", address: "Viale Vespucci 9", timezone: "Europe/Rome", online: true, enabled: true, apartment: null, kwh_today: null, pending_approvals: 0 };

const page = (el: React.ReactNode) => render(<MemoryRouter>{el}</MemoryRouter>);

beforeEach(() => {
  s.role = "viewer";
  s.scope = undefined;
  s.apartments = [];
});

describe("utente limitato ad alcuni appartamenti", () => {
  it("nessun appartamento assegnato: chiede di farsene assegnare uno, non parla dell'area Amministrazione", () => {
    s.scope = [];
    page(<ApartmentsPage />);
    expect(screen.getByTestId("apartments-empty")).toHaveTextContent(t("apartments.emptyAssigned"));
    expect(screen.getByTestId("apartments-empty")).not.toHaveTextContent(t("apartments.emptyHint"));
  });

  it("utente con «tutti» e nessun appartamento configurato: il messaggio di sempre, e a chi rivolgersi (D-77)", () => {
    s.scope = "all";
    page(<ApartmentsPage />);
    expect(screen.getByTestId("apartments-empty")).toHaveTextContent(t("apartments.empty"));
    expect(screen.getByTestId("apartments-empty-hint")).toHaveTextContent(t("apartments.emptyHintMember"));
    expect(screen.queryByTestId("add-apartment-btn")).not.toBeInTheDocument();
  });

  it("BFF precedente a P-18 (campo assente): trattato come «tutti»", () => {
    page(<ApartmentsPage />);
    expect(screen.getByTestId("apartments-empty")).toHaveTextContent(t("apartments.empty"));
  });

  it("Impostazioni > Profilo: il proprietario legge il nome del suo appartamento", () => {
    s.scope = ["apt-rimini-01"];
    s.apartments = [RIMINI];
    page(<SettingsPage />);
    expect(screen.getByTestId("settings-apartments")).toHaveTextContent("Rimini Mare");
  });

  it("Impostazioni > Profilo: amministratore e «tutti» leggono «tutti gli appartamenti»", () => {
    s.role = "admin";
    s.scope = ["apt-rimini-01"]; // ignored for an admin
    s.apartments = [RIMINI];
    page(<SettingsPage />);
    expect(screen.getByTestId("settings-apartments")).toHaveTextContent(t("admin.users.scopeAll"));
  });
});
