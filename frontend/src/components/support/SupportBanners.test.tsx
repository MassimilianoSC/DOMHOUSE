import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { t } from "@/i18n";
import { fmtDateTime, fmtTime } from "@/lib/format";
import { AdminSupportNotice, SupportBar, useOrgContextKey } from "./SupportBanners";

// Assistance access (P-50, D-86): the manager's fixed bar with «Termina»; the admin's notice with «Chiudi accesso»
// (ends the access) and the X (hides the notice only, until a new access).
const s = vi.hoisted(() => ({
  me: null as unknown,
  isAdmin: true,
  leaveSupport: vi.fn(async () => {}),
  refreshMe: vi.fn(async () => {}),
  closePlatform: vi.fn(async () => undefined),
  closeAdmin: vi.fn(async () => undefined),
}));

vi.mock("@/auth/AuthProvider", () => ({
  useAuth: () => ({ me: s.me, leaveSupport: s.leaveSupport, refreshMe: s.refreshMe }),
  useRole: () => ({ isAdmin: s.isAdmin }),
}));
vi.mock("@/api/platform", () => ({ platformApi: { closeSupport: s.closePlatform } }));
vi.mock("@/api/admin", () => ({ adminApi: { closeSupport: s.closeAdmin } }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const EXPIRES = "2026-10-16T16:30:00Z";
const ACCESS = { access_id: "sa-1", tenant_id: "t-1", operator_email: "marco@hqe.it", operator_name: "Marco Bianchi", reason: "Verifica termostato", opened_at: "", expires_at: EXPIRES, closed_at: null, status: "active" };

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  s.isAdmin = true;
});

