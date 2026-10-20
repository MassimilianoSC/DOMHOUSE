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
