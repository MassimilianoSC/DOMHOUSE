import { expect, test } from "@playwright/test";
import { NO_BROWSER_REASON } from "./environment";

// E-29: an app start that gets no answer ends with a message and a way out, not with a loading state for ever. In a real
// browser, with the real 15 s and the real reload, on a 360 px phone.

test.skip(Boolean(NO_BROWSER_REASON), NO_BROWSER_REASON ?? "");
test.use({ viewport: { width: 360, height: 780 } });

test("il profilo non risponde: dopo il tempo massimo il messaggio; Ricarica riporta dentro", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: /Amministratore demo/ }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));

  let blocked = true;
  await page.route("**/app/me", (route) => (blocked ? undefined : route.continue())); // blocked: never answered
  await page.goto("/impostazioni");
  await expect(page.getByTestId("page-problem")).toBeVisible({ timeout: 20_000 });
  const widths = await page.evaluate(() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]);
  expect(widths[0]).toBeLessThanOrEqual(widths[1] + 1);

  blocked = false;
  await page.getByTestId("page-problem-reload").click();
  await expect(page.locator("main h1").first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("page-problem")).toHaveCount(0);
});
