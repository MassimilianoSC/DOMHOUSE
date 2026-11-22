import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import type { Eliminazione, PlatformApartment } from "@/api/platform";
import { PlatformApartments } from "./PlatformApartments";

// A6 in Organizzazioni > an organization > Appartamenti (docs/proposta-a6.md; bff/API.md «Eliminazione di un
// appartamento»): «Disattiva», the 7 days, «Elimina» confirmed by writing the name, the deletion in progress or stopped
// with «Riprova». Only the platform manager, for now (answer 1210, point 1).

const s = vi.hoisted(() => ({
  apartments: vi.fn(),
  tenant: vi.fn(),
  disable: vi.fn(),
  reenable: vi.fn(),
  deleteApartment: vi.fn(),
  retryDeletion: vi.fn(),
  verifyApartment: vi.fn(),
}));

vi.mock("@/api/platform", () => ({
  platformApi: { apartments: s.apartments, tenant: s.tenant, disable: s.disable, reenable: s.reenable, deleteApartment: s.deleteApartment, retryDeletion: s.retryDeletion, verifyApartment: s.verifyApartment },
}));
vi.mock("@/api/deviceCredentials", () => ({ credentialsApi: () => ({ list: vi.fn(async () => ({ items: [] })) }) }));
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ me: { env: { app_env: "staging", instance_mode: "real", creazione_disponibile: true } }, refreshMe: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const DAY = 24 * 60 * 60_000;
const iso = (ms: number) => new Date(ms).toISOString();
const BASE: PlatformApartment = {
  apartment_id: "lab-ponte", name: "Bilocale Ponte", instance_url: "http://10.198.0.2:8151", port: null, enabled: true, timezone: "Europe/Rome",
  italianway_id: null, last_check: null, creazione: { stato: "pronto", passo: "collegamento", version: 5, porta: 8151, op: null, codice: null, messaggio: null, fatti: [], updated_at: "2026-11-01T10:00:00Z", updated_by: null },
  origine: "app", disattivato_at: null, disattivato_da: null, eliminabile_dal: null, eliminazione: null,
};
const apt = (over: Partial<PlatformApartment> = {}): PlatformApartment => ({ ...BASE, ...over });
/** Disabled 8 days ago by the platform manager: «Elimina» is possible. */
const off = (over: Partial<PlatformApartment> = {}) =>
  apt({ enabled: false, disattivato_at: iso(Date.now() - 8 * DAY), disattivato_da: { ruolo: "gestore", nome: "Giulia Rossi" }, eliminabile_dal: iso(Date.now() - DAY), ...over });
const elim = (over: Partial<Eliminazione> = {}): Eliminazione => ({
  stato: "in_corso", passo: "segreti", codice: null, messaggio: null, op: null, version: 2, iniziata_at: "2026-11-20T15:50:00Z", updated_at: "2026-11-20T15:55:00Z", updated_by: "Giulia Rossi", ...over,
});

function renderList() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <PlatformApartments tenantId="t-1" tenantName="Residenze Esempio" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function open(items: PlatformApartment[]) {
  s.apartments.mockResolvedValue(items);
  renderList();
  await screen.findByTestId(`platform-apt-${items[0].apartment_id}`);
}

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});
const type = (el: HTMLElement, value: string) => fireEvent.change(el, { target: { value } });
const q = (id: string) => screen.queryByTestId(id);

beforeEach(() => {
  vi.clearAllMocks();
  s.tenant.mockResolvedValue({ tenant_id: "t-1", name: "Residenze Esempio", created_at: "", first_admin: null, creazioni_ultima_ora: { usate: 0, limite: 5, libera_dal: null } });
  s.disable.mockResolvedValue(off());
  s.reenable.mockResolvedValue(apt());
  s.deleteApartment.mockResolvedValue({ eliminazione: elim() });
  s.retryDeletion.mockResolvedValue({ eliminazione: elim({ version: 3 }) });
});

