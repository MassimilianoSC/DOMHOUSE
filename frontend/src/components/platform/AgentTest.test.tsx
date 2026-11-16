import { act, fireEvent, render, screen } from "@testing-library/react";
import { ApiError } from "@/api/bff";
import type { AgentOp } from "@/api/platform";
import { AgentTest, agentTestable } from "./AgentTest";

// «Prova l'agente» (strumento A, A1; o1 448a71a): on the row of a staging apartment the platform sends the order
// «stato» to the agent on the VM, reads the operation again every 4 s while it is «inviato», and shows the outcome.
// Texts approved by the memoria storica (16 Nov). After 20 minutes it stops: the server then says «tempo_scaduto».
const s = vi.hoisted(() => ({ agentTest: vi.fn(), agentOp: vi.fn() }));
vi.mock("@/api/platform", () => ({ platformApi: { agentTest: s.agentTest, agentOp: s.agentOp } }));

const op = (over: Partial<AgentOp>): AgentOp => ({
  op_id: "op-123", operazione: "stato", apartment_id: "lab-01", seq: 1, stato: "inviato", codice: null,
  messaggio: "Ordine inviato all'agente sulla VM, in attesa della risposta", dati: null, creato_at: "2026-11-16T17:00:00Z", finito_at: null, ...over,
});
const OK = op({ stato: "riuscito", codice: "ok", messaggio: "Fatto", dati: { health: 200, stato: "ok", connector: "up", immagine: "europe-west8-docker.pkg.dev/x/engine:247fda0" } });

const box = () => screen.getByTestId("agent-test-lab-01");
const press = () => act(async () => { fireEvent.click(screen.getByTestId("agent-test-btn-lab-01")); });
// React schedules the next reading after each render: time goes on in steps, one render (act) per step
const wait = async (ms: number) => {
  for (let left = ms; left > 0; left -= 1_000) await act(async () => { await vi.advanceTimersByTimeAsync(Math.min(1_000, left)); });
};

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});
afterEach(() => vi.useRealTimers());

