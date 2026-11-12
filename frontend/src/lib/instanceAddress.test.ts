// @vitest-environment node
import { instanceAddress } from "./instanceAddress";

// P-83, T3d-5: the address of an apartment's engine as the server uses it (bff/instances.py base_url): the port is
// added only when the address has none. Before, the pages always appended it: «http://10.198.0.2:8101:8101».
describe("indirizzo del motore mostrato (P-83, T3d-5)", () => {
  it("indirizzo con la porta: la porta non si ripete", () => {
    expect(instanceAddress("http://10.198.0.2:8101", 8101)).toBe("http://10.198.0.2:8101");
    expect(instanceAddress("http://10.198.0.2:8101/api/v1", 8101)).toBe("http://10.198.0.2:8101/api/v1");
  });

  it("indirizzo senza porta: la porta si aggiunge dopo l'host, anche prima di un percorso", () => {
    expect(instanceAddress("http://10.198.0.2", 8102)).toBe("http://10.198.0.2:8102");
    expect(instanceAddress("http://10.198.0.2/api/v1", 8102)).toBe("http://10.198.0.2:8102/api/v1");
    expect(instanceAddress("10.198.0.2", 8102)).toBe("10.198.0.2:8102");
  });

  it("senza porta, o motore dimostrativo: l'indirizzo così com'è", () => {
    expect(instanceAddress("http://10.198.0.2:8101", null)).toBe("http://10.198.0.2:8101");
    expect(instanceAddress("mock://builtin", 8101)).toBe("mock://builtin");
  });
});