describe("Disattiva e Riattiva", () => {
  it("attivo: «Disattiva», niente «Riattiva» né «Elimina», nessuna DELETE di oggi", async () => {
    await open([apt()]);
    expect(screen.getByTestId("platform-apt-disable-lab-ponte")).toHaveTextContent("Disattiva");
    expect(q("platform-apt-reenable-lab-ponte")).toBeNull();
    expect(q("platform-apt-delete-lab-ponte")).toBeNull();
    expect(q("platform-apt-disabled-lab-ponte")).toBeNull();
  });

  it("«Disattiva» chiede prima, dicendo cosa fa davvero; poi la chiamata e l'elenco riletto", async () => {
    await open([apt()]);
    await click(screen.getByTestId("platform-apt-disable-lab-ponte"));
    const dialog = screen.getByTestId("apt-disable-dialog");
    expect(dialog).toHaveTextContent("Disattivare «Bilocale Ponte»?");
    expect(dialog).toHaveTextContent(
      "Gli automatismi del sistema domotico continuano. Si fermano notifiche (anche le gravi, come «sistema domotico non raggiungibile»), riepilogo del lunedì, prenotazioni da Italianway ed export Excel; le prenotazioni arrivate nel frattempo non si recuperano alla riattivazione.",
    );
    expect(dialog).toHaveTextContent("Dopo 7 giorni da disattivato si potrà eliminare.");
    expect(dialog).toHaveTextContent("Gli amministratori dell'organizzazione e i gestori della piattaforma ricevono un'email.");
    expect(s.disable).not.toHaveBeenCalled();
    await click(within(dialog).getByTestId("apt-disable-confirm"));
    expect(s.disable).toHaveBeenCalledWith("t-1", "lab-ponte", expect.any(String));
    expect(toast.success).toHaveBeenCalledWith("Bilocale Ponte disattivato.");
    await waitFor(() => expect(s.apartments).toHaveBeenCalledTimes(2));
  });

  it("«Annulla» nella finestra: niente", async () => {
    await open([apt()]);
    await click(screen.getByTestId("platform-apt-disable-lab-ponte"));
    await click(screen.getByTestId("apt-disable-back"));
    expect(s.disable).not.toHaveBeenCalled();
    expect(q("apt-disable-dialog")).toBeNull();
  });

  it("disattivato da meno di 7 giorni: chi e quando, da quando si potrà eliminare; «Elimina» spento, «Riattiva» subito", async () => {
    const when = iso(Date.now() + 5 * DAY);
    await open([off({ disattivato_at: "2026-11-20T15:05:00Z", disattivato_da: { ruolo: "amministratore", nome: "Marco Bianchi" }, eliminabile_dal: when })]);
    const line = screen.getByTestId("platform-apt-disabled-lab-ponte");
    expect(line).toHaveTextContent("Disattivato il 20 nov 2026, 16:05 da Marco Bianchi (amministratore)");
    expect(line).toHaveTextContent(/Si potrà eliminare dal \d{1,2} \w{3} \d{4}, \d\d:\d\d\./);
    expect(screen.getByTestId("platform-apt-delete-lab-ponte")).toBeDisabled();
    expect(q("platform-apt-disable-lab-ponte")).toBeNull();
    await click(screen.getByTestId("platform-apt-reenable-lab-ponte"));
    expect(s.reenable).toHaveBeenCalledWith("t-1", "lab-ponte", expect.any(String));
    expect(toast.success).toHaveBeenCalledWith("Bilocale Ponte riattivato.");
  });

  it("spento prima di A6 (senza ora): «Disattiva» fa partire i 7 giorni; «Elimina» spento", async () => {
    await open([off({ disattivato_at: null, disattivato_da: null, eliminabile_dal: null })]);
    expect(screen.getByTestId("platform-apt-disabled-lab-ponte")).toHaveTextContent("Spento senza data: «Disattiva» fa partire i 7 giorni dopo i quali si può eliminare.");
    expect(screen.getByTestId("platform-apt-disable-lab-ponte")).toBeEnabled();
    expect(screen.getByTestId("platform-apt-delete-lab-ponte")).toBeDisabled();
  });

  it("dev: nessun «Elimina» (D-118)", async () => {
    await open([off({ apartment_id: "dev", origine: "dev", eliminabile_dal: null })]);
    expect(q("platform-apt-delete-dev")).toBeNull();
    expect(screen.getByTestId("platform-apt-reenable-dev")).toBeInTheDocument();
  });
});

