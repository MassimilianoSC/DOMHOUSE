import { disablePush, enablePush, forgetPushResume, PushError, pushResumePending, pushState, syncPushToken } from "./push";

// Push on this device with everything simulated: Firebase messaging, the BFF (pushApi), the browser permission and
// the service worker registration.
const s = vi.hoisted(() => ({
  env: {} as Record<string, unknown>,
  ios: false,
  standalone: false,
  token: "tok-1",
  registration: { scope: "/" },
  getToken: vi.fn(),
  deleteToken: vi.fn(async () => true),
  subscribe: vi.fn(async () => ({ subscribed: true, tokens: 1 })),
  unsubscribe: vi.fn(async () => ({ subscribed: false })),
}));

vi.mock("@/lib/utils", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/utils")>();
  return { ...mod, env: Object.assign(s.env, mod.env) };
});
vi.mock("@/auth/firebase", () => ({ firebaseConfigured: true, firebaseApp: async () => ({ name: "app" }) }));
vi.mock("firebase/messaging", () => ({ getMessaging: () => ({ m: 1 }), getToken: s.getToken, deleteToken: s.deleteToken }));
vi.mock("@/api/admin", () => ({ pushApi: { subscribe: s.subscribe, unsubscribe: s.unsubscribe } }));
vi.mock("@/hooks/useInstallPrompt", () => ({ isIos: () => s.ios, isStandalone: () => s.standalone }));

const KEY = "domotica.pushToken";
const OWNER = "domotica.pushTokenOwner";
const own = (token: string, uid = "u1") => {
  localStorage.setItem(KEY, token);
  localStorage.setItem(OWNER, uid);
};
let permission: NotificationPermission;
const requestPermission = vi.fn(async () => permission);

function browserWithPush(on = true) {
  if (on) {
    vi.stubGlobal("Notification", { get permission() { return permission; }, requestPermission });
    vi.stubGlobal("PushManager", function PushManager() {});
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { ready: Promise.resolve(s.registration) } });
  } else {
    Reflect.deleteProperty(navigator, "serviceWorker");
  }
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  s.env.fcmEnabled = true;
  s.ios = false;
  s.standalone = false;
  permission = "default";
  s.getToken.mockImplementation(async () => s.token);
  s.token = "tok-1";
  browserWithPush();
});

afterEach(() => {
  Reflect.deleteProperty(navigator, "serviceWorker");
});

describe("push: stato del dispositivo", () => {
  it("browser senza push: «non supportato»; iPhone fuori dall'app installata: «installa»", () => {
    vi.stubGlobal("Notification", undefined);
    Reflect.deleteProperty(window, "Notification");
    browserWithPush(false);
    expect(pushState("u1")).toBe("unsupported");
    s.ios = true;
    expect(pushState("u1")).toBe("ios-install");
    s.standalone = true;
    expect(pushState("u1")).toBe("unsupported"); // installed but too old (before iOS 16.4): no Notification
  });

  it("permesso: bloccato → denied; mai chiesto → off; concesso con token → on; tolto dopo l'attivazione → revoked", () => {
    permission = "denied";
    expect(pushState("u1")).toBe("denied");
    permission = "default";
    expect(pushState("u1")).toBe("off");
    permission = "granted";
    own("tok-1");
    expect(pushState("u1")).toBe("on");
    permission = "default";
    expect(pushState("u1")).toBe("revoked");
  });
});

describe("push: attivazione e disattivazione", () => {
  it("attiva: chiede il permesso, prende il token con la registrazione del service worker del sito e lo registra sul BFF", async () => {
    permission = "granted";
    await enablePush("u1");
    expect(requestPermission).toHaveBeenCalledTimes(1);
    expect(s.getToken).toHaveBeenCalledWith({ m: 1 }, expect.objectContaining({ serviceWorkerRegistration: s.registration }));
    expect(s.subscribe).toHaveBeenCalledWith("tok-1");
    expect(localStorage.getItem(KEY)).toBe("tok-1");
    expect(localStorage.getItem(OWNER)).toBe("u1");
    expect(pushState("u1")).toBe("on");
    expect(pushState("u2")).toBe("off"); // another account on this device does not see it as its own
  });

  it("permesso negato: errore «denied», nessun token, niente sul BFF", async () => {
    permission = "denied";
    await expect(enablePush("u1")).rejects.toEqual(new PushError("denied"));
    expect(s.getToken).not.toHaveBeenCalled();
    expect(s.subscribe).not.toHaveBeenCalled();
  });

  it("browser senza push: errore «unsupported» senza chiedere il permesso", async () => {
    browserWithPush(false);
    await expect(enablePush("u1")).rejects.toEqual(new PushError("unsupported"));
    expect(requestPermission).not.toHaveBeenCalled();
  });

  it("FCM non dà un token: errore «no_token», niente sul BFF", async () => {
    permission = "granted";
    s.getToken.mockResolvedValueOnce("");
    await expect(enablePush("u1")).rejects.toEqual(new PushError("no_token"));
    expect(s.subscribe).not.toHaveBeenCalled();
  });

  it("disattiva: toglie il token dal BFF e anche presso FCM", async () => {
    own("tok-1");
    await disablePush();
    expect(s.unsubscribe).toHaveBeenCalledWith("tok-1");
    expect(s.deleteToken).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(KEY)).toBeNull();
    expect(localStorage.getItem(OWNER)).toBeNull();
  });
});

