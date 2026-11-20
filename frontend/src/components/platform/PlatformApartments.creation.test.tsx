import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import type { Creazione, PlatformApartment } from "@/api/platform";
import { PlatformApartments } from "./PlatformApartments";

// A2 in Organizzazioni > an organization > Appartamenti (docs/proposta-a2-sito.md §1, §3): «Nuovo appartamento» next to
// «Collega un sistema esistente», off before the click where the creation is not available (production until the second
// VM), and the rows of the creations in their three states.

const s = vi.hoisted(() => ({
  env: { app_env: "staging", instance_mode: "real", creazione_disponibile: true as boolean | undefined },
  apartments: vi.fn(),
  tenant: vi.fn(),
  createNew: vi.fn(),
  retryCreation: vi.fn(),
  cancelCreation: vi.fn(),
  credList: vi.fn(),
}));

vi.mock("@/api/platform", () => ({
  platformApi: { apartments: s.apartments, tenant: s.tenant, createNew: s.createNew, retryCreation: s.retryCreation, cancelCreation: s.cancelCreation },
}));
vi.mock("@/api/deviceCredentials", () => ({ credentialsApi: () => ({ list: s.credList }) }));
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ me: { env: s.env }, refreshMe: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const READY: PlatformApartment = { apartment_id: "apt-001", name: "Milano Centro", instance_url: "http://10.198.0.2:8101", port: null, enabled: true, timezone: "Europe/Rome", italianway_id: null, last_check: null, creazione: null };

function renderList() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>
        <PlatformApartments tenantId="t-1" tenantName="Residenze Esempio" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function open(items: PlatformApartment[] = [READY]) {
  s.apartments.mockResolvedValue(items);
  renderList();
  await screen.findByTestId(`platform-apt-${items[0].apartment_id}`);
}

const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

beforeEach(() => {
  vi.clearAllMocks();
  s.env = { app_env: "staging", instance_mode: "real", creazione_disponibile: true };
  s.credList.mockResolvedValue({ items: [] });
  s.retryCreation.mockResolvedValue({});
  s.cancelCreation.mockResolvedValue({});
  s.tenant.mockResolvedValue({ tenant_id: "t-1", name: "Residenze Esempio", created_at: "", first_admin: null, creazioni_ultima_ora: { usate: 0, limite: 5, libera_dal: null } });
});

describe("dove si crea (§1)", () => {
  it("due pulsanti: «Nuovo appartamento» principale e «Collega un sistema esistente» meno in evidenza", async () => {
    await open();
    const create = screen.getByTestId("platform-apt-new-btn-t-1");
    const link = screen.getByTestId("platform-apt-add-btn-t-1");
    expect(create).toHaveTextContent("Nuovo appartamento");
    expect(link).toHaveTextContent("Collega un sistema esistente");
    expect(create).toBeEnabled();
    expect(link.className).toMatch(/border/); // outline
    expect(screen.queryByTestId("platform-apt-new-unavailable-t-1")).toBeNull();
  });

  it("«Nuovo appartamento» apre il modulo della creazione; «Collega» quello di oggi", async () => {
    await open();
    await click(screen.getByTestId("platform-apt-new-btn-t-1"));
    expect(await screen.findByTestId("new-apt-dialog")).toBeInTheDocument();
    expect(screen.queryByTestId("platform-apt-create-dialog")).toBeNull();
  });

  it("il modulo di «Collega» ha il titolo nuovo", async () => {
    await open();
    await click(screen.getByTestId("platform-apt-add-btn-t-1"));
    expect(screen.getByTestId("platform-apt-create-dialog")).toHaveTextContent("Collega un sistema esistente a Residenze Esempio");
  });

  it("in produzione: «Nuovo appartamento» si vede ma è spento, con la riga della seconda macchina virtuale", async () => {
    s.env = { app_env: "prod", instance_mode: "real", creazione_disponibile: false };
    await open();
    expect(screen.getByTestId("platform-apt-new-btn-t-1")).toBeDisabled();
    expect(screen.getByTestId("platform-apt-new-unavailable-t-1")).toHaveTextContent("Non disponibile in produzione: arriverà con la seconda macchina virtuale.");
    expect(screen.getByTestId("platform-apt-add-btn-t-1")).toBeEnabled();
  });

  it("nello staging senza agente: spento, con la sua riga", async () => {
    s.env = { app_env: "staging", instance_mode: "real", creazione_disponibile: false };
    await open();
    expect(screen.getByTestId("platform-apt-new-btn-t-1")).toBeDisabled();
    expect(screen.getByTestId("platform-apt-new-unavailable-t-1")).toHaveTextContent("Non disponibile in questo ambiente: manca il collegamento con la macchina virtuale.");
  });

  it("un server che non manda il campo: acceso (il 503 resta come riserva dentro il modulo)", async () => {
    s.env = { app_env: "prod", instance_mode: "real", creazione_disponibile: undefined };
    await open();
    expect(screen.getByTestId("platform-apt-new-btn-t-1")).toBeEnabled();
  });
});

