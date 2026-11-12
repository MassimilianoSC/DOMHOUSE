import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { t } from "@/i18n";
import { resync } from "@/hooks/useApartmentStream";
import { useApartmentStore } from "@/store/apartmentStore";
import OverviewPage from "./OverviewPage";

vi.mock("@/auth/AuthProvider", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/AuthProvider")>()),
  useRole: () => ({ canWrite: true }),
}));

// P-83, D27 (site side): the engine stops while the page is open. The server says it in the summary (online false) and
// answers 502 to the re-read: the page must say «Sistema domotico non raggiungibile», not «In salute» from the state it
// kept, nor «In tempo reale» because the browser's stream to the server is still alive.
const SUMMARY = {
  apartment_id: "apt-1", name: "Casa", address: "", timezone: "Europe/Rome", enabled: true, simulated: false,
  online: true, apartment: null, health: null, contract_version: null, features: ["devices"], pending_approvals: null,
  kwh_today: null, energy_since: null,
};
const HEALTH_OK = {
  status: "ok",
  connector: { status: "up", connected_devices: 7, last_event_at: null },
  model_provider: { provider: "x", status: "up" },
  implementation: { name: "engine", version: "1" },
};
const UNREACHABLE: [number, unknown] = [502, { error: "instance_unreachable", message: "Sistema domotico non raggiungibile" }];

function bff(handler: (url: string) => [number, unknown]) {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const [status, body] = handler(String(input));
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }));
}

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/a/apt-1"]}>
        <Routes>
          <Route path="/a/:aptId" element={<OverviewPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function engineWasUp() {
  useApartmentStore.getState().reset("apt-1");
  useApartmentStore.getState().setSnapshot({ health: HEALTH_OK as never, devices: [], rooms: [] }, "apt-1");
  useApartmentStore.getState().setConnected(true);
}

afterEach(() => vi.unstubAllGlobals());

describe("P-83, D27: motore irraggiungibile con la pagina aperta", () => {
  it("riepilogo «online: false»: «non raggiungibile», niente «In salute» né «In tempo reale»", async () => {
    engineWasUp();
    bff(() => [200, { ...SUMMARY, online: false, features: [] }]);
    open();
    expect(await screen.findByText(t("instance.unreachable"))).toBeInTheDocument();
    expect(screen.queryByTestId("instance-health-status")).not.toBeInTheDocument();
    expect(screen.getByTestId("stream-status")).not.toHaveTextContent(t("overview.liveOn"));
  });

  it("502 alla rilettura, riepilogo ancora vecchio: lo stato salvato si azzera e la pagina dice «non raggiungibile»", async () => {
    engineWasUp();
    bff((url) => (url.includes("/instance/") ? UNREACHABLE : [200, { ...SUMMARY, health: HEALTH_OK }]));
    await resync("apt-1");
    expect(useApartmentStore.getState().health).toBeNull();
    open();
    expect(await screen.findByText(t("instance.unreachable"))).toBeInTheDocument();
    expect(screen.queryByTestId("instance-health-status")).not.toBeInTheDocument();
    expect(screen.getByTestId("stream-status")).not.toHaveTextContent(t("overview.liveOn"));
  });

  it("il motore torna (instance.health dallo stream): di nuovo «In salute» e «In tempo reale»", async () => {
    engineWasUp();
    bff((url) => (url.includes("/instance/") ? UNREACHABLE : [200, SUMMARY]));
    await resync("apt-1");
    useApartmentStore.getState().apply({ event: "instance.health", id: "9", data: HEALTH_OK } as never);
    open();
    expect(await screen.findByTestId("instance-health-status")).toHaveTextContent(t("instance.status.ok"));
    expect(screen.getByTestId("stream-status")).toHaveTextContent(t("overview.liveOn"));
  });
});