describe("push: riallineamento a ogni avvio", () => {
  it("stesso token: lo riconferma al BFF (che può averlo tolto), nient'altro", async () => {
    permission = "granted";
    own("tok-1");
    await syncPushToken("u1");
    expect(s.subscribe).toHaveBeenCalledWith("tok-1");
    expect(s.unsubscribe).not.toHaveBeenCalled();
  });

  it("token rinnovato da FCM: registra il nuovo, toglie il vecchio", async () => {
    permission = "granted";
    own("tok-old");
    await syncPushToken("u1");
    expect(s.subscribe).toHaveBeenCalledWith("tok-1");
    expect(s.unsubscribe).toHaveBeenCalledWith("tok-old");
    expect(localStorage.getItem(KEY)).toBe("tok-1");
  });

  it("permesso tolto dalle impostazioni: il BFF smette di mandare a questo dispositivo, lo stato resta «revoked»", async () => {
    permission = "default";
    own("tok-1");
    await syncPushToken("u1");
    expect(s.unsubscribe).toHaveBeenCalledWith("tok-1");
    expect(s.getToken).not.toHaveBeenCalled();
    expect(pushState("u1")).toBe("revoked");
  });

  it("mai attivate qui, o FCM spento nella build: nessuna chiamata", async () => {
    permission = "granted";
    await syncPushToken("u1");
    s.env.fcmEnabled = false;
    own("tok-1");
    await syncPushToken("u1");
    expect(s.getToken).not.toHaveBeenCalled();
    expect(s.subscribe).not.toHaveBeenCalled();
  });

  it("BFF non raggiungibile: nessun errore all'avvio, si riprova la volta dopo", async () => {
    permission = "granted";
    own("tok-1");
    s.subscribe.mockRejectedValueOnce(new Error("rete"));
    await expect(syncPushToken("u1")).resolves.toBeUndefined();
  });
});

describe("push: cambio di account sullo stesso dispositivo (D-59)", () => {
  it("token lasciato da un altro account senza «Esci»: tolto sul server e presso FCM, mai registrato per il nuovo utente (F4)", async () => {
    permission = "granted";
    own("tok-of-u1", "u1");
    await syncPushToken("u2");
    expect(s.unsubscribe).toHaveBeenCalledWith("tok-of-u1");
    expect(s.deleteToken).toHaveBeenCalledTimes(1);
    expect(s.subscribe).not.toHaveBeenCalled();
    expect(s.getToken).not.toHaveBeenCalled();
    expect(localStorage.getItem(KEY)).toBeNull();
    expect(pushState("u2")).toBe("off");
  });

  it("token senza proprietario (versione precedente): non adottato", async () => {
    permission = "granted";
    localStorage.setItem(KEY, "tok-legacy");
    expect(pushState("u1")).toBe("off");
    await syncPushToken("u1");
    expect(s.subscribe).not.toHaveBeenCalled();
    expect(s.unsubscribe).toHaveBeenCalledWith("tok-legacy");
    expect(s.deleteToken).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem(KEY)).toBeNull();
  });
});

describe("push: cancellazione che non riesce per la rete (N2)", () => {
  it("FCM non raggiungibile: il token resta sul dispositivo SENZA proprietario (spento per tutti) e si riprova al giro dopo", async () => {
    own("tok-1", "u1");
    s.deleteToken.mockRejectedValueOnce(new Error("offline"));
    await disablePush();
    expect(localStorage.getItem(KEY)).toBe("tok-1");
    expect(pushState("u1")).not.toBe("on"); // switched off now; it comes back only through the resume below (P-44)
    permission = "granted";
    await syncPushToken("u1"); // next start, network back
    expect(s.unsubscribe).toHaveBeenCalledTimes(2);
    expect(s.deleteToken).toHaveBeenCalledTimes(2);
    expect(s.subscribe).not.toHaveBeenCalled();
    expect(localStorage.getItem(KEY)).toBeNull();
  });
});