const creazione = (over: Partial<Creazione> = {}): Creazione => ({
  stato: "in_preparazione", passo: "motore", version: 3, porta: 8153, op: null, codice: null, messaggio: null, fatti: ["id", "porta", "segreti"], updated_at: "2026-11-19T16:21:00Z", updated_by: "Giulia Rossi", ...over,
});
const apt = (apartment_id: string, name: string, c: Creazione | null): PlatformApartment => ({ ...READY, apartment_id, name, instance_url: c ? "" : READY.instance_url, creazione: c });
const STOPPED = apt("lab-ponte", "Bilocale Ponte", creazione({ stato: "non_creato", passo: "motore", porta: 8152, version: 7, updated_at: "2026-11-19T16:05:00Z", codice: "motore_non_sano", messaggio: "Motore non sano", op: { op_id: "3f9c2a71-0000-4000-8000-000000000001", operazione: "crea_motore", stato: "fallito", codice: "motore_non_sano", messaggio: "Motore non sano" } }));
const PREPARING = apt("lab-giardino", "Trilocale Giardino", creazione());
const CANCELLING = apt("lab-via", "Bilocale Via", creazione({ stato: "annullamento_in_corso" }));
const CREATED = apt("lab-corte", "Monolocale Corte", creazione({ stato: "pronto", passo: "collegamento" }));
const row = (id: string) => screen.getByTestId(`platform-apt-${id}`);
const NOT_FOR_UNREADY = ["edit", "verify", "delete", "agent", "credentials-btn"];

