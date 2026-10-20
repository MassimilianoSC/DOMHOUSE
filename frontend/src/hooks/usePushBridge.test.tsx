import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { toast } from "sonner";
import { t } from "@/i18n";
import { usePushBridge } from "./usePushBridge";

// What the page does with the service worker's messages (P-11): toast for a push while the app is focused, router
// navigation for a tapped notification. The service worker is an EventTarget standing in for navigator.serviceWorker.
const s = vi.hoisted(() => ({ sync: vi.fn(async (): Promise<string | undefined> => undefined) }));
vi.mock("@/lib/push", () => ({ syncPushToken: s.sync }));
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ me: { user: { uid: "u1" } } }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

let sw: EventTarget;

function Probe() {
  usePushBridge();
  return <p data-testid="path">{useLocation().pathname}</p>;
}

function mount(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Probe />
    </MemoryRouter>,
  );
}

const fromWorker = (data: unknown) =>
  act(() => {
    sw.dispatchEvent(new MessageEvent("message", { data }));
  });

const push = { type: "domotica-push", notice: { title: "Milano Centro: approvazione richiesta", body: "Accendere il clima", link: "/a/apt-001/approvazioni", apartmentId: "apt-001" } };

beforeEach(() => {
  vi.clearAllMocks();
  sw = new EventTarget();
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: sw });
});

afterEach(() => {
  Reflect.deleteProperty(navigator, "serviceWorker");
});

describe("notifiche push: lato pagina", () => {
  it("all'avvio riallinea il token del dispositivo", () => {
    mount("/");
    expect(s.sync).toHaveBeenCalledTimes(1);
    expect(s.sync).toHaveBeenCalledWith("u1");
  });

  it("rientro della stessa persona con le notifiche riattivate: lo dice (P-44)", async () => {
    s.sync.mockResolvedValueOnce("resumed");
    mount("/");
    await vi.waitFor(() => expect(toast.success).toHaveBeenCalledWith(t("notify.resumed")));
  });

  it("rientro con il permesso del browser tolto: avvisa che restano spente e dove riattivarle (P-44)", async () => {
    s.sync.mockResolvedValueOnce("permission");
    mount("/");
    await vi.waitFor(() => expect(toast.warning).toHaveBeenCalledWith(t("notify.resumeNoPermission"), expect.anything()));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("niente da riattivare: nessun avviso", async () => {
    mount("/");
    await act(async () => {});
    expect(toast.success).not.toHaveBeenCalled();
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it("push con l'app in primo piano su un'altra pagina: avviso con «Apri», che porta al link", () => {
    mount("/impostazioni");
    fromWorker(push);
    expect(toast.info).toHaveBeenCalledWith("Milano Centro: approvazione richiesta", expect.objectContaining({ description: "Accendere il clima" }));
    const { action } = vi.mocked(toast.info).mock.calls[0][1] as unknown as { action: { onClick: () => void } };
    act(() => action.onClick());
    expect(screen.getByTestId("path")).toHaveTextContent("/a/apt-001/approvazioni");
  });

  it("push mentre si guarda già quell'appartamento: nessun avviso doppio (lo dà già lo stream)", () => {
    mount("/a/apt-001/consumi");
    fromWorker(push);
    expect(toast.info).not.toHaveBeenCalled();
  });

  it("tocco sulla notifica con l'app aperta: la pagina va al link senza ricaricare", () => {
    mount("/");
    fromWorker({ type: "domotica-open", link: "/a/apt-001" });
    expect(screen.getByTestId("path")).toHaveTextContent("/a/apt-001");
  });

  it("link non dell'app o messaggi estranei: ignorati o ricondotti a /", () => {
    mount("/impostazioni");
    fromWorker({ type: "altro", link: "/a/apt-001" });
    expect(screen.getByTestId("path")).toHaveTextContent("/impostazioni");
    fromWorker({ type: "domotica-open", link: "https://altro.it" });
    expect(screen.getByTestId("path")).toHaveTextContent(/^\/$/);
  });
});
