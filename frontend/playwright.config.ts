import { defineConfig } from "@playwright/test";
import { CHROMIUM_EXECUTABLE, NO_BROWSER_REASON, PYTHON, REPO_ROOT } from "./e2e/environment";

// Checks in a real browser (P-73): jsdom computes no layout, so «nothing sticks out of a 360 px phone» is measured
// here. `yarn e2e` starts the development BFF (data in memory, simulated engines, no Google Cloud) and the site on
// ports of their own, signs in with the development buttons and measures the pages. Without a browser on the machine
// the servers are not started and the checks are skipped with the reason (e2e/environment.ts).
const BFF_PORT = 8011;
const SITE_PORT = 5174;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${SITE_PORT}`,
    browserName: "chromium",
    launchOptions: CHROMIUM_EXECUTABLE ? { executablePath: CHROMIUM_EXECUTABLE } : {},
  },
  // CI #107: the development server is warmed first (e2e/warmup.setup.ts), so the first check does not pay for it
  projects: [
    { name: "riscaldamento", testMatch: /warmup\.setup\.ts$/ },
    { name: "prove", dependencies: ["riscaldamento"] },
  ],
  webServer: NO_BROWSER_REASON
    ? undefined
    : [
        {
          command: `"${PYTHON}" -m uvicorn bff.main:app --host 127.0.0.1 --port ${BFF_PORT}`,
          cwd: REPO_ROOT,
          // PORT too: the BFF calls its built-in simulated engines on its own port (8000 when missing). MOCK_TODAY (item 15,
          // o1 037f0a5; simulated connector only): a winter day, so the heating season is on whatever the real date, and
          // the checks that count on a boiler at 21 °C give the same result in summer
          env: { APP_ENV: "dev", AUTH_MODE: "dev", INSTANCE_MODE: "mock", REPOSITORY: "memory", FCM_ENABLED: "false", SUMMARY_JOB: "false", PORT: String(BFF_PORT), MOCK_TODAY: "2026-01-15" },
          url: `http://127.0.0.1:${BFF_PORT}/openapi.json`,
          reuseExistingServer: false,
          timeout: 60_000,
        },
        {
          command: `node node_modules/vite/bin/vite.js --port ${SITE_PORT} --strictPort --host 127.0.0.1`,
          env: { VITE_BFF_URL: `http://127.0.0.1:${BFF_PORT}`, VITE_AUTH_MODE: "dev" },
          url: `http://localhost:${SITE_PORT}/`,
          reuseExistingServer: false,
          timeout: 60_000,
        },
      ],
});
