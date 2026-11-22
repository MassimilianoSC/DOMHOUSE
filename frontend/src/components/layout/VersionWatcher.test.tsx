import { act, render } from "@testing-library/react";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { assetRefs } from "@/lib/appVersion";
import { browser } from "@/lib/lazyPage";
import { VersionWatcher } from "./VersionWatcher";

vi.mock("sonner", () => ({ toast: vi.fn() }));

// P-92 in the page: the checks start by themselves, the banner says «È disponibile una versione nuova» with
// «Aggiorna», and a change of page loads the newer version.
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
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  sessionStorage.clear();
  reload = vi.spyOn(browser, "reload").mockImplementation(() => {});
  fetchMock = vi.fn(async () => new Response(html("index-NEW.js"), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.mocked(toast).mockReset();
});

const advance = (ms: number) => act(async () => {
  await vi.advanceTimersByTimeAsync(ms);
});

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
    await act(async () => {
      window.dispatchEvent(new Event("pointerdown"));
    });
    await advance(2_000);
    expect(reload).not.toHaveBeenCalled();
    expect(toast).toHaveBeenCalledWith("È disponibile una versione nuova", expect.objectContaining({ id: "new-version", duration: Infinity }));
    const options = vi.mocked(toast).mock.calls[0][1] as unknown as { action: { label: string; onClick: () => void } };
    expect(options.action.label).toBe("Aggiorna");
    await act(async () => go("/impostazioni"));
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("«Aggiorna» ricarica subito", async () => {
    show(OLD);
    await act(async () => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "a" }));
    });
    await advance(2_000);
    const options = vi.mocked(toast).mock.calls[0][1] as unknown as { action: { onClick: () => void } };
    options.action.onClick();
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it("ritorno dallo sfondo: controlla subito e ricarica da sola", async () => {
    fetchMock.mockImplementation(async () => new Response(html("index-OLD.js")));
    show(OLD);
    await advance(2_000);
    expect(reload).not.toHaveBeenCalled();
    window.dispatchEvent(new Event("pointerdown"));
    // to the background for an hour: no checks while hidden; meanwhile a publication
    const visibility = (value: "visible" | "hidden") => Object.defineProperty(document, "visibilityState", { value, configurable: true });
    visibility("hidden");
    fetchMock.mockImplementation(async () => new Response(html("index-NEW.js")));
    try {
      await advance(60 * 60_000);
      expect(fetchMock).toHaveBeenCalledTimes(1);
      visibility("visible");
      await act(async () => {
        document.dispatchEvent(new Event("visibilitychange"));
      });
      await advance(0);
      expect(reload).toHaveBeenCalledTimes(1);
      expect(toast).not.toHaveBeenCalled();
    } finally {
      delete (document as { visibilityState?: unknown }).visibilityState;
    }
  });

  it("nel sito di sviluppo: nessuna richiesta", async () => {
    show("");
    await advance(15 * 60_000);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
