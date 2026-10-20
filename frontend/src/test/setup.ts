import "@testing-library/jest-dom/vitest";

// No test talks to the network: an un-mocked fetch is recorded and fails the test that made it, even when the code
// under test swallows the error. A test that needs the BFF stubs fetch itself (vi.stubGlobal) for that test.
let unexpected: string[] = [];

beforeEach(() => {
  unexpected = [];
  vi.stubGlobal("fetch", (input: RequestInfo | URL) => {
    unexpected.push(String(input instanceof Request ? input.url : input));
    return Promise.reject(new Error("fetch non simulata"));
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  if (unexpected.length) throw new Error(`Chiamata di rete non simulata: ${unexpected.join(", ")}`);
});
