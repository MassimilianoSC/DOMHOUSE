import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Apartment, Device, Room } from "@/api/types";
import { t } from "@/i18n";
import { fmtShortDateTime } from "@/lib/format";
import { StatusBand } from "./StatusBand";

const TZ = "Europe/Rome";
const inHours = (h: number) => new Date(Date.now() + h * 3_600_000).toISOString();

const apt = (over: Partial<Apartment> = {}): Apartment => ({
  apartment_id: "a1",
  name: "Corso Italia",
  timezone: TZ,
  occupancy: "occupied",
  mode: "comfort",
  hold: null,
  next_checkin: inHours(48),
  next_checkout: inHours(20),
  online: true,
  devices_online: 3,
  devices_total: 3,
  updated_at: "2026-10-23T10:00:00Z",
  ...over,
} as Apartment);

const rooms: Room[] = [{ room_id: "r1", name: "Camera" }, { room_id: "r2", name: "Soggiorno" }] as Room[];
const dev = (id: string, room: string, capabilities: Device["capabilities"]): Device =>
  ({ device_id: id, label: id, room_id: room, online: true, last_seen: null, capabilities }) as Device;

describe("fascia di stato della Panoramica (design, lotto 2)", () => {
  it("mostra modalità, occupazione, il prossimo fra check-in e check-out, finestre, consumo e dispositivi", () => {
    const devices = [
      dev("w1", "r1", { contact: { open: false, since: null } }),
      dev("m1", "r2", { power_meter: { watts: 10, kwh_today: 1.24 } }),
    ];
    render(<StatusBand apartment={apt()} devices={devices} rooms={rooms} kwhToday={null} energyOn tz={TZ} />);
    expect(screen.getByTestId("band-mode-value")).toHaveTextContent("Comfort");
    expect(screen.getByTestId("band-occupancy-value")).toHaveTextContent(t("occupancy.occupied"));
    expect(screen.getByTestId("band-next")).toHaveTextContent(t("overview.band.nextCheckout"));
    expect(screen.getByTestId("band-next-value")).toHaveTextContent(fmtShortDateTime(apt().next_checkout, TZ));
    expect(screen.getByTestId("band-windows-value")).toHaveTextContent(t("overview.band.windowsClosed"));
    expect(screen.getByTestId("band-energy-value")).toHaveTextContent("1,2 kWh");
    expect(screen.getByTestId("band-devices-value")).toHaveTextContent("3/3");
  });

  it("finestre aperte e dispositivi offline nell'inchiostro di attenzione, con le stanze", () => {
    const devices = [
      dev("w1", "r1", { contact: { open: true, since: null } }),
      dev("w2", "r2", { contact: { open: true, since: null } }),
    ];
    render(<StatusBand apartment={apt({ devices_online: 2 })} devices={devices} rooms={rooms} kwhToday={3} energyOn tz={TZ} />);
    expect(screen.getByTestId("band-windows-value")).toHaveTextContent(t("overview.band.windowsOpen", { count: 2 }));
    expect(screen.getByTestId("band-windows-value")).toHaveClass("text-warning-fg");
    expect(screen.getByTestId("band-windows")).toHaveTextContent("Camera, Soggiorno");
    expect(screen.getByTestId("band-energy-value")).toHaveTextContent("3 kWh");
    expect(screen.getByTestId("band-devices")).toHaveTextContent(t("overview.band.offline", { count: 1 }));
  });

  it("senza date future, senza sensori di finestra e con i consumi spenti: trattini", () => {
    render(<StatusBand apartment={apt({ next_checkin: null, next_checkout: inHours(-2) })} devices={[]} rooms={rooms} kwhToday={5} energyOn={false} tz={TZ} />);
    expect(screen.getByTestId("band-next")).toHaveTextContent(t("overview.band.nextNone"));
    expect(screen.getByTestId("band-next-value")).toHaveTextContent("—");
    expect(screen.getByTestId("band-windows")).toHaveTextContent(t("overview.band.windowsNone"));
    expect(screen.getByTestId("band-energy-value")).toHaveTextContent("—");
  });
});