describe("la riga dell'appartamento in creazione (§3)", () => {
  it("ordine: prima i non creati, poi in preparazione, poi gli altri", async () => {
    await open([READY, PREPARING, STOPPED]);
    const ids = [...document.querySelectorAll("li[data-creation]")].map((el) => el.getAttribute("data-testid"));
    expect(ids).toEqual(["platform-apt-lab-ponte", "platform-apt-lab-giardino", "platform-apt-apt-001"]);
  });

  it("in preparazione: etichetta, i cinque passi con fatto/in corso/da fare, chi l'ha avviata, la porta; nessun pulsante", async () => {
    await open([PREPARING]);
    const r = row("lab-giardino");
    expect(within(r).getByTestId("creation-state-lab-giardino")).toHaveTextContent("In preparazione");
    const steps = ["riserva", "segreti", "capienza", "motore", "collegamento"].map((p) => within(r).getByTestId(`creation-step-lab-giardino-${p}`));
    expect(steps.map((el) => el.getAttribute("data-state"))).toEqual(["fatto", "fatto", "fatto", "in_corso", "da_fare"]);
    expect(steps[3]).toHaveTextContent("4 · installazione del sistema domotico");
    expect(r).toHaveTextContent("Avviata il 19 nov 2026, 17:21 da Giulia Rossi · porta 8153");
    expect(r).toHaveTextContent("Puoi chiudere la pagina: la creazione va avanti anche senza di te.");
    for (const b of NOT_FOR_UNREADY) expect(screen.queryByTestId(`platform-apt-${b}-lab-giardino`)).toBeNull();
    expect(within(r).queryByRole("button", { name: /Riprova|Annulla/ })).toBeNull();
  });

  it("non creato: «Cosa è successo» con il testo del sito, il passo, id e porta riservati, ultimo tentativo e ID richiesta", async () => {
    await open([STOPPED]);
    const r = row("lab-ponte");
    expect(r).toHaveAttribute("data-creation", "non_creato");
    expect(within(r).getByTestId("creation-state-lab-ponte")).toHaveTextContent("Non creato");
    const box = within(r).getByTestId("creation-what-lab-ponte");
    expect(box).toHaveTextContent("Cosa è successo");
    expect(box).toHaveTextContent("Il sistema domotico non è partito: «Riprova», e se succede ancora serve un controllo.");
    expect(box).not.toHaveTextContent("Motore non sano");
    expect(box).toHaveTextContent("Si è fermata a: installazione del sistema domotico (passo 4 di 5)");
    expect(box).toHaveTextContent("L'id lab-ponte e la porta 8152 restano riservati finché non premi «Riprova» o «Annulla».");
    expect(box).toHaveTextContent("Ultimo tentativo: 19 nov 2026, 17:05, Giulia Rossi");
    expect(within(box).getByTestId("creation-op-lab-ponte")).toHaveTextContent("3f9c2a71");
    expect(within(r).getByTestId("creation-retry-lab-ponte")).toHaveTextContent("Riprova");
    expect(within(r).getByTestId("creation-cancel-lab-ponte")).toHaveTextContent("Annulla creazione");
    for (const b of NOT_FOR_UNREADY) expect(screen.queryByTestId(`platform-apt-${b}-lab-ponte`)).toBeNull();
  });

  it("l'id dell'appartamento intero e chiamato «ID», nelle righe in creazione e in quelle pronte", async () => {
    await open([STOPPED, apt("lab-giardino-panoramico", "Giardino", null)]);
    for (const id of ["lab-ponte", "lab-giardino-panoramico"]) {
      const el = screen.getByTestId(`platform-apt-id-${id}`);
      expect(el).toHaveTextContent(id);
      expect(el).toHaveAttribute("title", `ID: ${id}`);
    }
  });

  it("non creato con un codice che il sito non conosce: la frase del server", async () => {
    await open([apt("lab-x", "X", creazione({ stato: "non_creato", codice: "nuovo", messaggio: "Frase del server", op: { op_id: "op-1", operazione: "crea_motore", stato: "rifiutato", codice: "nuovo", messaggio: "Frase del server" } }))]);
    expect(screen.getByTestId("creation-what-lab-x")).toHaveTextContent("Frase del server");
  });

  it("annullamento in corso: etichetta, la frase, nessun pulsante di azione", async () => {
    await open([CANCELLING]);
    const r = row("lab-via");
    expect(within(r).getByTestId("creation-state-lab-via")).toHaveTextContent("Annullamento in corso");
    expect(r).toHaveTextContent("Si sta togliendo quello che era stato preparato; poi l'appartamento sparisce dall'elenco.");
    expect(within(r).queryByTestId("creation-retry-lab-via")).toBeNull();
    expect(within(r).queryByTestId("creation-cancel-lab-via")).toBeNull();
    for (const b of NOT_FOR_UNREADY) expect(screen.queryByTestId(`platform-apt-${b}-lab-via`)).toBeNull();
  });

  it("Riprova: subito, con la version; poi l'elenco si rilegge", async () => {
    await open([STOPPED]);
    await click(screen.getByTestId("creation-retry-lab-ponte"));
    expect(s.retryCreation).toHaveBeenCalledWith("t-1", "lab-ponte", 7, expect.any(String));
    await waitFor(() => expect(s.apartments).toHaveBeenCalledTimes(2));
  });

  it("Annulla creazione: chiede conferma con cosa si toglie; «Indietro» non fa niente", async () => {
    await open([STOPPED]);
    await click(screen.getByTestId("creation-cancel-lab-ponte"));
    const dlg = screen.getByTestId("creation-cancel-dialog");
    expect(dlg).toHaveTextContent("Annullare la creazione di Bilocale Ponte?");
    expect(dlg).toHaveTextContent("Togli tutto quello che è stato preparato per Bilocale Ponte: sistema domotico, accesso dei dispositivi e chiavi. L'id lab-ponte non si potrà più usare; la porta torna libera. Le chiavi si possono recuperare per 7 giorni.");
    await click(within(dlg).getByTestId("creation-cancel-back"));
    expect(screen.queryByTestId("creation-cancel-dialog")).toBeNull();
    expect(s.cancelCreation).not.toHaveBeenCalled();
    await click(screen.getByTestId("creation-cancel-lab-ponte"));
    await click(screen.getByTestId("creation-cancel-confirm"));
    expect(s.cancelCreation).toHaveBeenCalledWith("t-1", "lab-ponte", 7, expect.any(String));
    expect(screen.queryByTestId("creation-cancel-dialog")).toBeNull();
    await waitFor(() => expect(s.apartments).toHaveBeenCalledTimes(2));
  });

  it("Annulla quando sulla macchina virtuale non c'era niente: chiuso subito, l'avviso «annullata» una volta sola", async () => {
    s.cancelCreation.mockResolvedValue({ creazione: { stato: "annullato" } });
    await open([READY, STOPPED]);
    s.apartments.mockResolvedValue([READY]);
    await click(screen.getByTestId("creation-cancel-lab-ponte"));
    await click(screen.getByTestId("creation-cancel-confirm"));
    await waitFor(() => expect(screen.queryByTestId("platform-apt-lab-ponte")).toBeNull());
    expect(vi.mocked(toast.success).mock.calls.filter(([m]) => m === "Creazione di Bilocale Ponte annullata.")).toHaveLength(1);
  });

  it("Annulla che passa per «Annullamento in corso»: nessun avviso finché non sparisce", async () => {
    s.cancelCreation.mockResolvedValue({ creazione: creazione({ stato: "annullamento_in_corso", version: 8 }) });
    await open([STOPPED]);
    await click(screen.getByTestId("creation-cancel-lab-ponte"));
    await click(screen.getByTestId("creation-cancel-confirm"));
    expect(toast.success).not.toHaveBeenCalled();
  });

  it.each(["version_changed", "invalid_state"])("%s: «qualcuno ha appena cambiato» e l'elenco si rilegge da solo", async (code) => {
    s.retryCreation.mockRejectedValue(new ApiError(409, code, "x", "c-1"));
    await open([STOPPED]);
    await click(screen.getByTestId("creation-retry-lab-ponte"));
    expect(toast.info).toHaveBeenCalledWith("Qualcuno ha appena cambiato questa creazione: l'elenco è stato aggiornato.");
    expect(toast.error).not.toHaveBeenCalled();
    await waitFor(() => expect(s.apartments).toHaveBeenCalledTimes(2));
  });

  it("agent_publish_failed: la frase del server con l'ID richiesta dell'ordine", async () => {
    s.cancelCreation.mockRejectedValue(new ApiError(502, "agent_publish_failed", "Ordine non inviato", "c-1", { op: { op_id: "op-77" } }));
    await open([STOPPED]);
    await click(screen.getByTestId("creation-cancel-lab-ponte"));
    await click(screen.getByTestId("creation-cancel-confirm"));
    expect(toast.error).toHaveBeenCalledWith("Ordine non inviato", expect.objectContaining({ description: expect.anything() }));
  });
});

