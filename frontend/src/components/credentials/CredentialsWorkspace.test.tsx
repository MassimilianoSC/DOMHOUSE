import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { toast } from "sonner";
import type { DeviceCredential } from "@/api/deviceCredentials";
import { CredentialsWorkspace } from "./CredentialsWorkspace";

// A3, the windows of «Credenziali dei dispositivi» (docs/proposta-a3-sito.md §2, §4, §5; screens approved, 1182):
// Registra, the password shown once, Rigenera, Revoca confirmed by writing the code again, Riprova, the connection data,
// and what the page does with each refusal of the server (docs/proposta-a3-server.md §8.2).
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const BASE = "/app/apartments/lab-prova/device-credentials";
const PASSWORD = "q7Vx2LmR9tKp4sWb8Nd3Hf6Zc1Jy5AeU"; // invented for the test

const cred = (device_id: string, stato: DeviceCredential["stato"], azione: DeviceCredential["azione"] = null, extra: Partial<DeviceCredential> = {}): DeviceCredential => ({
  device_id,
  name: null,
  stato,
  version: 3,
  updated_at: "2026-11-19T15:12:00Z",
  updated_by: "Giulia Rossi",
  azione,
  engine_device_id: null,
  op: null,
  connection: { server: "mqtt.example.test:8883", ssl_ca: "ca.pem", client_id: `lab-prova.${device_id}`, user: `lab-prova.${device_id}`, topic_prefix: `lab-prova/${device_id}` },
  ...extra,
});

type Answer = { status: number; body?: unknown } | "network";
const s = vi.hoisted(() => ({
  items: [] as unknown[],
  answers: {} as Record<string, unknown>,
  calls: [] as { method: string; path: string; body: unknown }[],
}));

function stubServer() {
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    const path = new URL(url).pathname;
    const method = init.method ?? "GET";
    s.calls.push({ method, path, body: init.body ? JSON.parse(init.body as string) : undefined });
    const answer = (s.answers[`${method} ${path}`] ?? (method === "GET" && path === BASE ? { status: 200, body: { items: s.items } } : { status: 404, body: { error: "not_found", message: "?" } })) as Answer;
    if (answer === "network") throw new TypeError("Failed to fetch");
    return new Response(answer.body === undefined ? null : JSON.stringify(answer.body), { status: answer.status, headers: { "Content-Type": "application/json" } });
  }));
}

function open() {
  stubServer();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CredentialsWorkspace apartmentId="lab-prova" scope="apartment" />
    </QueryClientProvider>,
  );
}

const reads = () => s.calls.filter((c) => c.method === "GET").length;
const posts = () => s.calls.filter((c) => c.method === "POST");
// The «⋯» menu opens from the keyboard: jsdom has no real pointer events for Radix.
const openMenuItem = async (deviceId: string, item: string) => {
  const trigger = await screen.findByTestId(`credential-menu-${deviceId}`);
  await act(async () => {
    fireEvent.keyDown(trigger, { key: "Enter" });
  });
  fireEvent.click(await screen.findByTestId(`credential-${item}-${deviceId}`));
};

beforeEach(() => {
  vi.clearAllMocks();
  s.items = [];
  s.answers = {};
  s.calls = [];
  window.localStorage.clear();
  window.sessionStorage.clear();
  Object.assign(navigator, { clipboard: { writeText: vi.fn(async () => {}) } });
});

