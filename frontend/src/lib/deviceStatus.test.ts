import { adviceFor, fmtElapsed, isSensor, sortForDiagnosis, statusOf, statusText } from "./deviceStatus";

// «Stato dei dispositivi», first step (activation by the client §5): never connected = offline with no last_seen
// (o1, 15 Nov: the engine keeps the saved last_seen across restarts and catalog changes, D12), offline for how long,
// and what to check, different for a 230 V Shelly and for a battery sensor behind its bridge.
const NOW = Date.parse("2026-11-15T10:00:00.000Z");
const ago = (min: number) => new Date(NOW - min * 60_000).toISOString();
const relay = { switch: { on: false } };
const sensor = { contact: { open: false, since: null } };
const dev = (label: string, online: boolean, last_seen: string | null, capabilities: object = relay) => ({ device_id: label, label, room_id: "r", online, last_seen, capabilities }) as never;
const UP = { connectorDown: false };

describe("stato di un dispositivo", () => {
  it.each([
    [true, ago(1), "online"],
    [true, null, "online"],          // online wins even before a first last_seen
    [false, ago(120), "offline"],
    [false, null, "never"],
  ])("in linea %s, last_seen %s: %s", (online, last, status) => {
    expect(statusOf({ online, last_seen: last })).toBe(status);
  });

  it("sensore a batteria: solo letture; con relè, misuratore, clima o caldaia non lo è", () => {
    expect(isSensor({ capabilities: { contact: { open: false, since: null } } } as never)).toBe(true);
    expect(isSensor({ capabilities: { temperature: { celsius: 20 }, humidity: { percent: 50 } } } as never)).toBe(true);
    for (const c of [{ switch: {} }, { power_meter: {} }, { climate: {} }, { heating: {} }]) expect(isSensor({ capabilities: c } as never)).toBe(false);
  });

  it.each([
    [0, "meno di un minuto"], [0.9, "meno di un minuto"], [1, "1 minuto"], [59, "59 minuti"], [60, "1 ora"], [119, "1 ora"],
    [120, "2 ore"], [24 * 60 - 1, "23 ore"], [24 * 60, "1 giorno"], [3 * 24 * 60 + 5, "3 giorni"], [-5, "meno di un minuto"],
  ])("da quanto: %s minuti → «%s»", (min, text) => {
    expect(fmtElapsed(min * 60_000)).toBe(text);
  });

  it("i testi dello stato", () => {
    expect(statusText(dev("a", true, ago(1)), NOW)).toBe("In linea");
    expect(statusText(dev("a", false, ago(125)), NOW)).toBe("Offline da 2 ore");
    expect(statusText(dev("a", false, null), NOW)).toBe("Mai collegato");
  });
});

describe("cosa fare", () => {
  it("in linea: niente", () => {
    expect(adviceFor(dev("a", true, ago(1)), UP)).toBeNull();
    expect(adviceFor(dev("a", true, ago(1)), { connectorDown: true })).toBeNull();
  });

  it.each([
    ["mai collegato, Shelly", dev("a", false, null), "Non si è mai collegato. Controlla che abbia corrente, che sia collegato al Wi-Fi dell'appartamento e che le impostazioni del broker sul dispositivo siano giuste."],
    ["mai collegato, sensore", dev("a", false, null, sensor), "Non si è mai fatto sentire. Controlla che abbia la batteria, che sia abbinato al suo ponte e che non sia troppo lontano dal ponte."],
    ["offline, Shelly", dev("a", false, ago(30)), "Prima funzionava, ora non risponde. Controlla che abbia corrente e che il Wi-Fi dell'appartamento funzioni."],
    ["offline, sensore", dev("a", false, ago(30), sensor), "Prima funzionava, ora non manda più letture. Controlla la batteria e che il ponte sia acceso e in linea."],
  ])("%s", (_case, d, text) => {
    expect(adviceFor(d, UP)).toBe(text);
  });

  it("collegamento ai dispositivi fermo: non è un problema del singolo dispositivo", () => {
    const text = "Non è un problema di questo dispositivo: il sistema domotico non riceve notizie da nessun dispositivo.";
    expect(adviceFor(dev("a", false, null), { connectorDown: true })).toBe(text);
    expect(adviceFor(dev("a", false, ago(30), sensor), { connectorDown: true })).toBe(text);
  });
});

it("ordine: prima i mai collegati, poi gli offline, poi quelli in linea; dentro, per stanza e nome", () => {
  const rooms: Record<string, string> = { a: "Soggiorno", b: "Camera", c: "Bagno", d: "Camera", e: "Soggiorno" };
  const list = [dev("a", true, ago(1)), dev("b", false, ago(5)), dev("c", false, null), dev("d", true, ago(1)), dev("e", false, null)];
  expect(sortForDiagnosis(list, (d: { label: string }) => rooms[d.label]).map((d: { label: string }) => d.label)).toEqual(["c", "e", "b", "d", "a"]);
});