describe("barra fissa del gestore in assistenza", () => {
  beforeEach(() => {
    s.me = { user: { uid: "m1" }, tenant: { tenant_id: "t-2", name: "Riviera" }, support: { access_id: "sa-9", tenant_id: "t-2", expires_at: EXPIRES, reason: "x" }, support_access: [] };
  });

  it("dice dove si lavora, fino a quando e con quali permessi", () => {
    render(<SupportBar />);
    expect(screen.getByTestId("support-bar")).toHaveTextContent(t("support.bar", { name: "Riviera", until: fmtTime(EXPIRES) }));
  });

  it("«Termina»: prima esce dalla modalità (nessun avviso «scaduto» da chiamate in volo), poi chiude l'accesso sul server", async () => {
    render(<SupportBar />);
    await click(screen.getByTestId("support-end-btn"));
    expect(s.leaveSupport).toHaveBeenCalledTimes(1);
    expect(s.closePlatform).toHaveBeenCalledWith("t-2", "sa-9", expect.any(String));
    expect(s.leaveSupport.mock.invocationCallOrder[0]).toBeLessThan(s.closePlatform.mock.invocationCallOrder[0]);
  });

  it("chiusura non riuscita (rete): esce lo stesso dalla modalità assistenza, e avvisa di chiuderlo da Organizzazioni", async () => {
    s.closePlatform.mockRejectedValueOnce(new Error("rete"));
    render(<SupportBar />);
    await click(screen.getByTestId("support-end-btn"));
    expect(s.leaveSupport).toHaveBeenCalledTimes(1);
    expect(toast.warning).toHaveBeenCalledWith(t("support.closeFailed"), expect.anything());
  });

  it("chiusura riuscita: nessun avviso", async () => {
    render(<SupportBar />);
    await click(screen.getByTestId("support-end-btn"));
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it("fuori dall'assistenza: nessuna barra", () => {
    s.me = { user: { uid: "m1" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support_access: [] };
    render(<SupportBar />);
    expect(screen.queryByTestId("support-bar")).not.toBeInTheDocument();
  });
});

describe("avviso per l'amministratore", () => {
  beforeEach(() => {
    s.me = { user: { uid: "u1" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support_access: [ACCESS] };
  });

  it("chi, fino a quando, con quali permessi e perché", () => {
    render(<AdminSupportNotice />);
    const notice = screen.getByTestId("support-notice-sa-1");
    expect(notice).toHaveTextContent(t("support.notice", { name: "Marco Bianchi (marco@hqe.it)", until: fmtDateTime(EXPIRES) }));
    expect(notice).toHaveTextContent(t("support.reason", { reason: "Verifica termostato" }));
  });

  it("«Chiudi accesso»: conferma, chiusura sul server e profilo riletto", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<AdminSupportNotice />);
    await click(screen.getByTestId("support-close-sa-1"));
    expect(confirm).toHaveBeenCalledWith(t("support.closeConfirm", { name: "Marco Bianchi" }));
    expect(s.closeAdmin).toHaveBeenCalledWith("sa-1", expect.any(String));
    expect(s.refreshMe).toHaveBeenCalledTimes(1);
    confirm.mockRestore();
  });

  it("annullando la conferma non si chiude nulla", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<AdminSupportNotice />);
    await click(screen.getByTestId("support-close-sa-1"));
    expect(s.closeAdmin).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("la X nasconde solo l'avviso, anche dopo un ricaricamento; un accesso nuovo lo fa ricomparire", async () => {
    const { unmount } = render(<AdminSupportNotice />);
    await click(screen.getByTestId("support-dismiss-sa-1"));
    expect(screen.queryByTestId("support-notice-sa-1")).not.toBeInTheDocument();
    expect(s.closeAdmin).not.toHaveBeenCalled();
    unmount();
    render(<AdminSupportNotice />);
    expect(screen.queryByTestId("support-notice-sa-1")).not.toBeInTheDocument();
    s.me = { user: { uid: "u1" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support_access: [ACCESS, { ...ACCESS, access_id: "sa-2" }] };
    render(<AdminSupportNotice />);
    expect(screen.getByTestId("support-notice-sa-2")).toBeInTheDocument();
  });

  it("chi non è amministratore non vede l'avviso; nessun accesso, nessun avviso", () => {
    s.isAdmin = false;
    const { unmount } = render(<AdminSupportNotice />);
    expect(screen.queryByTestId("support-notice-sa-1")).not.toBeInTheDocument();
    unmount();
    s.isAdmin = true;
    s.me = { user: { uid: "u1" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support_access: [] };
    render(<AdminSupportNotice />);
    expect(screen.queryByTestId(/support-notice-/)).not.toBeInTheDocument();
  });
});

describe("cambio di organizzazione mostrata (revisione)", () => {
  function wrapper({ children }: { children: React.ReactNode }) {
    return <MemoryRouter initialEntries={["/a/apt-9/consumi"]}>{children}</MemoryRouter>;
  }
  const useProbe = () => ({ key: useOrgContextKey(), path: useLocation().pathname });

  it("uscendo dall'assistenza la chiave cambia (le pagine si rimontano: stream chiuso) e si torna a «/»", () => {
    s.me = { user: { uid: "m1" }, tenant: { tenant_id: "t-2", name: "Riviera" }, support: { access_id: "sa-9", tenant_id: "t-2", expires_at: EXPIRES, reason: "x" }, support_access: [] };
    const { result, rerender } = renderHook(useProbe, { wrapper });
    const before = result.current.key;
    expect(result.current.path).toBe("/a/apt-9/consumi");
    s.me = { user: { uid: "m1" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support: null, support_access: [] };
    rerender();
    expect(result.current.key).not.toBe(before);
    expect(result.current.path).toBe("/");
  });

  it("stessa organizzazione, profilo riletto: la chiave non cambia e non si naviga", () => {
    s.me = { user: { uid: "u1" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support: null, support_access: [] };
    const { result, rerender } = renderHook(useProbe, { wrapper });
    const before = result.current.key;
    s.me = { user: { uid: "u1" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support: null, support_access: [ACCESS] };
    rerender();
    expect(result.current.key).toBe(before);
    expect(result.current.path).toBe("/a/apt-9/consumi");
  });
});

describe("avviso dell'admin: si aggiorna da solo (revisione)", () => {
  it("con la pagina visibile, il profilo viene riletto ogni 2 minuti: un accesso aperto nel frattempo compare", async () => {
    vi.useFakeTimers();
    s.me = { user: { uid: "u1" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support_access: [] };
    render(<AdminSupportNotice />);
    await act(async () => {
      vi.advanceTimersByTime(120_000);
    });
    expect(s.refreshMe).toHaveBeenCalledTimes(1);
    vi.useRealTimers();
  });

  it("chi non è amministratore: nessuna rilettura", async () => {
    vi.useFakeTimers();
    s.isAdmin = false;
    render(<AdminSupportNotice />);
    await act(async () => {
      vi.advanceTimersByTime(240_000);
    });
    expect(s.refreshMe).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
});

describe("avviso dell'admin: rifiniture (D-89)", () => {
  it("avviso nascosto da una persona: per un'altra persona sullo stesso dispositivo ricompare", async () => {
    s.me = { user: { uid: "u1" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support_access: [ACCESS] };
    const { unmount } = render(<AdminSupportNotice />);
    await click(screen.getByTestId("support-dismiss-sa-1"));
    unmount();
    s.me = { user: { uid: "u2" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support_access: [ACCESS] };
    render(<AdminSupportNotice />);
    expect(screen.getByTestId("support-notice-sa-1")).toBeInTheDocument();
  });

  it("operatore che ha cancellato il proprio account: «utente rimosso», mai «null»", () => {
    s.me = { user: { uid: "u1" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support_access: [{ ...ACCESS, operator_email: null, operator_name: null }] };
    render(<AdminSupportNotice />);
    const notice = screen.getByTestId("support-notice-sa-1");
    expect(notice).toHaveTextContent(t("support.notice", { name: t("common.removedUser"), until: fmtDateTime(EXPIRES) }));
    expect(notice).not.toHaveTextContent("null");
  });

  it("solo l'email (nome assente): l'email da sola", () => {
    s.me = { user: { uid: "u1" }, tenant: { tenant_id: "t-1", name: "Flatsharing" }, support_access: [{ ...ACCESS, operator_name: null }] };
    render(<AdminSupportNotice />);
    expect(screen.getByTestId("support-notice-sa-1")).toHaveTextContent(t("support.notice", { name: "marco@hqe.it", until: fmtDateTime(EXPIRES) }));
  });
});
