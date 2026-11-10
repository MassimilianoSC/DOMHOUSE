import { act, fireEvent, render, screen } from "@testing-library/react";
import { t } from "@/i18n";
import { ScheduleDialog } from "./ScheduleDialog";

// D-212: «Quando» is the apartment's date and time. On the nights the clocks change the time saved follows the
// engine's rule, and a line under the field says what will happen; on the other days nothing.
const api = vi.hoisted(() => ({ createSchedule: vi.fn(async () => ({})), moveSchedule: vi.fn(async () => ({})) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => api }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));

function open(tz = "Europe/Rome") {
  render(<ScheduleDialog aptId="apt-001" tz={tz} open onOpenChange={() => {}} onDone={() => {}} />);
}
const field = () => screen.getByTestId("schedule-run-at-input") as HTMLInputElement;
const choose = (value: string) => fireEvent.change(field(), { target: { value } });
const note = () => screen.queryByTestId("schedule-dst-note");
async function save() {
  await act(async () => {
    fireEvent.click(screen.getByTestId("schedule-dialog-save"));
  });
}
const savedAt = () => (api.createSchedule.mock.calls.at(-1) as unknown as [{ run_at: string }])[0].run_at;

beforeEach(() => {
  api.createSchedule.mockClear();
});

describe("Programmazione, «Quando» nei giorni del cambio d'ora (D-212)", () => {
  it("28 marzo 2027 alle 02:30, che non esistono: la riga spiega, e si salva alle 03:30", async () => {
    open();
    choose("2027-03-28T02:30");
    expect(note()).toHaveTextContent(/^Il 28 marzo 2027 le 02:30 non esistono: quella notte gli orologi vanno avanti\. L'azione verrà eseguita alle 03:30\.$/);
    await save();
    expect(savedAt()).toBe("2027-03-28T01:30:00.000Z");
  });

  it("31 ottobre 2027 alle 02:30, che capitano due volte: la riga spiega, e si salva la prima volta", async () => {
    open();
    choose("2027-10-31T02:30");
    expect(note()).toHaveTextContent(/^Il 31 ottobre 2027 le 02:30 capitano due volte: quella notte gli orologi tornano indietro\. L'azione verrà eseguita la prima volta\.$/);
    await save();
    expect(savedAt()).toBe("2027-10-31T00:30:00.000Z");
  });

  it("le 01:30 di quei due giorni esistono una volta sola: nessuna riga, e l'ora giusta (i casi di o1)", async () => {
    open();
    choose("2027-03-28T01:30");
    expect(note()).toBeNull();
    await save();
    expect(savedAt()).toBe("2027-03-28T00:30:00.000Z");
    choose("2027-10-31T01:30");
    expect(note()).toBeNull();
    await save();
    expect(savedAt()).toBe("2027-10-30T23:30:00.000Z");
  });

  it("un giorno normale: nessuna riga", () => {
    open();
    choose("2027-05-10T08:00");
    expect(note()).toBeNull();
  });

  it("«L'8 marzo», non «Il 8 marzo» (New York cambia ora l'8 marzo 2026)", () => {
    open("America/New_York");
    choose("2026-03-08T02:30");
    expect(note()).toHaveTextContent(/^L'8 marzo 2026 le 02:30 non esistono/);
    expect(note()).toHaveTextContent(t("schedule.dstSkipped", { onDay: "L'8 marzo 2026", time: "02:30", actual: "03:30" }));
  });
});

describe("Programmazione, l'ora proposta all'apertura (D-212)", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("fra un'ora sull'orologio dell'appartamento, non su quello del browser", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2027-07-15T22:10:30Z"));
    open("Europe/Rome");
    expect(field().value).toBe("2027-07-16T01:10");
  });

  it("stesso istante, appartamento a New York: l'ora di New York", () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2027-07-15T22:10:30Z"));
    open("America/New_York");
    expect(field().value).toBe("2027-07-15T19:10");
  });
});
