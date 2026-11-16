import { useApartmentStore } from "./apartmentStore";

// A snapshot that arrives after the tab was emptied (or for another apartment) never fills the store (D-89).
beforeEach(() => {
  useApartmentStore.getState().reset("apt-1");
});

describe("store dell'appartamento: istantanee", () => {
  it("istantanea dello stesso appartamento: entra", () => {
    useApartmentStore.getState().setSnapshot({ devices: [] , rooms: [] }, "apt-1");
    expect(useApartmentStore.getState().loaded).toBe(true);
  });

  it("istantanea di un altro appartamento, o arrivata dopo lo svuotamento: ignorata", () => {
    useApartmentStore.getState().setSnapshot({ devices: [], rooms: [] }, "apt-2");
    expect(useApartmentStore.getState().loaded).toBe(false);
    useApartmentStore.getState().reset("");
    useApartmentStore.getState().setSnapshot({ devices: [], rooms: [] }, "apt-1");
    expect(useApartmentStore.getState().loaded).toBe(false);
  });

  it("senza appartamento indicato (modifica locale, come il cambio di nome): come prima", () => {
    useApartmentStore.getState().setSnapshot({ devices: [] });
    expect(useApartmentStore.getState().loaded).toBe(true);
  });
});

// Contract 1.0.6 (o1, answer 1143): device.state and device.online may carry battery_percent, optional. Present, even
// null, it replaces the level; absent, the level the page already has stays (an older engine never sends it).
describe("store dell'appartamento: livello della batteria dallo stream", () => {
  const SENSOR = { device_id: "s1", label: "Sensore", room_id: "r", online: true, last_seen: "2026-11-16T10:00:00Z", capabilities: { temperature: { celsius: 20 } }, battery_percent: 60 };
  const battery = () => (useApartmentStore.getState().devices[0] as { battery_percent?: number | null }).battery_percent;
  const apply = (event: string, data: object) => useApartmentStore.getState().apply({ event, id: "1", data } as never);
  beforeEach(() => useApartmentStore.getState().setSnapshot({ devices: [SENSOR as never], rooms: [] }, "apt-1"));

  it("device.state con battery_percent: aggiorna il livello", () => {
    apply("device.state", { device_id: "s1", capability: "temperature", state: { celsius: 21 }, battery_percent: 18 });
    expect(battery()).toBe(18);
  });

  it("device.online con battery_percent: aggiorna il livello, anche a null", () => {
    apply("device.online", { device_id: "s1", online: false, last_seen: "2026-11-16T11:00:00Z", battery_percent: 12 });
    expect(battery()).toBe(12);
    apply("device.online", { device_id: "s1", online: true, last_seen: "2026-11-16T11:05:00Z", battery_percent: null });
    expect(battery()).toBeNull();
  });

  it("senza battery_percent (motore di prima): il livello resta", () => {
    apply("device.state", { device_id: "s1", capability: "temperature", state: { celsius: 21 } });
    apply("device.online", { device_id: "s1", online: false, last_seen: "2026-11-16T11:00:00Z" });
    expect(battery()).toBe(60);
  });
});
