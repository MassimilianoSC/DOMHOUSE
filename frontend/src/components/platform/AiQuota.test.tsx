import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { toast } from "sonner";
import { ApiError } from "@/api/bff";
import type { AiQuotaView } from "@/api/platform";
import { fmtEuro, monthLabel, parseQuota } from "@/lib/aiQuota";
import { AiQuota } from "./AiQuota";

// F-13 (o1 59f3ba7) in an organisation's card: «Quota mensile dell'assistente (€)», the month's spending, empty and 0,
// and the server's limits in its 422 under the field.

const s = vi.hoisted(() => ({ aiQuota: vi.fn(), setAiQuota: vi.fn() }));
vi.mock("@/api/platform", () => ({ platformApi: { aiQuota: s.aiQuota, setAiQuota: s.setAiQuota } }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const VIEW = (over: Partial<AiQuotaView> = {}): AiQuotaView => ({ tenant_id: "t-1", quota_eur: null, month: "2026-11", spent_eur: 3.4, project_cap_eur: 20, project_spent_eur: 12.75, ...over });

async function show() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AiQuota tenantId="t-1" tenantName="Residenze Esempio" />
    </QueryClientProvider>,
  );
  return screen.findByTestId("tenant-ai-quota-t-1");
}
const input = () => screen.getByTestId("tenant-ai-quota-input-t-1") as HTMLInputElement;
const save = () => screen.getByTestId("tenant-ai-quota-save-t-1");
const click = (el: HTMLElement) => act(async () => {
  fireEvent.click(el);
});

beforeEach(() => {
  vi.clearAllMocks();
  s.setAiQuota.mockImplementation(async (_t: string, q: number | null) => VIEW({ quota_eur: q }));
});

describe("formati", () => {
  it("euro con due decimali, il mese per esteso, il campo letto all'italiana", () => {
    expect(fmtEuro(3.4)).toBe("3,40");
    expect(fmtEuro(0)).toBe("0,00");
    expect(monthLabel("2026-11")).toBe("novembre 2026");
    expect(monthLabel("strano")).toBe("strano");
    expect(parseQuota("")).toBeNull();
    expect(parseQuota(" 3,5 ")).toBe(3.5);
    expect(parseQuota("3.50")).toBe(3.5);
    expect(parseQuota("0")).toBe(0);
    expect(parseQuota("tre")).toBeUndefined();
    expect(parseQuota("-1")).toBeUndefined();
  });
});

describe("quota dell'assistente nella scheda dell'organizzazione (F-13)", () => {
  it("senza quota: campo vuoto, la spesa del mese e il tetto del progetto, cosa vuol dire vuoto e 0", async () => {
    s.aiQuota.mockResolvedValue(VIEW());
    const box = await show();
    expect(box).toHaveTextContent("Quota mensile dell'assistente (€)");
    expect(input()).toHaveAccessibleName("Quota mensile dell'assistente (€)");
    expect(input().value).toBe("");
    expect(box).toHaveTextContent("Speso a novembre 2026: 3,40 €. Senza quota vale il tetto del progetto: 20,00 € al mese per tutte le organizzazioni insieme, già spesi 12,75 €.");
    expect(box).toHaveTextContent("Vuoto: vale il tetto del progetto. 0: solo risposte rapide, l'assistente completo non si usa.");
    expect(save()).toBeDisabled();
  });

  it("con una quota: il campo la mostra, e la spesa è su quella quota", async () => {
    s.aiQuota.mockResolvedValue(VIEW({ quota_eur: 10 }));
    const box = await show();
    expect(input().value).toBe("10,00");
    expect(box).toHaveTextContent("Speso a novembre 2026: 3,40 € su 10,00 €.");
    expect(save()).toBeDisabled(); // unchanged
  });

  it("impostarla: «3,5» parte come 3.5, l'avviso verde e la riga nuova", async () => {
    s.aiQuota.mockResolvedValue(VIEW());
    const box = await show();
    fireEvent.change(input(), { target: { value: "3,5" } });
    await click(save());
    expect(s.setAiQuota).toHaveBeenCalledWith("t-1", 3.5, expect.any(String));
    expect(toast.success).toHaveBeenCalledWith("Quota dell'assistente di «Residenze Esempio» salvata: 3,50 € al mese.");
    expect(box).toHaveTextContent("Speso a novembre 2026: 3,40 € su 3,50 €.");
    expect(input().value).toBe("3,50");
  });

  it("0 è una quota: solo risposte rapide", async () => {
    s.aiQuota.mockResolvedValue(VIEW({ quota_eur: 10 }));
    await show();
    fireEvent.change(input(), { target: { value: "0" } });
    await click(save());
    expect(s.setAiQuota).toHaveBeenCalledWith("t-1", 0, expect.any(String));
    expect(toast.success).toHaveBeenCalledWith("Quota dell'assistente di «Residenze Esempio» salvata: 0,00 € al mese.");
  });

  it("toglierla: campo vuoto = tetto del progetto (null)", async () => {
    s.aiQuota.mockResolvedValue(VIEW({ quota_eur: 10 }));
    await show();
    fireEvent.change(input(), { target: { value: "" } });
    await click(save());
    expect(s.setAiQuota).toHaveBeenCalledWith("t-1", null, expect.any(String));
    expect(toast.success).toHaveBeenCalledWith("Quota dell'assistente di «Residenze Esempio» tolta: vale il tetto del progetto.");
  });

  it("un testo che non è un importo: «Salva» resta spento", async () => {
    s.aiQuota.mockResolvedValue(VIEW());
    await show();
    fireEvent.change(input(), { target: { value: "dieci" } });
    expect(save()).toBeDisabled();
  });

  it("fuori dai limiti del server: la sua frase sotto il campo, niente avviso rosso; sparisce scrivendo", async () => {
    const SENTENCE = "La quota deve essere un importo da 0 a 20,00 € (al massimo due decimali), oppure vuota per usare il tetto del progetto.";
    s.aiQuota.mockResolvedValue(VIEW());
    s.setAiQuota.mockRejectedValueOnce(new ApiError(422, "invalid_quota", SENTENCE, "c-1"));
    await show();
    fireEvent.change(input(), { target: { value: "25" } });
    await click(save());
    expect(screen.getByTestId("tenant-ai-quota-problem-t-1")).toHaveTextContent(SENTENCE);
    expect(input()).toHaveAttribute("aria-invalid", "true");
    expect(toast.error).not.toHaveBeenCalled();
    fireEvent.change(input(), { target: { value: "15" } });
    expect(screen.queryByTestId("tenant-ai-quota-problem-t-1")).toBeNull();
  });

  it("un altro errore: l'avviso rosso con l'ID richiesta", async () => {
    s.aiQuota.mockResolvedValue(VIEW());
    s.setAiQuota.mockRejectedValueOnce(new ApiError(404, "not_found", "Organizzazione inesistente", "c-2"));
    await show();
    fireEvent.change(input(), { target: { value: "5" } });
    await click(save());
    expect(toast.error).toHaveBeenCalledWith("Organizzazione inesistente", expect.anything());
    expect(screen.queryByTestId("tenant-ai-quota-problem-t-1")).toBeNull();
  });

  it("un server senza la quota (o un errore nel leggerla): il riquadro non c'è", async () => {
    s.aiQuota.mockRejectedValue(new ApiError(404, "not_found", "Not Found", "c-3"));
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <AiQuota tenantId="t-1" tenantName="Residenze Esempio" />
      </QueryClientProvider>,
    );
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    expect(screen.queryByTestId("tenant-ai-quota-t-1")).toBeNull();
  });
});
