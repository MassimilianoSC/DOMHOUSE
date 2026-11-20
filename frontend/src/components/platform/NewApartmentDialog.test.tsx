import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import { NewApartmentDialog } from "./NewApartmentDialog";

// A2, «Nuovo appartamento in ‹organizzazione›» (docs/proposta-a2-sito.md §2, §6.1): the id checked while typing, the
// limit of 5 creations an hour always in sight, and every refusal of «Crea» kept inside the form with what was written.

const s = vi.hoisted(() => ({
  appEnv: "staging",
  tenant: vi.fn(),
  createNew: vi.fn(),
}));

vi.mock("@/api/platform", () => ({ platformApi: { tenant: s.tenant, createNew: s.createNew } }));
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ me: { env: { app_env: s.appEnv, instance_mode: "real" } } }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const quota = (usate: number, libera_dal: string | null = null) => ({ tenant_id: "t-1", name: "Residenze Esempio", created_at: "2026-01-01T00:00:00Z", first_admin: null, creazioni_ultima_ora: { usate, limite: 5, libera_dal } });
const created = { apartment: { apartment_id: "lab-prova" }, creazione: { stato: "in_preparazione" } };
const onClose = vi.fn();
const onCreated = vi.fn();

async function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <NewApartmentDialog tenantId="t-1" tenantName="Residenze Esempio" onClose={onClose} onCreated={onCreated} />
    </QueryClientProvider>,
  );
  await screen.findByTestId("new-apt-dialog");
}

const type = (testId: string, value: string) => fireEvent.change(screen.getByTestId(testId), { target: { value } });
const fill = (id = "lab-prova", name = "Laboratorio di prova") => {
  type("apt-form-apartment_id", id);
  type("apt-form-name", name);
};
const save = () => act(async () => {
  fireEvent.click(screen.getByTestId("new-apt-save"));
});
const limit = () => screen.getByTestId("new-apt-limit");

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-20T15:00:00Z")); // 16:00 a Roma
  s.appEnv = "staging";
  s.tenant.mockResolvedValue(quota(2));
  s.createNew.mockResolvedValue(created);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("i campi (§2.1)", () => {
  it("titolo con l'organizzazione, riga su cosa aspettarsi, fuso già scritto, testi sotto id e codice Italianway", async () => {
    await open();
    expect(screen.getByText("Nuovo appartamento in Residenze Esempio")).toBeInTheDocument();
    expect(screen.getByText(/Ci vogliono alcuni minuti/)).toBeInTheDocument();
    expect(screen.getByTestId("apt-form-timezone")).toHaveValue("Europe/Rome");
    expect(screen.getByText("Nello staging comincia con lab- o test-; lettere minuscole, cifre e trattini. Non si cambia più.")).toBeInTheDocument();
    expect(screen.getByText("Si può aggiungere anche dopo.")).toBeInTheDocument();
    // no address or port: the server chooses them
    expect(screen.queryByTestId("apt-form-instance_url")).toBeNull();
    expect(screen.queryByTestId("apt-form-port")).toBeNull();
  });

  it("«Crea» acceso solo con id valido e nome scritto; l'id sbagliato si dice mentre si scrive", async () => {
    await open();
    const btn = screen.getByTestId("new-apt-save");
    expect(btn).toBeDisabled();
    type("apt-form-apartment_id", "apt-001");
    expect(screen.getByTestId("new-apt-id-problem")).toHaveTextContent("Id non valido: nello staging lab-… o test-…");
    type("apt-form-name", "Prova");
    expect(btn).toBeDisabled();
    type("apt-form-apartment_id", "lab-prova");
    expect(screen.queryByTestId("new-apt-id-problem")).toBeNull();
    expect(btn).toBeEnabled();
    type("apt-form-name", "   ");
    expect(btn).toBeDisabled();
  });

  it("il nome si ferma a 80 caratteri", async () => {
    await open();
    expect(screen.getByTestId("apt-form-name")).toHaveAttribute("maxLength", "80");
  });

  it("Crea manda id, nome, fuso e codice (vuoto = null), poi chiude e dice che è partita", async () => {
    await open();
    fill(" lab-prova ", " Laboratorio di prova ");
    await save();
    expect(s.createNew).toHaveBeenCalledWith("t-1", { apartment_id: "lab-prova", name: "Laboratorio di prova", timezone: "Europe/Rome", italianway_id: null }, expect.any(String));
    expect(toast.success).toHaveBeenCalledWith("Creazione di Laboratorio di prova avviata: ci vogliono alcuni minuti.");
    expect(onCreated).toHaveBeenCalledWith(created);
    expect(onClose).toHaveBeenCalled();
  });
});

