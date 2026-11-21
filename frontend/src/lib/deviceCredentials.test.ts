// @vitest-environment node
import type { DeviceCredential } from "@/api/deviceCredentials";
import { allowedActions, credentialsSignature, deviceIdProblem, inProgress, POLL_MS, MAX_POLL_MS, refusalNote, splitCredentials } from "./deviceCredentials";

// A3, device credentials (docs/proposta-a3-sito.md §3, docs/proposta-a3-server.md §4.3): what the site may offer for
// each state, how the list is ordered, the device code rule, and when the page reads the list again.

const cred = (device_id: string, stato: DeviceCredential["stato"], azione: DeviceCredential["azione"] = null): DeviceCredential => ({
  device_id,
  name: null,
  stato,
  version: 1,
  updated_at: "2026-11-19T15:00:00Z",
  updated_by: "Giulia Rossi",
  azione,
  engine_device_id: null,
  op: null,
  connection: { server: "mqtt.example.test:8883", ssl_ca: "ca.pem", client_id: `lab-prova.${device_id}`, user: `lab-prova.${device_id}`, topic_prefix: `lab-prova/${device_id}` },
});

describe("azioni ammesse per stato (tabella §4.3 del server)", () => {
  it.each([
    ["in_attesa", null, ["rigenera", "revoca"]],
    ["pronto", null, ["rigenera", "revoca"]],
    ["cambio_in_corso", "rigenera", ["revoca"]],
    ["revoca_in_corso", "revoca", []],
    ["revocato", null, ["registra"]],
    ["non_applicato", "registra", ["riprova", "rigenera", "revoca"]],
    ["non_applicato", "rigenera", ["riprova", "rigenera", "revoca"]],
    ["non_applicato", null, ["riprova", "rigenera", "revoca"]],
  ] as const)("%s (azione %s): %j", (stato, azione, actions) => {
    expect(allowedActions(cred("shellyplugmg3-aa01", stato, azione))).toEqual(actions);
  });

  it("revoca non applicata: solo «Riprova», perché «Rigenera» riattiverebbe il dispositivo", () => {
    expect(allowedActions(cred("shellyplugmg3-aa01", "non_applicato", "revoca"))).toEqual(["riprova"]);
  });

  it("in corso: in_attesa, cambio_in_corso, revoca_in_corso; gli altri no", () => {
    expect(["in_attesa", "cambio_in_corso", "revoca_in_corso"].every((s) => inProgress(s as DeviceCredential["stato"]))).toBe(true);
    expect(["pronto", "revocato", "non_applicato"].some((s) => inProgress(s as DeviceCredential["stato"]))).toBe(false);
  });
});

describe("ordine dell'elenco", () => {
  it("prima i non applicati, poi quelli in corso, poi i pronti, ognuno per codice; i revocati a parte", () => {
    const { active, revoked } = splitCredentials([
      cred("d-pronto-b", "pronto"),
      cred("d-revocato", "revocato"),
      cred("d-attesa", "in_attesa", "registra"),
      cred("d-pronto-a", "pronto"),
      cred("d-ko", "non_applicato", "revoca"),
      cred("d-cambio", "cambio_in_corso", "rigenera"),
      cred("d-revocato-a", "revocato"),
    ]);
    expect(active.map((c) => c.device_id)).toEqual(["d-ko", "d-attesa", "d-cambio", "d-pronto-a", "d-pronto-b"]);
    expect(revoked.map((c) => c.device_id)).toEqual(["d-revocato", "d-revocato-a"]);
  });
});

describe("codice del dispositivo (progetto §2.1)", () => {
  it.each([
    ["", "empty"],
    ["   ", "empty"],
    ["shellyplugmg3-9070695cb0d0", null],
    ["a", null],
    ["ShellyPlug", "invalid"], // the server refuses capitals, the site does not convert them
    ["-shelly", "invalid"],
    ["shelly_plug", "invalid"],
    ["shelly plug", "invalid"],
    ["a".repeat(64), null],
    ["a".repeat(65), "invalid"],
    ["connector", "reserved"], // the connector's own account on the broker (server §5.1)
  ])("%j → %s", (value, problem) => {
    expect(deviceIdProblem(value)).toBe(problem);
  });
});

