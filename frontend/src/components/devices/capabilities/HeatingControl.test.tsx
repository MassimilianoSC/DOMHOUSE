import { render, screen } from "@testing-library/react";
import type { Device } from "@/api/types";
import { TooltipProvider } from "@/components/ui/primitives";
import { ClimateControl, HeatingControl } from "./Controls";
import type { ClimateState, HeatingState } from "./types";

// D-128, D-129: for the boiler heating.on means "heating enabled" (the engine's thermostat drives the relay), not "the
// flame is on": the card says abilitato / disabilitato, the switch Attiva / Disattiva, and «sta scaldando ora» only
// when its own power meter shows it drawing power. The climate keeps Acceso / Spento and Accendi / Spegni.
const boiler = (watts?: number) =>
  ({
    device_id: "boiler-1",
    label: "Caldaia",
    room_id: "r-1",
    online: true,
    capabilities: { heating: { on: true, setpoint: 21, setpoint_min: 5, setpoint_max: 28 }, ...(watts === undefined ? {} : { power_meter: { watts, kwh_today: 1.2 } }) },
  }) as unknown as Device;
const HEAT = (on: boolean): HeatingState => ({ on, setpoint: 21, setpoint_min: 5, setpoint_max: 28 }) as HeatingState;

const renderHeating = (device: Device, on: boolean) =>
  render(
    <TooltipProvider>
      <HeatingControl device={device} state={HEAT(on)} tz="Europe/Rome" disabled={false} send={vi.fn()} />
    </TooltipProvider>,
  );

describe("caldaia: abilitata, non «accesa» (D-129)", () => {
  it("abilitata: «Riscaldamento abilitato», e l'interruttore dice «Disattiva Caldaia»", () => {
    renderHeating(boiler(), true);
    expect(screen.getByTestId("boiler-1-heating-status")).toHaveTextContent(/^Riscaldamento abilitato$/);
    expect(screen.getByTestId("boiler-1-heating-toggle")).toHaveAccessibleName("Disattiva Caldaia");
  });

  it("disabilitata: «Riscaldamento disabilitato», e l'interruttore dice «Attiva Caldaia»", () => {
    renderHeating(boiler(), false);
    expect(screen.getByTestId("boiler-1-heating-status")).toHaveTextContent(/^Riscaldamento disabilitato$/);
    expect(screen.getByTestId("boiler-1-heating-toggle")).toHaveAccessibleName("Attiva Caldaia");
  });

  it("misuratore sopra la soglia: «sta scaldando ora»; sotto la soglia o senza misuratore, niente", () => {
    const { unmount } = renderHeating(boiler(120), true);
    expect(screen.getByTestId("boiler-1-heating-now")).toHaveTextContent("sta scaldando ora");
    unmount();
    const second = renderHeating(boiler(8), true); // only the electronics on stand-by
    expect(screen.queryByTestId("boiler-1-heating-now")).not.toBeInTheDocument();
    second.unmount();
    renderHeating(boiler(), true);
    expect(screen.queryByTestId("boiler-1-heating-now")).not.toBeInTheDocument();
  });

  it("disabilitata con il misuratore che segna consumo: nessun «sta scaldando ora»", () => {
    renderHeating(boiler(120), false);
    expect(screen.queryByTestId("boiler-1-heating-now")).not.toBeInTheDocument();
  });
});

describe("clima: invariato (D-129)", () => {
  it("«Acceso» e l'interruttore «Spegni …»", () => {
    const ac = { device_id: "ac-1", label: "Clima soggiorno", room_id: "r-1", online: true, capabilities: { climate: { on: true } } } as unknown as Device;
    const state = { on: true, mode: "cool", setpoint: 24, fan: "auto", setpoint_min: 16, setpoint_max: 30 } as ClimateState;
    render(
      <TooltipProvider>
        <ClimateControl device={ac} state={state} tz="Europe/Rome" disabled={false} send={vi.fn()} />
      </TooltipProvider>,
    );
    expect(screen.getByText("Acceso")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Spegni Clima soggiorno" })).toBeInTheDocument();
  });
});
