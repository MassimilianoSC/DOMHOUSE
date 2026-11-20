import { pollWindow } from "./pollWindow";

// The 20 minutes of reading again (A2 §3.3, A3 §3): they start when what is on its way changes, and once over they stay
// over for the same orders, however many times React Query asks again.

describe("finestra di rilettura", () => {
  const MAX = 20 * 60_000;

  it("niente in corso: chiusa", () => {
    const open = pollWindow(MAX);
    expect(open("", 0)).toBe(false);
  });

  it("aperta per 20 minuti dall'inizio, poi chiusa anche se si chiede ancora", () => {
    const open = pollWindow(MAX);
    expect(open("a:in_preparazione:1", 1_000)).toBe(true);
    expect(open("a:in_preparazione:1", 1_000 + MAX - 1)).toBe(true);
    expect(open("a:in_preparazione:1", 1_000 + MAX)).toBe(false);
    expect(open("a:in_preparazione:1", 1_000 + MAX + 5)).toBe(false);
    expect(open("a:in_preparazione:1", 1_000 + 2 * MAX)).toBe(false);
  });

  it("un ordine nuovo (lo stato o la version cambia) apre altri 20 minuti", () => {
    const open = pollWindow(MAX);
    open("a:in_preparazione:1", 0);
    expect(open("a:in_preparazione:1", MAX)).toBe(false);
    expect(open("a:in_preparazione:2", MAX + 10)).toBe(true);
    expect(open("a:in_preparazione:2", 2 * MAX + 9)).toBe(true);
  });

  it("dopo un momento senza niente in corso, lo stesso segno riapre", () => {
    const open = pollWindow(MAX);
    open("a:x:1", 0);
    expect(open("", MAX + 1)).toBe(false);
    expect(open("a:x:1", MAX + 2)).toBe(true);
  });
});