describe("rilettura dell'elenco ogni 4 secondi, al massimo 20 minuti", () => {
  it("ogni 4 s, al massimo 20 minuti (la finestra è lib/pollWindow)", () => {
    expect(POLL_MS).toBe(4_000);
    expect(MAX_POLL_MS).toBe(20 * 60_000);
  });
  it("il segno di cosa è in corso: i dispositivi in attesa, in cambio o in revoca, con stato e version", () => {
    expect(credentialsSignature([cred("d", "in_attesa", "registra"), cred("e", "pronto"), cred("f", "revoca_in_corso", "revoca")])).toBe("d:in_attesa:1|f:revoca_in_corso:1");
  });
  it("senza nulla in corso: segno vuoto", () => {
    expect(credentialsSignature([cred("d", "pronto"), cred("e", "non_applicato", "revoca"), cred("f", "revocato")])).toBe("");
    expect(credentialsSignature(undefined)).toBe("");
  });
});

describe("A5: gli accessi rifiutati di un dispositivo (docs/proposta-a5.md; bff/API.md, «rifiuti»)", () => {
  const NOW = new Date("2026-11-20T16:00:00Z").getTime(); // 17:00 a Roma
  const with_ = (stato: DeviceCredential["stato"], rifiuti: DeviceCredential["rifiuti"]) => ({ ...cred("presa-cucina", stato), rifiuti });

  it("null vuol dire «non lo so»: nessuna riga, mai «0»; zero rifiuti: nessuna riga; campo assente: nessuna riga", () => {
    expect(refusalNote(with_("pronto", null), NOW)).toBeNull();
    expect(refusalNote(with_("pronto", { conteggio_24h: 0, ultimo: null }), NOW)).toBeNull();
    expect(refusalNote(cred("presa-cucina", "pronto"), NOW)).toBeNull();
  });

  it("dopo l'ultima modifica: quanti, l'ora dell'ultimo, e «Cosa fare»", () => {
    expect(refusalNote(with_("pronto", { conteggio_24h: 12, ultimo: "2026-11-20T14:05:00Z" }), NOW)).toEqual({
      kind: "warning",
      text: "Accessi rifiutati nelle ultime 24 ore: 12, l'ultimo alle 15:05.",
    });
    expect(refusalNote(with_("in_attesa", { conteggio_24h: 1, ultimo: "2026-11-20T14:05:00Z" }), NOW)).toEqual({
      kind: "warning",
      text: "Un accesso rifiutato nelle ultime 24 ore, alle 15:05.",
    });
  });

  it("l'ultimo di un altro giorno: la data, nell'ora di Roma", () => {
    expect(refusalNote(with_("non_applicato", { conteggio_24h: 3, ultimo: "2026-11-19T23:30:00Z" }), NOW)?.text).toBe(
      "Accessi rifiutati nelle ultime 24 ore: 3, l'ultimo alle 00:30.",
    );
    expect(refusalNote(with_("non_applicato", { conteggio_24h: 3, ultimo: "2026-11-19T22:30:00Z" }), NOW)?.text).toBe(
      "Accessi rifiutati nelle ultime 24 ore: 3, l'ultimo il 19/11 alle 23:30.",
    );
  });

  it("tutti prima dell'ultima modifica (per esempio una «Rigenera»): grigio, niente «Cosa fare»", () => {
    expect(refusalNote(with_("pronto", { conteggio_24h: 4, ultimo: "2026-11-19T14:59:00Z" }), NOW)?.kind).toBe("past");
    expect(refusalNote(with_("cambio_in_corso", { conteggio_24h: 4, ultimo: "2026-11-19T14:59:00Z" }), NOW)?.kind).toBe("past");
  });

  it("revocato: lo Shelly prova ancora; revoca in corso: solo il numero", () => {
    expect(refusalNote(with_("revocato", { conteggio_24h: 3, ultimo: "2026-11-20T14:05:00Z" }), NOW)?.kind).toBe("revoked");
    expect(refusalNote(with_("revoca_in_corso", { conteggio_24h: 3, ultimo: "2026-11-20T14:05:00Z" }), NOW)?.kind).toBe("plain");
  });
});