describe("pronto (§3.4)", () => {
  it("creato dall'app e nessuno Shelly registrato: verifica, agente, credenziali e l'invito", async () => {
    await open([CREATED]);
    const r = row("lab-corte");
    expect(await within(r).findByTestId("creation-ready-lab-corte")).toHaveTextContent("Pronto. Prossimi passi: registra gli Shelly e scrivi l'elenco dei dispositivi.");
    expect(within(r).getByTestId("platform-apt-verify-lab-corte")).toBeInTheDocument();
    expect(within(r).getByTestId("platform-apt-credentials-btn-lab-corte")).toBeInTheDocument();
  });

  it("creato dall'app, anche pronto: niente «Modifica collegamento» né «Elimina» (o1 1f7d4b0: 409 created_from_app; l'eliminazione con A6)", async () => {
    await open([CREATED, READY]);
    expect(screen.queryByTestId("platform-apt-edit-lab-corte")).toBeNull();
    expect(screen.queryByTestId("platform-apt-delete-lab-corte")).toBeNull();
    // an apartment connected by hand keeps them
    expect(screen.getByTestId("platform-apt-edit-apt-001")).toBeInTheDocument();
    expect(screen.getByTestId("platform-apt-delete-apt-001")).toBeInTheDocument();
  });

  it("in preparazione subito dopo «Riprova», senza ordine (op null): i passi giusti, nessun errore", async () => {
    await open([apt("lab-r", "R", creazione({ passo: "capienza", op: null }))]);
    expect(screen.getByTestId("creation-step-lab-r-capienza")).toHaveAttribute("data-state", "in_corso");
  });

  it("con almeno uno Shelly registrato: niente invito", async () => {
    s.credList.mockResolvedValue({ items: [{ device_id: "shellyplugmg3-3c4d5e6f7a8b", stato: "pronto" }] });
    await open([CREATED]);
    await waitFor(() => expect(s.credList).toHaveBeenCalled());
    expect(screen.queryByTestId("creation-ready-lab-corte")).toBeNull();
  });

  it("collegato a mano: nessun invito e nessuna lettura delle credenziali", async () => {
    await open([READY]);
    expect(screen.queryByTestId("creation-ready-apt-001")).toBeNull();
    expect(s.credList).not.toHaveBeenCalled();
  });
});

