import { act, render } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { bffFetch } from "@/api/bff";
import { assetRefs } from "@/lib/appVersion";
import { browser } from "@/lib/lazyPage";
import { RETRY_MS, VersionWatcher } from "./VersionWatcher";

vi.mock("sonner", () => ({ toast: vi.fn() }));

// P-92 in the page: the checks start by themselves, the banner says «È disponibile una versione nuova» with
// «Aggiorna», and a change of page loads the newer version; never over something in use (review P1, P2, P4, P11).
const html = (entry: string) => `<script type="module" crossorigin src="/assets/${entry}"></script><link rel="stylesheet" href="/assets/index-AAA.css">`;
const OLD = assetRefs(html("index-OLD.js"));

let go: (to: string) => void = () => {};
function Nav() {
  go = useNavigate();
  return null;
}

function show(baseline: string) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <VersionWatcher baseline={baseline} />
      <Nav />
    </MemoryRouter>,
  );
}

let reload: ReturnType<typeof vi.spyOn>;
let site: { entry: string; fail: boolean };
let fetchMock: ReturnType<typeof vi.fn>;
/** Requests to the BFF stay on their way until the test answers them. */
let answerWrite: () => void = () => {};

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date", "performance"] });
  sessionStorage.clear();
  reload = vi.spyOn(browser, "reload").mockImplementation(() => {});
  site = { entry: "index-NEW.js", fail: false };
  fetchMock = vi.fn((input: RequestInfo | URL) => {
    if (String(input) === "/") return site.fail ? Promise.reject(new TypeError("Failed to fetch")) : Promise.resolve(new Response(html(site.entry), { status: 200 }));
    return new Promise<Response>((resolve) => {
      answerWrite = () => resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.mocked(toast).mockReset();
  document.body.innerHTML = "";
});

const advance = (ms: number) => act(async () => {
  await vi.advanceTimersByTimeAsync(ms);
});
const fire = (target: EventTarget, event: Event) => act(async () => {
  target.dispatchEvent(event);
});
const bannerAction = () => (vi.mocked(toast).mock.calls[0][1] as unknown as { action: { label: string; onClick: () => void } }).action;

function visibility(value: "visible" | "hidden") {
  Object.defineProperty(document, "visibilityState", { value, configurable: true });
}
afterEach(() => {
  delete (document as { visibilityState?: unknown }).visibilityState;
});

/** An hour in the background (no checks while hidden), a publication meanwhile, then back. */
async function backgroundAndBack() {
  visibility("hidden");
  await advance(60 * 60_000);
  site.entry = "index-NEWER.js";
  visibility("visible");
  await fire(document, new Event("visibilitychange"));
  await advance(0);
}

describe("VersionWatcher", () => {
  it("chiede index.html alla rete, mai alla cache del browser", async () => {
    show(OLD);
    await advance(2_000);
    expect(fetchMock).toHaveBeenCalledWith("/", expect.objectContaining({ cache: "no-store" }));
  });

  it("versione nuova appena aperta: ricarica da sola", async () => {
    show(OLD);
    await advance(2_000);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(toast).not.toHaveBeenCalled();
  });

  it("già in uso: l'avviso con «Aggiorna», poi il cambio di pagina carica la versione nuova", async () => {
    show(OLD);
    await fire(window, new Event("pointerdown"));
    await advance(2_000);
    expect(reload).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith("È disponibile una versione nuova", expect.objectContaining({ id: "new-version", duration: Infinity }));
    expect(bannerAction().label).toBe("Aggiorna");
    await act(async () => go("/impostazioni"));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("«Aggiorna» ricarica subito", async () => {
    show(OLD);
    await fire(window, new KeyboardEvent("keydown", { key: "a" }));
    await advance(2_000);
    bannerAction().onClick();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("ritorno dallo sfondo, pagina mai toccata: controlla subito e ricarica da sola", async () => {
    site.entry = "index-OLD.js";
    show(OLD);
    await advance(2_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await backgroundAndBack();
    expect(fetchMock).toHaveBeenCalledTimes(2); // nothing while hidden
    expect(reload).toHaveBeenCalledTimes(1);
    expect(toast).not.toHaveBeenCalled();
  });

  it("ritorno dallo sfondo dopo averla usata (P1): solo l'avviso, niente si perde", async () => {
    site.entry = "index-OLD.js";
    show(OLD);
    await advance(2_000);
    await fire(window, new Event("pointerdown")); // a switch changed in Regole, not saved
    await backgroundAndBack();
    expect(reload).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledTimes(1);
  });

  it("ritorno dallo sfondo con la rete non ancora pronta (P11): un nuovo tentativo dopo 2,5 secondi", async () => {
    site.entry = "index-OLD.js";
    show(OLD);
    await advance(2_000);
    site.fail = true;
    visibility("hidden");
    await advance(60 * 60_000);
    site.entry = "index-NEWER.js";
    visibility("visible");
    await fire(document, new Event("visibilitychange"));
    await advance(0);
    expect(reload).not.toHaveBeenCalled();
    site.fail = false;
    await advance(RETRY_MS);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("ritorno dalla cache avanti/indietro (pageshow persisted): come un ritorno dallo sfondo", async () => {
    site.entry = "index-OLD.js";
    show(OLD);
    await advance(2_000);
    await advance(60 * 60_000);
    site.entry = "index-NEWER.js";
    const shown = new Event("pageshow") as PageTransitionEvent;
    Object.defineProperty(shown, "persisted", { value: true });
    await fire(window, shown);
    await advance(0);
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("rete tornata (online): controlla; oltre i primi secondi, l'avviso", async () => {
    site.entry = "index-OLD.js";
    show(OLD);
    await advance(30_000);
    site.entry = "index-NEWER.js";
    await fire(window, new Event("online"));
    await advance(0);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(toast).toHaveBeenCalledTimes(1);
    expect(reload).not.toHaveBeenCalled();
  });

  it("finestra aperta sullo schermo (pageBusy vero): l'avviso al posto della ricarica", async () => {
    document.body.insertAdjacentHTML("beforeend", '<div role="dialog">Disattivare?</div>');
    show(OLD);
    await advance(2_000);
    expect(reload).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledTimes(1);
  });

  it("una modifica ancora in viaggio verso il server (P2): il cambio di pagina non ricarica finché non arriva la risposta", async () => {
    show(OLD);
    await fire(window, new Event("pointerdown"));
    await advance(2_000);
    let saved = false;
    void bffFetch("/app/admin/apartments/apt-1", { method: "PATCH", body: { name: "x" } }).then(() => {
      saved = true;
    });
    await advance(0);
    await act(async () => go("/impostazioni"));
    expect(reload).not.toHaveBeenCalled();
    answerWrite();
    await advance(0);
    expect(saved).toBe(true);
    await act(async () => go("/"));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("memoria della scheda che non funziona (P4): niente ricarica automatica, solo l'avviso", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    show(OLD);
    await advance(2_000);
    expect(reload).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledTimes(1);
  });

  it("nel sito di sviluppo: nessuna richiesta", async () => {
    show("");
    await advance(15 * 60_000);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
