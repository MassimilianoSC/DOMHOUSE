import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen } from "@testing-library/react";
import itJson from "@/i18n/it.json";
import type { DeviceError, TrackedCommand } from "@/store/streamReducer";
import { CommandChip, reasonText } from "./CommandChip";

// D-218: the chip under each device card says how its last command went: «in corso» while the engine works on it,
// «eseguito», or the error with its reason and the request's id to give to the support.
const TEST_ID = "command-status-dev-1";
const cmd = (over: Partial<TrackedCommand>): TrackedCommand => ({
  command_id: "cmd-1", device_id: "dev-1", status: "pending", reason: null, ...over,
});
const chip = () => screen.getByTestId(TEST_ID);
const show = (command?: TrackedCommand, error?: DeviceError) =>
  render(<CommandChip command={command} error={error} testId={TEST_ID} />);

describe("CommandChip, lo stato dell'ultimo comando di un dispositivo", () => {
  it("senza comando né errore non mostra nulla", () => {
    const { container } = show();
    expect(container).toBeEmptyDOMElement();
  });

  it.each(["pending", "sent", "verifying"] as const)("%s: «in corso», con lo stato nel suo attributo", (status) => {
    show(cmd({ status }));
    expect(chip()).toHaveTextContent(/^in corso$/);
    expect(chip()).toHaveAttribute("data-status", status);
    expect(chip()).toHaveAttribute("role", "status");
    expect(chip().className).toContain("bg-warning-bg");
  });

  it("acked: «eseguito», in verde, senza identificativo da copiare", () => {
    show(cmd({ status: "acked", correlationId: "c0ffee00-1111-2222-3333-444455556666" }));
    expect(chip()).toHaveTextContent(/^eseguito$/);
    expect(chip().className).toContain("bg-positive-bg");
    expect(screen.queryByTestId(`${TEST_ID}-correlation`)).toBeNull();
  });

  it("failed con il motivo: «errore: <motivo> · <codice>» e l'ID richiesta da copiare", () => {
    show(cmd({ status: "failed", reason: "blocked_by_rule", correlationId: "c0ffee00-1111-2222-3333-444455556666" }));
    expect(chip()).toHaveTextContent(/^errore: bloccato da una regola · blocked_by_rule/);
    expect(chip().className).toContain("bg-negative-bg");
    expect(screen.getByTestId(`${TEST_ID}-correlation`)).toHaveAttribute("data-correlation-id", "c0ffee00-1111-2222-3333-444455556666");
  });

  it("timeout senza motivo: «nessuna risposta», senza i due punti", () => {
    show(cmd({ status: "timeout" }));
    expect(chip()).toHaveTextContent(/^nessuna risposta$/);
    expect(chip()).toHaveAttribute("data-status", "timeout");
  });

  it("un motivo che l'app non conosce ancora si mostra con il suo codice", () => {
    show(cmd({ status: "failed", reason: "nuovo_motivo" as TrackedCommand["reason"] }));
    expect(chip()).toHaveTextContent(/^errore: nuovo_motivo · nuovo_motivo$/);
  });

  it("un errore senza comando (la richiesta non è partita): il messaggio e il suo ID", () => {
    show(undefined, { message: "Server non raggiungibile", code: "NETWORK", correlationId: "abcdef12-0000-0000-0000-000000000000" });
    expect(chip()).toHaveTextContent(/^Server non raggiungibile/);
    expect(chip()).toHaveAttribute("data-status", "error");
    expect(screen.getByTestId(`${TEST_ID}-correlation`)).toHaveAttribute("data-correlation-id", "abcdef12-0000-0000-0000-000000000000");
  });

  it("un errore senza ID non mostra il pulsante da copiare", () => {
    show(undefined, { message: "Comando non valido", code: "BAD", correlationId: null });
    expect(chip()).toHaveTextContent(/^Comando non valido$/);
    expect(screen.queryByTestId(`${TEST_ID}-correlation`)).toBeNull();
  });

  it("con un comando e un errore vince l'errore (P-83, D47): un nuovo comando cancella l'errore, quindi l'errore che c'è è il più recente", () => {
    show(cmd({ status: "acked" }), { message: "Server non raggiungibile", code: "NETWORK", correlationId: null });
    expect(chip()).toHaveTextContent(/^Server non raggiungibile$/);
    expect(chip()).toHaveAttribute("data-status", "error");
  });
});

describe("CommandChip, i testi dei motivi", () => {
  it("reasonText: vuoto senza motivo", () => {
    expect(reasonText(null)).toBe("");
    expect(reasonText(undefined)).toBe("");
  });

  it("ogni motivo del contratto ha il suo testo in italiano", () => {
    const contract = readFileSync(resolve(process.cwd(), "../contract/openapi.yaml"), "utf-8");   // vitest runs in frontend/
    const reasons = /CommandReason:\s*\n\s*type: string\s*\n\s*enum: \[([^\]]+)\]/.exec(contract)?.[1].split(",").map((s) => s.trim());
    expect(reasons?.length).toBeGreaterThan(0);
    expect(Object.keys(itJson.command.reason).sort()).toEqual([...(reasons ?? [])].sort());
    for (const r of reasons ?? []) expect(reasonText(r)).toBe(`${(itJson.command.reason as Record<string, string>)[r]} · ${r}`);
  });
});
