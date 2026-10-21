import { render, screen } from "@testing-library/react";
import { t } from "@/i18n";
import { EnvBanner } from "./EnvBanner";

// P-67 (D-136): «Ambiente di prova» when /app/me says app_env "staging"; nothing in production, on the PC, or before
// the profile has arrived.
const s = vi.hoisted(() => ({ me: null as unknown }));
vi.mock("@/auth/AuthProvider", () => ({ useAuth: () => ({ me: s.me }) }));

const withEnv = (app_env: string) => ({ env: { app_env, auth_mode: "firebase", fcm_enabled: false, instance_mode: "real" } });

describe("fascia «Ambiente di prova»", () => {
  it("staging: la fascia con il testo", () => {
    s.me = withEnv("staging");
    render(<EnvBanner testId="env-banner" />);
    expect(screen.getByTestId("env-banner")).toHaveTextContent(`${t("envBanner.staging")} · ${t("envBanner.stagingHint")}`);
    expect(screen.getByTestId("env-banner")).toHaveTextContent("Ambiente di prova · i dati sono separati da quelli veri");
  });

  it.each(["prod", "dev"])("%s: niente fascia", (app_env) => {
    s.me = withEnv(app_env);
    render(<EnvBanner testId="env-banner" />);
    expect(screen.queryByTestId("env-banner")).toBeNull();
  });

  it("profilo non ancora arrivato: niente fascia", () => {
    s.me = null;
    render(<EnvBanner testId="env-banner" />);
    expect(screen.queryByTestId("env-banner")).toBeNull();
  });
});
