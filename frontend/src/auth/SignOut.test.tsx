import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { pushResumePending } from "@/lib/push";
import { useApartmentStore } from "@/store/apartmentStore";
import { useFeatureStore } from "@/store/featureStore";
import { AuthProvider, useAuth } from "./AuthProvider";

// Nothing of a user stays in the tab or on the device after they leave (P-36, D-59): push token dropped BEFORE the
// sign-out (and before the revocation, which would make the call fail with 401), cached answers, stores and assistant
// conversations cleared, also when another account signs in without "Esci".
vi.mock("@/lib/utils", async (importOriginal) => {
  const mod = await importOriginal<typeof import("@/lib/utils")>();
  return { ...mod, env: { ...mod.env, authMode: "dev", bffUrl: "", fcmEnabled: true } };
});
vi.mock("@/auth/firebase", () => ({ firebaseConfigured: true, firebaseApp: async () => ({}), firebaseAuth: async () => ({}), continueUrl: () => ({ url: "" }) }));
const fcm = vi.hoisted(() => ({ deleteToken: vi.fn(async () => true) }));
vi.mock("firebase/messaging", () => ({ getMessaging: () => ({}), deleteToken: fcm.deleteToken }));

const calls: string[] = [];
let ctx: ReturnType<typeof useAuth>;
let client: QueryClient;

function Probe() {
  ctx = useAuth();
  return <p data-testid="who">{ctx.status} {ctx.me?.user.uid ?? ""}</p>;
}

function bff() {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const path = new URL(url).pathname;
    calls.push(`${init?.method ?? "GET"} ${path}`);
    if (path === "/app/me") {
      const email = (init?.headers as Record<string, string>)["X-Dev-User"];
      const uid = email?.split("@")[0];
      return new Response(JSON.stringify({ user: { uid, email, display_name: "" }, role: "operator", tenant: { tenant_id: "t", name: "T" }, env: {} }), { status: 200 });
    }
    return new Response(null, { status: 204 });
  }));
}

async function signIn(email: string) {
  await act(() => ctx.devLogin(email));
  await waitFor(() => expect(screen.getByTestId("who")).toHaveTextContent(`authenticated ${email.split("@")[0]}`));
}

/** What a session leaves behind: cached answers, live store, runtime-disabled features, chat, push token. */
function leaveTraces(uid: string) {
  client.setQueryData(["apartments"], [{ apartment_id: "apt-001", name: `casa di ${uid}` }]);
  useApartmentStore.getState().reset("apt-001");
  useFeatureStore.getState().disable("apt-001", "energy");
  sessionStorage.setItem("assistant.apt-001", JSON.stringify([{ text: `chat di ${uid}` }]));
  localStorage.setItem("domotica.pushToken", `tok-${uid}`);
  localStorage.setItem("domotica.pushTokenOwner", uid);
}

function expectClean() {
  expect(client.getQueryData(["apartments"])).toBeUndefined();
  expect(useApartmentStore.getState().apartmentId).toBe("");
  expect(useFeatureStore.getState().disabled).toEqual({});
  expect(sessionStorage.getItem("assistant.apt-001")).toBeNull();
}

beforeEach(() => {
  calls.length = 0;
  localStorage.clear();
  sessionStorage.clear();
  client = new QueryClient();
  bff();
  render(
    <QueryClientProvider client={client}>
      <AuthProvider>
        <Probe />
      </AuthProvider>
    </QueryClientProvider>,
  );
});

