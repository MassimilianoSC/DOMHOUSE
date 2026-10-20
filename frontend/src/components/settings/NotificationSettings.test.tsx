import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { toast } from "sonner";
import { t } from "@/i18n";
import { NotificationSettings } from "./NotificationSettings";

// Settings > Notifiche: what the header says depends on FCM (build flag) and on the BFF's APP_ENV.
const state = vi.hoisted(() => {
  class PushError extends Error {
    constructor(public reason: string) {
      super(reason);
    }
  }
  return { appEnv: "staging", env: {} as Record<string, unknown>, pushState: "off", PushError, enablePush: vi.fn(), disablePush: vi.fn() };
});

vi.mock("@/lib/utils", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/utils")>();
  return { ...mod, env: Object.assign(state.env, mod.env) };
});
vi.mock("@/auth/AuthProvider", () => ({
  useAuth: () => ({ me: { user: { uid: "u1" }, env: { app_env: state.appEnv, auth_mode: "firebase", fcm_enabled: false, simulator: true, instance_mode: "mock" } } }),
}));
vi.mock("@/api/admin", () => ({
  pushApi: { status: async () => ({ fcm_enabled: false, tokens: 2, prefs: { approvals: true, offline: true, decisions: false } }), setPrefs: vi.fn() },
}));
vi.mock("@/lib/push", () => ({
  pushState: () => state.pushState,
  enablePush: state.enablePush,
  disablePush: state.disablePush,
  PushError: state.PushError,
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

function renderCard() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <NotificationSettings />
    </QueryClientProvider>,
  );
  return screen.getByTestId("settings-notifications");
}

beforeEach(() => {
  vi.clearAllMocks();
  state.env.fcmEnabled = false;
  state.appEnv = "staging";
  state.pushState = "off";
});

describe("Impostazioni > Notifiche: intestazione", () => {
  it("staging senza notifiche push: dice che gli avvisi compaiono nell'app, non «Modalità sviluppo»", () => {
    const card = renderCard();
    expect(screen.getByTestId("settings-push-mode")).toHaveTextContent(t("settings.notifications.inAppMode"));
    expect(card).toHaveTextContent(t("settings.notifications.inAppHint"));
    expect(card).not.toHaveTextContent(t("settings.notifications.devMode"));
    expect(card).not.toHaveTextContent("FCM");
    expect(screen.queryByTestId("settings-push-toggle-btn")).not.toBeInTheDocument();
  });

  it("produzione senza notifiche push: stesso testo dello staging", () => {
    state.appEnv = "prod";
    renderCard();
    expect(screen.getByTestId("settings-push-mode")).toHaveTextContent(t("settings.notifications.inAppMode"));
  });

  it("sviluppo senza notifiche push: «Modalità sviluppo» con l'indicazione tecnica", () => {
    state.appEnv = "dev";
    const card = renderCard();
    expect(screen.getByTestId("settings-push-mode")).toHaveTextContent(t("settings.notifications.devMode"));
    expect(card).toHaveTextContent(t("settings.notifications.devHint"));
  });

  it("notifiche push attive: «Notifiche push su questo dispositivo» e il pulsante per attivarle", async () => {
    state.env.fcmEnabled = true;
    const card = renderCard();
    expect(screen.getByTestId("settings-push-mode")).toHaveTextContent(t("settings.notifications.pushMode"));
    expect(await screen.findByTestId("settings-push-toggle-btn")).toHaveTextContent(t("settings.notifications.enable"));
    expect(card).not.toHaveTextContent(t("settings.notifications.inAppMode"));
  });
});

describe("Impostazioni > Notifiche: stato delle notifiche push sul dispositivo", () => {
  beforeEach(() => {
    state.env.fcmEnabled = true;
  });

  it.each([
    ["unsupported", "settings.notifications.statusUnsupported"],
    ["ios-install", "settings.notifications.statusIosInstall"],
    ["denied", "settings.notifications.statusDenied"],
  ])("%s: dice perché e non mostra il pulsante", (s, key) => {
    state.pushState = s;
    renderCard();
    expect(screen.getByTestId("settings-push-status")).toHaveTextContent(t(key));
    expect(screen.queryByTestId("settings-push-toggle-btn")).not.toBeInTheDocument();
  });

  it("revoked: dice che il permesso è stato tolto e offre «Attiva»", () => {
    state.pushState = "revoked";
    renderCard();
    expect(screen.getByTestId("settings-push-status")).toHaveTextContent(t("settings.notifications.statusRevoked"));
    expect(screen.getByTestId("settings-push-toggle-btn")).toHaveTextContent(t("settings.notifications.enable"));
  });

  it("attivazione riuscita: «Notifiche attive su questo dispositivo» e il pulsante diventa «Disattiva»", async () => {
    state.enablePush.mockImplementationOnce(async () => {
      state.pushState = "on";
    });
    renderCard();
    expect(screen.queryByTestId("settings-push-status")).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByTestId("settings-push-toggle-btn"));
    });
    expect(toast.success).toHaveBeenCalledWith(t("settings.notifications.enabledDone"));
    expect(screen.getByTestId("settings-push-toggle-btn")).toHaveTextContent(t("settings.notifications.disable"));
  });

  it("permesso negato alla richiesta: avviso «Permesso non concesso…» e stato «bloccate»", async () => {
    state.enablePush.mockImplementationOnce(async () => {
      state.pushState = "denied";
      throw new state.PushError("denied");
    });
    renderCard();
    await act(async () => {
      fireEvent.click(screen.getByTestId("settings-push-toggle-btn"));
    });
    expect(toast.error).toHaveBeenCalledWith(t("settings.notifications.errorDenied"), expect.anything());
    expect(screen.getByTestId("settings-push-status")).toHaveTextContent(t("settings.notifications.statusDenied"));
  });

  it("disattivazione: «Notifiche disattivate su questo dispositivo»", async () => {
    state.pushState = "on";
    state.disablePush.mockImplementationOnce(async () => {
      state.pushState = "off";
    });
    renderCard();
    await act(async () => {
      fireEvent.click(screen.getByTestId("settings-push-toggle-btn"));
    });
    expect(state.disablePush).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith(t("settings.notifications.disabledDone"));
    expect(screen.getByTestId("settings-push-toggle-btn")).toHaveTextContent(t("settings.notifications.enable"));
  });
});

describe("Impostazioni > Notifiche: uscita e rientro (P-44)", () => {
  it("notifiche attive: spiega che all'uscita si spengono e al rientro della stessa persona si riaccendono", () => {
    state.env.fcmEnabled = true;
    state.pushState = "on";
    renderCard();
    expect(screen.getByTestId("settings-push-signout-hint")).toHaveTextContent(t("settings.notifications.signOutHint"));
  });

  it("notifiche spente: la spiegazione non c'è", () => {
    state.env.fcmEnabled = true;
    renderCard();
    expect(screen.queryByTestId("settings-push-signout-hint")).not.toBeInTheDocument();
  });
});