describe("il limite di 5 creazioni l'ora (§2.2)", () => {
  it("sotto il limite: il riquadro dice il limite e il conto dell'ultima ora", async () => {
    await open();
    await waitFor(() => expect(limit()).toHaveTextContent("Si possono creare al massimo 5 appartamenti all'ora per ogni organizzazione. Nell'ultima ora: 2 su 5."));
    expect(limit()).toHaveAttribute("data-reached", "false");
  });

  it("finché il conto non arriva (o un server vecchio non lo manda): il limite senza il conto", async () => {
    s.tenant.mockResolvedValue({ tenant_id: "t-1", name: "Residenze Esempio", created_at: "", first_admin: null });
    await open();
    await waitFor(() => expect(s.tenant).toHaveBeenCalled());
    expect(limit()).toHaveTextContent("Si possono creare al massimo 5 appartamenti all'ora per ogni organizzazione.");
    expect(limit()).not.toHaveTextContent("Nell'ultima ora");
  });

  it("raggiunto all'apertura: riquadro giallo, «Crea» spento, l'ora del server a Roma", async () => {
    s.tenant.mockResolvedValue(quota(5, "2026-11-20T16:42:00Z"));
    await open();
    await waitFor(() => expect(limit()).toHaveAttribute("data-reached", "true"));
    expect(limit()).toHaveTextContent("Limite raggiunto: questa organizzazione ha già creato 5 appartamenti nell'ultima ora. Potrai crearne un altro dalle 17:42.");
    expect(limit().className).toMatch(/warning/);
    fill();
    expect(screen.getByTestId("new-apt-save")).toBeDisabled();
  });

  it("raggiunto, con l'ora di un altro giorno: con la data", async () => {
    s.tenant.mockResolvedValue(quota(5, "2026-11-20T23:12:00Z"));
    await open();
    await waitFor(() => expect(limit()).toHaveTextContent("Potrai crearne un altro dal 21/11 alle 00:12."));
  });

  it("429 al clic: lo stesso testo nel riquadro, il modulo resta aperto con i dati scritti, nessun avviso che sparisce", async () => {
    s.createNew.mockRejectedValue(new ApiError(429, "rate_limited", "Troppe operazioni in poco tempo", "c-1", { limite: 5, riprova_dal: "2026-11-20T16:42:00Z" }));
    await open();
    fill();
    await save();
    expect(limit()).toHaveTextContent("Limite raggiunto: questa organizzazione ha già creato 5 appartamenti nell'ultima ora. Potrai crearne un altro dalle 17:42.");
    expect(limit()).toHaveAttribute("data-reached", "true");
    expect(screen.getByTestId("apt-form-apartment_id")).toHaveValue("lab-prova");
    expect(screen.getByTestId("new-apt-save")).toBeDisabled();
    expect(onClose).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
    expect(screen.queryByText("Troppe operazioni in poco tempo")).toBeNull();
  });

  it("429 senza ora: il limite e «Riprova più tardi», mai la frase generica da sola", async () => {
    s.createNew.mockRejectedValue(new ApiError(429, "rate_limited", "Troppe operazioni in poco tempo", "c-1"));
    await open();
    fill();
    await save();
    expect(limit()).toHaveTextContent("Limite raggiunto: si possono creare al massimo 5 appartamenti all'ora per ogni organizzazione. Riprova più tardi.");
    expect(screen.queryByText("Troppe operazioni in poco tempo")).toBeNull();
  });
});