describe("rilettura e avvisi alla fine (§3.2, §3.3)", () => {
  const wait = async (ms: number) => {
    for (let left = ms; left > 0; left -= 1_000) await act(async () => { await vi.advanceTimersByTimeAsync(Math.min(1_000, left)); });
  };
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("in preparazione: rilegge ogni 4 secondi; arrivato a pronto, l'avviso «‹nome› è pronto.» e la rilettura si ferma", async () => {
    s.apartments.mockResolvedValueOnce([PREPARING]).mockResolvedValueOnce([PREPARING]).mockResolvedValue([{ ...PREPARING, creazione: creazione({ stato: "pronto", passo: "collegamento" }) }]);
    renderList();
    await screen.findByTestId("platform-apt-lab-giardino");
    expect(s.apartments).toHaveBeenCalledTimes(1);
    await wait(4_000);
    expect(s.apartments).toHaveBeenCalledTimes(2);
    await wait(4_000);
    expect(s.apartments).toHaveBeenCalledTimes(3);
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Trilocale Giardino è pronto."));
    await wait(12_000);
    expect(s.apartments).toHaveBeenCalledTimes(3);
  });

  it("annullamento in corso finché sparisce: l'avviso «Creazione di ‹nome› annullata.»", async () => {
    s.apartments.mockResolvedValueOnce([READY, CANCELLING]).mockResolvedValue([READY]);
    renderList();
    await screen.findByTestId("platform-apt-lab-via");
    await wait(4_000);
    await waitFor(() => expect(screen.queryByTestId("platform-apt-lab-via")).toBeNull());
    expect(toast.success).toHaveBeenCalledWith("Creazione di Bilocale Via annullata.");
  });

  it("senza niente in corso non rilegge", async () => {
    await open([READY, STOPPED]);
    await wait(12_000);
    expect(s.apartments).toHaveBeenCalledTimes(1);
  });

  it("al massimo 20 minuti", async () => {
    s.apartments.mockResolvedValue([PREPARING]);
    renderList();
    await screen.findByTestId("platform-apt-lab-giardino");
    await act(async () => { await vi.advanceTimersByTimeAsync(20 * 60_000 + 8_000); });
    const n = s.apartments.mock.calls.length;
    await wait(12_000);
    expect(s.apartments.mock.calls.length).toBe(n);
  });
});