describe("Elimina", () => {
  async function openDelete(a: PlatformApartment = off()) {
    await open([a]);
    await click(screen.getByTestId(`platform-apt-delete-${a.apartment_id}`));
    return screen.getByTestId("apt-delete-dialog");
  }
  const confirm = () => screen.getByTestId("apt-delete-confirm");
  const field = () => screen.getByTestId("apt-delete-name");

  it("creato dall'app: cosa si perde, cosa resta, l'id che non torna, l'email", async () => {
    const dialog = await openDelete();
    expect(dialog).toHaveTextContent("Eliminare «Bilocale Ponte»?");
    expect(dialog).toHaveTextContent("lab-ponte");
    expect(dialog).toHaveTextContent("Residenze Esempio");
    expect(dialog).toHaveTextContent("Si perdono il sistema domotico con i suoi dati e le credenziali dei dispositivi; l'appartamento sparisce dall'app per tutti i suoi utenti.");
    expect(dialog).toHaveTextContent("Restano prenotazioni e riepiloghi per 12 mesi e il registro dell'organizzazione per 24 mesi. Lo storico del sistema domotico si può recuperare per 30 giorni, con l'aiuto dell'assistenza HQE.");
    expect(dialog).toHaveTextContent("L'ID lab-ponte non si potrà più usare.");
    expect(dialog).toHaveTextContent("Gli amministratori dell'organizzazione e i gestori della piattaforma ricevono un'email.");
    expect(q("apt-delete-manual")).toBeNull();
  });

  it("si accende solo con il nome esatto: maiuscole comprese, spazi ai lati non contano", async () => {
    await openDelete();
    expect(field()).toHaveAccessibleName(/Scrivi il nome dell'appartamento per confermare/);
    expect(confirm()).toBeDisabled();
    type(field(), "bilocale ponte");
    expect(confirm()).toBeDisabled();
    type(field(), "Bilocale");
    expect(confirm()).toBeDisabled();
    type(field(), "  Bilocale Ponte ");
    expect(confirm()).toBeEnabled();
  });

  it("conferma: il nome scritto al server; parte, si dice, l'elenco si rilegge", async () => {
    await openDelete();
    type(field(), " Bilocale Ponte ");
    await click(confirm());
    expect(s.deleteApartment).toHaveBeenCalledWith("t-1", "lab-ponte", " Bilocale Ponte ", expect.any(String));
    expect(toast.success).toHaveBeenCalledWith("Eliminazione di Bilocale Ponte avviata: ci vogliono alcuni minuti.");
    expect(q("apt-delete-dialog")).toBeNull();
    await waitFor(() => expect(s.apartments).toHaveBeenCalledTimes(2));
  });

  it("collegato a mano: l'avviso del motore che resta; nessuno storico; tolto subito", async () => {
    s.deleteApartment.mockResolvedValue({ eliminazione: elim({ stato: "eliminato" }) });
    const dialog = await openDelete(off({ apartment_id: "lab-01", name: "Laboratorio", origine: "a_mano", creazione: null }));
    expect(screen.getByTestId("apt-delete-manual")).toHaveTextContent("Il sistema domotico sulla macchina virtuale resta: lo toglie a mano l'assistenza HQE.");
    expect(dialog).toHaveTextContent("L'appartamento sparisce dall'app per tutti i suoi utenti.");
    expect(dialog).toHaveTextContent("Restano prenotazioni e riepiloghi per 12 mesi e il registro dell'organizzazione per 24 mesi.");
    expect(dialog).not.toHaveTextContent("Lo storico");
    type(field(), "Laboratorio");
    await click(confirm());
    expect(toast.success).toHaveBeenCalledWith("Laboratorio eliminato.");
  });

  it("dimostrativo: nessun avviso del motore", async () => {
    await openDelete(off({ apartment_id: "apt-demo", name: "Demo", origine: "dimostrativo", instance_url: "mock://demo", creazione: null }));
    expect(q("apt-delete-manual")).toBeNull();
  });

  it("422 name_mismatch: la frase del server sotto il campo, la finestra resta", async () => {
    s.deleteApartment.mockRejectedValue(new ApiError(422, "name_mismatch", "Il nome non corrisponde", "c-1"));
    await openDelete();
    type(field(), "Bilocale Ponte");
    await click(confirm());
    expect(screen.getByTestId("apt-delete-name-error")).toHaveTextContent("Il nome non corrisponde");
    expect(screen.getByTestId("apt-delete-dialog")).toBeInTheDocument();
  });

  it("429: il limite di 2 al giorno e da quando si potrà", async () => {
    s.deleteApartment.mockRejectedValue(new ApiError(429, "rate_limited", "Troppe eliminazioni", "c-2", { riprova_dal: iso(Date.now() + 2 * DAY) }));
    await openDelete();
    type(field(), "Bilocale Ponte");
    await click(confirm());
    expect(screen.getByTestId("apt-delete-error")).toHaveTextContent(/^Limite raggiunto: si possono eliminare al massimo 2 appartamenti al giorno per ogni organizzazione\. Potrai eliminarne un altro dal \d\d\/\d\d alle \d\d:\d\d\.$/);
  });

  it("409 too_early: da quando si potrà", async () => {
    s.deleteApartment.mockRejectedValue(new ApiError(409, "too_early", "Troppo presto", "c-3", { eliminabile_dal: "2026-11-27T15:05:00Z" }));
    await openDelete();
    type(field(), "Bilocale Ponte");
    await click(confirm());
    expect(screen.getByTestId("apt-delete-error")).toHaveTextContent("Non ancora: si potrà eliminare dal 27 nov 2026, 16:05.");
  });

  it("altri rifiuti: la frase del server con l'ID richiesta", async () => {
    s.deleteApartment.mockRejectedValue(new ApiError(409, "deletion_in_progress", "Eliminazione già in corso", "c-4"));
    await openDelete();
    type(field(), "Bilocale Ponte");
    await click(confirm());
    expect(screen.getByTestId("apt-delete-error")).toHaveTextContent("Eliminazione già in corso");
    expect(screen.getByTestId("apt-delete-error-id")).toHaveTextContent("c-4");
  });
});

describe("la riga dell'eliminazione", () => {
  it("in corso: l'etichetta, i tre passi, chi l'ha avviata; nessun pulsante", async () => {
    await open([off({ eliminazione: elim() })]);
    const r = screen.getByTestId("platform-apt-lab-ponte");
    expect(r).toHaveAttribute("data-deletion", "in_corso");
    expect(within(r).getByTestId("deletion-state-lab-ponte")).toHaveTextContent("Eliminazione in corso");
    const steps = ["motore", "segreti", "database"].map((p) => within(r).getByTestId(`deletion-step-lab-ponte-${p}`));
    expect(steps.map((el) => el.getAttribute("data-state"))).toEqual(["fatto", "in_corso", "da_fare"]);
    expect(steps.map((el) => el.textContent)).toEqual([expect.stringContaining("1 · sistema domotico"), expect.stringContaining("2 · chiavi"), expect.stringContaining("3 · dati dell'app")]);
    expect(r).toHaveTextContent("Si tolgono il sistema domotico, le chiavi e i dati; poi l'appartamento sparisce dall'elenco. Puoi chiudere la pagina: l'eliminazione continua.");
    expect(r).toHaveTextContent("Avviata il 20 nov 2026, 16:50 da Giulia Rossi");
    expect(within(r).queryAllByRole("button", { name: /Riprova|Disattiva|Riattiva|Elimina|Verifica/ })).toHaveLength(0);
  });

  it("non riuscita: «Cosa è successo», il passo, l'ultimo tentativo, l'ID richiesta, «Riprova» con la version", async () => {
    const OP = "3f9c2a71-0000-4000-8000-000000000021";
    await open([off({ eliminazione: elim({ stato: "non_riuscita", passo: "segreti", codice: "chiavi_non_distrutte", messaggio: "Secrets not destroyed", version: 4, op: { op_id: OP, operazione: "togli_motore", stato: "fallito", codice: "x", messaggio: "x" } }) })]);
    const r = screen.getByTestId("platform-apt-lab-ponte");
    expect(within(r).getByTestId("deletion-state-lab-ponte")).toHaveTextContent("Eliminazione non riuscita");
    const box = within(r).getByTestId("deletion-what-lab-ponte");
    expect(box).toHaveTextContent("Cosa è successo");
    expect(box).toHaveTextContent("Il sistema domotico è stato tolto, ma le chiavi no: premi «Riprova».");
    expect(box).toHaveTextContent("Si è fermata a: chiavi (passo 2 di 3)");
    expect(box).toHaveTextContent("Ultimo tentativo: 20 nov 2026, 16:55, Giulia Rossi");
    expect(within(box).getByTestId("deletion-op-lab-ponte")).toHaveTextContent(OP.slice(0, 8));
    await click(within(r).getByTestId("deletion-retry-lab-ponte"));
    expect(s.retryDeletion).toHaveBeenCalledWith("t-1", "lab-ponte", 4, expect.any(String));
    await waitFor(() => expect(s.apartments).toHaveBeenCalledTimes(2));
  });

  it("«Riprova» rifiutato perché qualcuno ha appena cambiato: lo si dice e l'elenco si rilegge", async () => {
    s.retryDeletion.mockRejectedValue(new ApiError(409, "version_changed", "Cambiato", "c-5"));
    await open([off({ eliminazione: elim({ stato: "non_riuscita" }) })]);
    await click(screen.getByTestId("deletion-retry-lab-ponte"));
    expect(toast.info).toHaveBeenCalled();
    await waitFor(() => expect(s.apartments).toHaveBeenCalledTimes(2));
  });
});

describe("rilettura e avviso alla fine", () => {
  const wait = async (ms: number) => {
    for (let left = ms; left > 0; left -= 1_000) await act(async () => { await vi.advanceTimersByTimeAsync(Math.min(1_000, left)); });
  };
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("in corso: rilegge ogni 4 secondi; sparito dall'elenco, «‹nome› eliminato.» e la rilettura si ferma", async () => {
    const other = apt({ apartment_id: "lab-altro", name: "Altro" });
    s.apartments.mockResolvedValueOnce([off({ eliminazione: elim() }), other]).mockResolvedValueOnce([off({ eliminazione: elim({ passo: "database" }) }), other]).mockResolvedValue([other]);
    renderList();
    await screen.findByTestId("platform-apt-lab-ponte");
    await wait(4_000);
    expect(s.apartments).toHaveBeenCalledTimes(2);
    await wait(4_000);
    await waitFor(() => expect(screen.queryByTestId("platform-apt-lab-ponte")).toBeNull());
    expect(toast.success).toHaveBeenCalledWith("Bilocale Ponte eliminato.");
    const calls = s.apartments.mock.calls.length;
    await wait(12_000);
    expect(s.apartments).toHaveBeenCalledTimes(calls);
  });
});

// Usability reading (22 Nov, answers of the memoria): what stays on the walls (5.2), and the apartment's ID where the
// row has no request ID (8.1).
describe("testi dalla lettura di usabilità", () => {
  const DEVICES = "Gli Shelly restano montati e, per quanto sappiamo oggi, restano come sono in quel momento: se la caldaia è accesa, può restare accesa senza che nessuno la comandi. Prima di eliminare metti l'appartamento in «Casa vuota», oppure fai togliere gli Shelly.";

  it("«Elimina» di un appartamento creato dall'app: la riga gialla su Shelly e caldaia", async () => {
    await open([off()]);
    await click(screen.getByTestId("platform-apt-delete-lab-ponte"));
    expect(screen.getByTestId("apt-delete-devices")).toHaveTextContent(DEVICES);
  });

  it.each(["a_mano", "dimostrativo"] as const)("%s: niente riga (il sistema domotico resta, o non ci sono Shelly)", async (origine) => {
    await open([off({ origine, creazione: null })]);
    await click(screen.getByTestId("platform-apt-delete-lab-ponte"));
    expect(q("apt-delete-devices")).toBeNull();
    if (origine === "a_mano") expect(screen.getByTestId("apt-delete-manual")).toHaveTextContent("Il sistema domotico sulla macchina virtuale resta: lo toglie a mano l'assistenza HQE.");
  });

  it("eliminazione ferma senza un ordine dietro: l'ID dell'appartamento, con la sua etichetta, al posto dell'ID richiesta", async () => {
    await open([off({ eliminazione: elim({ stato: "non_riuscita", passo: "database", codice: "errore_interno", op: null }) })]);
    const box = screen.getByTestId("deletion-what-lab-ponte");
    expect(box).toHaveTextContent("Errore interno del server. Premi «Riprova»; se succede ancora, scrivi all'assistenza HQE con l'ID qui sotto.");
    expect(box).toHaveTextContent("ID dell'appartamento");
    expect(box).not.toHaveTextContent("ID richiesta");
    expect(within(box).getByTestId("deletion-apt-id-lab-ponte")).toHaveTextContent("lab-ponte");
    expect(q("deletion-op-lab-ponte")).toBeNull();
  });
});