describe("uscita: niente resta dell'utente che esce (D-59)", () => {
  it("Esci: prima il token push tolto sul BFF, poi l'uscita; dati della scheda e token del dispositivo cancellati", async () => {
    await signIn("anna@demo.it");
    leaveTraces("anna");
    calls.length = 0;
    await act(() => ctx.logout());
    expect(calls).toEqual(["DELETE /app/push/subscribe"]);
    expect(screen.getByTestId("who")).toHaveTextContent("anonymous");
    expect(localStorage.getItem("domotica.pushToken")).toBeNull();
    expectClean();
    expect(pushResumePending("anna")).toBe(true); // P-44: back on when anna signs in again here
    expect(pushResumePending("bruno")).toBe(false);
  });

  it("Esci da tutti i dispositivi: token tolto PRIMA della revoca delle sessioni", async () => {
    await signIn("anna@demo.it");
    leaveTraces("anna");
    calls.length = 0;
    await act(() => ctx.logoutEverywhere());
    expect(calls).toEqual(["DELETE /app/push/subscribe", "POST /app/me/revoke-sessions"]);
    expectClean();
    expect(pushResumePending("anna")).toBe(true);
  });

  it("Esci con le notifiche spente su questo dispositivo: al rientro restano spente (P-44)", async () => {
    await signIn("anna@demo.it");
    await act(() => ctx.logout());
    expect(pushResumePending("anna")).toBe(false);
  });

  it("rete assente sulla cancellazione del token: l'uscita prosegue lo stesso", async () => {
    await signIn("anna@demo.it");
    leaveTraces("anna");
    const ok = global.fetch;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") throw new TypeError("Failed to fetch");
      return ok(url, init);
    }));
    await act(() => ctx.logout());
    expect(screen.getByTestId("who")).toHaveTextContent("anonymous");
    expect(localStorage.getItem("domotica.pushToken")).toBeNull();
    expectClean();
  });

  it("un altro account entra senza «Esci» del precedente: i dati della scheda vengono svuotati", async () => {
    await signIn("anna@demo.it");
    leaveTraces("anna");
    await signIn("bruno@demo.it");
    expectClean();
  });

  it("sessione rifiutata dal server senza «Esci» (scaduta o revocata): dati svuotati e token tolto, anche presso FCM (F4)", async () => {
    await signIn("anna@demo.it");
    leaveTraces("anna");
    fcm.deleteToken.mockClear();
    const ok = global.fetch;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      calls.push(`${init?.method ?? "GET"} ${path}`);
      if (path === "/app/me") return new Response(JSON.stringify({ error: "unauthorized", message: "Sessione scaduta" }), { status: 401 });
      if (path === "/app/push/subscribe") return new Response(JSON.stringify({ error: "unauthorized", message: "Sessione scaduta" }), { status: 401 });
      return ok(url, init);
    }));
    calls.length = 0;
    await act(() => ctx.refreshMe());
    await waitFor(() => expect(fcm.deleteToken).toHaveBeenCalledTimes(1));
    expect(calls).toContain("DELETE /app/push/subscribe"); // tried; the BFF refuses it without a session
    expect(screen.getByTestId("who")).toHaveTextContent("anonymous");
    expect(localStorage.getItem("domotica.pushToken")).toBeNull();
    expectClean();
    expect(pushResumePending("anna")).toBe(true); // P-44: imposed sign-out, same person back → push back on
  });

  it("stesso account che ricarica il profilo: nessuna pulizia", async () => {
    await signIn("anna@demo.it");
    leaveTraces("anna");
    await act(() => ctx.refreshMe());
    expect(client.getQueryData(["apartments"])).toBeDefined();
    expect(sessionStorage.getItem("assistant.apt-001")).not.toBeNull();
  });
});

describe("Elimina il mio account rifiutato dal server (D-73: ultimo gestore, ultimo amministratore)", () => {
  it("409 last_manager: l'errore arriva con il messaggio del server, si resta dentro e le notifiche del dispositivo restano attive", async () => {
    await signIn("anna@demo.it");
    leaveTraces("anna");
    fcm.deleteToken.mockClear();
    const ok = global.fetch;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url).pathname;
      calls.push(`${init?.method ?? "GET"} ${path}`);
      if (path === "/app/me" && init?.method === "DELETE") {
        return new Response(JSON.stringify({ error: "last_manager", message: "Sei l'ultimo gestore della piattaforma: nomina un altro gestore prima di eliminare il tuo account" }), { status: 409 });
      }
      return ok(url, init);
    }));
    calls.length = 0;
    let error: unknown;
    await act(async () => {
      await ctx.deleteAccount().catch((e) => (error = e));
    });
    expect((error as Error).message).toBe("Sei l'ultimo gestore della piattaforma: nomina un altro gestore prima di eliminare il tuo account");
    expect(calls).toEqual(["DELETE /app/me"]); // no push unsubscribe before the server accepted the deletion
    expect(fcm.deleteToken).not.toHaveBeenCalled();
    expect(localStorage.getItem("domotica.pushToken")).toBe("tok-anna");
    expect(screen.getByTestId("who")).toHaveTextContent("authenticated anna");
  });

  it("eliminazione accettata: poi il token del dispositivo viene cancellato e si esce", async () => {
    await signIn("anna@demo.it");
    leaveTraces("anna");
    fcm.deleteToken.mockClear();
    calls.length = 0;
    await act(() => ctx.deleteAccount());
    expect(calls[0]).toBe("DELETE /app/me");
    await waitFor(() => expect(fcm.deleteToken).toHaveBeenCalledTimes(1));
    expect(localStorage.getItem("domotica.pushToken")).toBeNull();
    expect(screen.getByTestId("who")).toHaveTextContent("anonymous");
    expectClean();
    expect(pushResumePending("anna")).toBe(false); // the account is gone: nothing to resume (P-44)
  });
});
