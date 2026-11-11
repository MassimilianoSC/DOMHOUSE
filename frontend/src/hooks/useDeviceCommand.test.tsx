import { act, fireEvent, render, renderHook, screen } from "@testing-library/react";
import { ApiError } from "@/api/bff";
import { CommandChip } from "@/components/devices/CommandChip";
import { SetpointStepper } from "@/components/devices/capabilities/SetpointStepper";
import { useApartmentStore } from "@/store/apartmentStore";
import { useDeviceCommand } from "./useDeviceCommand";

// P-83: what a device card shows after its commands (D47), and two taps before the answer (D72).
const s = vi.hoisted(() => ({
  send: vi.fn(),
  release: [] as (() => void)[],
}));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ sendCommand: s.send }) }));
vi.mock("@/lib/actions", () => ({ showError: vi.fn() }));

beforeEach(() => {
  s.send.mockReset();
  s.release = [];
  useApartmentStore.getState().reset("apt-1");
});

it("D47: comando A eseguito, poi B rifiutato: il chip dice l'errore, non «eseguito»", async () => {
  s.send
    .mockResolvedValueOnce({ command_id: "A", status: "pending", reason: null, capability: "switch", correlation_id: "c1" })
    .mockRejectedValueOnce(new ApiError(409, "device_offline", "Il dispositivo non è raggiungibile", "c2"));
  const { result } = renderHook(() => useDeviceCommand("apt-1", "dev-1"));
  await act(async () => { await result.current.send({ capability: "switch", action: "turn_on" }); });
  act(() => useApartmentStore.getState().apply({ event: "command.updated", id: "5", data: { command_id: "A", device_id: "dev-1", status: "acked", reason: null } } as never));
  await act(async () => { await result.current.send({ capability: "switch", action: "turn_off" }); });
  render(<CommandChip command={result.current.status} error={result.current.error} testId="chip" />);
  expect(screen.getByTestId("chip")).toHaveAttribute("data-status", "error");
  expect(screen.getByTestId("chip")).toHaveTextContent("Il dispositivo non è raggiungibile");
});

it("D47: un comando nuovo partito altrove (solo dallo stream) toglie l'errore vecchio", async () => {
  s.send.mockRejectedValueOnce(new ApiError(409, "device_offline", "Il dispositivo non è raggiungibile", "c2"));
  const { result } = renderHook(() => useDeviceCommand("apt-1", "dev-1"));
  await act(async () => { await result.current.send({ capability: "switch", action: "turn_off" }); });
  expect(result.current.error).toBeDefined();
  act(() => useApartmentStore.getState().apply({ event: "command.updated", id: "6", data: { command_id: "X", device_id: "dev-1", status: "acked", reason: null } } as never));
  expect(result.current.error).toBeUndefined();
  expect(result.current.status?.command_id).toBe("X");
});

it("D72: due tocchi prima della risposta HTTP mandano un solo comando, e il dispositivo è «occupato» intanto", async () => {
  s.send.mockImplementation(() => new Promise((res) => s.release.push(() => res({ command_id: `C${s.release.length}`, status: "pending", reason: null }))));
  const { result } = renderHook(() => useDeviceCommand("apt-1", "dev-1"));
  const sent: number[] = [];
  render(<SetpointStepper value={21} min={16} max={25} disabled={result.current.busy} onChange={(v) => { sent.push(v); void result.current.send({ capability: "heating", action: "set_heating", params: { setpoint: v } }); }} testId="sp" />);
  fireEvent.click(screen.getByTestId("sp-inc"));
  fireEvent.click(screen.getByTestId("sp-dec"));
  expect(s.send).toHaveBeenCalledTimes(1);
  expect(s.send.mock.calls[0][1]).toEqual({ capability: "heating", action: "set_heating", params: { setpoint: 21.5 } });
  expect(result.current.busy).toBe(true);
  await act(async () => { s.release.forEach((r) => r()); });
  expect(result.current.busy).toBe(true); // ora è il comando, «pending», a tenerlo occupato
});

it("D72: dopo una richiesta fallita il dispositivo torna libero", async () => {
  s.send.mockRejectedValueOnce(new ApiError(502, "instance_unreachable", "Sistema domotico non raggiungibile", "c3"));
  const { result } = renderHook(() => useDeviceCommand("apt-1", "dev-1"));
  await act(async () => { await result.current.send({ capability: "switch", action: "turn_on" }); });
  expect(result.current.busy).toBe(false);
  s.send.mockResolvedValueOnce({ command_id: "B", status: "pending", reason: null });
  await act(async () => { await result.current.send({ capability: "switch", action: "turn_on" }); });
  expect(s.send).toHaveBeenCalledTimes(2);
});
