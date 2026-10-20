import { render, screen } from "@testing-library/react";
import type { VerifyResult } from "@/api/admin";
import { t } from "@/i18n";
import { VerifyBadge } from "./apartmentForm";

// "Verifica connessione" outcome. After L4 (Fable review) the platform gets only {apartment_id, ok, error,
// contract_version}; the organization admin still gets health and version too (N6).
describe("esito della verifica della connessione", () => {
  it("risposta ridotta della piattaforma: esito e versione del contratto", () => {
    render(<VerifyBadge r={{ apartment_id: "apt-001", ok: true, error: null, contract_version: "1.0.4" } as VerifyResult} />);
    const badge = screen.getByTestId("verify-result-apt-001");
    expect(badge).toHaveTextContent(t("admin.apartments.verifyOk"));
    expect(badge).toHaveTextContent("1.0.4");
    expect(badge).not.toHaveTextContent("/health");
  });

  it("risposta completa dell'amministratore: salute, versione e numero di funzioni", () => {
    render(
      <VerifyBadge
        r={{ apartment_id: "apt-002", reachable: true, ok: true, error: null, contract_version: "1.0.4", features: ["apartment", "devices"], health: { status_code: 200, body: { status: "ok" } }, version: { status_code: 200, body: {} } } as unknown as VerifyResult}
      />,
    );
    const badge = screen.getByTestId("verify-result-apt-002");
    expect(badge).toHaveTextContent("/health: ok (200)");
    expect(badge).toHaveTextContent("1.0.4");
    expect(badge).toHaveTextContent(`2 ${t("admin.features.title").toLowerCase()}`);
  });

  it("verifica non riuscita: il motivo leggibile", () => {
    render(<VerifyBadge r={{ apartment_id: "apt-003", ok: false, error: "Istanza non raggiungibile", contract_version: null } as VerifyResult} />);
    expect(screen.getByTestId("verify-result-apt-003")).toHaveTextContent(`${t("admin.apartments.verifyKo")}Istanza non raggiungibile`);
  });
});