describe("«Registra un dispositivo»", () => {
  it("il codice si controlla mentre si scrive: spazi e «connector» no, il pulsante resta spento; le maiuscole diventano minuscole da sole", async () => {
    open();
    fireEvent.click(await screen.findByTestId("credentials-register-btn"));
    const field = await screen.findByTestId("credential-register-input");
    const save = screen.getByTestId("credential-register-save");
    expect(save).toBeDisabled();
    fireEvent.change(field, { target: { value: "Shelly Plug" } });
    expect(screen.getByTestId("credential-register-problem")).toHaveTextContent("Solo lettere minuscole, cifre e trattini, fino a 64 caratteri.");
    expect(save).toBeDisabled();
    fireEvent.change(field, { target: { value: "connector" } });
    expect(screen.getByTestId("credential-register-problem")).toHaveTextContent("riservato");
    expect(save).toBeDisabled();
    fireEvent.change(field, { target: { value: "shellyplugmg3-aa01" } });
    expect(screen.queryByTestId("credential-register-problem")).toBeNull();
    expect(save).toBeEnabled();
    // usability reading 2.10: the Shelly shows its name in capitals
    fireEvent.change(field, { target: { value: "ShellyPlugMG3-AA01" } });
    expect(field).toHaveValue("shellyplugmg3-aa01");
    expect(screen.queryByTestId("credential-register-problem")).toBeNull();
    expect(save).toBeEnabled();
    expect(posts()).toEqual([]);
  });

  it("registrato: la password compare una volta, con i valori da copiare e i nomi dei campi dello Shelly", async () => {
    const c = cred("shellyplugmg3-aa01", "in_attesa", "registra");
    s.answers[`POST ${BASE}`] = { status: 201, body: { credential: c, password: PASSWORD } };
    open();
    fireEvent.click(await screen.findByTestId("credentials-register-btn"));
    fireEvent.change(await screen.findByTestId("credential-register-input"), { target: { value: "shellyplugmg3-aa01" } });
    fireEvent.click(screen.getByTestId("credential-register-save"));
    const dlg = await screen.findByTestId("credential-password-dialog");
    expect(posts()).toEqual([{ method: "POST", path: BASE, body: { device_id: "shellyplugmg3-aa01" } }]);
    expect(dlg).toHaveTextContent("La vedi solo ora.");
    // usability reading 2.6, 2.8, 2.11: the whole sentences
    expect(dlg).toHaveTextContent("Copiala adesso nella pagina dello Shelly: non ricaricare la pagina e non chiudere la scheda finché non hai finito. Dopo non si può più leggere, né qui né altrove. Se la perdi, usa «Rigenera».");
    expect(dlg).toHaveTextContent("Nella pagina MQTT dello Shelly (la voce delle impostazioni dove si scrive a quale server collegarsi) compila i campi così, nell'ordine:");
    expect(dlg).toHaveTextContent("Se il tuo PC sincronizza gli appunti con altri dispositivi, dopo la copia svuotali (su Windows: tasto Windows + V, poi «Cancella tutto»).");
    expect(within(dlg).getByTestId("credential-value-password")).toHaveTextContent(PASSWORD);
    expect(within(dlg).getByTestId("credential-value-server")).toHaveTextContent("mqtt.example.test:8883");
    expect(within(dlg).getByTestId("credential-value-client_id")).toHaveTextContent("lab-prova.shellyplugmg3-aa01");
    expect(within(dlg).getByTestId("credential-value-user")).toHaveTextContent("lab-prova.shellyplugmg3-aa01");
    expect(within(dlg).getByTestId("credential-value-topic_prefix")).toHaveTextContent("lab-prova/shellyplugmg3-aa01");
    for (const shelly of ["«Connection type»", "Default TLS", "«MQTT prefix»", "«Server»", "«Client ID»", "«Username»", "«Password»"]) expect(dlg).toHaveTextContent(shelly);
    // copy
    fireEvent.click(within(dlg).getByTestId("credential-copy-password"));
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(PASSWORD));
    // the list is read again after the action
    await waitFor(() => expect(reads()).toBeGreaterThanOrEqual(2));
  });

  it("la finestra della password non si chiude con Esc né senza la spunta; chiusa, la password non è più da nessuna parte", async () => {
    s.answers[`POST ${BASE}`] = { status: 201, body: { credential: cred("shellyplugmg3-aa01", "in_attesa", "registra"), password: PASSWORD } };
    open();
    fireEvent.click(await screen.findByTestId("credentials-register-btn"));
    fireEvent.change(await screen.findByTestId("credential-register-input"), { target: { value: "shellyplugmg3-aa01" } });
    fireEvent.click(screen.getByTestId("credential-register-save"));
    const dlg = await screen.findByTestId("credential-password-dialog");
    expect(within(dlg).queryByRole("button", { name: /^Chiudi$/ })).toBeDisabled();
    expect(within(dlg).queryByLabelText("Chiudi", { selector: "button[aria-label]" })).toBeNull(); // no «×»
    fireEvent.keyDown(dlg, { key: "Escape" });
    expect(screen.getByTestId("credential-password-dialog")).toBeInTheDocument();
    fireEvent.click(within(dlg).getByTestId("credential-password-copied"));
    fireEvent.click(within(dlg).getByTestId("credential-password-close"));
    await waitFor(() => expect(screen.queryByTestId("credential-password-dialog")).toBeNull());
    expect(document.body.textContent).not.toContain(PASSWORD);
    expect(JSON.stringify({ ...window.localStorage })).not.toContain(PASSWORD);
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain(PASSWORD);
    expect(window.location.href).not.toContain(PASSWORD);
  });

  it("ordine non partito (201 con non_applicato): la password vale lo stesso, sopra il messaggio in rosso con l'ID richiesta", async () => {
    const op = { op_id: "3f9c2a71-0000-4000-8000-000000000002", stato: "fallito", messaggio: "Ordine non inviato al sistema domotico: copia comunque la password, poi usa «Riprova»" };
    s.answers[`POST ${BASE}`] = { status: 201, body: { credential: cred("shellyplugmg3-aa01", "non_applicato", "registra", { op }), password: PASSWORD } };
    open();
    fireEvent.click(await screen.findByTestId("credentials-register-btn"));
    fireEvent.change(await screen.findByTestId("credential-register-input"), { target: { value: "shellyplugmg3-aa01" } });
    fireEvent.click(screen.getByTestId("credential-register-save"));
    const dlg = await screen.findByTestId("credential-password-dialog");
    expect(within(dlg).getByTestId("credential-password-not-applied")).toHaveTextContent(op.messaggio);
    expect(within(dlg).getByTestId("credential-password-op")).toHaveAttribute("data-correlation-id", op.op_id);
    expect(within(dlg).getByTestId("credential-value-password")).toHaveTextContent(PASSWORD);
  });

  it("senza indirizzo nell'ambiente (server null): «Non configurato in questo ambiente», senza «Copia»", async () => {
    const c = cred("shellyplugmg3-aa01", "in_attesa", "registra");
    s.answers[`POST ${BASE}`] = { status: 201, body: { credential: { ...c, connection: { ...c.connection, server: null } }, password: PASSWORD } };
    open();
    fireEvent.click(await screen.findByTestId("credentials-register-btn"));
    fireEvent.change(await screen.findByTestId("credential-register-input"), { target: { value: "shellyplugmg3-aa01" } });
    fireEvent.click(screen.getByTestId("credential-register-save"));
    const dlg = await screen.findByTestId("credential-password-dialog");
    expect(within(dlg).getByTestId("credential-value-server")).toHaveTextContent("Non configurato in questo ambiente");
    expect(within(dlg).queryByTestId("credential-copy-server")).toBeNull();
  });

  it("già registrato (409): la finestra si chiude, l'elenco si rilegge, il messaggio del server", async () => {
    s.answers[`POST ${BASE}`] = { status: 409, body: { error: "already_registered", message: "Questo dispositivo ha già una password. Se è persa, usa «Rigenera»." } };
    open();
    fireEvent.click(await screen.findByTestId("credentials-register-btn"));
    fireEvent.change(await screen.findByTestId("credential-register-input"), { target: { value: "shellyplugmg3-aa01" } });
    fireEvent.click(screen.getByTestId("credential-register-save"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Questo dispositivo ha già una password. Se è persa, usa «Rigenera».", expect.anything()));
    await waitFor(() => expect(screen.queryByTestId("credential-register-dialog")).toBeNull());
    expect(reads()).toBeGreaterThanOrEqual(2);
  });

  it("rete caduta: non sappiamo se la password è nata; l'elenco si rilegge", async () => {
    s.answers[`POST ${BASE}`] = "network";
    open();
    fireEvent.click(await screen.findByTestId("credentials-register-btn"));
    fireEvent.change(await screen.findByTestId("credential-register-input"), { target: { value: "shellyplugmg3-aa01" } });
    fireEvent.click(screen.getByTestId("credential-register-save"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Non sappiamo se la password è stata creata. Ricarica l'elenco: se il dispositivo risulta registrato, usa «Rigenera».", expect.anything()));
    expect(screen.queryByTestId("credential-password-dialog")).toBeNull();
  });

  it("«Registra di nuovo» su un revocato: nessun campo, la password nuova subito", async () => {
    s.items = [cred("d-rev", "revocato")];
    s.answers[`POST ${BASE}`] = { status: 201, body: { credential: cred("d-rev", "in_attesa", "registra"), password: PASSWORD } };
    open();
    fireEvent.click(await screen.findByTestId("credentials-revoked-toggle"));
    fireEvent.click(screen.getByTestId("credential-reregister-d-rev"));
    expect(await screen.findByTestId("credential-password-dialog")).toHaveTextContent(PASSWORD);
    expect(posts()).toEqual([{ method: "POST", path: BASE, body: { device_id: "d-rev" } }]);
  });
});

describe("«Rigenera»", () => {
  it("la conferma dice cosa succede; poi la password nuova, con la version letta", async () => {
    s.items = [cred("d-ok", "pronto")];
    s.answers[`POST ${BASE}/d-ok/rigenera`] = { status: 200, body: { credential: cred("d-ok", "cambio_in_corso", "rigenera", { version: 4 }), password: PASSWORD } };
    open();
    await openMenuItem("d-ok", "regenerate");
    const confirm = await screen.findByTestId("credential-regenerate-dialog");
    expect(confirm).toHaveTextContent("Quella di adesso smette di valere appena il sistema domotico conferma il cambio");
    fireEvent.click(within(confirm).getByTestId("credential-regenerate-confirm"));
    expect(await screen.findByTestId("credential-password-dialog")).toHaveTextContent(PASSWORD);
    expect(posts()).toEqual([{ method: "POST", path: `${BASE}/d-ok/rigenera`, body: { version: 3 } }]);
  });

  it("qualcuno ha cambiato il dispositivo (409 version_changed): l'elenco si rilegge da solo e lo dice", async () => {
    s.items = [cred("d-ok", "pronto")];
    s.answers[`POST ${BASE}/d-ok/rigenera`] = { status: 409, body: { error: "version_changed", message: "Qualcuno ha appena cambiato questo dispositivo: ricarica l'elenco." } };
    open();
    await openMenuItem("d-ok", "regenerate");
    const before = reads();
    fireEvent.click(within(await screen.findByTestId("credential-regenerate-dialog")).getByTestId("credential-regenerate-confirm"));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("Elenco aggiornato: controlla lo stato prima di riprovare."));
    await waitFor(() => expect(reads()).toBeGreaterThan(before));
    expect(screen.queryByTestId("credential-password-dialog")).toBeNull();
  });
});

describe("«Revoca»", () => {
  it("si conferma riscrivendo il codice: il pulsante si accende solo con il codice uguale", async () => {
    s.items = [cred("shellyplugmg3-aa01", "pronto")];
    s.answers[`POST ${BASE}/shellyplugmg3-aa01/revoca`] = { status: 202, body: { credential: cred("shellyplugmg3-aa01", "revoca_in_corso", "revoca", { version: 4 }) } };
    open();
    await openMenuItem("shellyplugmg3-aa01", "revoke");
    const dlg = await screen.findByTestId("credential-revoke-dialog");
    expect(dlg).toHaveTextContent("Il dispositivo smette subito di funzionare");
    expect(dlg).toHaveTextContent("Per riattivarlo bisogna andare sul posto");
    const go = within(dlg).getByTestId("credential-revoke-confirm");
    const field = within(dlg).getByTestId("credential-revoke-input");
    expect(go).toBeDisabled();
    fireEvent.change(field, { target: { value: "shellyplugmg3-aa0" } });
    expect(go).toBeDisabled();
    fireEvent.change(field, { target: { value: "SHELLYPLUGMG3-AA01" } });
    expect(go).toBeDisabled();
    fireEvent.change(field, { target: { value: " shellyplugmg3-aa01 " } });
    expect(go).toBeEnabled();
    fireEvent.click(go);
    await waitFor(() => expect(posts()).toEqual([{ method: "POST", path: `${BASE}/shellyplugmg3-aa01/revoca`, body: { version: 3 } }]));
    await waitFor(() => expect(screen.queryByTestId("credential-revoke-dialog")).toBeNull());
  });

  it("ordine non inviato (502): il messaggio del server con l'ID richiesta dell'operazione; l'elenco si rilegge", async () => {
    s.items = [cred("d-ok", "pronto")];
    s.answers[`POST ${BASE}/d-ok/revoca`] = { status: 502, body: { error: "agent_publish_failed", message: "Ordine non inviato all'agente", details: { op: { op_id: "9a8b7c6d-0000-4000-8000-000000000003", stato: "fallito", codice: "non_inviato", messaggio: "Ordine non inviato" } } } };
    open();
    await openMenuItem("d-ok", "revoke");
    const dlg = await screen.findByTestId("credential-revoke-dialog");
    fireEvent.change(within(dlg).getByTestId("credential-revoke-input"), { target: { value: "d-ok" } });
    const before = reads();
    fireEvent.click(within(dlg).getByTestId("credential-revoke-confirm"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Ordine non inviato all'agente", expect.anything()));
    const description = (toast.error as unknown as { mock: { calls: [string, { description: React.ReactElement }][] } }).mock.calls[0][1].description;
    render(<>{description}</>);
    expect(screen.getByTestId("toast-correlation-id")).toHaveAttribute("data-correlation-id", "9a8b7c6d-0000-4000-8000-000000000003");
    await waitFor(() => expect(reads()).toBeGreaterThan(before));
  });
});

describe("«Riprova»", () => {
  it("nessuna conferma: rimanda con la version letta e rilegge l'elenco", async () => {
    s.items = [cred("d-ko", "non_applicato", "revoca")];
    s.answers[`POST ${BASE}/d-ko/riprova`] = { status: 202, body: { credential: cred("d-ko", "revoca_in_corso", "revoca", { version: 4 }) } };
    open();
    fireEvent.click(await screen.findByTestId("credential-retry-d-ko"));
    await waitFor(() => expect(posts()).toEqual([{ method: "POST", path: `${BASE}/d-ko/riprova`, body: { version: 3 } }]));
    await waitFor(() => expect(reads()).toBeGreaterThanOrEqual(2));
  });

  it("già in corso (409 operation_in_progress): il messaggio del server e l'elenco riletto", async () => {
    s.items = [cred("d-ko", "non_applicato", "registra")];
    s.answers[`POST ${BASE}/d-ko/riprova`] = { status: 409, body: { error: "operation_in_progress", message: "C'è già un'operazione in corso su questo dispositivo: aspetta che finisca." } };
    open();
    fireEvent.click(await screen.findByTestId("credential-retry-d-ko"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("C'è già un'operazione in corso su questo dispositivo: aspetta che finisca.", expect.anything()));
    await waitFor(() => expect(reads()).toBeGreaterThanOrEqual(2));
  });

  it("stato cambiato (409 invalid_state): rilegge da solo e lo dice", async () => {
    s.items = [cred("d-ko", "non_applicato", "registra")];
    s.answers[`POST ${BASE}/d-ko/riprova`] = { status: 409, body: { error: "invalid_state", message: "Con lo stato di adesso questa azione non si può fare: ricarica l'elenco." } };
    open();
    fireEvent.click(await screen.findByTestId("credential-retry-d-ko"));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("Elenco aggiornato: questa azione non c'è più per lo stato di adesso."));
  });
});

describe("«Dati di collegamento»", () => {
  it("gli stessi valori, mai la password: al suo posto dice di usare «Rigenera»", async () => {
    s.items = [cred("d-ok", "pronto")];
    open();
    fireEvent.click(await screen.findByTestId("credential-connection-d-ok"));
    const dlg = await screen.findByTestId("credential-connection-dialog");
    expect(within(dlg).getByTestId("credential-value-client_id")).toHaveTextContent("lab-prova.d-ok");
    expect(within(dlg).getByTestId("credential-value-password")).toHaveTextContent("Password: non si può più leggere. Se è persa o l'ha vista chi non doveva, usa «Rigenera».");
    expect(within(dlg).queryByTestId("credential-copy-password")).toBeNull();
    expect(posts()).toEqual([]);
  });
});

// §3: while an order is on its way the list is read again every 4 s, for at most 20 minutes; then the page stops, even
// though React Query asks again after every reading (found with A2: the 20 minutes restarted when they ended).
describe("rilettura mentre un ordine è in corso", () => {
  const wait = async (ms: number) => {
    for (let left = ms; left > 0; left -= 1_000) await act(async () => { await vi.advanceTimersByTimeAsync(Math.min(1_000, left)); });
  };
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("ogni 4 secondi, e dopo 20 minuti si ferma davvero", async () => {
    s.items = [cred("shellyplugmg3-3c4d5e6f7a8b", "in_attesa", "registra")];
    open();
    await screen.findByTestId("credential-row-shellyplugmg3-3c4d5e6f7a8b");
    const first = reads();
    await wait(4_000);
    expect(reads()).toBe(first + 1);
    await act(async () => { await vi.advanceTimersByTimeAsync(20 * 60_000 + 8_000); });
    const n = reads();
    await wait(12_000);
    expect(reads()).toBe(n);
  });
});

describe("A5: gli accessi rifiutati nella riga (docs/proposta-a5.md)", () => {
  it("con rifiuti dopo l'ultima modifica: il riquadro giallo con «Cosa fare» e il ritardo", async () => {
    s.items = [
      cred("presa-cucina", "pronto", null, { rifiuti: { conteggio_24h: 12, ultimo: new Date(Date.now() - 60_000).toISOString() } }),
      cred("presa-bagno", "pronto", null, { rifiuti: null }),
      cred("presa-sala", "pronto", null, { rifiuti: { conteggio_24h: 0, ultimo: null } }),
    ];
    open();
    const box = await screen.findByTestId("credential-refusals-presa-cucina");
    expect(box).toHaveAttribute("data-kind", "warning");
    expect(box).toHaveTextContent(/^Accessi rifiutati nelle ultime 24 ore: 12, l'ultimo alle \d\d:\d\d\./);
    expect(box).toHaveTextContent("Cosa fare: nello Shelly utente o password non corrispondono. Controlla l'utente in «Dati di collegamento» e quello scritto nella pagina dello Shelly (per aprirla devi essere sulla sua stessa rete Wi-Fi); la password non si può rivedere: se non l'hai più, «Rigenera» e scrivi la nuova nello Shelly.");
    expect(box).toHaveTextContent("I tentativi compaiono con circa 10 minuti di ritardo e restano contati per 24 ore.");
    // «non lo so» and zero: no line, never «0»
    expect(screen.queryByTestId("credential-refusals-presa-bagno")).toBeNull();
    expect(screen.queryByTestId("credential-refusals-presa-sala")).toBeNull();
    expect(screen.getByTestId("credential-row-presa-bagno")).not.toHaveTextContent("Accessi rifiutati");
  });

  it("tutti prima dell'ultima modifica: in grigio, senza «Cosa fare»", async () => {
    s.items = [cred("presa-cucina", "pronto", null, { rifiuti: { conteggio_24h: 4, ultimo: "2026-11-19T15:00:00Z" } })];
    open();
    const box = await screen.findByTestId("credential-refusals-presa-cucina");
    expect(box).toHaveAttribute("data-kind", "past");
    expect(box).toHaveTextContent("Tutti prima dell'ultima modifica: se lo Shelly ha i dati nuovi, non serve fare niente.");
    expect(box).not.toHaveTextContent("Cosa fare");
  });

  it("revocato: lo Shelly prova ancora a collegarsi", async () => {
    s.items = [cred("presa-cucina", "revocato", null, { rifiuti: { conteggio_24h: 3, ultimo: new Date(Date.now() - 60_000).toISOString() } })];
    open();
    const toggle = await screen.findByTestId("credentials-revoked-toggle");
    fireEvent.click(toggle);
    const box = await screen.findByTestId("credential-refusals-presa-cucina");
    expect(box).toHaveAttribute("data-kind", "revoked");
    expect(box).toHaveTextContent("Lo Shelly prova ancora a collegarsi: spegnilo, oppure «Registra di nuovo».");
    expect(box).not.toHaveTextContent("Cosa fare");
  });
});
