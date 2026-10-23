import { act, fireEvent, render, screen } from "@testing-library/react";
import { t } from "@/i18n";

// The «Installa l'app» card of Settings. useInstallPrompt keeps its state at module level (the browser fires
// beforeinstallprompt once, at load), so every test loads a fresh copy of the page after setting up the browser.
vi.mock("@/auth/AuthProvider", () => ({
  useAuth: () => ({
    me: { user: { uid: "u1", email: "gestore@esempio.it", display_name: "" }, role: "operator", tenant: { tenant_id: "t1", name: "Demo" }, env: { app_env: "dev", auth_mode: "dev", instance_mode: "mock", simulator: true } },
    logout: vi.fn(),
  }),
}));
vi.mock("@/components/settings/AccountSettings", () => ({ AccountSettings: ({ profile }: { profile?: React.ReactNode }) => <>{profile}</> }));
vi.mock("@/components/settings/NotificationSettings", () => ({ NotificationSettings: () => null }));
vi.mock("@/hooks/useFeatures", () => ({ useApartments: () => ({ data: [] }) }));

const ANDROID_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Mobile Safari/537.36";
const IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1";

async function loadPage({ standalone = false, userAgent = ANDROID_UA } = {}) {
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: (query: string) => ({ matches: standalone && query.includes("standalone"), media: query, addEventListener: () => {}, removeEventListener: () => {} }),
  });
  vi.spyOn(window.navigator, "userAgent", "get").mockReturnValue(userAgent);
  vi.resetModules();
  const { default: SettingsPage } = await import("./SettingsPage");
  render(<SettingsPage />);
}

function offerInstall(outcome: "accepted" | "dismissed") {
  const ev = Object.assign(new Event("beforeinstallprompt", { cancelable: true }), {
    prompt: vi.fn(async () => {}),
    userChoice: Promise.resolve({ outcome }),
  });
  act(() => {
    window.dispatchEvent(ev);
  });
  return ev;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Impostazioni: «Installa l'app»", () => {
  it("prompt del browser disponibile: pulsante «Installa», che apre il prompt; accettato → «App installata»", async () => {
    await loadPage();
    const ev = offerInstall("accepted");
    expect(ev.defaultPrevented).toBe(true);
    const btn = screen.getByTestId("settings-install-btn");
    expect(btn).toHaveTextContent(t("settings.installBtn"));
    await act(async () => {
      fireEvent.click(btn);
    });
    expect(ev.prompt).toHaveBeenCalledTimes(1);
    expect(await screen.findByTestId("settings-installed")).toHaveTextContent(t("settings.installed"));
  });

  it("prompt rifiutato: il pulsante sparisce e restano le istruzioni", async () => {
    await loadPage();
    offerInstall("dismissed");
    await act(async () => {
      fireEvent.click(screen.getByTestId("settings-install-btn"));
    });
    expect(screen.queryByTestId("settings-install-btn")).not.toBeInTheDocument();
    expect(screen.queryByTestId("settings-installed")).not.toBeInTheDocument();
    expect(screen.getByTestId("settings-install-card")).toHaveTextContent(t("settings.installAndroid"));
  });

  it("iPhone: istruzioni per Safari, nessun pulsante", async () => {
    await loadPage({ userAgent: IPHONE_UA });
    const card = screen.getByTestId("settings-install-card");
    expect(card).toHaveTextContent(t("settings.installIos"));
    expect(card).not.toHaveTextContent(t("settings.installAndroid"));
    expect(screen.queryByTestId("settings-install-btn")).not.toBeInTheDocument();
  });

  it("app già installata (aperta a schermo intero): «App installata su questo dispositivo»", async () => {
    await loadPage({ standalone: true });
    expect(screen.getByTestId("settings-installed")).toHaveTextContent(t("settings.installed"));
    expect(screen.queryByTestId("settings-install-btn")).not.toBeInTheDocument();
  });

  it("Android o computer senza prompt: istruzioni per Chrome e per iPhone", async () => {
    await loadPage();
    const card = screen.getByTestId("settings-install-card");
    expect(card).toHaveTextContent(t("settings.installAndroid"));
    expect(card).toHaveTextContent(t("settings.installIos"));
    expect(screen.queryByTestId("settings-install-btn")).not.toBeInTheDocument();
  });
});
