import { expect, test, type Page } from "@playwright/test";
import { NO_BROWSER_REASON } from "./environment";
import { overflowing, settle, signIn } from "./measure";

// A3, «Credenziali dei dispositivi» in a real browser (docs/proposta-a3-sito.md §1.5): on a phone the list becomes
// cards and the values to copy go one under the other; nothing may stick out. The first check talks to the development
// server with o1's routes (25c97cf: an empty list; a demo apartment refused with 422 invalid_apartment before any
// password exists); the others answer in the browser to show every state and the password window. Invented codes only.

test.skip(Boolean(NO_BROWSER_REASON), NO_BROWSER_REASON ?? "");

const CONNECTION = (id: string) => ({ server: "mqtt.example.test:8883", ssl_ca: "ca.pem", client_id: `lab-prova.${id}`, user: `lab-prova.${id}`, topic_prefix: `lab-prova/${id}` });
const cred = (device_id: string, stato: string, azione: string | null, extra: object = {}) => ({
  device_id, name: null, stato, version: 2, updated_at: "2026-11-19T15:12:00Z", updated_by: "Giulia Rossi", azione, engine_device_id: null, op: null, connection: CONNECTION(device_id), ...extra,
});
const ITEMS = [
  cred("shellyplusi4-0a1b2c3d4e5f", "non_applicato", "revoca", { op: { op_id: "7c41e9a2-0000-4000-8000-000000000001", stato: "scartato", codice: "scartato", messaggio: "Ordine scartato dal sistema domotico" } }),
  cred("shelly1pmminig3-1a2b3c4d5e6f", "in_attesa", "registra"),
  cred("shellyhtg3-2b3c4d5e6f7a", "cambio_in_corso", "rigenera"),
  cred("shellyplugmg3-3c4d5e6f7a8b", "pronto", null),
  cred("shellyplugmg3-4d5e6f7a8b9c", "revocato", null),
];
const PASSWORD = "q7Vx2LmR9tKp4sWb8Nd3Hf6Zc1Jy5AeU"; // invented

async function firstApartment(page: Page): Promise<string> {
  const card = page.locator('[data-testid^="apartment-card-"]').first();
  await expect(card).toBeVisible({ timeout: 15_000 });
  return (await card.getAttribute("data-testid"))!.replace("apartment-card-", "");
}

test.describe("credenziali dei dispositivi", () => {
  test("sul server di sviluppo: elenco vuoto, e un appartamento dimostrativo rifiutato prima di creare la password", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 780 });
    await signIn(page);
    const apt = await firstApartment(page);
    await page.goto(`/a/${apt}/credenziali`);
    await settle(page);
    await expect(page.getByTestId("credentials-empty")).toBeVisible({ timeout: 15_000 });
    expect(await overflowing(page)).toEqual([]);
    await page.getByTestId("credentials-register-btn").click();
    await page.getByTestId("credential-register-input").fill("shellyplugmg3-5e6f7a8b9c0d");
    await page.getByTestId("credential-register-save").click();
    // the server's own sentence (422 invalid_apartment): no password window
    await expect(page.getByText("non valido per questo ambiente")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("credential-password-dialog")).toHaveCount(0);
  });

  for (const width of [360, 390, 430]) {
    test(`a ${width} px: ogni stato, i revocati aperti e la finestra della password, senza niente fuori dallo schermo`, async ({ page }) => {
      await page.setViewportSize({ width, height: 800 });
      await page.route("**/device-credentials", async (route) => {
        if (route.request().method() === "GET") return route.fulfill({ json: { items: ITEMS } });
        return route.fulfill({ status: 201, json: { credential: cred("shellyplugmg3-5e6f7a8b9c0d", "in_attesa", "registra"), password: PASSWORD } });
      });
      await signIn(page);
      const apt = await firstApartment(page);
      await page.goto(`/a/${apt}/credenziali`);
      await settle(page);
      await expect(page.getByTestId("credential-row-shellyplusi4-0a1b2c3d4e5f")).toBeVisible({ timeout: 15_000 });
      await page.getByTestId("credentials-revoked-toggle").click();
      await expect(page.getByTestId("credential-reregister-shellyplugmg3-4d5e6f7a8b9c")).toBeVisible();
      expect(await overflowing(page)).toEqual([]);

      await page.getByTestId("credentials-register-btn").click();
      await page.getByTestId("credential-register-input").fill("shellyplugmg3-5e6f7a8b9c0d");
      await page.getByTestId("credential-register-save").click();
      const dialog = page.getByTestId("credential-password-dialog");
      await expect(dialog.getByTestId("credential-value-password")).toHaveText(PASSWORD);
      // measured once the opening animation (fade and zoom) is over; where the window starts is dialog-open.spec.ts
      await page.waitForFunction(() => document.querySelector('[data-testid="credential-password-dialog"]')?.getAnimations().every((a) => a.playState === "finished") ?? false);
      // the window scrolls inside itself; every value and every «Copia» stays within the screen
      for (const key of ["topic_prefix", "server", "client_id", "user", "password"]) {
        for (const id of [`credential-value-${key}`, `credential-copy-${key}`]) {
          const box = await dialog.getByTestId(id).boundingBox();
          expect(box, id).not.toBeNull();
          expect(box!.x, id).toBeGreaterThanOrEqual(0);
          expect(box!.x + box!.width, id).toBeLessThanOrEqual(width + 1);
        }
      }
      // Esc does not close it; the box and «Chiudi» do
      await page.keyboard.press("Escape");
      await expect(dialog).toBeVisible();
      await dialog.getByTestId("credential-password-copied").check();
      await dialog.getByTestId("credential-password-close").click();
      await expect(dialog).toHaveCount(0);
      await expect(page.getByText(PASSWORD)).toHaveCount(0);
    });
  }
});