describe("gli altri rifiuti di «Crea» restano nel modulo (§6.1)", () => {
  async function refuse(err: ApiError) {
    s.createNew.mockRejectedValue(err);
    await open();
    fill();
    await save();
    expect(onClose).not.toHaveBeenCalled();
    expect(toast.error).not.toHaveBeenCalled();
  }

  it("invalid_apartment_id e already_exists: sotto il campo Id, con il testo del sito; sparisce quando l'id cambia", async () => {
    await refuse(new ApiError(409, "already_exists", "Identificativo non disponibile", "c-1"));
    expect(screen.getByTestId("new-apt-id-problem")).toHaveTextContent("Identificativo non disponibile: è già usato, o lo è stato.");
    type("apt-form-apartment_id", "lab-altro");
    expect(screen.queryByTestId("new-apt-id-problem")).toBeNull();
  });

  it("invalid_apartment_id: il testo del sito sotto il campo Id", async () => {
    await refuse(new ApiError(422, "invalid_apartment_id", "invalid", "c-1"));
    expect(screen.getByTestId("new-apt-id-problem")).toHaveTextContent("Id non valido: nello staging lab-… o test-…, lettere minuscole, cifre e trattini.");
  });

  it("external_id_in_use: la frase del server sotto il codice Italianway", async () => {
    await refuse(new ApiError(409, "external_id_in_use", "Codice Italianway già usato da un altro appartamento", "c-1"));
    expect(screen.getByTestId("new-apt-italianway-problem")).toHaveTextContent("Codice Italianway già usato da un altro appartamento");
  });

  it("no_free_port: nel riquadro rosso, con il testo del sito", async () => {
    await refuse(new ApiError(409, "no_free_port", "fascia piena", "c-1"));
    expect(screen.getByTestId("new-apt-error")).toHaveTextContent("Non c'è più posto per un nuovo sistema domotico in questo ambiente.");
  });

  it("secret_conflict: il testo del sito con l'ID richiesta da copiare", async () => {
    await refuse(new ApiError(409, "secret_conflict", "segreto", "corr-77"));
    expect(screen.getByTestId("new-apt-error")).toHaveTextContent("C'è già una chiave con questo nome, creata fuori dall'app: scegli un altro ID.");
    expect(screen.getByTestId("new-apt-error-id")).toHaveTextContent("corr-77");
  });

  it("agent_publish_failed: la frase del server con l'ID richiesta dell'ordine", async () => {
    await refuse(new ApiError(502, "agent_publish_failed", "Ordine non inviato all'agente", "corr-1", { op: { op_id: "op-9" } }));
    expect(screen.getByTestId("new-apt-error")).toHaveTextContent("Ordine non inviato all'agente");
    expect(screen.getByTestId("new-apt-error-id")).toHaveTextContent("op-9");
  });

  it("agent_not_configured in produzione: la riga della seconda macchina virtuale", async () => {
    s.appEnv = "prod";
    await refuse(new ApiError(503, "agent_not_configured", "Agente non configurato", "c-1"));
    expect(screen.getByTestId("new-apt-error")).toHaveTextContent("Non disponibile in produzione: arriverà con la seconda macchina virtuale.");
  });

  it("agent_not_configured nello staging: la frase del server", async () => {
    await refuse(new ApiError(503, "agent_not_configured", "Agente non configurato", "c-1"));
    expect(screen.getByTestId("new-apt-error")).toHaveTextContent("Agente non configurato");
  });

  it("server irraggiungibile: la frase con l'ID richiesta, i dati restano", async () => {
    await refuse(new ApiError(0, "network", "Server non raggiungibile", "corr-5"));
    expect(screen.getByTestId("new-apt-error")).toHaveTextContent("Server non raggiungibile");
    expect(screen.getByTestId("apt-form-name")).toHaveValue("Laboratorio di prova");
  });

  it("un nuovo tentativo toglie il riquadro rosso di prima", async () => {
    await refuse(new ApiError(409, "no_free_port", "fascia piena", "c-1"));
    s.createNew.mockResolvedValue(created);
    await save();
    expect(onClose).toHaveBeenCalled();
  });
});
