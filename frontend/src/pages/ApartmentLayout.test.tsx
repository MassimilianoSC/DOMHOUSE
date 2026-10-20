import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { t } from "@/i18n";
import ApartmentLayout from "./ApartmentLayout";

// An apartment the BFF refuses (404: missing or not assigned to this user, P-18) gets an explanation, no stream and a
// way back; an accessible one renders its page as before.
const s = vi.hoisted(() => ({ stream: vi.fn() }));
vi.mock("@/hooks/useApartmentStream", () => ({ useApartmentStream: s.stream }));

function answer(status: number, body: unknown) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })));
}

function open(path = "/a/apt-002") {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/" element={<p data-testid="apartments-list">elenco</p>} />
          <Route path="/a/:aptId" element={<ApartmentLayout />}>
            <Route index element={<p data-testid="overview">panoramica</p>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("appartamento non accessibile", () => {
  it("404: «Appartamento non disponibile», nessuna Panoramica, nessuno stream", async () => {
    answer(404, { error: "not_found", message: "Appartamento non trovato" });
    open();
    expect(await screen.findByTestId("apartment-unavailable")).toHaveTextContent(t("apartments.unavailable"));
    expect(screen.getByTestId("apartment-unavailable")).toHaveTextContent(t("apartments.unavailableHint"));
    expect(screen.queryByTestId("overview")).not.toBeInTheDocument();
    expect(s.stream).not.toHaveBeenCalledWith("apt-002");
  });

  it("403: stesso avviso", async () => {
    answer(403, { error: "forbidden", message: "Non autorizzato" });
    open();
    expect(await screen.findByTestId("apartment-unavailable")).toBeInTheDocument();
  });

  it("«Torna agli appartamenti» riporta all'elenco", async () => {
    answer(404, { error: "not_found", message: "Appartamento non trovato" });
    open();
    fireEvent.click(await screen.findByText(t("apartments.backToList")));
    expect(screen.getByTestId("apartments-list")).toBeInTheDocument();
  });

  it("appartamento accessibile: la pagina si apre e lo stream parte", async () => {
    answer(200, { apartment_id: "apt-002", name: "Rimini Mare", timezone: "Europe/Rome", features: ["apartment", "devices"], contract_version: "1.0.4", online: true, enabled: true });
    open();
    expect(await screen.findByTestId("overview")).toBeInTheDocument();
    expect(screen.queryByTestId("apartment-unavailable")).not.toBeInTheDocument();
    expect(s.stream).toHaveBeenLastCalledWith("apt-002");
  });
});
