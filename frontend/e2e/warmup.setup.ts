import { expect, test as setup } from "@playwright/test";
import { NO_BROWSER_REASON } from "./environment";

// CI #107 (19 Nov): the first check of the run failed at 375 px with «main h1 not found» after 15 s, while the same page
// at 390-430 px took 1.5 s. Vite's development server prepares the dependencies and each module the first time a
// browser asks for them, and in the CI there is never a cache: measured on o2's PC, the first check takes 20.9 s cold
// (`vite --force`) and 3.9 s warm. Here, before every check, the server is warmed with no hurry: the sign-in, the list
// of the apartments, one page of an apartment and the general pages. The checks keep their own 15 s.

setup.skip(Boolean(NO_BROWSER_REASON), NO_BROWSER_REASON ?? "");

const COLD = 120_000;

setup("riscaldamento del server di sviluppo", async ({ page }) => {
  setup.setTimeout(4 * COLD);
  await page.goto("/login", { timeout: COLD });
  await page.getByRole("button", { name: /Amministratore demo/ }).click({ timeout: COLD });
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: COLD });
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: COLD });
  const card = page.locator('[data-testid^="apartment-card-"]').first();
  const apt = (await card.getAttribute("data-testid", { timeout: COLD }))!.replace("apartment-card-", "");
  for (const path of [`/a/${apt}/consumi`, "/admin", "/impostazioni"]) {
    await page.goto(path, { timeout: COLD });
    await expect(page.locator("main h1").first()).toBeVisible({ timeout: COLD });
  }
});
