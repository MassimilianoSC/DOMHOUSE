import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { AdminFeatures } from "./AdminFeatures";

// P-83, D45: the server replaces the whole list of functions. Two switches touched one after the other, before the
// first save came back, both started from the same old list: the second save turned the first function on again.
const ALL = ["apartment", "devices", "energy", "rules"];
const s = vi.hoisted(() => ({
  tenant: { tenant_id: "t-1", name: "Flat", enabled_features: null as string[] | null, all_features: [] as string[] },
  apts: [] as unknown[],
  patchTenant: vi.fn(),
  patchApartment: vi.fn(),
  release: [] as (() => void)[],
}));
vi.mock("@/api/admin", () => ({
  adminApi: {
    tenant: async () => ({ ...s.tenant }),
    apartments: async () => s.apts,
    patchTenant: s.patchTenant,
    patchApartment: s.patchApartment,
  },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));

/** The server answers when released, and keeps what it saved (it replaces the whole list). */
const slow = (apply: () => void) => new Promise((res) => s.release.push(() => { apply(); res({}); }));
type Body = { enabled_features?: string[] | null; clear_features?: boolean };
const saved = (body: Body) => (body.clear_features ? null : body.enabled_features ?? null);
const bodies = (fn: typeof s.patchTenant, arg = 0) => fn.mock.calls.map((c) => (c[arg] as { enabled_features: string[] }).enabled_features);

async function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AdminFeatures />
    </QueryClientProvider>,
  );
  await screen.findByTestId("tenant-feature-energy");
}

beforeEach(() => {
  s.tenant = { tenant_id: "t-1", name: "Flat", enabled_features: null, all_features: ALL };
  s.apts = [{ apartment_id: "apt-1", name: "Casa", enabled_features: null }];
  s.patchTenant.mockReset().mockImplementation((body: Body) => slow(() => { s.tenant = { ...s.tenant, enabled_features: saved(body) }; }));
  s.patchApartment.mockReset().mockImplementation((id: string, body: Body) =>
    slow(() => { s.apts = (s.apts as { apartment_id: string }[]).map((a) => (a.apartment_id === id ? { ...a, enabled_features: saved(body) } : a)); }));
  s.release = [];
});

describe("Funzioni: interruttori toccati di seguito (P-83, D45)", () => {
  it("organizzazione: spenta «Consumi», poi «Regole» prima della risposta: nessun salvataggio riaccende «Consumi»", async () => {
    await open();
    fireEvent.click(screen.getByTestId("tenant-feature-energy"));
    fireEvent.click(screen.getByTestId("tenant-feature-rules"));
    await act(async () => { s.release.splice(0).forEach((r) => r()); });
    fireEvent.click(screen.getByTestId("tenant-feature-rules"));
    await act(async () => { s.release.splice(0).forEach((r) => r()); });
    expect(bodies(s.patchTenant)[0]).not.toContain("energy");
    for (const body of bodies(s.patchTenant)) expect(body).not.toContain("energy");
    expect(bodies(s.patchTenant).at(-1)).not.toContain("rules");
  });

  it("appartamento: lo stesso con le eccezioni di un appartamento", async () => {
    await open();
    fireEvent.click(screen.getByTestId("apt-feature-apt-1-energy"));
    fireEvent.click(screen.getByTestId("apt-feature-apt-1-rules"));
    await act(async () => { s.release.splice(0).forEach((r) => r()); });
    fireEvent.click(screen.getByTestId("apt-feature-apt-1-rules"));
    await act(async () => { s.release.splice(0).forEach((r) => r()); });
    for (const body of bodies(s.patchApartment, 1)) expect(body).not.toContain("energy");
    expect(bodies(s.patchApartment, 1).at(-1)).not.toContain("rules");
  });

  it("durante il salvataggio gli interruttori sono disattivati", async () => {
    await open();
    fireEvent.click(screen.getByTestId("tenant-feature-energy"));
    expect(screen.getByTestId("tenant-feature-rules")).toBeDisabled();
    await act(async () => { s.release.splice(0).forEach((r) => r()); });
    expect(screen.getByTestId("tenant-feature-rules")).not.toBeDisabled();
  });
});
