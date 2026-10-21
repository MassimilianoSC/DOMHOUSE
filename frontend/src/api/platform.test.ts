import { platformApi } from "./platform";

// P-71 (a): removing a platform manager never puts the email in the path (paths end up in the logs): POST with the
// email in the body.
const calls: { url: string; init: RequestInit }[] = [];

beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return new Response(null, { status: 204 });
  }));
});

describe("gestori della piattaforma: rimozione", () => {
  it("POST /app/platform/managers/remove con l'email nel corpo, mai nel percorso", async () => {
    await platformApi.removeManager("sol@hqe.it", "corr-1");
    expect(calls).toHaveLength(1);
    const { url, init } = calls[0];
    expect(new URL(url).pathname).toBe("/app/platform/managers/remove");
    expect(url).not.toMatch(/sol|hqe|%40/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ email: "sol@hqe.it" });
  });
});
