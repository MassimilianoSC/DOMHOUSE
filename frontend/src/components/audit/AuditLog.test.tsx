import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { adminApi } from "@/api/admin";
import { platformApi } from "@/api/platform";
import { PlatformAudit } from "@/components/platform/PlatformAudit";
import { t } from "@/i18n";
import type { AuditEntry } from "@/lib/auditLog";
import { AuditLog } from "./AuditLog";

// «Registro attività» (P-47): the admin's list and the platform's, with «Carica altri»; the BFF simulated by fetch.
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ refreshMe: vi.fn() }) }));

const ANNA = { kind: "user" as const, uid: "u1", email: "anna@fs.it", display_name: "Anna Rossi", removed: false };
const row = (id: string, over: Partial<AuditEntry> = {}): AuditEntry => ({
  audit_id: id, at: "2026-10-16T08:00:00Z", tenant_id: "t-1", action: "invite_resent", actor: ANNA,
  target: { type: "user", id: "u2", label: "bruno@fs.it" }, details: {}, ...over,
});

let calls: string[];
let pages: Record<string, unknown>;

function bff() {
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const u = new URL(url);
    calls.push(u.pathname + u.search);
    const body = u.pathname === "/app/platform/tenants" ? [{ tenant_id: "t-1", name: "Flatsharing", created_at: "", first_admin: null }, { tenant_id: "t-2", name: "Riviera", created_at: "", first_admin: null }] : pages[u.search] ?? { items: [], next: null };
    return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
}

const wrap = (el: React.ReactNode) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{el}</QueryClientProvider>);

beforeEach(() => {
  pages = {};
  bff();
});

describe("Amministrazione > Registro attività", () => {
  it("una frase per azione, dalla più recente; «Carica altri» chiede la pagina dopo con il cursore", async () => {
    pages["?limit=50"] = { items: [row("a1"), row("a2", { action: "user_removed" })], next: "cur-2" };
    pages["?limit=50&before=cur-2"] = { items: [row("a3", { action: "role_changed", details: { from: "viewer", to: "admin" } })], next: null };
    wrap(<AuditLog load={adminApi.audit} queryKey={["admin", "audit"]} hint={t("audit.hint")} />);
    expect(await screen.findByTestId("audit-sentence-a1")).toHaveTextContent("Anna Rossi ha inviato di nuovo l'invito a bruno@fs.it");
    expect(screen.getByTestId("audit-sentence-a2")).toHaveTextContent("Anna Rossi ha rimosso bruno@fs.it");
    expect(calls).toEqual(["/app/admin/audit?limit=50"]);
    await act(async () => {
      fireEvent.click(screen.getByTestId("audit-more"));
    });
    expect(await screen.findByTestId("audit-sentence-a3")).toHaveTextContent("da «Sola lettura» a «Amministratore»");
    expect(calls).toEqual(["/app/admin/audit?limit=50", "/app/admin/audit?limit=50&before=cur-2"]);
    expect(screen.queryByTestId("audit-more")).not.toBeInTheDocument();
  });

  it("nessuna azione: lo stato vuoto, senza «Carica altri»", async () => {
    wrap(<AuditLog load={adminApi.audit} queryKey={["admin", "audit"]} hint={t("audit.hint")} />);
    expect(await screen.findByTestId("audit-empty")).toHaveTextContent(t("audit.empty"));
    expect(screen.queryByTestId("audit-more")).not.toBeInTheDocument();
    expect(screen.getByTestId("audit-hint")).toHaveTextContent(t("audit.hint"));
  });

  it("il motivo di una sospensione compare sotto la frase", async () => {
    pages["?limit=50"] = { items: [row("a1", { action: "tenant_suspended", actor: { kind: "platform", uid: null, email: null, display_name: null, removed: false }, target: { type: "tenant", id: "t-1", label: "Flatsharing" }, details: { reason: "prova" } })], next: null };
    wrap(<AuditLog load={adminApi.audit} queryKey={["admin", "audit"]} hint={t("audit.hint")} />);
    expect(await screen.findByTestId("audit-sentence-a1")).toHaveTextContent("Gestore della piattaforma (HQE) ha sospeso l'organizzazione «Flatsharing»");
    expect(screen.getByTestId("audit-note-a1")).toHaveTextContent("Motivo: prova");
  });
});

describe("Organizzazioni > Registro attività", () => {
  it("parte dalla prima organizzazione (tenant_id obbligatorio); si passa a un'altra o alle azioni della piattaforma", async () => {
    pages["?tenant_id=t-1&limit=50"] = { items: [row("a1")], next: null };
    pages["?scope=platform&limit=50"] = { items: [row("p1", { tenant_id: null, action: "manager_added", target: { type: "manager", id: "u9", label: "carla@hqe.it" } })], next: null };
    wrap(<PlatformAudit />);
    expect(await screen.findByTestId("audit-sentence-a1")).toBeInTheDocument();
    expect(calls).toContain("/app/platform/audit?tenant_id=t-1&limit=50");
    fireEvent.change(screen.getByTestId("audit-scope-select"), { target: { value: "t-2" } });
    await waitFor(() => expect(calls).toContain("/app/platform/audit?tenant_id=t-2&limit=50"));
    expect(await screen.findByTestId("audit-empty")).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("audit-scope-select"), { target: { value: "platform" } });
    expect(await screen.findByTestId("audit-sentence-p1")).toHaveTextContent("Anna Rossi ha nominato carla@hqe.it gestore della piattaforma");
    expect(calls).toContain("/app/platform/audit?scope=platform&limit=50");
    expect(screen.getByRole("option", { name: t("audit.platformScope") })).toBeInTheDocument();
  });

  it("platformApi.audit: un'organizzazione con tenant_id, la piattaforma con scope=platform", async () => {
    await platformApi.audit("t-9", "cur");
    await platformApi.audit("platform");
    expect(calls).toEqual(["/app/platform/audit?tenant_id=t-9&limit=50&before=cur", "/app/platform/audit?scope=platform&limit=50"]);
  });
});

describe("i due registri hanno nomi diversi (D-160)", () => {
  it("Amministrazione: «Registro dell'organizzazione» sopra il registro", async () => {
    wrap(<AuditLog load={adminApi.audit} queryKey={["admin", "audit"]} hint={t("audit.hint")} title={t("audit.titleTenant")} />);
    expect(screen.getByTestId("audit-title")).toHaveTextContent("Registro dell'organizzazione");
    expect(await screen.findByTestId("audit-empty")).toBeInTheDocument();
  });

  it("Organizzazioni: «Registro della piattaforma» sopra la scelta del registro", async () => {
    wrap(<PlatformAudit />);
    expect(screen.getByTestId("audit-title")).toHaveTextContent("Registro della piattaforma");
    expect(await screen.findByTestId("audit-scope-select")).toBeInTheDocument();
  });

  it("senza titolo il registro resta com'era, e nessuno dei due si chiama più «Registro attività»", () => {
    wrap(<AuditLog load={adminApi.audit} queryKey={["admin", "audit", "x"]} hint={t("audit.hint")} />);
    expect(screen.queryByTestId("audit-title")).toBeNull();
    expect(t("audit.titleTenant")).not.toBe("Registro attività");
    expect(t("audit.titlePlatform")).not.toBe("Registro attività");
  });
});
