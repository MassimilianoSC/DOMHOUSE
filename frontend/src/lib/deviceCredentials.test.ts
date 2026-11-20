// @vitest-environment node
import type { DeviceCredential } from "@/api/deviceCredentials";
import { allowedActions, credentialsSignature, deviceIdProblem, inProgress, POLL_MS, MAX_POLL_MS, splitCredentials } from "./deviceCredentials";

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