describe("push: rientro della STESSA persona sullo stesso dispositivo (P-44)", () => {
  /** "Esci" (or a sign-out imposed from outside) with push on for u1: off now, to be resumed for u1 only. */
  async function leave(uid = "u1") {
    own("tok-old", uid);
    await disablePush({ resume: true });
  }

  it("uscita con le notifiche attive: spente subito, al rientro della stessa persona riattivate senza chiedere il permesso", async () => {
    permission = "granted";
    await leave();
    expect(localStorage.getItem(KEY)).toBeNull();
    expect(s.deleteToken).toHaveBeenCalledTimes(1);
    expect(pushResumePending("u1")).toBe(true);
    await expect(syncPushToken("u1")).resolves.toBe("resumed");
    expect(requestPermission).not.toHaveBeenCalled();
    expect(s.subscribe).toHaveBeenCalledWith("tok-1");
    expect(pushState("u1")).toBe("on");
    expect(pushResumePending("u1")).toBe(false);
  });

  it("un'altra persona sullo stesso dispositivo: per lei restano spente; la prima, al suo rientro, le ritrova", async () => {
    permission = "granted";
    await leave("u1");
    await expect(syncPushToken("u2")).resolves.toBeUndefined();
    expect(s.getToken).not.toHaveBeenCalled();
    expect(s.subscribe).not.toHaveBeenCalled();
    expect(pushState("u2")).toBe("off");
    await expect(syncPushToken("u1")).resolves.toBe("resumed");
    expect(localStorage.getItem(OWNER)).toBe("u1");
  });

  it("due persone che escono con le notifiche attive: ognuna le ritrova al suo rientro", async () => {
    permission = "granted";
    await leave("u1");
    await leave("u2");
    expect(pushResumePending("u1")).toBe(true);
    expect(pushResumePending("u2")).toBe(true);
  });

  it("spente a mano da Impostazioni, o mai attivate: al rientro restano spente", async () => {
    permission = "granted";
    own("tok-old", "u1");
    await disablePush(); // «Disattiva» in Impostazioni
    await disablePush({ resume: true }); // then «Esci»: nothing was on any more
    await expect(syncPushToken("u1")).resolves.toBeUndefined();
    expect(s.getToken).not.toHaveBeenCalled();
    expect(pushResumePending("u1")).toBe(false);
  });

  it("permesso del browser tolto nel frattempo: nessuna richiesta di permesso, restano spente e lo dice una volta sola", async () => {
    permission = "granted";
    await leave();
    permission = "default";
    await expect(syncPushToken("u1")).resolves.toBe("permission");
    expect(requestPermission).not.toHaveBeenCalled();
    expect(s.getToken).not.toHaveBeenCalled();
    expect(pushState("u1")).toBe("off");
    await expect(syncPushToken("u1")).resolves.toBeUndefined();
  });

  it("permesso bloccato nel frattempo: stesso comportamento", async () => {
    permission = "granted";
    await leave();
    permission = "denied";
    await expect(syncPushToken("u1")).resolves.toBe("permission");
    expect(s.getToken).not.toHaveBeenCalled();
  });

  it("token ancora in cancellazione presso FCM: nessun token nuovo finché la cancellazione non riesce, poi la riattivazione", async () => {
    permission = "granted";
    s.deleteToken.mockRejectedValueOnce(new Error("offline"));
    await leave();
    expect(localStorage.getItem(KEY)).toBe("tok-old"); // kept without owner
    s.deleteToken.mockRejectedValueOnce(new Error("offline"));
    await expect(syncPushToken("u1")).resolves.toBeUndefined(); // still offline
    expect(s.getToken).not.toHaveBeenCalled();
    expect(pushResumePending("u1")).toBe(true);
    await expect(syncPushToken("u1")).resolves.toBe("resumed"); // network back: deleted first, then a new token
    expect(s.deleteToken).toHaveBeenCalledTimes(3);
    expect(s.deleteToken.mock.invocationCallOrder[2]).toBeLessThan(s.getToken.mock.invocationCallOrder[0]);
    expect(localStorage.getItem(KEY)).toBe("tok-1");
    expect(localStorage.getItem(OWNER)).toBe("u1");
  });

  it("FCM o BFF non raggiungibili alla riattivazione: si riprova al giro dopo", async () => {
    permission = "granted";
    await leave();
    s.subscribe.mockRejectedValueOnce(new Error("rete"));
    await expect(syncPushToken("u1")).resolves.toBeUndefined();
    expect(pushResumePending("u1")).toBe(true);
    expect(localStorage.getItem(KEY)).toBeNull();
    await expect(syncPushToken("u1")).resolves.toBe("resumed");
  });

  it("token lasciato da chi non è uscito con «Esci» (sessione scaduta) e rientro di un'altra persona: spento per lei, la prima lo ritrova", async () => {
    permission = "granted";
    own("tok-of-u1", "u1");
    await expect(syncPushToken("u2")).resolves.toBeUndefined();
    expect(s.subscribe).not.toHaveBeenCalled();
    expect(pushResumePending("u2")).toBe(false);
    expect(pushResumePending("u1")).toBe(true);
  });

  it("account eliminato: niente da riattivare", async () => {
    permission = "granted";
    await leave();
    forgetPushResume("u1");
    await expect(syncPushToken("u1")).resolves.toBeUndefined();
    expect(s.getToken).not.toHaveBeenCalled();
  });

  it("FCM spento nella build o browser senza push: nessuna chiamata, la riattivazione resta in attesa", async () => {
    permission = "granted";
    await leave();
    s.env.fcmEnabled = false;
    await expect(syncPushToken("u1")).resolves.toBeUndefined();
    expect(s.getToken).not.toHaveBeenCalled();
    expect(pushResumePending("u1")).toBe(true);
  });
});