describe("Prova l'agente", () => {
  it.each([["lab-01", true], ["test-a", true], ["dev", true], ["apt-001", false], ["laboratorio", false], ["devx", false]])("%s ammesso: %s", (id, ok) => {
    expect(agentTestable(id)).toBe(ok);
  });

  it("in attesa il messaggio del server; rilegge ogni 4 secondi; riuscito: motore, collegamento ai dispositivi e versione", async () => {
    s.agentTest.mockResolvedValue(op({}));
    s.agentOp.mockResolvedValueOnce(op({})).mockResolvedValueOnce(OK);
    render(<AgentTest apartmentId="lab-01" />);
    expect(screen.getByTestId("agent-test-btn-lab-01")).toHaveTextContent("Prova l'agente");
    await press();
    expect(box()).toHaveTextContent("Ordine inviato all'agente sulla VM, in attesa della risposta");
    expect(screen.getByTestId("agent-test-btn-lab-01")).toBeDisabled();
    await wait(3_900);
    expect(s.agentOp).not.toHaveBeenCalled();
    await wait(100);
    expect(s.agentOp).toHaveBeenCalledTimes(1);
    expect(s.agentOp).toHaveBeenCalledWith("op-123");
    await wait(4_000);
    expect(s.agentOp).toHaveBeenCalledTimes(2);
    expect(box()).toHaveAttribute("data-state", "riuscito");
    expect(box()).toHaveTextContent(/^Agente raggiungibile\. Motore: sano · collegamento ai dispositivi: attivo · versione: 247fda0$/);
    await wait(20_000);
    expect(s.agentOp).toHaveBeenCalledTimes(2);   // finished: no more reading
    expect(screen.getByTestId("agent-test-btn-lab-01")).not.toBeDisabled();
  });

  it("riuscito con il motore che non risponde e il collegamento fermo; senza versione", async () => {
    s.agentTest.mockResolvedValue(op({ stato: "riuscito", codice: "ok", messaggio: "Fatto", dati: { health: 0, connector: "down" } }));
    render(<AgentTest apartmentId="lab-01" />);
    await press();
    expect(box()).toHaveTextContent(/^Agente raggiungibile\. Motore: non risponde · collegamento ai dispositivi: fermo$/);
    expect(s.agentOp).not.toHaveBeenCalled();
  });

  it("rifiutato, scartato o fallito: il messaggio del server in rosso, con il codice dell'operazione da copiare", async () => {
    s.agentTest.mockResolvedValue(op({}));
    s.agentOp.mockResolvedValue(op({ stato: "rifiutato", codice: "motore_assente", messaggio: "Il motore di questo appartamento non c'è sulla VM" }));
    render(<AgentTest apartmentId="lab-01" />);
    await press();
    await wait(4_000);
    expect(box()).toHaveAttribute("data-state", "rifiutato");
    expect(box()).toHaveTextContent("Il motore di questo appartamento non c'è sulla VM");
    expect(box().className).toContain("text-destructive");
    expect(screen.getByTestId("agent-test-id-lab-01")).toHaveAttribute("data-correlation-id", "op-123");
  });

  it("dopo 20 minuti in attesa smette di rileggere e mostra il messaggio del server per «tempo_scaduto»", async () => {
    s.agentTest.mockResolvedValue(op({}));
    let reads = 0;
    s.agentOp.mockImplementation(async () => {
      reads += 1;
      // the server expires the operation when it is read after 20 minutes
      return reads * 4_000 >= 20 * 60_000 ? op({ stato: "fallito", codice: "tempo_scaduto", messaggio: "Nessuna risposta dall'agente entro 20 minuti: riprova" }) : op({});
    });
    render(<AgentTest apartmentId="lab-01" />);
    await press();
    await wait(20 * 60_000 + 4_000);
    expect(box()).toHaveTextContent("Nessuna risposta dall'agente entro 20 minuti: riprova");
    const total = s.agentOp.mock.calls.length;
    await wait(60_000);
    expect(s.agentOp.mock.calls.length).toBe(total);
  });

  it("anche se il server non l'avesse ancora chiusa, dopo 20 minuti smette comunque", async () => {
    s.agentTest.mockResolvedValue(op({}));
    s.agentOp.mockResolvedValue(op({}));
    render(<AgentTest apartmentId="lab-01" />);
    await press();
    await wait(20 * 60_000 + 8_000);
    const total = s.agentOp.mock.calls.length;
    expect(total).toBeLessThanOrEqual(301);
    await wait(60_000);
    expect(s.agentOp.mock.calls.length).toBe(total);
    expect(screen.getByTestId("agent-test-btn-lab-01")).not.toBeDisabled();
  });

  it("ambiente senza agente (503): «Agente non ancora installato in questo ambiente.»", async () => {
    s.agentTest.mockRejectedValue(new ApiError(503, "agent_not_configured", "Agente non configurato", "c-1"));
    render(<AgentTest apartmentId="lab-01" />);
    await press();
    expect(box()).toHaveTextContent(/^Agente non ancora installato in questo ambiente\.$/);
    expect(box()).toHaveAttribute("data-state", "not-configured");
  });

  it("altro errore della richiesta (502): il messaggio del server e il codice della richiesta da copiare", async () => {
    s.agentTest.mockRejectedValue(new ApiError(502, "agent_publish_failed", "Ordine non inviato all'agente", "c0ffee00-1111-2222-3333-444455556666"));
    render(<AgentTest apartmentId="lab-01" />);
    await press();
    expect(box()).toHaveTextContent("Ordine non inviato all'agente");
    expect(box().className).toContain("text-destructive");
    expect(screen.getByTestId("agent-test-id-lab-01")).toHaveAttribute("data-correlation-id", "c0ffee00-1111-2222-3333-444455556666");
  });

  it("chiuso prima della risposta (si cambia pagina): non rilegge più", async () => {
    s.agentTest.mockResolvedValue(op({}));
    s.agentOp.mockResolvedValue(op({}));
    const { unmount } = render(<AgentTest apartmentId="lab-01" />);
    await press();
    unmount();
    await wait(60_000);
    expect(s.agentOp).not.toHaveBeenCalled();
  });
});
