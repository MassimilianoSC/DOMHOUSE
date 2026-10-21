import { act, fireEvent, render, screen } from "@testing-library/react";
import type { Apartment, Device } from "@/api/types";
import { t } from "@/i18n";
import { useApartmentStore } from "@/store/apartmentStore";
import { HoldControl } from "./ApartmentControls";

// «Forza per…» with a window open (D-127): during a hold the rules are off, so the climate stays on with the window
// open. The person is warned, with the rooms, and may confirm anyway. Without open windows nothing changes.
const s = vi.hoisted(() => ({ setHold: vi.fn(async (_body: { minutes: number }, _c: string) => ({})) }));
vi.mock("@/api/instance", () => ({ instanceApi: () => ({ setHold: s.setHold }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), info: vi.fn(), success: vi.fn(), warning: vi.fn() } }));

const APT = { mode: "comfort", hold: null, timezone: "Europe/Rome", updated_at: "2026-10-21T08:00:00Z" } as unknown as Apartment;
const ROOMS = [{ room_id: "r-sog", name: "Soggiorno" }, { room_id: "r-cam", name: "Camera" }, { room_id: "r-cuc", name: "Cucina" }];
const win = (id: string, room: string, open: boolean) => ({ device_id: id, label: `Finestra ${id}`, room_id: room, online: true, capabilities: { contact: { open } } }) as unknown as Device;
const clima = { device_id: "ac-1", label: "Clima", room_id: "r-sog", online: true, capabilities: { climate: { on: true } } } as unknown as Device;

function setup(devices: Device[]) {
  useApartmentStore.getState().reset("apt-001");
  useApartmentStore.getState().setSnapshot({ devices, rooms: ROOMS as never });
  render(<HoldControl aptId="apt-001" apartment={APT} canWrite />);
}

const click = (testId: string) => act(async () => {
  fireEvent.click(screen.getByTestId(testId));
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe("forzatura con una finestra aperta (D-127)", () => {
  it("nessuna finestra aperta: la forzatura parte subito, senza avviso", async () => {
    setup([clima, win("w1", "r-sog", false)]);
    await click("hold-btn-30");
    expect(screen.queryByTestId("hold-window-warning")).not.toBeInTheDocument();
    expect(s.setHold).toHaveBeenCalledWith({ minutes: 30 }, expect.any(String));
  });

  it("una finestra aperta: avviso con la stanza prima della conferma; la forzatura non parte finché non si conferma", async () => {
    setup([clima, win("w1", "r-sog", true)]);
    await click("hold-btn-120");
    const dialog = screen.getByTestId("hold-window-warning");
    expect(dialog).toHaveTextContent(t("hold.windowOpen", { rooms: "Soggiorno" }));
    expect(dialog).toHaveTextContent("Finestra aperta in Soggiorno: durante la forzatura il clima resta acceso.");
    expect(s.setHold).not.toHaveBeenCalled();
    await click("hold-window-confirm");
    expect(s.setHold).toHaveBeenCalledWith({ minutes: 120 }, expect.any(String));
    expect(screen.queryByTestId("hold-window-warning")).not.toBeInTheDocument();
  });

  it("più finestre aperte: elenca le stanze, una volta sola ciascuna", async () => {
    setup([win("w1", "r-sog", true), win("w2", "r-cam", true), win("w3", "r-sog", true), win("w4", "r-cuc", false)]);
    await click("hold-btn-360");
    expect(screen.getByTestId("hold-window-warning")).toHaveTextContent("Finestre aperte in Soggiorno e Camera: durante la forzatura il clima resta acceso.");
  });

  it("annullando, nessuna forzatura", async () => {
    setup([win("w1", "r-cam", true)]);
    await click("hold-btn-30");
    await click("hold-window-cancel");
    expect(s.setHold).not.toHaveBeenCalled();
    expect(screen.queryByTestId("hold-window-warning")).not.toBeInTheDocument();
  });

  it("annullare una forzatura in corso non chiede niente, anche con una finestra aperta", async () => {
    useApartmentStore.getState().reset("apt-001");
    useApartmentStore.getState().setSnapshot({ devices: [win("w1", "r-sog", true)], rooms: ROOMS as never });
    render(<HoldControl aptId="apt-001" apartment={{ ...APT, hold: { mode: "comfort", until: "2099-01-01T00:00:00Z" } } as unknown as Apartment} canWrite />);
    await click("hold-cancel-btn");
    expect(screen.queryByTestId("hold-window-warning")).not.toBeInTheDocument();
    expect(s.setHold).toHaveBeenCalledWith({ minutes: 0 }, expect.any(String));
  });
});
